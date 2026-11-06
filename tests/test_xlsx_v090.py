""".xlsx input through the safe reader (T89..T101, v0.9.0).

Every fixture is built deterministically with the standard library only:
fixed zip entry order, fixed timestamps (1980-01-01 00:00:00), explicit
compression per entry, no platform extras -- the same bytes every time
(T99 then proves order/compression/timestamps do not matter anyway).

Cell values are asserted through ``run -o`` with a keep-all configuration
(``inspect`` prints column statistics only, never values); structural
parity between the .xlsx and its CSV twin is asserted on every subcommand.

  T89  an .xlsx reads as the same table as its CSV twin (all subcommands)
  T90  shared / inline / rich strings; furigana <rPh> never reaches values
  T91  numbers stay raw text, booleans/errors as literals, formulas use the
       cached value (missing caches are counted on stderr), leading zeros
       survive in string cells
  T92  date-styled serials -> ISO (1900 and 1904 systems, with time); an
       unconvertible serial stops with unsupported_format
  T93  sheet selection: default = first visible sheet, --sheet by name or
       1-based index, missing -> exit 2, notices on stderr, unused sheets
       leak nothing
  T94  the safe reader refuses DOCTYPE / ENTITY / encryption / zip bombs /
       entry floods / duplicate parts / oversized parts / malformed XML /
       missing main part, each with its code only, exit 1, nothing written
  T95  expansion is measured while reading (a bomb is stopped inside the
       budget without materialising it)
  T96  the Strict OOXML namespace is refused by URI; a renamed prefix with
       the standard URI reads fine
  T97  empty / duplicate headers and column mismatches behave exactly like
       the same content as CSV (same exit codes, same messages)
  T98  hidden rows and columns are data; a merged cell holds its top-left
       value only; the empty right/bottom margins are not part of the table
  T99  zip order, compression and timestamps do not change any result
  T100 .xls / .xlsm / other zips / non-regular files are refused with
       unsupported_format / main_part_missing / not_regular_file
  T101 the input layer imports the standard library only, and marker
       strings planted in furigana, a hidden sheet and an unused sheet
       never reach any output
"""
import ast
import contextlib
import dataclasses
import hashlib
import io
import json
import os
import re
import tempfile
import time
import tracemalloc
import unittest
import zipfile

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEOPLE = os.path.join(REPO, "examples", "people.csv")
CONFIG = os.path.join(REPO, "examples", "config.json")

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
P_TYPE_NS = "http://schemas.openxmlformats.org/package/2006/content-types"
STRICT_NS = "http://purl.oclc.org/ooxml/spreadsheetml/main"


