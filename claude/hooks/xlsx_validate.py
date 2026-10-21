#!/usr/bin/env python3
"""Check .xlsx files for structures that make Excel offer to repair the workbook.

Usage: xlsx_validate.py FILE...

Errors are structures Excel is known to repair (and may drop data while doing so), and
files that cannot be read or checked at all. Warnings are inconsistencies that are not
confirmed to trigger a repair, and encrypted or legacy compound files, which are not checked.
Exit status: 0 when no file has errors, 1 when any file has errors, 2 on usage error.
Only the Python standard library is used, so the script runs without a project environment.
"""

import posixpath
import re
import sys
import time
import xml.etree.ElementTree as ET
import zipfile

MAX_REPORTS_PER_CHECK = 5
DEADLINE_CHECK_EVERY = 2000
MAX_ROW = 1048576
MAX_COL = 16384
CFB_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
REL_TYPE_SHARED_STRINGS = "/sharedStrings"
REL_TYPE_STYLES = "/styles"
REL_TYPE_WORKSHEET = "/worksheet"


def local(tag):
    return tag.rsplit("}", 1)[-1]


def children(elem, name):
    return [c for c in elem if local(c.tag) == name]


def child(elem, name):
    for c in elem:
        if local(c.tag) == name:
            return c
    return None


def attr(elem, name):
    """Read an attribute by local name, ignoring its namespace (r:id and similar)."""
    for key, value in elem.attrib.items():
        if local(key) == name:
            return value
    return None


def as_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def col_to_num(col):
    n = 0
    for ch in col:
        n = n * 26 + ord(ch) - 64
    return n


CELL_RE = re.compile(r"^\$?([A-Z]{1,3})\$?(\d+)$")
COL_RE = re.compile(r"^\$?([A-Z]{1,3})$")
ROW_RE = re.compile(r"^\$?(\d+)$")


def parse_ref(ref):
    m = CELL_RE.match(ref)
    if not m:
        return None
    return int(m.group(2)), col_to_num(m.group(1))


def parse_range(part):
    """Return (row1, col1, row2, col2) for A1, A1:B2, A:B or 1:2; None if unparsable."""
    a, _, b = part.partition(":")
    b = b or a
    ca, cb = parse_ref(a), parse_ref(b)
    if ca and cb:
        return min(ca[0], cb[0]), min(ca[1], cb[1]), max(ca[0], cb[0]), max(ca[1], cb[1])
    ma, mb = COL_RE.match(a), COL_RE.match(b)
    if ma and mb:
        c1, c2 = col_to_num(ma.group(1)), col_to_num(mb.group(1))
        return 1, min(c1, c2), MAX_ROW, max(c1, c2)
    ma, mb = ROW_RE.match(a), ROW_RE.match(b)
    if ma and mb:
        r1, r2 = int(ma.group(1)), int(mb.group(1))
        return min(r1, r2), 1, max(r1, r2), MAX_COL
    return None


def overlaps(x, y):
    return x[0] <= y[2] and y[0] <= x[2] and x[1] <= y[3] and y[1] <= x[3]


def overlapping_pairs(items):
    """items: (label, group, rect). Yield label pairs from different groups whose rects overlap.

    Rectangles are swept in row order and only those still spanning the current row are
    compared, so typical sheets (ranges spread over many rows) stay close to linear.
    """
    active = []
    for label, group, rect in sorted(items, key=lambda item: item[2][0]):
        active = [a for a in active if a[2][2] >= rect[0]]
        for other_label, other_group, other_rect in active:
            if other_group != group and overlaps(rect, other_rect):
                yield other_label, label
        active.append((label, group, rect))


class TimeLimit(Exception):
    pass


