#!/usr/bin/env python3
"""原文を1本落とし、本物かどうか確かめてから sources/ に残す。

検索結果の URL は古いことが多く、2026-10-09 の試しでは 11 本中 5 本が
404・ログインの壁・PDF のふりをした HTML だった。拡張子や HTTP の成否では
見分けられないので、中身の先頭と文字数で判定する。

論文だけでなく個人の発信も落とす。YouTube は字幕を `[分:秒] 文` の形で
.md にする（場所を時刻で指せるように）。X はログインの壁で本文が取れないので、
取りに行かずに FAIL を返す。

使い方:
    fetch.py <sources_dir> <name> <url>
出力（標準出力に1行・タブ区切り）:
    OK   <name> <保存したファイル> <文字数> <先頭の一行>
    FAIL <name> <理由>
"""

import codecs
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

# 本文として読める最低の文字数。404 ページや認証の壁は数百〜数千文字に収まる。
# PDF は英語の論文が多いので高め。HTML は日本語の短い記事を通すため低め
# （大陸塗りの試しで 2,904 字の本物の記事が 3,000 の下限で落ちた）。
MIN_TEXT_CHARS = 3000
MIN_HTML_CHARS = 1000
MAX_BYTES = 40_000_000
# 本文ではなく壁に当たったと分かる言い回し。小文字で照合する。
WALL_PATTERNS = (
    "404 not found",
    "page not found",
    "access denied",
    "you do not currently have access",
    "sign in to continue",
    "log in to continue",
    "enable javascript",
    "are you a robot",
    "captcha",
)


class _Redirect308(urllib.request.HTTPRedirectHandler):
    """Python 3.10 でも 308 の転送をたどる。

    3.10 の HTTPRedirectHandler は http_error_308 を持たず、redirect_request も 308 をはねる
    （どちらも 3.11 で足された）。308 は 307 と同じく「同じメソッドのまま別の URL へ」なので、
    307 として扱わせる。3.11 以降では動きは変わらない（openhands.dev などが 308 を返す・#3）。
    """

    http_error_308 = urllib.request.HTTPRedirectHandler.http_error_302

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, 307 if code == 308 else code, msg, headers, newurl)


_OPENER = urllib.request.build_opener(_Redirect308)