def cli(argv):
    """In-process main(); argparse usage errors fold to exit 2."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = main(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue().encode("utf-8"), err.getvalue().encode("utf-8")


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def keep_all_cfg(path, columns):
    """keep-roles for every column except column 0, which is an exact qi.

    The engine refuses a config with no qi column, so the value probes
    carry a constant first column (all rows share it, the crowd holds,
    and no value is generalized or suppressed).
    """
    cols = {name: {"role": "keep"} for name in columns}
    cols[columns[0]] = {"role": "qi", "type": "exact"}
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"k": 2, "columns": cols}))
    return path


# ----------------------------------------------------------------------
# deterministic .xlsx builder
# ----------------------------------------------------------------------

def _esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _col_letter(i):
    letters = ""
    i += 1
    while i:
        i, rem = divmod(i - 1, 26)
        letters = chr(ord("A") + rem) + letters
    return letters


SHARED = []          # <si> items, in order; reset by build_xlsx
_SHARED_RAW = {}     # raw text or rich item -> its index in SHARED


def _shared_index(key):
    """The shared-string index of a raw text or a ready-made <si> item."""
    if key not in _SHARED_RAW:
        if key.startswith("<si>"):
            item = key
        else:
            item = (f'<si><t xml:space="preserve">{_esc(key)}</t></si>')
        _SHARED_RAW[key] = len(SHARED)
        SHARED.append(item)
    return _SHARED_RAW[key]


def _cell_xml(ref, spec):
    """One <c>; a bare value means a shared string."""
    if not isinstance(spec, dict):
        spec = {"s": spec}
    if "style" in spec:
        attrs = f' r="{ref}" s="{spec["style"]}"'
    else:
        attrs = f' r="{ref}"'
    if "f" in spec:                                   # formula cell
        attrs += ' t="str"' if spec.get("str") else ""
        body = f"<f>{_esc(spec['f'])}</f>"
        if "v" in spec:
            body += f"<v>{_esc(str(spec['v']))}</v>"
        return f"<c{attrs}>{body}</c>"
    if "s" in spec:                                   # shared string
        index = _shared_index(spec["s"])
        return f'<c{attrs} t="s"><v>{index}</v></c>'
    if "rich" in spec:                                # shared rich + phonetic
        runs = "".join(f'<r><t xml:space="preserve">{_esc(t)}</t></r>'
                       for t in spec["rich"])
        ph = (f'<rPh xml:space="preserve"><t>{_esc(spec["ph"])}</t></rPh>'
              if spec.get("ph") else "")
        base = (f'<t xml:space="preserve">{_esc(spec["text"])}</t>'
                if spec.get("rich_with_base") else "")
        item = f"<si>{runs}{ph}{base}</si>"
        return f'<c{attrs} t="s"><v>{_shared_index(item)}</v></c>'
    if "inline" in spec:                              # inline string
        return (f'<c{attrs} t="inlineStr"><is><t xml:space="preserve">'
                f'{_esc(spec["inline"])}</t></is></c>')
    if "n" in spec:                                   # numeric, raw text
        return f"<c{attrs}><v>{_esc(str(spec['n']))}</v></c>"
    if "b" in spec:                                   # boolean
        return f'<c{attrs} t="b"><v>{spec["b"]}</v></c>'
    if "e" in spec:                                   # error literal
        return f'<c{attrs} t="e"><v>{_esc(spec["e"])}</v></c>'
    raise AssertionError(f"unknown cell spec: {spec!r}")


def _sheet_xml(rows, merges=()):
    body = []
    for idx, row in enumerate(rows, start=1):
        hidden = ' hidden="1"' if isinstance(row, tuple) else ""
        cells = row[0] if isinstance(row, tuple) else row
        parts = []
        for ci, spec in enumerate(cells):
            if spec is None:
                continue
            parts.append(_cell_xml(f"{_col_letter(ci)}{idx}", spec))
        body.append(f'<row r="{idx}"{hidden}>{"".join(parts)}</row>')
    merge_xml = ""
    if merges:
        items = "".join(f'<mergeCell ref="{m}"/>' for m in merges)
        merge_xml = f'<mergeCells count="{len(merges)}">{items}</mergeCells>'
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<worksheet xmlns="{MAIN_NS}" xmlns:r="{R_NS}">'
            f'<sheetData>{"".join(body)}</sheetData>{merge_xml}'
            f'</worksheet>')


def build_xlsx(sheets, *, styles=None, date1904=False,
               workbook_xml=None, sheet_xml=None, main_ns=MAIN_NS,
               order=None, compress=None, mtime=(1980, 1, 1, 0, 0, 0),
               extra_entries=(), encrypt_parts=(), duplicate_part=None,
               drop_parts=(), merges=(), keep_shared=False):
    """Build a deterministic .xlsx byte string.

    sheets        list of row-lists (one per sheet); a row may be a tuple
                  (cells,) marking it hidden; a sheet may be a dict
                  {"rows": [...], "state": "hidden"}
    styles        {"xfs": [numFmtId per xf], "numFmts": {id: formatCode}}
    workbook_xml  raw override for xl/workbook.xml
    sheet_xml     dict {sheet index: raw override}
    main_ns       the namespace URI to declare (STRICT_NS for T96)
    order         explicit entry order (T99 shuffles it)
    compress      dict {name: ZIP_STORED/ZIP_DEFLATED}
    extra_entries [(name, bytes)] written after the standard parts
    encrypt_parts names whose zip entries carry the encrypted flag
    duplicate_part alternative spelling of xl/workbook.xml written twice
    drop_parts    names to omit
    """
    global SHARED
    if not keep_shared:      # sheet_xml overrides may pre-fill the pool
        SHARED = []
        _SHARED_RAW.clear()
    sheet_states = []
    sheet_entries = []
    for idx, rows in enumerate(sheets, start=1):
        state = ""
        if isinstance(rows, dict):
            state = rows.get("state", "")
            rows = rows["rows"]
        sheet_states.append(state)
        override = (sheet_xml or {}).get(idx)
        xml = override if override is not None else _sheet_xml(
            rows, merges=merges if idx == 1 else ())
        sheet_entries.append(xml)
    has_shared = bool(SHARED)
    custom = (styles or {}).get("numFmts", {})
    xfs = (styles or {}).get("xfs", [0])

    if workbook_xml is None:
        pr = '<workbookPr date1904="1"/>' if date1904 else ""
        sheet_tags = ""
        for idx, state in enumerate(sheet_states, start=1):
            st = f' state="{state}"' if state else ""
            sheet_tags += (f'<sheet name="Sheet{idx}" sheetId="{idx}" '
                           f'r:id="rId{idx}"{st}/>')
        workbook_xml = ('<?xml version="1.0" encoding="UTF-8" '
                        f'standalone="yes"?>\n'
                        f'<workbook xmlns="{main_ns}" xmlns:r="{R_NS}">{pr}'
                        f'<sheets>{sheet_tags}</sheets></workbook>')

    rel_items = []
    for idx in range(1, len(sheets) + 1):
        rel_items.append(f'<Relationship Id="rId{idx}" '
                         f'Type="{R_NS}/worksheet" '
                         f'Target="worksheets/sheet{idx}.xml"/>')
    rel_id = len(sheets) + 1
    if has_shared:
        rel_items.append(f'<Relationship Id="rId{rel_id}" '
                         f'Type="{R_NS}/sharedStrings" '
                         f'Target="sharedStrings.xml"/>')
        rel_id += 1
    if styles is not None:
        rel_items.append(f'<Relationship Id="rId{rel_id}" '
                         f'Type="{R_NS}/styles" Target="styles.xml"/>')
    rels_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
                f'<Relationships xmlns="{P_REL_NS}">{"".join(rel_items)}'
                f'</Relationships>')

    if isinstance(workbook_xml, bytes):
        wb_blob = workbook_xml
    else:
        wb_blob = workbook_xml.encode("utf-8")
    parts = {"xl/workbook.xml": wb_blob,
             "xl/_rels/workbook.xml.rels": rels_xml.encode("utf-8")}
    for idx, xml in enumerate(sheet_entries, start=1):
        parts[f"xl/worksheets/sheet{idx}.xml"] = xml.encode("utf-8")
    if has_shared:
        parts["xl/sharedStrings.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<sst xmlns="{MAIN_NS}" count="{len(SHARED)}" '
            f'uniqueCount="{len(SHARED)}">{"".join(SHARED)}</sst>'
        ).encode("utf-8")
    if styles is not None:
        numfmt_xml = ""
        if custom:
            items = "".join(f'<numFmt numFmtId="{k}" formatCode="{_esc(v)}"/>'
                            for k, v in custom.items())
            numfmt_xml = f'<numFmts count="{len(custom)}">{items}</numFmts>'
        xf_items = "".join(f'<xf numFmtId="{n}" fontId="0" fillId="0" '
                           f'borderId="0" applyNumberFormat="1"/>'
                           for n in xfs)
        parts["xl/styles.xml"] = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            f'<styleSheet xmlns="{MAIN_NS}">{numfmt_xml}'
            '<fonts count="1"><font><sz val="11"/>'
            '<name val="Calibri"/></font></fonts>'
            '<fills count="1"><fill><patternFill patternType="none"/>'
            '</fill></fills><borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" '
            'borderId="0"/></cellStyleXfs>'
            f'<cellXfs count="{len(xfs)}">{xf_items}</cellXfs>'
            '</styleSheet>').encode("utf-8")

    ct_items = ['<Default Extension="rels" ContentType='
                '"application/vnd.openxmlformats-package.relationships+xml"/>',
                '<Default Extension="xml" ContentType="application/xml"/>',
                '<Override PartName="/xl/workbook.xml" ContentType='
                '"application/vnd.openxmlformats-officedocument.'
                'spreadsheetml.sheet.main+xml"/>']
    for idx in range(1, len(sheets) + 1):
        ct_items.append(f'<Override PartName="/xl/worksheets/sheet{idx}.xml" '
                        'ContentType="application/vnd.openxmlformats-'
                        'officedocument.spreadsheetml.worksheet+xml"/>')
    parts["[Content_Types].xml"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Types xmlns="{P_TYPE_NS}">{"".join(ct_items)}</Types>'
    ).encode("utf-8")
    parts["_rels/.rels"] = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        f'<Relationships xmlns="{P_REL_NS}"><Relationship Id="rId1" '
        f'Type="{R_NS}/officeDocument" Target="xl/workbook.xml"/>'
        '</Relationships>').encode("utf-8")

    for name in drop_parts:
        parts.pop(name, None)
    for name, blob in extra_entries:
        parts[name] = blob

    if order is None:
        names = [n for n in ("[Content_Types].xml", "_rels/.rels",
                             "xl/workbook.xml",
                             "xl/_rels/workbook.xml.rels") if n in parts]
        names += [n for n in parts if n not in names]
    else:
        names = order
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zi = zipfile.ZipInfo(name, date_time=mtime)
            zi.compress_type = (compress or {}).get(name, zipfile.ZIP_DEFLATED)
            zi.external_attr = 0o600 << 16
            zf.writestr(zi, parts[name])
        if duplicate_part:
            zi = zipfile.ZipInfo(duplicate_part, date_time=mtime)
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o600 << 16
            zf.writestr(zi, parts["xl/workbook.xml"])
    data = buf.getvalue()
    for name in encrypt_parts:            # zipfile resets flag_bits; patch
        data = _set_entry_flag(data, name, 0x1)   # both headers by hand
    return data


def _set_entry_flag(data: bytes, target: str, mask: int) -> bytes:
    """OR a general-purpose bit into one entry's local + central headers."""
    buf = bytearray(data)
    for sig, off_name_len, off_name, off_flag in (
            (b"PK\x03\x04", 26, 30, 6), (b"PK\x01\x02", 28, 46, 8)):
        i = 0
        while True:
            i = buf.find(sig, i)
            if i < 0:
                break
            nlen = int.from_bytes(buf[i + off_name_len:i + off_name_len + 2],
                                  "little")
            name = bytes(buf[i + off_name:i + off_name + nlen])
            if name == target.encode("utf-8"):
                buf[i + off_flag] |= mask
            i += 4
    return bytes(buf)


