#!/usr/bin/env python3
"""地図の「場」を見張り、前回から新しく出たものを一覧にする（Ellis の monitoring）。

検索ではなく RSS / Atom を引く。検索は結果が揺れて費用もかかるが、フィードは
「その場所に新しく出たもの」をそのまま返す。決まった Qiita・Zenn・X を毎回検索する代わりに、
掘って見つけた場所を見張るための道具。

新着には要約をつけない。代わりにフィードに入っている原文の冒頭を1行そのまま載せる
（エージェントの言葉を挟まずに、選ぶ手がかりだけ出す）。

使い方:
    watch.py add   <topic_dir> <url> [名前]   … 見張る先を足す（RSS の場所は自動で探す）
    watch.py list  <topic_dir>               … 見張る先の一覧
    watch.py check <topic_dir> [--days N] [--fresh]
                                             … 新着を出して watch/<日付-時刻>.md に残す
                                               初回のフィードは直近 N 日（既定14）だけ
                                               --fresh は見た記録を無視して窓だけで選び直す
                                               新着の無い場所も、最新の1件を窓に関係なく出す

置き場（<topic_dir> = ~/research/<話題>/）:
    watch.tsv          種類・名前・フィードの URL・元の URL（タブ区切り）
    watch-state.json   フィードごとに見たことのある記事の URL
    watch/<日付>.md     check の結果
"""

import datetime as dt
import email.utils
import html
import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 imozuru-watch"}
ATOM = "{http://www.w3.org/2005/Atom}"
# 冒頭の1行の長さ。選ぶ手がかりには足り、要約の代わりにはならない長さに留める。
HEAD_CHARS = 120
# 見たことのある URL をフィードごとに残す上限。フィードは新しい順に数十件しか返さないので、
# これだけあれば「前に見たもの」を新着と取り違えない。
SEEN_LIMIT = 500


class _Redirect308(urllib.request.HTTPRedirectHandler):
    """Python 3.10 でも 308 の転送をたどる（3.10 は 308 を扱わない）。

    fetch.py と同じもの。-I で動かすとスクリプトの置き場が import の道に入らないので、写して持つ。
    """

    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, 307 if code == 308 else code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Redirect308)


def fetch(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers=UA)
    with _OPENER.open(req, timeout=60) as res:
        return res.read(5_000_000), res.headers.get("Content-Type", "")


def known_feed(url: str) -> tuple[str, str] | None:
    """URL の形だけでフィードが分かる場所。種類とフィードの URL を返す。"""
    rules = [
        (r"^https?://qiita\.com/tags/([^/?#]+)", "qiita-tag", "https://qiita.com/tags/{0}/feed"),
        (r"^https?://zenn\.dev/topics/([^/?#]+)", "zenn-topic", "https://zenn.dev/topics/{0}/feed"),
        (r"^https?://zenn\.dev/([^/?#]+)/?$", "zenn-user", "https://zenn.dev/{0}/feed"),
        (r"^https?://note\.com/([^/?#]+)/?$", "note-user", "https://note.com/{0}/rss"),
        (r"^https?://qiita\.com/([^/?#]+)/?$", "qiita-user", "https://qiita.com/{0}/feed"),
        (r"^https?://(?:www\.|old\.)?reddit\.com/r/([^/?#]+)", "reddit", "https://www.reddit.com/r/{0}/.rss"),
    ]
    for pat, kind, tmpl in rules:
        m = re.match(pat, url)
        if m:
            return kind, tmpl.format(*m.groups())
    if "export.arxiv.org/api/query" in url:
        return "arxiv", url
    return None


def discover(url: str) -> tuple[str, str]:
    """ページの <link rel="alternate" type="application/rss+xml"> からフィードを探す。

    個人ブログ・はてな・WordPress・YouTube のチャンネルページはこれを持っている。
    URL そのものがフィードなら、それをそのまま使う。
    """
    hit = known_feed(url)
    if hit:
        return hit
    body, ctype = fetch(url)
    if "xml" in ctype or body.lstrip()[:5] in (b"<?xml", b"<rss ", b"<feed"):
        return "feed", url
    text = body.decode("utf-8", errors="replace")
    for m in re.finditer(r"<link\b[^>]*>", text, re.I):
        tag = m.group(0)
        if re.search(r'type=["\']application/(rss|atom)\+xml', tag, re.I):
            href = re.search(r'href=["\']([^"\']+)', tag)
            if href:
                feed = html.unescape(href.group(1))
                if feed.startswith("/"):
                    root = re.match(r"^https?://[^/]+", url).group(0)
                    feed = root + feed
                kind = "youtube" if "youtube.com/feeds" in feed else "site"
                return kind, feed
    raise SystemExit(f"RSS が見つからない: {url}（ページに RSS の案内が無い。X・pixiv はそもそも出していない）")