class Deadline:
    def __init__(self, seconds):
        self.seconds = seconds
        self.at = time.monotonic() + seconds if seconds else None
        self._ticks = 0

    def tick(self):
        self._ticks += 1
        if self.at is not None and self._ticks % DEADLINE_CHECK_EVERY == 0 and time.monotonic() > self.at:
            raise TimeLimit()


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.error_kinds = []
        self._counts = {}

    def _add(self, bucket, key, message):
        n = self._counts.get(key, 0) + 1
        self._counts[key] = n
        if n <= MAX_REPORTS_PER_CHECK:
            bucket.append(message)
        elif n == MAX_REPORTS_PER_CHECK + 1:
            bucket.append(f"... more of the same ({key})")

    def error(self, key, message):
        if key not in self.error_kinds:
            self.error_kinds.append(key)
        self._add(self.errors, key, message)

    def warning(self, key, message):
        self._add(self.warnings, key, message)


def number_attr(report, where, elem, name):
    """Return the attribute as int, None when absent; report an error when it is not a number."""
    value = elem.get(name)
    if value is None:
        return None
    n = as_int(value)
    if n is None:
        report.error("number", f"{where}: attribute {name}={value!r} is not a number")
    return n


def rels_path_for(part):
    base, name = posixpath.split(part)
    return posixpath.join(base, "_rels", name + ".rels")


def resolve_target(source_part, target):
    if target.startswith("/"):
        return target.lstrip("/")
    return posixpath.normpath(posixpath.join(posixpath.dirname(source_part), target))


def read_relationships(trees, source_part):
    """Map rId -> (type, resolved internal target) for one part; external targets are skipped."""
    tree = trees.get(rels_path_for(source_part))
    rels = {}
    if tree is None:
        return rels
    for rel in children(tree, "Relationship"):
        if rel.get("TargetMode") == "External":
            continue
        rels[rel.get("Id")] = (rel.get("Type", ""), resolve_target(source_part, rel.get("Target", "")))
    return rels


def check_package(names, trees, report):
    ct = trees.get("[Content_Types].xml")
    if ct is None:
        report.error("content-types", "[Content_Types].xml is missing or unreadable")
        return
    defaults = {d.get("Extension", "").lower() for d in children(ct, "Default")}
    overrides = {o.get("PartName", "").lstrip("/") for o in children(ct, "Override")}
    # Only parts reached through relationships need a content type; Excel itself leaves
    # unreferenced leftovers such as [trash]/0000.dat without one.
    for rels_name in sorted(names):
        if not rels_name.endswith(".rels") or rels_name not in trees:
            continue
        folder, file = posixpath.split(rels_name)
        source = posixpath.join(posixpath.dirname(folder), file[: -len(".rels")])
        for rel in children(trees[rels_name], "Relationship"):
            if rel.get("TargetMode") == "External":
                continue
            target = resolve_target(source, rel.get("Target", ""))
            if target not in names:
                report.error("relationship", f"{rels_name}: target {target} does not exist")
                continue
            ext = target.rsplit(".", 1)[-1].lower() if "." in target else ""
            if target not in overrides and ext not in defaults:
                report.error("content-types", f"no content type for part {target}")


def iter_part(z, name, deadline, free_depth=2, free_under=None):
    """Stream (event, element, depth) over one XML part; depth is 1 for the root element.

    After the caller has seen an element's "end", the element is detached from its parent when
    it is exactly `free_depth` deep and, if `free_under` is given, lies under a depth-2 element
    with one of those tag names. Deeper elements stay attached until that ancestor is detached,
    so the caller can still read an element's children at its "end" (for example a cell's <v>).
    """
    stack = []
    with z.open(name) as f:
        for event, elem in ET.iterparse(f, events=("start", "end")):
            if event == "start":
                stack.append(elem)
                yield event, elem, len(stack)
                continue
            depth = len(stack)
            yield event, elem, depth
            stack.pop()
            if depth == free_depth and (free_under is None or local(stack[1].tag) in free_under):
                stack[-1].remove(elem)
            deadline.tick()


def check_well_formed(z, name, deadline):
    for _ in iter_part(z, name, deadline):
        pass


# OOXML writes characters that XML cannot hold as _xHHHH_ (and a literal "_x" as _x005F_x).
OOXML_ESCAPE_RE = re.compile(r"_x([0-9A-Fa-f]{4})_")


def ooxml_unescape(text):
    return OOXML_ESCAPE_RE.sub(lambda m: chr(int(m.group(1), 16)), text)