def csv_twin(rows):
    buf = io.StringIO(newline="")
    for row in rows:
        buf.write(",".join(row) + "\n")
    return buf.getvalue().encode("utf-8")


def strip_scan_vars(html_bytes):
    """scan pages carry the input file name and its SHA-256; drop both."""
    text = html_bytes.decode("utf-8")
    text = re.sub(r"[0-9a-f]{64}", "", text)
    text = text.replace(".csv", "").replace(".xlsx", "")
    return text


class XlsxCase(unittest.TestCase):
    def write_workbook(self, tmp, data, name="t.xlsx"):
        path = os.path.join(tmp, name)
        with open(path, "wb") as fh:
            fh.write(data)
        return path

    def run_keep_all(self, path, columns, tmp, tag="o"):
        cfg = keep_all_cfg(os.path.join(tmp, f"cfg_{tag}.json"), columns)
        dest = os.path.join(tmp, f"out_{tag}.csv")
        code, _, err = cli(["run", path, "-c", cfg, "-o", dest, "--quiet"])
        blob = open(dest, "rb").read() if os.path.exists(dest) else b""
        return code, blob, err


class T89XlsxReadsAsItsCsvTwin(XlsxCase):
    def test_all_subcommands_match_the_csv_twin(self):
        rows = [["name", "zip", "age"],
                ["Takahashi Hina", "1500052", "40"],
                ["Kobayashi Haruto", "1500053", "40"]]
        cfg = {"k": 2, "columns": {
            "name": {"role": "keep"},
            "zip": {"role": "qi", "type": "prefix", "length": 4},
            "age": {"role": "qi", "type": "numeric", "widths": [5, 10, 20]},
        }}
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows]))
            csv = os.path.join(d, "t.csv")
            with open(csv, "wb") as fh:
                fh.write(csv_twin(rows))
            cfg_path = os.path.join(d, "cfg.json")
            with open(cfg_path, "w", encoding="utf-8") as fh:
                fh.write(json.dumps(cfg))
            self.assertEqual(cli(["inspect", xlsx]), cli(["inspect", csv]))
            outs = {}
            for tag, src in (("xlsx", xlsx), ("csv", csv)):
                dest = os.path.join(d, f"o_{tag}.csv")
                code, _, err = cli(["run", src, "-c", cfg_path, "-o", dest,
                                    "--quiet"])
                self.assertEqual(code, 0, tag)
                outs[tag] = sha256_file(dest)
                _, _, perr = cli(["plan", src, "-c", cfg_path])
                _, _, aerr = cli(["audit", src, "-c", cfg_path])
                outs[tag + "_p"] = perr
                outs[tag + "_a"] = aerr
            self.assertEqual(outs["xlsx"], outs["csv"])
            self.assertEqual(outs["xlsx_p"], outs["csv_p"])
            self.assertEqual(outs["xlsx_a"], outs["csv_a"])
            htmls = {}
            for tag, src in (("xlsx", xlsx), ("csv", csv)):
                html = os.path.join(d, f"s_{tag}.html")
                code, _, _ = cli(["scan", src, "--lang", "en", "-o", html])
                self.assertEqual(code, 0, tag)
                htmls[tag] = strip_scan_vars(open(html, "rb").read())
            self.assertEqual(htmls["xlsx"], htmls["csv"])