def plain(s: str | None) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", " ", s or ""))
    return re.sub(r"\s+", " ", s).strip()


def parse_date(s: str | None) -> dt.datetime | None:
    if not s:
        return None
    s = s.strip()
    try:
        d = email.utils.parsedate_to_datetime(s)  # RSS 2.0 の形
    except (TypeError, ValueError):
        try:
            d = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))  # Atom の形
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=dt.timezone.utc)


def items(feed_bytes: bytes) -> list[dict]:
    """RSS 2.0 と Atom の記事を、題・URL・日付・冒頭の形にそろえる。

    フィードは他人のサーバーから来る。DOCTYPE や ENTITY を含む XML は、外部の実体の
    読み込みや入れ子の展開（billion laughs）に使われうるので、読まずに弾く。
    defusedxml を使うのが定石だが入っていない（新しく入れるのは確認が要る）。
    ふつうの RSS / Atom は DOCTYPE を使わないので、弾いて困ることはまず無い。
    """
    # 宣言は根の要素より前にしか置けない。本文（HTML の記事を CDATA で含むもの）に
    # 「<!DOCTYPE html>」が書かれていても弾かないよう、根の前だけを見る。
    root_at = re.search(rb"<(rss|feed|rdf:RDF)\b", feed_bytes)
    prolog = feed_bytes[: root_at.start()] if root_at else feed_bytes
    if re.search(rb"<!(DOCTYPE|ENTITY)", prolog, re.I):
        raise ValueError("DOCTYPE か ENTITY を含むフィードは読まない")
    root = ET.fromstring(feed_bytes)
    out = []
    for it in root.iter("item"):
        out.append({
            "title": plain(it.findtext("title")),
            "link": (it.findtext("link") or "").strip(),
            "date": parse_date(it.findtext("pubDate") or it.findtext("{http://purl.org/dc/elements/1.1/}date")),
            "head": plain(it.findtext("description")),
        })
    for en in root.iter(f"{ATOM}entry"):
        link = ""
        for ln in en.findall(f"{ATOM}link"):
            if ln.get("rel", "alternate") == "alternate":
                link = ln.get("href", "")
                break
        head = en.findtext(f"{ATOM}summary") or en.findtext(f"{ATOM}content") \
            or en.findtext("{http://search.yahoo.com/mrss/}group/{http://search.yahoo.com/mrss/}description")
        out.append({
            "title": plain(en.findtext(f"{ATOM}title")),
            "link": link,
            "date": parse_date(en.findtext(f"{ATOM}published") or en.findtext(f"{ATOM}updated")),
            "head": plain(head),
        })
    return out


def load_watch(topic: Path) -> list[list[str]]:
    p = topic / "watch.tsv"
    if not p.exists():
        return []
    return [ln.split("\t") for ln in p.read_text(encoding="utf-8").splitlines()
            if ln and not ln.startswith("#")]


def cmd_add(topic: Path, url: str, name: str | None) -> int:
    # 1つ足せなくても、続けて他を足せるように例外で落とさず1行で返す
    # （Reddit が 429 を返してトレースバックで止まった・2026-10-10 の試し）。
    try:
        kind, feed = discover(url)
        found = items(fetch(feed)[0])  # 引けないフィードは足さない
    except SystemExit as e:
        print(f"足せなかった: {e}")
        return 1
    except Exception as e:
        print(f"足せなかった: {url}（{type(e).__name__}: {e}）")
        return 1
    for row in load_watch(topic):
        if row[2] == feed:
            print(f"もう見張っている: {row[1]} {feed}")
            return 0
    if name:
        label = name
    elif kind == "arxiv":
        q = re.search(r"search_query=([^&]+)", url)
        label = "arxiv " + (urllib.parse.unquote(q.group(1)) if q else "query")
    elif kind == "feed" and found:
        label = found[0]["title"][:30]
    else:
        # 末尾だけだと「blog」「releases」ばかりになって見分けられないので、ドメインと道筋で名づける
        label = re.sub(r"^https?://(www\.)?", "", url).rstrip("/")[:40]
    topic.mkdir(parents=True, exist_ok=True)
    p = topic / "watch.tsv"
    if not p.exists():
        p.write_text("# 種類\t名前\tフィード\t元の URL\n", encoding="utf-8")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"{kind}\t{label}\t{feed}\t{url}\n")
    print(f"足した: {kind}\t{label}\t{feed}（いま {len(found)} 件）")
    return 0