def utf16_len(text):
    # surrogatepass: an unescaped _xD842_ leaves a lone surrogate, which counts as one unit.
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def check_phonetic(name, index, si, report):
    """Check the phonetic runs (rPh) of one shared string against its base text.

    sb/eb are offsets into the base text (the si's own t, or its rich text runs), counted in
    UTF-16 units. Excel repairs a string whose runs overlap or fall outside the text.
    """
    runs = children(si, "rPh")
    if not runs:
        return
    base_parts = [t.text or "" for t in children(si, "t")]
    for r in children(si, "r"):
        base_parts += [t.text or "" for t in children(r, "t")]
    base = ooxml_unescape("".join(base_parts))
    length = utf16_len(base)
    where = f"{name}: shared string #{index} ({base[:15]!r})"
    spans = []
    for run in runs:
        sb, eb = as_int(run.get("sb")), as_int(run.get("eb"))
        if sb is None or eb is None:
            report.error("phonetic", f"{where}: phonetic run has sb={run.get('sb')!r} eb={run.get('eb')!r}")
            continue
        if sb > eb:
            report.error("phonetic", f"{where}: phonetic run sb={sb} is after eb={eb}")
        elif not 0 <= sb <= eb <= length:
            report.error("phonetic", f"{where}: phonetic run sb={sb} eb={eb} is outside the text (length {length})")
        spans.append((sb, eb))
        text = ooxml_unescape("".join(t.text or "" for t in children(run, "t")))
        if not text:
            report.warning("phonetic-text", f"{where}: phonetic run sb={sb} eb={eb} has no text")
        elif any(ord(ch) < 32 and ch not in "\t\n\r" for ch in text):
            report.warning("phonetic-text", f"{where}: phonetic run sb={sb} eb={eb} contains control characters")
    spans.sort()
    for (sb1, eb1), (sb2, eb2) in zip(spans, spans[1:]):
        if sb2 < eb1 or (sb1, eb1) == (sb2, eb2):
            report.error("phonetic", f"{where}: phonetic runs {sb1}-{eb1} and {sb2}-{eb2} overlap")


def count_shared_strings(z, name, deadline, report):
    """Return (number of si, root attributes) for the shared strings part, checking phonetic runs."""
    n, attrs = 0, {}
    for event, elem, depth in iter_part(z, name, deadline):
        if event == "start" and depth == 1:
            attrs = dict(elem.attrib)
        elif event == "end" and depth == 2 and local(elem.tag) == "si":
            check_phonetic(name, n, elem, report)
            n += 1
    return n, attrs


def check_cell(name, c, r, prev_col, report, n_strings, n_xfs):
    """Check one cell; return its column number (or prev_col when the reference is invalid)."""
    ref = c.get("r")
    if ref:
        parsed = parse_ref(ref)
        if parsed is None:
            report.error("cell-ref", f"{name}: invalid cell reference {ref!r}")
            return prev_col
        cr, cc = parsed
        if cr != r:
            report.error("cell-ref", f"{name}: cell {ref} is inside row {r}")
    else:
        cc = prev_col + 1
    if cc <= prev_col:
        report.error("cell-order", f"{name}: cell {ref or cc} in row {r} is out of column order or duplicated")
    s = number_attr(report, f"{name}: cell {ref}", c, "s")
    if s is not None and s >= n_xfs:
        report.error("style-index", f"{name}: cell {ref} style {s} >= cellXfs count {n_xfs}")
    if c.get("t") == "s":
        v = child(c, "v")
        index = as_int((v.text or "").strip()) if v is not None else None
        if index is None or index < 0 or index >= n_strings:
            shown = v.text if v is not None else "(none)"
            report.error("shared-string", f"{name}: cell {ref} refers to shared string {shown!r} but only {n_strings} exist")
    return max(prev_col, cc)