class T90Strings(XlsxCase):
    def test_shared_inline_rich_without_furigana(self):
        rows = [["grp", "name", "note"],
                ["g", "Takahashi", {"s": "shared value"}],
                ["g", {"rich": ["head", "tail"], "rich_with_base": False,
                       "ph": "フリガナよみ", "text": "headtail"},
                 {"inline": "inline value"}],
                ["g", {"rich": ["base"], "rich_with_base": True,
                       "ph": "きほんよみ", "text": "base"},
                 {"s": "plain"}]]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows]))
            code, blob, err = self.run_keep_all(
                xlsx, ["grp", "name", "note"], d)
            self.assertEqual(code, 0)
            data = blob.decode("utf-8")
            self.assertIn("shared value", data)
            self.assertIn("inline value", data)
            self.assertIn("headtail", data)
            self.assertIn("base", data)
            self.assertIn("plain", data)
            self.assertNotIn("フリガナよみ", data)   # furigana is gone
            self.assertNotIn("きほんよみ", data)


class T91NumbersBoolsErrorsFormulas(XlsxCase):
    def test_raw_numbers_bools_errors_and_formula_caches(self):
        rows = [["grp", "num", "flag", "err", "formula", "zero", "nocache"],
                ["g", {"n": "0042"}, {"b": "1"}, {"e": "#N/A"},
                 {"f": "SUM(B2:B2)", "v": "42", "str": True},
                 {"s": "0123"}, {"f": "1/0"}],
                ["g", {"n": "3.1400000000000001"}, {"b": "0"},
                 {"e": "#VALUE!"},
                 {"f": "B2*2", "v": "84", "str": True},
                 {"s": "x"}, {"f": "2/0"}]]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows]))
            code, blob, err = self.run_keep_all(xlsx, [
                "grp", "num", "flag", "err", "formula", "zero",
                "nocache"], d)
            self.assertEqual(code, 0)
            data = blob.decode("utf-8")
            self.assertIn("0042", data)          # raw text, not 42
            self.assertIn("3.1400000000000001", data)
            self.assertIn("TRUE", data)
            self.assertIn("FALSE", data)
            self.assertIn("#N/A", data)
            self.assertIn("#VALUE!", data)
            self.assertIn(",42,", data)          # cached values
            self.assertIn(",84,", data)
            self.assertIn("0123", data)          # leading zeros survive
            self.assertIn("formula cells have no cached value",
                          err.decode())
            # the nocache cells land empty (last column of each row)
            self.assertIn("g,0042,TRUE,#N/A,42,0123,\n", data)
            self.assertIn("g,3.1400000000000001,FALSE,#VALUE!,84,x,\n",
                          data)