def download(url: str) -> tuple[bytes, str]:
    """URL を取りに行き、本体と Content-Type を返す。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 imozuru"})
    with _OPENER.open(req, timeout=90) as res:
        return res.read(MAX_BYTES), res.headers.get("Content-Type", "")


# Shift_JIS と名乗るページの多くは実際には Windows の拡張（①・髙 など）を含むので、上位互換の cp932 で読む
_CHARSET_ALIASES = {"shift_jis": "cp932", "shift-jis": "cp932", "sjis": "cp932", "x-sjis": "cp932",
                    "windows-31j": "cp932", "ms_kanji": "cp932"}


def _declared_charsets(body: bytes, ctype: str) -> list[str]:
    """Content-Type と HTML の meta が名乗る文字コードを、この順に返す。"""
    found = re.findall(r"charset\s*=\s*[\"']?([\w.:-]+)", ctype or "", re.I)
    # meta はファイルの頭に置かれる決まり（HTML 仕様で先頭 1024 バイト以内）。余裕を見て 4096 まで見る
    found += re.findall(rb"<meta[^>]*charset\s*=\s*[\"']?([\w.:-]+)", body[:4096], re.I)
    names = [(n.decode("ascii", "ignore") if isinstance(n, bytes) else n).lower() for n in found]
    return [_CHARSET_ALIASES.get(n, n) for n in names]


def decode_text(body: bytes, ctype: str = "") -> str:
    """本文を、書かれている文字コードで文字にする。

    いつも UTF-8 で読んでいたため、Shift_JIS の日本語記事が U+FFFD の羅列になって中身が消えた
    （pju-hoge さんのフォークで見つかった・2026-10-15）。名乗りは嘘のこともあるので、
    名乗った文字コード → UTF-8 → 日本語の定番の順に「化けずに読めるか」で試し、最初に通ったものを使う。
    どれも通らなければ、置換文字のいちばん少ないものを採る。
    """
    candidates = []
    for name in [*_declared_charsets(body, ctype), "utf-8", "cp932", "euc_jp"]:
        try:
            codec = codecs.lookup(name).name
        except LookupError:  # 知らない名乗り（x-user-defined など）は飛ばす
            continue
        if codec not in candidates:
            candidates.append(codec)
    for codec in candidates:
        try:
            return body.decode(codec)
        except UnicodeDecodeError:
            continue
    return min((body.decode(c, errors="replace") for c in candidates), key=lambda t: t.count("�"))


def missing(*commands: str) -> list[str]:
    """手元に無い外部コマンドの名前を返す。無いまま呼ぶと FileNotFoundError で止まるため。"""
    return [c for c in commands if shutil.which(c) is None]


def pdf_to_text(pdf: Path) -> str:
    """pdftotext で段組みを保ったまま文字にする。行番号で原文を指せるように -layout を使う。

    Xpdf の pdftotext（Git for Windows に入っている）は既定で Latin-1 を出すので、
    -enc UTF-8 で出力の文字コードを決める。poppler の pdftotext も同じ引数を受け付ける（#3）。
    """
    if missing("pdftotext"):
        return ""
    out = pdf.with_suffix(".txt")
    subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", str(pdf), str(out)], check=False,
                   stderr=subprocess.DEVNULL)
    return out.read_text(encoding="utf-8", errors="replace") if out.exists() else ""


def ocr_pdf(pdf: Path) -> str:
    """文字の層が無い PDF（紙を読み取った画像だけの古い論文）を、手元の tesseract で文字にする。

    Spencer ら 1995 の PDF は取れたのに pdftotext が1文字しか返さなかった（2026-10-10）。
    英語だけ（入っている言語データが eng のみ）。1ページずつ 200dpi の画像にして読む。
    OCR の誤りは残るので、.txt の先頭に OCR だと書いて、読む人が原本と照らせるようにする。
    pdftoppm か tesseract が無ければ何もせず空を返す（呼び手が FAIL に無いコマンドを書く）。
    """
    if missing("pdftoppm", "tesseract"):
        return ""
    tmp = pdf.parent / f".{pdf.stem}-ocr"
    tmp.mkdir(exist_ok=True)
    subprocess.run(["pdftoppm", "-r", "200", "-png", str(pdf), str(tmp / "p")],
                   check=False, stderr=subprocess.DEVNULL)
    pages = []
    for img in sorted(tmp.glob("p-*.png")):
        res = subprocess.run(["tesseract", str(img), "-", "-l", "eng"],
                             capture_output=True, encoding="utf-8", errors="replace")
        pages.append(f"=== page {img.stem.split('-')[-1]} ===\n{res.stdout}")
        img.unlink()
    tmp.rmdir()
    text = "\n".join(pages)
    out = pdf.with_suffix(".txt")
    out.write_text("（OCR で起こした本文。誤りが残るので、引用は原本の PDF で確かめる）\n\n" + text,
                   encoding="utf-8")
    return text


HAS_AX = shutil.which("ax") is not None


class _TextExtractor(HTMLParser):
    """ax が無い環境で、HTML から本文の文字を取り出す。

    ax ほど本文を見分けられない。<main> か <article> があって中身が十分なら、その中だけを使う。
    無いページではナビゲーションやフッターの文字も混ざるが、行番号で原文を指すには足りる。
    リンクは「後ろへ」たどる手がかりなので `[文字](URL)` で残す。
    """

    FOCUS = {"main", "article"}

    SKIP = {"script", "style", "noscript", "svg", "template", "iframe"}
    BLOCK = {"p", "div", "section", "article", "main", "header", "footer", "nav", "aside",
             "li", "tr", "br", "hr", "pre", "blockquote", "table", "ul", "ol", "dl", "dt", "dd",
             "figure", "figcaption"}
    HEADING = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### ", "h5": "##### ", "h6": "###### "}

    def __init__(self, base: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base = base
        self.parts: list[str] = []
        self.skip = 0
        self.href: str | None = None
        self.link_text: list[str] = []
        self.focus = 0
        self.focus_parts: list[str] = []

    def _emit(self, piece: str) -> None:
        self.parts.append(piece)
        if self.focus:
            self.focus_parts.append(piece)

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif self.skip:
            return
        elif tag in self.FOCUS:
            self.focus += 1
        elif tag in self.HEADING:
            self._emit("\n\n" + self.HEADING[tag])
        elif tag in self.BLOCK:
            self._emit("\n")
        elif tag == "a":
            href = dict(attrs).get("href")
            if href and not href.startswith(("#", "javascript:")):
                self.href = urllib.parse.urljoin(self.base, href)
                self.link_text = []

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif self.skip:
            return
        elif tag in self.FOCUS:
            self.focus = max(0, self.focus - 1)
        elif tag in self.HEADING or tag in self.BLOCK:
            self._emit("\n")
        elif tag == "a" and self.href is not None:
            text = " ".join("".join(self.link_text).split())
            self._emit(f"[{text}]({self.href})" if text else "")
            self.href = None

    def handle_data(self, data):
        if self.skip:
            return
        if self.href is not None:
            self.link_text.append(data)
        else:
            self._emit(data)

    def text(self) -> str:
        focused = "".join(self.focus_parts)
        # 中身の薄い <main>（ページの殻だけ）を掴んだときは全体に戻す
        raw = focused if len(focused.strip()) >= MIN_HTML_CHARS else "".join(self.parts)
        lines = (" ".join(line.split()) for line in raw.splitlines())
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def html_to_md(url: str, out: Path, body: bytes | None = None, ctype: str = "") -> str:
    """本文を markdown にする。要約はしない。

    ax があれば ax（--all で全文）。無ければ標準ライブラリで文字を取り出す。
    body を渡されたら取り直さずにそれを使う（ax が無いときの二重の取得を避ける）。
    ctype は body の Content-Type。文字コードの名乗りを読むのに使う。
    """
    if HAS_AX:
        res = subprocess.run(["ax", url, "--md", "--all"], capture_output=True,
                             encoding="utf-8", errors="replace")
        text = res.stdout
    else:
        if body is None:
            body, ctype = download(url)
        if body[:5] == b"%PDF-":
            # 転送先が PDF だった。呼び手が「%PDF」で気づいて PDF として取り直す
            text = "%PDF"
        else:
            parser = _TextExtractor(url)
            parser.feed(decode_text(body, ctype))
            text = parser.text()
    out.write_text(text, encoding="utf-8")
    return text


def ax_save(url: str, out: Path) -> bool:
    """本体をそのままファイルに保存する。保存できたら True。

    HAL（hal.inria.fr）は urllib には HTML を返し、ax には転送先の PDF を返す（2026-10-11）。
    そのとき html_to_md は PDF の中身を文字として .md に書いてしまうので、ここで丸ごと取り直す。
    ax が無いときは urllib で取り直す。
    """
    if HAS_AX:
        subprocess.run(["ax", url, "-o", str(out)], capture_output=True)
    else:
        try:
            out.write_bytes(download(url)[0])
        except Exception:  # 取れなければ呼び手が FAIL にする
            return False
    return out.exists() and out.stat().st_size > 0


YOUTUBE = re.compile(r"(youtube\.com/(watch|shorts|live)|youtu\.be/)")
X_POST = re.compile(r"^https?://(www\.)?(x|twitter)\.com/")
# 字幕は数分の動画でも千文字に届かないことがあるので、論文より低い下限を使う。
MIN_TRANSCRIPT_CHARS = 300


def youtube_to_md(url: str, out: Path) -> str:
    """yt-dlp で字幕だけ落とし（動画は落とさない）、時刻つきの本文にする。

    手動の字幕を優先し、無ければ自動字幕。日本語→英語の順。自動字幕は同じ文が
    次の区間にも繰り返し出るので、直前と同じ文は捨てる。

    自動字幕は誤変換が多い（大陸塗りの試しで「線画」が「洗画」）。どちらを使ったかを
    見出しに残し、読み手が引用を動画で確かめるべきか分かるようにする。手動と自動は
    同じファイル名で出てくるので、まず手動だけで取り、無いときだけ自動で取り直す。
    題名の出力は --encoding で UTF-8 に決める。Windows でパイプに出すと、決めない限り cp932 になる。
    """
    tmp = out.parent / f".{out.stem}-subs"
    tmp.mkdir(exist_ok=True)
    kind = "手動"
    for flag in ("--write-subs", "--write-auto-subs"):
        meta = subprocess.run(
            ["yt-dlp", "--no-update", "--skip-download", flag, "--encoding", "utf-8",
             "--sub-langs", "ja,en", "--sub-format", "vtt", "--no-simulate",
             "--print", "%(title)s\t%(uploader)s\t%(upload_date)s",
             "-o", str(tmp / "v.%(ext)s"), url],
            capture_output=True, encoding="utf-8", errors="replace")
        if any(tmp.glob("*.vtt")):
            break
        kind = "自動（誤変換あり・引用は動画で確かめる）"
    vtts = sorted(tmp.glob("*.vtt"), key=lambda p: (".ja" not in p.name, p.name))
    lines, last = [], ""
    if vtts:
        stamp = "00:00"
        for raw in vtts[0].read_text(encoding="utf-8", errors="replace").splitlines():
            m = re.match(r"(\d\d):(\d\d):(\d\d)\.\d+ -->", raw)
            if m:
                h, mi, s = (int(x) for x in m.groups())
                stamp = f"{h * 60 + mi:02d}:{s:02d}"
                continue
            text = re.sub(r"<[^>]+>", "", raw).strip()
            if not text or text in ("WEBVTT",) or text.startswith(("Kind:", "Language:")):
                continue
            if text != last:
                lines.append(f"[{stamp}] {text}")
                last = text
    for p in tmp.iterdir():
        p.unlink()
    tmp.rmdir()
    head = meta.stdout.strip().split("\t")
    title = head[0] if head and head[0] else url
    info = " / ".join(head[1:]) if len(head) > 1 else ""
    body = "\n".join(lines)
    out.write_text(f"# {title}\n\n{url}\n{info}\n字幕: {kind + ' ' + vtts[0].name if vtts else 'なし'}\n\n{body}\n",
                   encoding="utf-8")
    return body


def first_line(text: str) -> str:
    for line in text.splitlines():
        line = re.sub(r"\s+", " ", line).strip()
        if len(line) > 8:
            return line[:100]
    return ""


def save_verified(saved: Path, kept: Path, destination: Path) -> Path:
    """検査を通ったファイルだけを、同じファイルシステム内で保存先に移す。"""
    if saved != kept:
        saved.replace(destination / saved.name)
    target = destination / kept.name
    kept.replace(target)
    return target


def valid_source_name(name: str) -> bool:
    """保存する原文の名前は、パスではなく単一のファイル名に限る。"""
    device = name.split(".", 1)[0].rstrip(" ").upper()
    return (bool(name.strip(" .")) and name == name.rstrip(" .")
            and not any(c in name for c in "/\\:")
            and not any(ord(c) < 32 or 127 <= ord(c) <= 159 for c in name)
            and device not in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
            and not re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", device))


def fetch_source(sources: Path, name: str, url: str, destination: Path) -> int:
    """sources は今回の取得専用の一時置き場。取得・変換・検査中は保存済みの原文に触れない。"""
    if not valid_source_name(name):
        print(f"FAIL\t{name!r}\t原文の名前は単一のファイル名にする")
        return 1

    if X_POST.match(url):
        print(f"FAIL\t{name}\tX はログインの壁で本文が取れない（URL を map.md に残す）")
        return 1
    if YOUTUBE.search(url):
        if missing("yt-dlp"):
            print(f"FAIL\t{name}\tyt-dlp が無いので字幕を落とせない")
            return 1
        kept = sources / f"{name}.md"
        body = youtube_to_md(url, kept)
        if len(body) < MIN_TRANSCRIPT_CHARS:
            kept.unlink(missing_ok=True)
            print(f"FAIL\t{name}\t字幕が無いか短すぎる（{len(body)}文字）")
            return 1
        kept = save_verified(kept, kept, destination)
        print(f"OK\t{name}\t{kept}\t{len(body)}\t{first_line(body)}")
        return 0

    try:
        body, ctype = download(url)
    except Exception as e:  # HTTP エラーも接続失敗も、呼び手にとっては同じ「取れない」
        print(f"FAIL\t{name}\t{type(e).__name__}: {e}")
        return 1

    if not body.strip():
        # 中身の無い 200/202 を返すサーバーがある（Cornell の論文置き場・2026-10-10）。
        # ブラウザでないと中身を渡さないボット対策のことが多い＝ユーザーのブラウザで開いてもらう候補
        print(f"FAIL\t{name}\t空の応答（ボット対策の可能性・ブラウザで開けば読めるかも）")
        return 1
    if body[:5] == b"%PDF-":
        saved = sources / f"{name}.pdf"
        saved.write_bytes(body)
        text = pdf_to_text(saved)
        kept = saved.with_suffix(".txt")
        if len(text.strip()) < 200 and not re.search(r"arxiv\.org", url):
            text = ocr_pdf(saved)  # 文字の層が無い PDF。arXiv は下で HTML 版に切り替える
    elif ctype.startswith(("text/plain", "text/markdown", "application/json", "text/csv")):
        # GitHub の README やデータ（raw.githubusercontent.com）はこの形で来る
        # （和田三造の配色のデータで FAIL した・2026-10-10）。中身をそのまま残す。
        # HTML の判定より先に見る。先頭が `<!-- AUTO GENERATED -->` の markdown を
        # HTML と見なして ax に回し、改行が全部消えた（chrome-devtools-mcp の tool-reference・2026-10-11）。
        ext = ".json" if "json" in ctype else ".csv" if "csv" in ctype else ".md"
        kept = saved = sources / f"{name}{ext}"
        text = decode_text(body, ctype)
        kept.write_text(text, encoding="utf-8")
    elif "html" in ctype or body.lstrip()[:1] == b"<":
        kept = sources / f"{name}.md"
        text = html_to_md(url, kept, body, ctype)
        saved = kept
        # HTML のつもりが、ax は転送をたどって PDF 本体を受け取っていた（HAL）。PDF として取り直す
        if text.lstrip().startswith("%PDF"):
            kept.unlink(missing_ok=True)
            saved = sources / f"{name}.pdf"
            if ax_save(url, saved) and saved.read_bytes()[:5] == b"%PDF-":
                text = pdf_to_text(saved)
                kept = saved.with_suffix(".txt")
                if len(text.strip()) < 200:
                    text = ocr_pdf(saved)
            else:
                saved.unlink(missing_ok=True)
                print(f"FAIL\t{name}\t転送先の PDF を保存できなかった")
                return 1
    else:
        print(f"FAIL\t{name}\t扱えない形式: {ctype or '不明'}")
        return 1

    # arXiv の PDF は pdftotext で本文が0文字になることがある（2026-10-09 の試しで
    # COLE・Accordion）。同じ論文の HTML 版なら取れたので、短いときだけ切り替える。
    arxiv_id = re.search(r"arxiv\.org/(?:pdf|abs)/(\d{4}\.\d{4,5}(?:v\d+)?)", url)
    if arxiv_id and len(text) < MIN_TEXT_CHARS:
        for p in (saved, kept):
            p.unlink(missing_ok=True)
        kept = saved = sources / f"{name}.md"
        text = html_to_md(f"https://arxiv.org/html/{arxiv_id.group(1)}", kept)

    floor = MIN_TEXT_CHARS if saved.suffix == ".pdf" else MIN_HTML_CHARS
    head = text[:4000].lower()
    wall = next((p for p in WALL_PATTERNS if p in head), None)
    if len(text) < floor or (wall and len(text) < MIN_TEXT_CHARS * 4):
        for p in (saved, kept):
            p.unlink(missing_ok=True)
        reason = f"壁に当たった（{wall}）" if wall else f"本文が短すぎる（{len(text)}文字）"
        # PDF の文字起こしに要るコマンドが欠けていたなら、短い理由はたいていそれ
        lacking = missing("pdftotext", "pdftoppm", "tesseract") if saved.suffix == ".pdf" else []
        if lacking:
            reason += f"。{'・'.join(lacking)} が無い"
        print(f"FAIL\t{name}\t{reason}")
        return 1

    kept = save_verified(saved, kept, destination)
    print(f"OK\t{name}\t{kept}\t{len(text)}\t{first_line(text)}")
    return 0


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    sources, name, url = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    if not valid_source_name(name):
        print(f"FAIL\t{name!r}\t原文の名前は単一のファイル名にする")
        return 1
    sources.mkdir(parents=True, exist_ok=True)
    # 変換や FAIL の後始末は一時置き場だけで行う。同名の原文を検査前に上書きしない。
    # 保存先の中に作るので、成功時の replace はファイルシステムをまたがない。
    with tempfile.TemporaryDirectory(prefix=".imozuru-fetch-", dir=sources) as tmp:
        return fetch_source(Path(tmp), name, url, sources)


if __name__ == "__main__":
    # 本文の先頭の一行を出すので、端末の文字コードに無い字（cp932 の à など）で落ちないようにする
    sys.stdout.reconfigure(errors="replace")
    sys.exit(main())