def check_sheet(name, z, part, report, n_strings, n_xfs, n_dxfs, deadline):
    """Stream one worksheet part; return the number of shared-string cell references."""
    string_refs = 0
    prev_row = 0
    r = 0
    prev_col = 0
    in_sheet_data = False
    merge = dvs = None
    cfs = []
    for event, elem, depth in iter_part(z, part, deadline, free_depth=3, free_under={"sheetData"}):
        tag = local(elem.tag)
        if event == "start":
            if depth == 2 and tag == "sheetData":
                in_sheet_data = True
            elif in_sheet_data and depth == 3 and tag == "row":
                found = number_attr(report, f"{name}: row after {prev_row}", elem, "r")
                r = found if found is not None else prev_row + 1
                if r <= prev_row:
                    report.error("row-order", f"{name}: row {r} comes after row {prev_row} (rows must be ascending and unique)")
                prev_row = max(prev_row, r)
                if elem.get("customFormat") in ("1", "true"):
                    s = number_attr(report, f"{name}: row {r}", elem, "s")
                    if s is not None and s >= n_xfs:
                        report.error("style-index", f"{name}: row {r} style {s} >= cellXfs count {n_xfs}")
                prev_col = 0
            continue
        if in_sheet_data and depth == 4 and tag == "c":
            prev_col = check_cell(name, elem, r, prev_col, report, n_strings, n_xfs)
            if elem.get("t") == "s":
                string_refs += 1
        elif depth == 2:
            if tag == "sheetData":
                in_sheet_data = False
            elif tag == "mergeCells":
                merge = elem
            elif tag == "dataValidations":
                dvs = elem
            elif tag == "conditionalFormatting":
                cfs.append(elem)

    merges = []
    for i, mc in enumerate(children(merge, "mergeCell") if merge is not None else []):
        rect = parse_range(mc.get("ref", ""))
        if rect is None:
            report.error("merge", f"{name}: invalid merged range {mc.get('ref')!r}")
            continue
        merges.append((mc.get("ref"), i, rect))
    for a, b in overlapping_pairs(merges):
        report.error("merge", f"{name}: merged ranges {a} and {b} overlap")

    if dvs is not None:
        items = children(dvs, "dataValidation")
        count = number_attr(report, f"{name}: dataValidations", dvs, "count")
        if count is not None and count != len(items):
            report.warning("dv-count", f"{name}: dataValidations count={count} but {len(items)} exist")
        parts = []
        for i, dv in enumerate(items):
            for part in (dv.get("sqref") or "").split():
                rect = parse_range(part)
                if rect is None:
                    report.error("data-validation", f"{name}: invalid data validation range {part!r}")
                    continue
                parts.append((part, i, rect))
        for a, b in overlapping_pairs(parts):
            report.error("data-validation", f"{name}: data validation ranges {a} and {b} overlap")

    priorities = []
    for cf in cfs:
        where = f"{name}: conditional format {cf.get('sqref')}"
        for rule in children(cf, "cfRule"):
            dxf = number_attr(report, where, rule, "dxfId")
            if dxf is not None and (dxf < 0 or dxf >= n_dxfs):
                report.error("cf-dxf", f"{where} uses dxfId {dxf} but only {n_dxfs} exist")
            priority = number_attr(report, where, rule, "priority")
            if priority is not None:
                priorities.append(priority)
    seen, duplicated = set(), set()
    for p in priorities:
        (duplicated if p in seen else seen).add(p)
    if duplicated:
        report.warning("cf-priority", f"{name}: duplicated conditional format priorities {sorted(duplicated)}")
    return string_refs


def guarded(report, name, work):
    """Run work() for one part; report unreadable or malformed parts. Return work()'s value or None."""
    try:
        return work()
    except ET.ParseError as e:
        report.error("xml", f"{name}: malformed XML ({e})")
    except TimeLimit:
        raise
    except Exception as e:  # CRC mismatch, truncated member, unsupported compression
        report.error("zip", f"{name}: cannot read part ({type(e).__name__}: {e})")
    return None