class T92Dates(XlsxCase):
    def test_builtin_and_custom_formats_1900_and_1904(self):
        rows = [["grp", "d14", "custom", "with_time", "plain"],
                ["g", {"n": "45000", "style": 1},
                 {"n": "45000", "style": 2},
                 {"n": "45000.25", "style": 3}, {"n": "45000"}],
                ["g", {"n": "1", "style": 1}, {"n": "59", "style": 2},
                 {"n": "44927.75", "style": 3}, {"n": "1"}]]
        styles = {"xfs": [0, 14, 164, 22], "numFmts": {"164": "yyyy/m/d"}}
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows], styles=styles))
            code, blob, err = self.run_keep_all(
                xlsx, ["grp", "d14", "custom", "with_time", "plain"], d)
            self.assertEqual(code, 0)
            data = blob.decode("utf-8")
            self.assertIn("2023-03-15", data)       # serial 45000
            self.assertIn("2023-03-15 06:00:00", data)
            self.assertIn("2023-01-01 18:00:00", data)   # 44927.75
            self.assertIn("1900-01-01", data)       # serial 1
            self.assertIn("1900-02-28", data)       # serial 59
            self.assertIn(",45000\n", data)         # plain number stays raw
            self.assertIn(",1\n", data)

    def test_1904_system(self):
        rows = [["grp", "d"], ["g", {"n": "1", "style": 1}],
                ["g", {"n": "0", "style": 1}]]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(
                d, build_xlsx([rows], styles={"xfs": [0, 14]}, date1904=True))
            code, blob, _ = self.run_keep_all(xlsx, ["grp", "d"], d)
            self.assertEqual(code, 0)
            data = blob.decode("utf-8")
            self.assertIn("1904-01-02", data)       # serial 1
            self.assertIn("1904-01-01", data)       # serial 0

    def test_unconvertible_values_stop_with_unsupported_format(self):
        for serial in ("60", "-1", "5000000"):
            rows = [["d"], [{"n": serial, "style": 1}]]
            with tempfile.TemporaryDirectory() as d:
                xlsx = self.write_workbook(
                    d, build_xlsx([rows], styles={"xfs": [0, 14]}))
                code, _, err = cli(["inspect", xlsx])
                self.assertEqual(code, 1, serial)
                self.assertEqual(err, b"error: unsupported_format\n", serial)


class T93SheetSelection(XlsxCase):
    SHEETS = [{"rows": [["grp", "mark"], ["g", "hidden-first"],
                        ["g", "filler-one"]],
               "state": "hidden"},
              {"rows": [["grp", "col"], ["g", "visible-second"],
                        ["g", "filler-two"]]},
              {"rows": [["grp", "col"], ["g", "visible-third"],
                        ["g", "filler-three"]]}]

    def test_default_picks_the_first_visible_sheet(self):
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx(self.SHEETS))
            code, blob, err = self.run_keep_all(
                xlsx, ["grp", "col"], d, tag="def")
            self.assertEqual(code, 0)
            self.assertIn(b"visible-second", blob)
            self.assertNotIn(b"hidden-first", blob)
            self.assertIn(b"input workbook: 3 sheets, using sheet 2", err)

    def test_sheet_by_name_and_index(self):
        sheets = [{"rows": [["grp", "a"], ["g", "first"],
                            ["g", "more-first"]]},
                  {"rows": [["grp", "a"], ["g", "second"],
                            ["g", "more-second"]],
                   "state": "veryHidden"}]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx(sheets))
            code, _, err = cli(["inspect", xlsx, "--sheet", "Sheet2"])
            self.assertEqual(code, 0)
            self.assertIn(b"using sheet 2 (hidden)", err)
            code, _, err = cli(["inspect", xlsx, "--sheet", "2"])
            self.assertEqual(code, 0)
            self.assertIn(b"using sheet 2 (hidden)", err)
            code, _, err = cli(["inspect", xlsx, "--sheet", "Sheet1"])
            self.assertEqual(code, 0)
            self.assertNotIn(b"(hidden)", err)

    def test_by_name_reads_the_hidden_sheet_values(self):
        sheets = [{"rows": [["grp", "a"], ["g", "first"],
                            ["g", "more-first"]]},
                  {"rows": [["grp", "a"], ["g", "second"],
                            ["g", "more-second"]],
                   "state": "veryHidden"}]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx(sheets))
            cfg = keep_all_cfg(os.path.join(d, "cfg.json"), ["grp", "a"])
            dest = os.path.join(d, "out.csv")
            code, _, _ = cli(["run", xlsx, "-c", cfg, "-o", dest,
                              "--sheet", "Sheet2", "--quiet"])
            self.assertEqual(code, 0)
            self.assertIn(b"second", open(dest, "rb").read())

    def test_missing_sheet_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([[["a"], ["x"]]]))
            for name in ("Nope", "9", "0"):
                code, _, err = cli(["inspect", xlsx, "--sheet", name])
                self.assertEqual(code, 2, name)
                self.assertIn(b"no such sheet", err, name)

    def test_sheet_applies_to_xlsx_only(self):
        code, _, err = cli(["inspect", PEOPLE, "--sheet", "1"])
        self.assertEqual(code, 2)
        self.assertIn(b"--sheet applies to xlsx only", err)

    def test_only_hidden_workbook_is_refused(self):
        sheets = [{"rows": [["a"], ["h1"]], "state": "hidden"}]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx(sheets))
            code, _, err = cli(["inspect", xlsx])
            self.assertEqual(code, 2)
            self.assertIn(b"no visible sheet", err)


