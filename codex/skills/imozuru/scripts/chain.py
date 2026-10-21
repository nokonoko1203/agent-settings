#!/usr/bin/env python3
"""論文の引用を前へ・後ろへたどる（OpenAlex）。

Bates 1989 の footnote chasing（後ろへ）と citation searching（前へ）を道具でやる。
引用をたどると、その分野の言葉を知らなくても次の論文に行ける（Bates 1989 L301-302）。

OpenAlex は1日 1,000 回まで無料の枠（x-ratelimit-limit-usd 0.1）。プリペイドの残高が
0 なら枠を超えても止まるだけで課金されない。API キーや支払いの登録はしない。

使い方:
    chain.py find  <DOI か題名>          … 論文を特定して ID を出す（題名なら候補5件）
    chain.py refs  <ID か DOI> [-n 20]    … 後ろへ: その論文が引いている文献
    chain.py cites <ID か DOI> [-n 20]    … 前へ: その論文を引いている文献（被引用の多い順）
    chain.py author <著者名> [-n 20]      … 著者で追う: その人の論文（被引用の多い順）
出力: 1行1本、タブ区切り（年 被引用数 ID 題名 DOI 無料PDF）
"""

import json
import sys
import urllib.parse
import urllib.request

API = "https://api.openalex.org"
FIELDS = "id,display_name,publication_year,cited_by_count,doi,best_oa_location"


def get(path: str, **params) -> dict:
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "imozuru (mailto omitted)"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.load(res)


def search_title(key: str) -> list[dict]:
    """題名だけを対象に探し、被引用の多い順に5件返す。

    全文検索（search=）は解説記事や重複の記録が上に来て、Kuhlthau 1991 の本体が
    5位以内に出なかった。題名に絞って被引用順に並べると本体が1位に来た。
    題名に著者名を混ぜると外れるので、題名の語だけを渡す。

    登録された題名が副題抜きのことがある（Marchionini 2006 は "Exploratory search"
    だけ）。全部の語では0件になるので、0件なら前半の3語で引き直す。
    """
    words = key.replace(",", " ").replace(":", " ").split()
    for terms in (words, words[:3]):
        hits = get("/works", filter="title.search:" + " ".join(terms),
                   sort="cited_by_count:desc", **{"per-page": 5}, select=FIELDS)["results"]
        if hits:
            return hits
    return []


def resolve(key: str) -> dict:
    """DOI・OpenAlex ID・題名のどれからでも論文を1本引く。題名なら被引用の最も多い1本。"""
    if key.startswith("W") or "openalex.org/" in key:
        return get(f"/works/{key.rsplit('/', 1)[-1]}", select=FIELDS)
    if key.startswith("10.") or "doi.org/" in key:
        doi = key.split("doi.org/")[-1]
        return get(f"/works/doi:{doi}", select=FIELDS)
    hits = search_title(key)
    if not hits:
        raise SystemExit(f"見つからない: {key}")
    return hits[0]


def row(w: dict) -> str:
    oa = (w.get("best_oa_location") or {}).get("pdf_url") or ""
    wid = (w.get("id") or "").rsplit("/", 1)[-1]
    return "\t".join(str(x) for x in (
        w.get("publication_year"), w.get("cited_by_count"), wid,
        (w.get("display_name") or "")[:120], w.get("doi") or "", oa))


def main() -> int:
    args = sys.argv[1:]
    n = 20
    if "-n" in args:
        i = args.index("-n")
        n = int(args[i + 1])
        del args[i:i + 2]
    if len(args) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    cmd, key = args[0], " ".join(args[1:])

    if cmd == "find":
        # 題名のときは候補を全部見せる。どれが本体かを読み手が確かめられるように。
        hits = [resolve(key)] if key.startswith(("W", "10.")) or "/" in key else search_title(key)
        if not hits:
            print(f"候補なし: {key}（DOI で引き直すか、題名の語を減らす）")
        for w in hits:
            print(row(w))
    elif cmd in ("refs", "cites"):
        wid = resolve(key)["id"].rsplit("/", 1)[-1]
        flt = f"cited_by:{wid}" if cmd == "refs" else f"cites:{wid}"
        res = get("/works", filter=flt, sort="cited_by_count:desc",
                  **{"per-page": n}, select=FIELDS)
        print(f"# {cmd} {wid} 全{res['meta']['count']}本中 上位{len(res['results'])}本")
        for w in res["results"]:
            print(row(w))
    elif cmd == "author":
        hits = get("/authors", search=key, **{"per-page": 1})["results"]
        if not hits:
            raise SystemExit(f"著者が見つからない: {key}")
        a = hits[0]
        aid = a["id"].rsplit("/", 1)[-1]
        inst = ", ".join(i["display_name"] for i in a.get("last_known_institutions") or [])
        print(f"# author {a['display_name']} {aid} {inst} 論文{a.get('works_count')}本")
        res = get("/works", filter=f"author.id:{aid}", sort="cited_by_count:desc",
                  **{"per-page": n}, select=FIELDS)
        for w in res["results"]:
            print(row(w))
    else:
        print(__doc__, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
