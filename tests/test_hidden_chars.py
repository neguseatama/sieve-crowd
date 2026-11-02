"""invisible-character observation tests (T43-T45, v0.7.1).

T43 pins the scan itself (per column: rows / chars / kinds, the four kind
names, id/drop counted but never warned, leading BOM never counted).
T44 pins the plan integration: the exact stderr lines in both languages, the
findings.warnings elements, the hidden_chars_summary key, --no-hidden-chars.
T45 pins determinism (row/column permutation -> byte-identical findings JSON)
and the sentinel rule: no cell value and no code point ever appears in any
output — kind names and counts only.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# memo(keep): zero_width | city(qi): variation_selector | dx(sensitive): tag
# note(id): zero_width (counted, never warned) | junk(drop): clean
# row 2 gives dx a bidi control too (two kinds in one column).
CSV = ("memo,city,dx,note,junk\n"
       "ZX\u200BQV1,TY\uFE0F2,WQ\U000E00013,KQ\uFEFF4,PQ5\n"
       "plain,,x\u202E6,,\n").encode()
CFG = json.dumps({"k": 3, "columns": {
    "memo": {"role": "keep"},
    "city": {"role": "qi", "type": "exact"},
    "dx": {"role": "sensitive"},
    "note": {"role": "id"},
    "junk": {"role": "drop"}}}, ensure_ascii=False).encode()

EXPECTED_WARNINGS = [
    {"code": "hidden_chars", "column": "city", "declared_role": "qi",
     "rows": 1, "chars": 1, "kinds": ["variation_selector"]},
    {"code": "hidden_chars", "column": "dx", "declared_role": "sensitive",
     "rows": 2, "chars": 2, "kinds": ["bidi_control", "tag"]},
    {"code": "hidden_chars", "column": "memo", "declared_role": "keep",
     "rows": 1, "chars": 1, "kinds": ["zero_width"]},
]

EN_LINES = [
    '  - hidden_chars: "city" (declared qi): 1 row(s) contain invisible characters '
    "(variation_selector); values that look identical form separate groups",
    '  - hidden_chars: "dx" (declared sensitive): 2 row(s) contain invisible characters '
    "(bidi_control, tag); they stay in the output",
    '  - hidden_chars: "memo" (declared keep): 1 row(s) contain invisible characters '
    "(zero_width); they stay in the output",
]

JA_LINES = [
    "  - hidden_chars: 「city」（宣言 qi）: 1 行に不可視文字（variation_selector）が含まれています。"
    "見た目が同じ値が別のグループに分かれます",
    "  - hidden_chars: 「dx」（宣言 sensitive）: 2 行に不可視文字（bidi_control, tag）が含まれています。"
    "出力にそのまま残ります",
    "  - hidden_chars: 「memo」（宣言 keep）: 1 行に不可視文字（zero_width）が含まれています。"
    "出力にそのまま残ります",
]


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def _plan(d, csv_data, cfg_data, *extra):
    src = os.path.join(d, "in.csv")
    with open(src, "wb") as fh:
        fh.write(csv_data)
    cfg = os.path.join(d, "c.json")
    with open(cfg, "wb") as fh:
        fh.write(cfg_data)
    fj = os.path.join(d, "f.json")
    if os.path.exists(fj):
        os.unlink(fj)
    rc, out, err = call("plan", src, "-c", cfg, "--findings-json", fj, *extra)
    findings, raw = None, ""
    if os.path.exists(fj):
        with open(fj, "rb") as fh:
            raw = fh.read()
        findings = json.loads(raw.decode("utf-8"))
    return rc, out, err, findings, raw, fj


class T43HiddenScan(unittest.TestCase):
    """T43: the per-column scan, the four kinds, roles, the BOM."""

    def test_per_column_rows_chars_kinds(self):
        from sieve_crowd import hidden_chars
        from sieve_crowd.csvio import read_table
        header, rows = read_table(CSV)
        roles = {"memo": "keep", "city": "qi", "dx": "sensitive",
                 "note": "id", "junk": "drop"}
        warnings, summary = hidden_chars.analyze(header, rows, roles)
        self.assertEqual(warnings, EXPECTED_WARNINGS)
        self.assertEqual(summary, {"columns_checked": 5, "columns_flagged": 3})

    def test_the_four_kinds_are_distinguished(self):
        from sieve_crowd import hidden_chars
        from sieve_crowd.csvio import read_table
        header, rows = read_table(
            ("a,b,c,d\n"
             "1\u200Bx,2\u202Ey,3\U000E0001z,4\uFE0Fw\n").encode())
        roles = {"a": "keep", "b": "keep", "c": "keep", "d": "keep"}
        warnings, _ = hidden_chars.analyze(header, rows, roles)
        got = {w["column"]: (w["rows"], w["chars"], w["kinds"]) for w in warnings}
        self.assertEqual(got["a"], (1, 1, ["zero_width"]))
        self.assertEqual(got["b"], (1, 1, ["bidi_control"]))
        self.assertEqual(got["c"], (1, 1, ["tag"]))
        self.assertEqual(got["d"], (1, 1, ["variation_selector"]))

    def test_leading_bom_is_never_counted(self):
        from sieve_crowd import hidden_chars
        from sieve_crowd.csvio import read_table
        header, rows = read_table(CSV)
        base = hidden_chars.analyze(header, rows, {"memo": "keep", "city": "qi",
                                                  "dx": "sensitive", "note": "id",
                                                  "junk": "drop"})
        with_bom = hidden_chars.analyze(
            *read_table(b"\xef\xbb\xbf" + CSV),
            {"memo": "keep", "city": "qi", "dx": "sensitive", "note": "id",
             "junk": "drop"})
        self.assertEqual(with_bom, base)


class T44PlanIntegration(unittest.TestCase):
    """T44: warning lines (en/ja), findings elements, summary, --no-hidden-chars."""

    def test_stderr_lines_and_findings_in_english(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f, raw, fj = _plan(d, CSV, CFG)
            self.assertEqual(rc, 0, err)
            for line in EN_LINES:
                self.assertIn(line, err)
            self.assertEqual([w for w in f["warnings"]
                              if w["code"] == "hidden_chars"], EXPECTED_WARNINGS)
            self.assertEqual(f["hidden_chars_summary"],
                             {"columns_checked": 5, "columns_flagged": 3})

    def test_stderr_lines_in_japanese(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f, raw, fj = _plan(d, CSV, CFG, "--lang", "ja")
            self.assertEqual(rc, 0, err)
            for line in JA_LINES:
                self.assertIn(line, err)

    def test_findings_shape_without_packs_or_derived(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f, raw, fj = _plan(d, CSV, CFG,
                                             "--no-builtin-hints", "--no-derived")
            self.assertEqual(rc, 0, err)
            self.assertEqual(sorted(f), ["columns", "hidden_chars_summary",
                                         "pack_info", "packs", "warnings"])
            self.assertEqual(f["packs"], [])
            self.assertEqual(f["warnings"], EXPECTED_WARNINGS)
            self.assertEqual(f["hidden_chars_summary"],
                             {"columns_checked": 5, "columns_flagged": 3})

    def test_no_hidden_chars_disables_everything(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f, raw, fj = _plan(d, CSV, CFG, "--no-hidden-chars")
            self.assertEqual(rc, 0, err)
            self.assertNotIn("hidden_chars", err)
            self.assertNotIn("hidden_chars", json.dumps(f, ensure_ascii=False))
            self.assertNotIn("hidden_chars_summary", f)
            # with nothing else enabled there is no findings file at all
            rc, out, err, f, raw, fj = _plan(d, CSV, CFG, "--no-hidden-chars",
                                             "--no-builtin-hints", "--no-derived")
            self.assertEqual(rc, 0, err)
            self.assertFalse(os.path.exists(fj))


class T45DeterminismAndSentinels(unittest.TestCase):
    """T45: permutation-invariant bytes; values and code points never leak."""

    def test_row_and_column_permutations_are_byte_identical(self):
        perm_rows = ("memo,city,dx,note,junk\n"
                     "plain,,x\u202E6,,\n"
                     "ZX\u200BQV1,TY\uFE0F2,WQ\U000E00013,KQ\uFEFF4,PQ5\n").encode()
        perm_cols = ("junk,dx,city,memo,note\n"
                     "PQ5,WQ\U000E00013,TY\uFE0F2,ZX\u200BQV1,KQ\uFEFF4\n"
                     ",x\u202E6,,plain,\n").encode()
        with tempfile.TemporaryDirectory() as d:
            _, _, _, _, raw1, _ = _plan(d, CSV, CFG,
                                        "--no-builtin-hints", "--no-derived")
            _, _, _, _, raw2, _ = _plan(d, perm_rows, CFG,
                                        "--no-builtin-hints", "--no-derived")
            _, _, _, _, raw3, _ = _plan(d, perm_cols, CFG,
                                        "--no-builtin-hints", "--no-derived")
            self.assertEqual(raw1, raw2)
            self.assertEqual(raw1, raw3)

    def test_no_cell_value_and_no_code_point_ever_appears(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f, raw, fj = _plan(d, CSV, CFG)
            text = err + out + raw.decode("utf-8")
            for sentinel in ("ZXQ", "TY2", "WQ3", "KQ4", "PQ5", "plain"):
                self.assertNotIn(sentinel, text, sentinel)
            for hex_name in ("200B", "FE0F", "E0001", "FEFF", "202E", "0x", "U+"):
                self.assertNotIn(hex_name, raw.decode("utf-8"), hex_name)
            # the kind names are the only vocabulary
            self.assertIn("zero_width", raw.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