class T94SafeReadingRefusals(XlsxCase):
    def read_with_limits(self, tmp, data, **limits):
        """Run inspect on an xlsx with overridden ReadLimits defaults."""
        from sieve_crowd import xlsx_reader
        orig = xlsx_reader.ReadLimits
        ns = {"__annotations__": dict(getattr(orig, "__annotations__", {}))}
        ns.update(limits)
        narrowed = dataclasses.dataclass(
            type("Narrow", (orig,), ns), init=True)
        xlsx_reader.ReadLimits = narrowed
        try:
            xlsx_path = self.write_workbook(tmp, data)
            return cli(["inspect", xlsx_path])
        finally:
            xlsx_reader.ReadLimits = orig

    def assert_refused(self, got, code):
        got_code, _, err = got
        self.assertEqual(got_code, 1)
        self.assertEqual(err, f"error: {code}\n".encode())

    def test_each_refusal_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            data = build_xlsx([[["a"], ["x"]]])
            # DOCTYPE (+ ENTITY) in the workbook part
            bad_wb = (b'<?xml version="1.0"?>\n<!DOCTYPE workbook [\n'
                      b'<!ENTITY a "b">\n]>\n'
                      b'<workbook xmlns="' + MAIN_NS.encode() + b'"/>')
            self.assert_refused(
                self.read_with_limits(tmp, build_xlsx(
                    [[["a"], ["x"]]], workbook_xml=bad_wb)),
                "doctype_not_allowed")
            # encryption flag on the main part
            self.assert_refused(
                self.read_with_limits(tmp, build_xlsx(
                    [[["a"], ["x"]]], encrypt_parts=("xl/workbook.xml",))),
                "encrypted")
            # duplicate part (case-insensitive)
            self.assert_refused(
                self.read_with_limits(tmp, build_xlsx(
                    [[["a"], ["x"]]], duplicate_part="XL/WORKBOOK.XML")),
                "duplicate_part")
            # missing main part
            self.assert_refused(
                self.read_with_limits(tmp, build_xlsx(
                    [[["a"], ["x"]]], drop_parts=("xl/workbook.xml",))),
                "main_part_missing")
            # malformed XML in the sheet part
            self.assert_refused(
                self.read_with_limits(tmp, build_xlsx(
                    [[["a"], ["x"]]],
                    sheet_xml={1: '<worksheet xmlns="' + MAIN_NS + '">'
                                   "<sheetData><row r='1'>"})),
                "malformed_xml")
            # entry flood
            flood = [(f"xl/worksheets/sheet{i}.xml", b"<x/>")
                     for i in range(2, 12)]
            self.assert_refused(
                self.read_with_limits(tmp, build_xlsx(
                    [[["a"], ["x"]]], extra_entries=flood), max_entries=10),
                "too_many_entries")
            # oversized part (declared and actual)
            self.assert_refused(
                self.read_with_limits(tmp, data, max_part_bytes=64),
                "part_too_large")
            # oversized file
            self.assert_refused(
                self.read_with_limits(tmp, data, max_file_bytes=16),
                "file_too_large")
            # total budget
            self.assert_refused(
                self.read_with_limits(tmp, data, max_total_bytes=64),
                "total_too_large")
            # element flood
            self.assert_refused(
                self.read_with_limits(tmp, data, max_elements=4),
                "too_many_elements")

    def test_not_a_zip_at_all(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "t.xlsx")
            with open(src, "wb") as fh:
                fh.write(b"this is not a zip file at all")
            code, _, err = cli(["inspect", src])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: unsupported_format\n")

    def test_nothing_is_written_on_refusal(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "t.xlsx")
            with open(src, "wb") as fh:
                fh.write(b"not a zip")
            dest = os.path.join(d, "out.csv")
            code, _, _ = cli(["run", src, "-c", CONFIG, "-o", dest,
                              "--quiet"])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(dest))

    def test_fifo_is_not_a_regular_file(self):
        with tempfile.TemporaryDirectory() as d:
            fifo = os.path.join(d, "pipe.xlsx")
            os.mkfifo(fifo)
            code, _, err = cli(["inspect", fifo])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: not_regular_file\n")

    def test_directory_is_not_a_regular_file(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "dir.xlsx")
            os.mkdir(folder)
            code, _, err = cli(["inspect", folder])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: not_regular_file\n")


class T95SequentialBomb(XlsxCase):
    def test_expansion_is_bounded_while_reading(self):
        # the sheet part expands to 128 MiB of spaces; the reader must stop
        # inside a 1 MiB budget while streaming it, never materialising it
        space_blob = b" " * (128 << 20)
        bomb_sheet = (b'<worksheet xmlns="' + MAIN_NS.encode() +
                      b'"><sheetData><row>' + space_blob +
                      b"</row></sheetData></worksheet>")
        del space_blob
        with tempfile.TemporaryDirectory() as tmp:
            data = build_xlsx([[["a"], ["x"]]], sheet_xml={1: None},
                              drop_parts=("xl/worksheets/sheet1.xml",),
                              extra_entries=[("xl/worksheets/sheet1.xml",
                                              bomb_sheet)])
            from sieve_crowd import xlsx_reader
            orig = xlsx_reader.ReadLimits
            ns = {"__annotations__": dict(orig.__annotations__),
                  "max_total_bytes": 1 << 20,
                  "max_part_bytes": 1 << 29}
            narrowed = dataclasses.dataclass(type("Narrow", (orig,), ns))
            xlsx_reader.ReadLimits = narrowed
            tracemalloc.start()
            try:
                xlsx_path = self.write_workbook(tmp, data)
                started = time.monotonic()
                code, _, err = cli(["inspect", xlsx_path])
                elapsed = time.monotonic() - started
            finally:
                xlsx_reader.ReadLimits = orig
                _, peak = tracemalloc.get_traced_memory()
                tracemalloc.stop()
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: total_too_large\n")
            self.assertLess(elapsed, 30.0)
            self.assertLess(peak, 32 * 1024 * 1024)