def cmd_check(topic: Path, days: int, fresh: bool) -> None:
    """新着を出す。fresh なら見たことの記録を無視して、窓（days）だけで選び直す。

    初回の窓の外の記事も「見た」と記録されるので、窓を広げて出し直したいときに
    記録が邪魔をする（14日で出したあと 30日で見直せなかった・2026-10-10 の試し）。
    """
    rows = load_watch(topic)
    if not rows:
        raise SystemExit(f"見張る先が無い: {topic}/watch.tsv（watch.py add で足す）")
    state_p = topic / "watch-state.json"
    state = json.loads(state_p.read_text(encoding="utf-8")) if state_p.exists() else {}
    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(days=days)
    lines = [f"# 新着 {now.astimezone():%Y-%m-%d %H:%M}", ""]
    quiet: list[str] = []
    total = 0
    for kind, label, feed, *_ in rows:
        try:
            got = items(fetch(feed)[0])
        except Exception as e:  # 1つのフィードが落ちても他は見る
            lines += [f"## {label}（{kind}）", f"- 取れなかった: {type(e).__name__}: {e}", ""]
            continue
        seen = set() if fresh else set(state.get(feed, []))
        first = fresh or feed not in state
        new = [i for i in got if i["link"] and i["link"] not in seen
               and (not first or (i["date"] and i["date"] >= cutoff))]
        new.sort(key=lambda i: i["date"] or now, reverse=True)
        state[feed] = ([i["link"] for i in got] + list(set(state.get(feed, [])) - {i["link"] for i in got}))[:SEEN_LIMIT]
        if not new:
            # 新着が無くても、窓に関係なくそのフィードの最新を1行出す。公式の最新が
            # 窓の外に落ちて見えなくなるのを防ぐ（React 19.3 が 31日前で漏れた）。
            dated = [i for i in got if i["date"]]
            if dated:
                last = max(dated, key=lambda i: i["date"])
                quiet.append(f"- {label}（{kind}）最新 {last['date'].astimezone():%Y-%m-%d} [{last['title']}]({last['link']})")
            else:
                quiet.append(f"- {label}（{kind}）記事なし")
            continue
        total += len(new)
        lines.append(f"## {label}（{kind}）{'・直近' + str(days) + '日' if first else ''}")
        for i in new:
            day = i["date"].astimezone().strftime("%Y-%m-%d") if i["date"] else "日付なし"
            lines.append(f"- {day} [{i['title']}]({i['link']})")
            if i["head"]:
                lines.append(f"  > {i['head'][:HEAD_CHARS]}{'…' if len(i['head']) > HEAD_CHARS else ''}")
        lines.append("")
    if total == 0:
        lines += ["新着なし", ""]
    if quiet:
        lines += ["## 新着の無かった場所（窓に関係なく最新の1件）", *quiet, ""]
    state_p.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    # 秒まで入れる。日付だけだと同じ日の2回目が1回目を上書きして消した（2026-10-10 の試し）。
    out = topic / "watch" / f"{now.astimezone():%Y-%m-%d-%H%M%S}.md"
    n = 2
    while out.exists():  # 同じ秒にもう一度回したときも、前の結果を消さない
        out = out.with_name(f"{now.astimezone():%Y-%m-%d-%H%M%S}-{n}.md")
        n += 1
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\n→ {out}（新着 {total} 件・見張る先 {len(rows)}）")


def main() -> int:
    args = sys.argv[1:]
    days = 14
    fresh = "--fresh" in args
    if fresh:
        args.remove("--fresh")
    if "--days" in args:
        i = args.index("--days")
        days = int(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, topic = args[0], Path(args[1]).expanduser()
    if cmd == "add" and len(args) >= 3:
        return cmd_add(topic, args[2], args[3] if len(args) > 3 else None)
    elif cmd == "list":
        for row in load_watch(topic):
            print("\t".join(row))
    elif cmd == "check":
        cmd_check(topic, days, fresh)
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    # 記事の題と冒頭を出すので、端末の文字コードに無い字（cp932 の à など）で落ちないようにする
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