def check_workbook(z, report, deadline):
    names = set(z.namelist())
    trees = {}
    # Package-level parts are small: parse them whole.
    for name in sorted(names):
        if name == "[Content_Types].xml" or name.endswith(".rels"):
            tree = guarded(report, name, lambda: ET.fromstring(z.read(name)))
            if tree is not None:
                trees[name] = tree
    check_package(names, trees, report)

    root_rels = read_relationships(trees, "")
    workbook_part = next((t for typ, t in root_rels.values() if typ.endswith("/officeDocument")), "xl/workbook.xml")
    workbook = guarded(report, workbook_part, lambda: ET.fromstring(z.read(workbook_part))) if workbook_part in names else None
    if workbook is None:
        report.error("workbook", f"workbook part {workbook_part} is missing or unreadable")
        return
    wb_rels = read_relationships(trees, workbook_part)
    checked = set(trees) | {workbook_part}

    styles_part = next((t for typ, t in wb_rels.values() if typ.endswith(REL_TYPE_STYLES)), None)
    styles = guarded(report, styles_part, lambda: ET.fromstring(z.read(styles_part))) if styles_part in names else None
    checked.add(styles_part)
    xfs = child(styles, "cellXfs") if styles is not None else None
    dxfs = child(styles, "dxfs") if styles is not None else None
    n_xfs = len(children(xfs, "xf")) if xfs is not None else 1
    n_dxfs = len(children(dxfs, "dxf")) if dxfs is not None else 0

    # Shared strings and worksheets can be hundreds of MB: stream them.
    sst_part = next((t for typ, t in wb_rels.values() if typ.endswith(REL_TYPE_SHARED_STRINGS)), None)
    n_strings, sst_attrs = 0, None
    if sst_part in names:
        counted = guarded(report, sst_part, lambda: count_shared_strings(z, sst_part, deadline, report))
        if counted is not None:
            n_strings, sst_attrs = counted
        checked.add(sst_part)

    string_refs = 0
    sheets = child(workbook, "sheets")
    for sheet in children(sheets, "sheet") if sheets is not None else []:
        rid = attr(sheet, "id")
        typ, part = wb_rels.get(rid, ("", None))
        if part is None:
            report.error("workbook", f"sheet '{sheet.get('name')}' refers to missing relationship {rid}")
            continue
        if not typ.endswith(REL_TYPE_WORKSHEET) or part not in names:
            continue
        label = f"sheet '{sheet.get('name')}' ({part})"
        refs = guarded(report, part, lambda: check_sheet(label, z, part, report, n_strings, n_xfs, n_dxfs, deadline))
        string_refs += refs or 0
        checked.add(part)

    for name in sorted(names - checked):
        if name.endswith(".xml"):
            guarded(report, name, lambda: check_well_formed(z, name, deadline))

    if sst_attrs is not None:
        holder = ET.Element("sst", sst_attrs)
        unique = number_attr(report, sst_part, holder, "uniqueCount")
        if unique is not None and unique != n_strings:
            report.warning("sst-count", f"{sst_part}: uniqueCount={unique} but {n_strings} strings exist")
        count = number_attr(report, sst_part, holder, "count")
        if count is not None and count != string_refs:
            report.warning("sst-count", f"{sst_part}: count={count} but {string_refs} cells refer to shared strings")


def validate(path, time_limit=None):
    """Return a Report for one file. Never raises: a file that cannot be checked is an error.

    With time_limit (seconds), checking stops at the limit; problems found so far are kept and
    a warning says the rest of the file was not checked.
    """
    report = Report()
    try:
        with open(path, "rb") as f:
            head = f.read(len(CFB_MAGIC))
        if head == CFB_MAGIC:
            report.warning("compound-file", "compound file (encrypted workbook or legacy format); structure not checked")
            return report
        with zipfile.ZipFile(path) as z:
            check_workbook(z, report, Deadline(time_limit))
    except TimeLimit:
        report.warning("time-limit", f"stopped after {time_limit:.0f}s; the rest of the file was not checked")
    except (zipfile.BadZipFile, OSError) as e:
        report.error("zip", f"cannot open as a zip package: {e}")
    except Exception as e:
        report.error("internal", f"could not validate ({type(e).__name__}: {e})")
    return report


def main(argv):
    if len(argv) < 2:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    failed = False
    for path in argv[1:]:
        report = validate(path)
        if report.errors:
            failed = True
        status = "ERROR" if report.errors else ("WARNING" if report.warnings else "OK")
        print(f"{path}: {status}")
        for message in report.errors:
            print(f"  error: {message}")
        for message in report.warnings:
            print(f"  warning: {message}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