class T96Namespace(XlsxCase):
    def test_strict_namespace_is_refused_by_uri(self):
        strict_wb = ('<?xml version="1.0" encoding="UTF-8"?>\n'
                     f'<workbook xmlns="{STRICT_NS}" xmlns:r="{R_NS}">'
                     '<sheets><sheet name="Sheet1" sheetId="1" '
                     'r:id="rId1"/></sheets></workbook>')
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx(
                [[["a"], ["x"]]], workbook_xml=strict_wb))
            code, _, err = cli(["inspect", xlsx])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: unsupported_namespace\n")
            # a strict-URI sheet inside a standard workbook is refused too
            strict_sheet = _sheet_xml([["a"], ["x"]]).replace(
                MAIN_NS, STRICT_NS)
            xlsx = self.write_workbook(d, build_xlsx(
                [[["a"], ["x"]]], sheet_xml={1: strict_sheet}), name="t2.xlsx")
            code, _, err = cli(["inspect", xlsx])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: unsupported_namespace\n")

    def test_renamed_prefix_with_standard_uri_reads(self):
        sheet = _sheet_xml([["grp", "a"], ["g", "x"], ["g", "y"]])
        for old, new in (("<worksheet ", "<x:worksheet "),
                         ("</worksheet>", "</x:worksheet>"),
                         (f'xmlns="{MAIN_NS}"', f'xmlns:x="{MAIN_NS}"'),
                         ("<sheetData>", "<x:sheetData>"),
                         ("</sheetData>", "</x:sheetData>"),
                         ("<row ", "<x:row "), ("</row>", "</x:row>"),
                         ("<c ", "<x:c "), ("</c>", "</x:c>"),
                         ("<v>", "<x:v>"), ("</v>", "</x:v>")):
            sheet = sheet.replace(old, new)
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx(
                [[["grp", "a"], ["g", "x"], ["g", "y"]]],
                sheet_xml={1: sheet}, keep_shared=True))
            code, blob, _ = self.run_keep_all(xlsx, ["grp", "a"], d)
            self.assertEqual(code, 0)
            self.assertIn(b"a", blob)
            self.assertIn(b"x", blob)


class T97HeaderParity(XlsxCase):
    CASES = {
        "empty_first_row": [[]],
        "empty_header_cell": [[["", "b"], ["1", "2"]]],
        "duplicate_header": [[["a", "a"], ["1", "2"]]],
        "long_row": [[["a", "b"], ["1", "2", "3"]]],
    }

    def test_same_exit_code_and_message_as_csv(self):
        for tag, rows in self.CASES.items():
            with tempfile.TemporaryDirectory() as d:
                xlsx = self.write_workbook(d, build_xlsx(rows))
                csv = os.path.join(d, "t.csv")
                with open(csv, "wb") as fh:
                    fh.write(csv_twin(rows[0]))
                self.assertEqual(cli(["inspect", xlsx]),
                                 cli(["inspect", csv]), tag)

    def test_short_rows_are_padded_to_the_header_width(self):
        # design 3.3: "rows are aligned to the header width (shortfalls are
        # filled with empties)" -- an .xlsx row ending early is sparse
        # cells, not a malformed line, so only the long direction keeps
        # the csvio mismatch error (reported as a design note)
        rows = [["a", "b"], ["1"], ["1", "3"]]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows]))
            code, out, err = cli(["inspect", xlsx])
            self.assertEqual(code, 0, err)
            code2, blob, _ = self.run_keep_all(xlsx, ["a", "b"], d)
            self.assertEqual(code2, 0)
            self.assertIn(b"1,\n", blob)      # the short row padded
            self.assertIn(b"1,3", blob)

    def test_trailing_empty_rows_are_dropped(self):
        rows = [["a", "b"], ["1", "2"], [], [], []]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows]))
            code, out, err = cli(["inspect", xlsx])
            self.assertEqual(code, 0)
            self.assertIn(b"records: 1", out)
            csv = os.path.join(d, "t.csv")
            with open(csv, "wb") as fh:
                fh.write(csv_twin([["a", "b"], ["1", "2"]]))
            self.assertEqual(cli(["inspect", csv]), (code, out, err))


class T98HiddenRowsColsAndMerges(XlsxCase):
    def test_hidden_rows_are_data(self):
        rows = [["grp", "a", "b"], ["g", "1", "2"],
                (["g", "3", "4"],)]          # row 3 hidden
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows]))
            code, blob, _ = self.run_keep_all(
                xlsx, ["grp", "a", "b"], d)
            self.assertEqual(code, 0)
            self.assertIn(b"3,4", blob)
            code, out, _ = cli(["inspect", xlsx])
            self.assertIn(b"records: 2", out)

    def test_hidden_cols_are_data(self):
        rows = [["a", "b"], ["1", "2"], ["1", "3"]]
        cols = ('<cols><col min="2" max="2" hidden="1" width="10" '
                'customWidth="1"/></cols>')
        sheet = _sheet_xml(rows).replace("<sheetData>",
                                         cols + "<sheetData>")
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(
                d, build_xlsx([rows], sheet_xml={1: sheet},
                              keep_shared=True))
            code, blob, _ = self.run_keep_all(xlsx, ["a", "b"], d)
            self.assertEqual(code, 0)
            self.assertIn(b"1,2", blob)

    def test_merged_cell_keeps_the_top_left_value(self):
        rows = [["grp", "b", "c"], ["g", "1", "2"], ["g", "top", ""], []]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows],
                                                     merges=("B3:C3",)))
            code, blob, _ = self.run_keep_all(
                xlsx, ["grp", "b", "c"], d)
            self.assertEqual(code, 0)
            self.assertIn(b"top", blob)
            code, out, _ = cli(["inspect", xlsx])
            self.assertIn(b"records: 2", out)   # trailing empties dropped

    def test_right_and_bottom_margins_are_not_the_table(self):
        rows = [["a", "b"], ["1", "2"], ["3", "4"]]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx([rows]))
            code, out, _ = cli(["inspect", xlsx])
            self.assertEqual(code, 0)
            self.assertIn(b"records: 2", out)


class T99DeterministicAcrossZipLayouts(XlsxCase):
    def test_order_compression_timestamps_do_not_matter(self):
        rows = [["grp", "name", "age"], ["g", "Takahashi Hina", "40"],
                ["g", "Kobayashi Haruto", "40"]]
        plain = build_xlsx([rows])
        shuffled = build_xlsx(
            [rows], order=["xl/_rels/workbook.xml.rels",
                           "xl/worksheets/sheet1.xml", "xl/workbook.xml",
                           "xl/sharedStrings.xml", "[Content_Types].xml",
                           "_rels/.rels"])
        stored = build_xlsx([rows], mtime=(2020, 5, 17, 13, 44, 7),
                            compress={"xl/worksheets/sheet1.xml":
                                      zipfile.ZIP_STORED})
        self.assertNotEqual(plain, shuffled)
        self.assertNotEqual(plain, stored)
        with tempfile.TemporaryDirectory() as d:
            cfg = keep_all_cfg(os.path.join(d, "cfg.json"),
                               ["grp", "name", "age"])
            outs = []
            for tag, data in (("a", plain), ("b", shuffled), ("c", stored)):
                xlsx = self.write_workbook(d, data, name=f"t{tag}.xlsx")
                outs.append(cli(["inspect", xlsx]))
                dest = os.path.join(d, f"o{tag}.csv")
                code, _, _ = cli(["run", xlsx, "-c", cfg, "-o", dest,
                                  "--quiet"])
                self.assertEqual(code, 0)
                with open(dest, "rb") as fh:
                    outs.append((code, fh.read(), b""))
            for other in (2, 4):
                self.assertEqual(outs[0], outs[other])
            self.assertEqual(outs[1], outs[3])
            self.assertEqual(outs[1], outs[5])


class T100OtherFormatsAreRefused(unittest.TestCase):
    def test_xls_and_xlsm(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("t.xls", "t.xlsm"):
                src = os.path.join(d, name)
                with open(src, "wb") as fh:
                    fh.write(build_xlsx([[["a"], ["x"]]]))
                code, _, err = cli(["inspect", src])
                self.assertEqual(code, 1, name)
                self.assertEqual(err, b"error: unsupported_format\n", name)

    def test_directory_with_xlsx_suffix_is_not_a_regular_file(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "dir.xlsx")
            os.mkdir(folder)
            code, _, err = cli(["inspect", folder])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: not_regular_file\n")


class T101SafetyProof(XlsxCase):
    STDLIB_OK = {"io", "csv", "json", "enum", "zipfile", "xml", "re", "os",
                 "posixpath", "stat", "datetime", "dataclasses", "typing",
                 "__future__", "unicodedata", "zlib"}

    def test_input_layer_imports_the_standard_library_only(self):
        seen = {}
        for mod in ("tabular", "xlsx_reader"):
            path = os.path.join(REPO, "sieve_crowd", mod + ".py")
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        seen.setdefault(alias.name.split(".")[0],
                                        set()).add(mod)
                elif isinstance(node, ast.ImportFrom):
                    if node.level or node.module is None:
                        continue          # relative import: package-internal
                    seen.setdefault(node.module.split(".")[0],
                                    set()).add(mod)
        self.assertTrue(seen)
        for top, users in seen.items():
            if top == "sieve_crowd" or top in self.STDLIB_OK:
                continue
            raise AssertionError(f"non-stdlib import {top!r} in {users}")

    def test_markers_never_leak(self):
        sheets = [{"rows": [["grp", "name", "note"],
                            ["g", "Takahashi",
                             {"rich": ["kanji"], "rich_with_base": True,
                              "ph": "MARKER_FURIGANA", "text": "kanji"}],
                            ["g", "u", "v"]]},
                  {"rows": [["h"], ["MARKER_HIDDEN"]], "state": "hidden"},
                  {"rows": [["u"], ["MARKER_UNUSED"]]}]
        with tempfile.TemporaryDirectory() as d:
            xlsx = self.write_workbook(d, build_xlsx(sheets))
            markers = (b"MARKER_FURIGANA", b"MARKER_HIDDEN",
                       b"MARKER_UNUSED")
            outputs = {}
            code, out, err = cli(["inspect", xlsx, "--sheet", "Sheet1"])
            self.assertEqual(code, 0)
            outputs["inspect"] = out + err
            cfg = keep_all_cfg(os.path.join(d, "cfg.json"),
                               ["grp", "name", "note"])
            dest = os.path.join(d, "o.csv")
            code, out, err = cli(["run", xlsx, "-c", cfg, "-o", dest,
                                  "--quiet"])
            self.assertEqual(code, 0)
            with open(dest, "rb") as fh:
                outputs["run"] = fh.read() + err
            html = os.path.join(d, "s.html")
            code, out, err = cli(["scan", xlsx, "--lang", "en", "-o", html])
            self.assertEqual(code, 0)
            with open(html, "rb") as fh:
                outputs["scan"] = fh.read() + err
            code, out, err = cli(["plan", xlsx, "-c", cfg])
            self.assertEqual(code, 0)
            outputs["plan"] = out + err
            code, out, err = cli(["audit", xlsx, "-c", cfg])
            self.assertEqual(code, 0)
            outputs["audit"] = out + err
            for where, blob in outputs.items():
                for marker in markers:
                    self.assertNotIn(marker, blob, (where, marker))


if __name__ == "__main__":
    unittest.main()
