"""audit tests (T31-T39, v0.7.0).

``audit`` observes the table as it is: it generalizes nothing, transforms
nothing and judges nothing.  It reports integers only — counts and per-mille
values floored with integer division — so the same table yields byte-identical
output on every platform.

  - A  equivalence classes on the QI tuple (count, sizes, buckets, per-mille)
  - B  per QI column (distinct without empty cells, column-unique rows, and
       rows_below_k recomputed with that column dropped)
  - C  repeated subjects (only with --subject): rows per person, per-class
       distinct subjects, and rows_overstated — classes that look safe on rows
       but hold fewer than k distinct people

Alignment pins (the request, section 2): audit reuses the engine's own ``_norm``
(NFC + strip) and groups exactly like ``measure``/``diagnose`` at level 0 — all
rows, empty QI values take part as the empty value, no missing-value filtering
(the same numbers ``plan`` reports as ``before``).  T31 cross-checks those.

The suite stays standard-library only, so T38 pins the packaging contract at
text level (``packages = ["sieve_crowd"]`` ships every module in the package,
therefore ``audit.py``) and re-pins the golden SHAs and the import block.
"""
import contextlib
import hashlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Golden SHAs, re-pinned for v0.7.0 (audit must not touch any of these paths).
RUN_TABLE_SHA = "b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138d8ae040061500e"
TEMPLATE_SHA = "66e7eaf4a42d86b15b422eee39fca550b9c7ada0049ba4b6f7dd31e6cc0c4159"
TEMPLATE_SHA2 = "664a19bb8c3a0279eba10e1923ba737817110d88def32c97e966d4c1744ed94b"
# jp-basic 1.3.0 (v0.7.2: jp-person-name and jp-address added) — re-measured from the bytes.
BUILTIN_PACK_SHA = "c62948240bc31e35a5ffbd35ccfe943899e0b82e0ab4dbf857ad76c3135eb02c"
# The frozen cores: byte-for-byte, nothing in v0.7.0 may edit them.
CONFIG_PY_SHA = "3fc0b1f9e95b7f05c88b4bf00f37faa6f529fd9e1c3fa000c54c137bd16d3a3d"
ENGINE_PY_SHA = "d7384c5eb5c6012f731ab9af04e0483ca92316b6b73b980f4a88a3541616dc5d"


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def _write(d, name, data):
    path = os.path.join(d, name)
    with open(path, "wb") as fh:
        fh.write(data)
    return path


def _audit(d, csv_data, cfg_data, *extra):
    """Run audit in d; return (rc, stdout, stderr, audit-object-or-None, raw-json)."""
    src = _write(d, "in.csv", csv_data)
    cfg = _write(d, "c.json", cfg_data)
    fj = os.path.join(d, "f.json")
    rc, out, err = call("audit", src, "-c", cfg, "--findings-json", fj, *extra)
    raw = ""
    audit = None
    if os.path.exists(fj):
        with open(fj, encoding="utf-8") as fh:
            raw = fh.read()
        audit = json.loads(raw)["audit"]
    return rc, out, err, audit, raw


# T31: a hand-computable table.  n=7, k=3.
#   classes (age,zip): (30,111)x3, (31,222)x2, (32,333)x1, (34,444)x1
T31_CSV = ("age,zip\n"
           "30,111\n30,111\n30,111\n31,222\n31,222\n32,333\n34,444\n").encode()
T31_CFG = json.dumps({"k": 3, "columns": {
    "age": {"role": "qi", "type": "exact"},
    "zip": {"role": "qi", "type": "exact"}}}).encode()

# T33: repeated subjects.  names/zips are sentinels (never a plain count word).
#   classes: (30,ZQ11)x3 {N1,N2} | (40,ZQ12)x2 {N3,N4} | (50,ZQ13)x2 {N5, empty}
T33_CSV = ("name,age,zip\n"
           "NVQ1,30,ZQ11\nNVQ1,30,ZQ11\nNVQ2,30,ZQ11\n"
           "NVQ3,40,ZQ12\nNVQ4,40,ZQ12\n"
           "NVQ5,50,ZQ13\n,50,ZQ13\n").encode()
T33_CFG = json.dumps({"k": 3, "columns": {
    "name": {"role": "keep"},
    "age": {"role": "qi", "type": "exact"},
    "zip": {"role": "qi", "type": "exact"}}}).encode()


class T31Classes(unittest.TestCase):
    """T31: the A items on a hand-computed table, and the alignment with the
    numbers plan already reports (same names, same numbers)."""

    def test_a_items_are_exact(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, a, raw = _audit(d, T31_CSV, T31_CFG)
            self.assertEqual(rc, 0)
            self.assertEqual(a["schema"], 1)
            self.assertEqual(a["rows"], 7)
            self.assertEqual(a["k"], 3)
            self.assertEqual(a["qi"], ["age", "zip"])
            self.assertEqual(a["classes"], {
                "count": 4, "min_size": 1, "unique_rows": 2, "rows_below_k": 4,
                "unique_permille": 285, "below_k_permille": 571,
                "size_buckets": {"1": 2, "2": 2, "3": 3, "4": 0,
                                 "5-9": 0, "10-49": 0, "50+": 0}})

    def test_same_names_same_numbers_as_plan(self):
        # the request, section 2.3: plan's before block and audit's classes are
        # the same observation at level 0 — the numbers must agree exactly.
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, T31_CSV, T31_CFG)
            self.assertEqual(rc, 0)
            src = _write(d, "in.csv", T31_CSV)
            cfg = _write(d, "c.json", T31_CFG)
            rj = os.path.join(d, "r.json")
            rc2, _, _ = call("plan", src, "-c", cfg, "--report-json", rj)
            self.assertEqual(rc2, 0)
            with open(rj, encoding="utf-8") as fh:
                plan = json.load(fh)
            before = plan["before"]
            self.assertEqual(a["classes"]["count"], before["crowds"])
            self.assertEqual(a["classes"]["min_size"], before["smallest_crowd"])
            self.assertEqual(a["classes"]["unique_rows"], before["records_alone"])
            self.assertEqual(a["classes"]["rows_below_k"], before["records_below_k"])


class T32BoundariesAndZero(unittest.TestCase):
    """T32: bucket boundaries (4/5, 9/10, 49/50), floored per-mille, n = 0."""

    @staticmethod
    def _csv(sizes):
        rows = []
        z = 0
        for s in sizes:
            z += 1
            rows.extend(f"{1000 + z},{2000 + z}\n" for _ in range(s))
        return ("age,zip\n" + "".join(rows)).encode()

    CFG = json.dumps({"k": 2, "columns": {
        "age": {"role": "qi", "type": "exact"},
        "zip": {"role": "qi", "type": "exact"}}}).encode()

    def test_bucket_edges_count_rows(self):
        data = self._csv([4, 5, 9, 10, 49, 50])          # n = 127
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, data, self.CFG)
            self.assertEqual(rc, 0)
            self.assertEqual(a["rows"], 127)
            self.assertEqual(a["classes"]["count"], 6)
            self.assertEqual(a["classes"]["size_buckets"],
                             {"1": 0, "2": 0, "3": 0, "4": 4,
                              "5-9": 14, "10-49": 59, "50+": 50})

    def test_permille_is_floored_integer_division(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, T31_CSV, T31_CFG)
            self.assertEqual(a["classes"]["unique_permille"], 1000 * 2 // 7)
            self.assertEqual(a["classes"]["below_k_permille"], 1000 * 4 // 7)
            self.assertEqual(a["classes"]["unique_permille"], 285)   # 285.71 -> 285
            self.assertEqual(a["classes"]["below_k_permille"], 571)  # 571.42 -> 571

    def test_empty_table_reports_zeros(self):
        data = b"age,zip\n"
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, data, self.CFG)
            self.assertEqual(rc, 0)
            self.assertEqual(a["rows"], 0)
            self.assertEqual(a["classes"], {
                "count": 0, "min_size": 0, "unique_rows": 0, "rows_below_k": 0,
                "unique_permille": 0, "below_k_permille": 0,
                "size_buckets": {"1": 0, "2": 0, "3": 0, "4": 0,
                                 "5-9": 0, "10-49": 0, "50+": 0}})
            self.assertEqual(a["qi_columns"], [
                {"column": "age", "distinct": 0, "unique_rows": 0,
                 "rows_below_k_without": 0},
                {"column": "zip", "distinct": 0, "unique_rows": 0,
                 "rows_below_k_without": 0}])


class T33Subjects(unittest.TestCase):
    """T33: the C items — repeats, buckets, per-class subjects, and the
    rows_overstated observation with its warning."""

    def test_c_items_are_exact(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, a, raw = _audit(d, T33_CSV, T33_CFG, "--subject", "name")
            self.assertEqual(rc, 0)
            self.assertEqual(a["subject"], {
                "column": "name",
                "rows_with_subject": 6, "rows_missing_subject": 1,
                "subjects": 6, "repeated_subjects": 1,
                "rows_in_repeated_subjects": 2, "max_rows_per_subject": 2,
                "rows_per_subject_buckets": {"1": 5, "2": 1, "3-4": 0,
                                             "5-9": 0, "10+": 0},
                "class_subjects": {"min_distinct": 2, "rows_below_k": 7,
                                   "rows_overstated": 3}})
            self.assertEqual(a["warnings"], [
                {"code": "small_classes", "rows": 4},
                {"code": "subject_overstated", "rows": 3}])
            self.assertNotIn("NVQ1", err)      # sentinels never leave the table
            self.assertNotIn("NVQ1", raw)

    def test_empty_subject_is_one_person_per_row(self):
        # the same table, every subject empty: each row is its own subject.
        data = ("name,age,zip\n"
                ",30,ZQ11\n,30,ZQ11\n,30,ZQ11\n").encode()
        cfg = T33_CFG
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, data, cfg, "--subject", "name")
            self.assertEqual(rc, 0)
            s = a["subject"]
            self.assertEqual(s["rows_with_subject"], 0)
            self.assertEqual(s["rows_missing_subject"], 3)
            self.assertEqual(s["subjects"], 3)          # one person per row
            self.assertEqual(s["repeated_subjects"], 0)
            self.assertEqual(s["rows_in_repeated_subjects"], 0)
            self.assertEqual(s["max_rows_per_subject"], 1)
            self.assertEqual(s["rows_per_subject_buckets"],
                             {"1": 3, "2": 0, "3-4": 0, "5-9": 0, "10+": 0})
            # per class, the three rows are three distinct subjects -> k = 3
            # is met on people, so nothing is overstated.
            self.assertEqual(s["class_subjects"], {"min_distinct": 3,
                                                   "rows_below_k": 0,
                                                   "rows_overstated": 0})
            self.assertEqual(a["warnings"], [])

    def test_rows_overstated_needs_both_conditions(self):
        # size >= k is NOT enough by itself, but a 4-row class holding 3
        # distinct people (NVQ1 twice, NVQ2, NVQ3) meets k = 3 on both levels:
        # nothing below k, nothing overstated.
        data = ("name,age,zip\n"
                "NVQ1,30,ZQ11\nNVQ1,30,ZQ11\nNVQ2,30,ZQ11\nNVQ3,30,ZQ11\n").encode()
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, data, T33_CFG, "--subject", "name")
            self.assertEqual(rc, 0)
            self.assertEqual(a["subject"]["class_subjects"],
                             {"min_distinct": 3, "rows_below_k": 0,
                              "rows_overstated": 0})
            self.assertEqual(a["warnings"], [])


class T34SubjectValidation(unittest.TestCase):
    """T34: the subject column is validated against the configuration; the
    message names the column and never a cell value."""

    CSV = ("id,name,age,zip,disease,note\n"
           "ID1,NVQ1,30,ZQ11,flu,hello\nID2,NVQ1,30,ZQ11,cold,world\n").encode()
    CFG = json.dumps({"k": 2, "columns": {
        "id": {"role": "id"},
        "name": {"role": "keep"},
        "age": {"role": "qi", "type": "exact"},
        "zip": {"role": "qi", "type": "exact"},
        "disease": {"role": "sensitive"},
        "note": {"role": "drop"}}}).encode()

    def test_unknown_column_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, a, _ = _audit(d, self.CSV, self.CFG, "--subject", "ghost")
            self.assertEqual(rc, 2)
            self.assertIn("ghost", err)
            self.assertNotIn("ID1", err)        # no cell values in the message
            self.assertIsNone(a)

    def test_qi_and_sensitive_columns_are_refused(self):
        for col in ("age", "zip", "disease"):
            with tempfile.TemporaryDirectory() as d:
                rc, _, err, a, _ = _audit(d, self.CSV, self.CFG, "--subject", col)
                self.assertEqual(rc, 2, col)
                self.assertIn(col, err)
                self.assertNotIn("NVQ1", err)   # no cell values in the message
                self.assertIsNone(a)

    def test_id_and_keep_and_drop_columns_are_allowed(self):
        for col in ("id", "name", "note"):
            with tempfile.TemporaryDirectory() as d:
                rc, _, _, a, _ = _audit(d, self.CSV, self.CFG, "--subject", col)
                self.assertEqual(rc, 0, col)
                self.assertEqual(a["subject"]["column"], col)

    def test_without_subject_the_c_items_are_absent(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, a, raw = _audit(d, self.CSV, self.CFG)
            self.assertEqual(rc, 0)
            self.assertIsNone(a["subject"])
            self.assertNotIn("subject_overstated", raw)
            self.assertEqual([w["code"] for w in a["warnings"]], [])


class T35QiColumns(unittest.TestCase):
    """T35: the B items — distinct (empty cells excluded), column-unique rows,
    rows_below_k_without; empty QI cells behave like plan's level 0."""

    CSV = ("name,a,b\n"
           "NQ1,1,x\nNQ2,1,x\nNQ3,2,y\nNQ4,3,z\nNQ5,,w\n").encode()   # n=5
    CFG = json.dumps({"k": 2, "columns": {
        "name": {"role": "keep"},
        "a": {"role": "qi", "type": "exact"},
        "b": {"role": "qi", "type": "exact"}}}).encode()

    def test_b_items_are_exact(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, self.CSV, self.CFG)
            self.assertEqual(rc, 0)
            self.assertEqual(a["qi_columns"], [
                {"column": "a", "distinct": 3, "unique_rows": 2,
                 "rows_below_k_without": 3},
                {"column": "b", "distinct": 4, "unique_rows": 3,
                 "rows_below_k_without": 3}])
            # the empty 'a' cell takes part as a value (level 0, star) but is
            # not counted in distinct: classes (1,x)x2 (2,y) (3,z) ("",w)
            self.assertEqual(a["classes"]["count"], 4)
            self.assertEqual(a["classes"]["min_size"], 1)
            self.assertEqual(a["classes"]["unique_rows"], 3)

    def test_single_qi_column(self):
        data = "c\np\nq\nr\n".encode()                 # n = 3
        cfg = json.dumps({"k": 5, "columns": {"c": {"role": "qi", "type": "exact"}}}).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, data, cfg)
            self.assertEqual(rc, 0)
            self.assertEqual(a["qi_columns"], [
                {"column": "c", "distinct": 3, "unique_rows": 3,
                 "rows_below_k_without": 3}])       # dropping c -> one class of n=3 < k=5
            cfg2 = json.dumps({"k": 2, "columns": {"c": {"role": "qi", "type": "exact"}}}).encode()
            rc, _, _, a, _ = _audit(d, data, cfg2)
            self.assertEqual(a["qi_columns"][0]["rows_below_k_without"], 0)  # n=3 >= k=2

    def test_norm_is_the_engine_norm(self):
        # the engine's _norm (NFC + strip): padding merges (" 10" == "10") but
        # NFC does NOT fold full-width digits (NFKC would) — "１０" stays apart.
        data = ("c\n"
                "\uff11\uff10\n"        # full-width 10
                "１０\n"                # same, NFC-equal
                " 10\n"                 # padded
                "9\n").encode()
        cfg = json.dumps({"k": 2, "columns": {"c": {"role": "qi", "type": "exact"}}}).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, data, cfg)
            self.assertEqual(rc, 0)
            self.assertEqual(a["classes"]["count"], 3)   # {"１０", "10", "9"}
            self.assertEqual(a["classes"]["min_size"], 1)
            self.assertEqual(a["qi_columns"][0]["distinct"], 3)
            self.assertEqual(a["qi_columns"][0]["unique_rows"], 2)  # the "10" and "9" rows


class T36Determinism(unittest.TestCase):
    """T36: row order and column order must not change a single byte."""

    CSV = ("age,zip\n30,111\n31,222\n30,111\n32,333\n31,222\n34,444\n").encode()
    CFG = json.dumps({"k": 3, "columns": {
        "age": {"role": "qi", "type": "exact"},
        "zip": {"role": "qi", "type": "exact"}}}).encode()

    @staticmethod
    def _run(d, name, csv, *extra):
        src = _write(d, name, csv)
        cfg = _write(d, "c.json", T36Determinism.CFG)
        fj = os.path.join(d, name + ".json")
        rc, _, err = call("audit", src, "-c", cfg, "--findings-json", fj, *extra)
        assert rc == 0
        with open(fj, "rb") as fh:
            return fh.read(), err

    def test_row_and_column_permutations_are_byte_identical(self):
        rows = self.CSV
        shuffled = ("age,zip\n34,444\n30,111\n32,333\n30,111\n31,222\n31,222\n"
                    ).encode()   # same rows, reordered
        swapped = ("zip,age\n111,30\n222,31\n111,30\n333,32\n222,31\n444,34\n").encode()
        with tempfile.TemporaryDirectory() as d:
            base, base_err = self._run(d, "a.csv", rows)
            shuf, shuf_err = self._run(d, "b.csv", shuffled)
            swap, swap_err = self._run(d, "c.csv", swapped)
            self.assertEqual(base, shuf)
            self.assertEqual(base, swap)
            self.assertEqual(base_err, shuf_err)
            self.assertEqual(base_err, swap_err)

    def test_same_input_twice_is_identical(self):
        with tempfile.TemporaryDirectory() as d:
            first, first_err = self._run(d, "a.csv", self.CSV)
            second, second_err = self._run(d, "b.csv", self.CSV)
            self.assertEqual(first, second)
            self.assertEqual(first_err, second_err)


class T37SentinelsAndKeys(unittest.TestCase):
    """T37: no cell value anywhere (subject values included), fixed key sets,
    and --findings-json is replaced unconditionally like plan's."""

    CSV = T33_CSV
    CFG = T33_CFG
    SENTINELS = ("NVQ1", "NVQ2", "NVQ3", "NVQ4", "NVQ5", "ZQ11", "ZQ12", "ZQ13")

    def test_no_cell_values_in_any_output(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, a, raw = _audit(d, self.CSV, self.CFG, "--subject", "name")
            self.assertEqual(rc, 0)
            self.assertEqual(out, "")          # audit writes nothing to stdout
            for s in self.SENTINELS:
                self.assertNotIn(s, err)
                self.assertNotIn(s, raw)

    def test_key_sets_are_fixed(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, self.CSV, self.CFG, "--subject", "name")
            self.assertEqual(set(a), {"schema", "rows", "k", "qi", "classes",
                                      "qi_columns", "subject", "warnings"})
            self.assertEqual(set(a["classes"]),
                             {"count", "min_size", "unique_rows", "rows_below_k",
                              "unique_permille", "below_k_permille", "size_buckets"})
            self.assertEqual(set(a["classes"]["size_buckets"]),
                             {"1", "2", "3", "4", "5-9", "10-49", "50+"})
            for col in a["qi_columns"]:
                self.assertEqual(set(col), {"column", "distinct", "unique_rows",
                                            "rows_below_k_without"})
            self.assertEqual(set(a["subject"]),
                             {"column", "rows_with_subject", "rows_missing_subject",
                              "subjects", "repeated_subjects",
                              "rows_in_repeated_subjects", "max_rows_per_subject",
                              "rows_per_subject_buckets", "class_subjects"})
            self.assertEqual(set(a["subject"]["rows_per_subject_buckets"]),
                             {"1", "2", "3-4", "5-9", "10+"})
            self.assertEqual(set(a["subject"]["class_subjects"]),
                             {"min_distinct", "rows_below_k", "rows_overstated"})
            for w in a["warnings"]:
                self.assertEqual(set(w), {"code", "rows"})

    def test_key_sets_without_subject(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _, a, _ = _audit(d, self.CSV, self.CFG)
            self.assertEqual(set(a), {"schema", "rows", "k", "qi", "classes",
                                      "qi_columns", "subject", "warnings"})
            self.assertIsNone(a["subject"])

    def test_findings_json_is_replaced_like_plan(self):
        with tempfile.TemporaryDirectory() as d:
            src1 = _write(d, "one.csv", T31_CSV)                 # 7 rows
            src2 = _write(d, "two.csv", T36Determinism.CSV)      # 6 rows
            cfg = _write(d, "c.json", T31_CFG)
            fj = os.path.join(d, "f.json")
            rc, _, _ = call("audit", src1, "-c", cfg, "--findings-json", fj)
            self.assertEqual(rc, 0)
            with open(fj, encoding="utf-8") as fh:
                first = json.load(fh)["audit"]
            rc, _, _ = call("audit", src2, "-c", cfg, "--findings-json", fj)
            self.assertEqual(rc, 0)
            with open(fj, encoding="utf-8") as fh:
                second = json.load(fh)["audit"]
            self.assertNotEqual(first["rows"], second["rows"])
            self.assertEqual(second["rows"], 6)


class T38Pins(unittest.TestCase):
    """T38: the golden outputs are unchanged, audit is not imported by the
    other subcommands, the packaging ships audit.py, and the frozen cores are
    byte-identical."""

    def test_run_table_matches_golden_sha(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.csv")
            rc, _, _ = call("run", os.path.join(REPO, "examples", "people.csv"),
                            "-c", os.path.join(REPO, "examples", "config.json"),
                            "-o", out, "--quiet")
            self.assertEqual(rc, 0)
            with open(out, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), RUN_TABLE_SHA)

    def test_inspect_templates_match_golden_shas(self):
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t1.json")
            call("inspect", os.path.join(REPO, "examples", "people.csv"),
                 "--config-out", tpl, "--no-builtin-hints")
            with open(tpl, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), TEMPLATE_SHA)
            tpl2 = os.path.join(d, "t2.json")
            call("inspect", os.path.join(REPO, "examples", "people.csv"),
                 "--config-out", tpl2)
            with open(tpl2, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), TEMPLATE_SHA2)

    def test_builtin_pack_bytes_are_pinned(self):
        from sieve_crowd.hintpack_builtin import BUILTIN_PACK_BYTES
        self.assertEqual(hashlib.sha256(BUILTIN_PACK_BYTES).hexdigest(),
                         BUILTIN_PACK_SHA)

    def test_audit_is_never_imported_by_run_plan_inspect(self):
        def probe(cmd, banned):
            code = (
                "import sys; from sieve_crowd.cli import main; main(%r); "
                "hit = %r & set(sys.modules); "
                "print('OK' if not hit else 'IMPORTED:' + ','.join(sorted(hit)))"
            ) % (cmd, banned)
            out = subprocess.check_output([sys.executable, "-c", code], text=True)
            self.assertIn("OK", out)
            self.assertNotIn("IMPORTED:", out)

        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            probe(["run", people, "-c", config, "-o", out, "--quiet"],
                  {"sieve_crowd.hintpack", "sieve_crowd.derived", "sieve_crowd.audit"})
            probe(["plan", people, "-c", config], {"sieve_crowd.audit"})
            probe(["inspect", people], {"sieve_crowd.audit"})

    def test_packaging_ships_audit_py(self):
        # text-level pin (the suite stays standard-library only): the wheel is
        # built from the whole package, so every module in sieve_crowd ships.
        self.assertTrue(os.path.isfile(os.path.join(REPO, "sieve_crowd", "audit.py")))
        with open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8") as fh:
            pyproject = fh.read()
        self.assertIn('packages = ["sieve_crowd"]', pyproject)

    def test_frozen_cores_are_byte_identical(self):
        for rel, sha in (("sieve_crowd/config.py", CONFIG_PY_SHA),
                         ("sieve_crowd/engine.py", ENGINE_PY_SHA)):
            with open(os.path.join(REPO, rel), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sha, rel)


class T39WarningsAndExitCodes(unittest.TestCase):
    """T39: the warning lines (both languages), exit 0 with warnings, the
    language switch, and the --help text."""

    def test_warning_lines_english(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, _, _ = _audit(d, T33_CSV, T33_CFG, "--subject", "name")
            self.assertEqual(rc, 0)
            self.assertIn('  - small_classes: 4 row(s) sit in classes smaller than k=3', err)
            self.assertIn('  - subject_overstated: 3 row(s) sit in classes of size >= k, '
                          'but with fewer than k distinct subjects (column "name")', err)

    def test_warning_lines_japanese(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, _, _ = _audit(d, T33_CSV, T33_CFG, "--subject", "name",
                                      "--lang", "ja")
            self.assertEqual(rc, 0)
            self.assertIn("  - small_classes: 4 行が、サイズ k=3 未満のグループに属しています", err)
            self.assertIn("  - subject_overstated: 3 行は、サイズは k 以上ですが、"
                          "異なる対象（列「name」）が k 人に届かないグループに属しています", err)

    def test_warnings_do_not_judge(self):
        # observation, not judgment: the report carries counts, never verdicts.
        words = ("unsafe", "insecure", "danger", "risky", "安全", "危険")
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, a, raw = _audit(d, T33_CSV, T33_CFG, "--subject", "name")
            self.assertEqual(rc, 0)             # warnings do not change the exit code
            self.assertTrue(a["warnings"])
            for w in words:
                self.assertNotIn(w, err)
                self.assertNotIn(w, err.lower())
                self.assertNotIn(w, raw)

    def test_report_text_is_pinned(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, _, _ = _audit(d, T31_CSV, T31_CFG)
            self.assertEqual(rc, 0)
            for line in (
                "Status: audit (observation only; nothing is generalized, searched or written)",
                "Records: 7, k = 3, qi: age, zip",
                "Equivalence classes on the QI tuple: count 4, smallest 1, "
                "unique rows 2, rows below k 4",
                "  per mille (floor): unique 285, below k 571",
                "  rows by class size: 1:2, 2:2, 3:3, 4:0, 5-9:0, 10-49:0, 50+:0",
                "  age: distinct 4, unique rows 2, rows below k without it 4",
                "  zip: distinct 4, unique rows 2, rows below k without it 4",
                "Warnings:",
                "  - small_classes: 4 row(s) sit in classes smaller than k=3",
            ):
                self.assertIn(line, err)

    def test_report_text_without_warnings(self):
        data = b"age,zip\n1,2\n1,2\n"
        cfg = json.dumps({"k": 2, "columns": {
            "age": {"role": "qi", "type": "exact"},
            "zip": {"role": "qi", "type": "exact"}}}).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, _, _ = _audit(d, data, cfg)
            self.assertEqual(rc, 0)
            self.assertIn("Warnings: none", err)
            self.assertIn("Records: 2, k = 2, qi: age, zip", err)
            self.assertIn("Equivalence classes on the QI tuple: count 1, smallest 2, "
                          "unique rows 0, rows below k 0", err)

    def test_report_text_japanese(self):
        # a no-warning table: the ja lines end in 警告: なし
        data = b"age,zip\n1,2\n1,2\n"
        cfg = json.dumps({"k": 2, "columns": {
            "age": {"role": "qi", "type": "exact"},
            "zip": {"role": "qi", "type": "exact"}}}).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, _, _ = _audit(d, data, cfg, "--lang", "ja")
            self.assertEqual(rc, 0)
            for line in (
                "状態: 監査（観測のみ。一般化も探索も書き込みもしません）",
                "レコード: 2 件、k = 2、準識別子: age, zip",
                "同値類（準識別子の組）: 1 個、最小 2、一独りの行 0 件、k 未満 0 件",
                "  千分率（切り捨て）: 一独り 0、k 未満 0",
                "  サイズ別の行数: 1:0, 2:2, 3:0, 4:0, 5-9:0, 10-49:0, 50+:0",
                "  age: 異なる値 1、一独りの行 0、この列を外すと k 未満 0 件",
                "警告: なし",
            ):
                self.assertIn(line, err)

    def test_report_text_japanese_with_warning(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, _, _ = _audit(d, T31_CSV, T31_CFG, "--lang", "ja")
            self.assertEqual(rc, 0)
            self.assertIn("警告:", err)
            self.assertIn("  - small_classes: 4 行が、サイズ k=3 未満のグループに属しています", err)

    def test_subject_report_text(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, _, _ = _audit(d, T33_CSV, T33_CFG, "--subject", "name")
            self.assertEqual(rc, 0)
            for line in (
                'Subject "name": rows with 6, missing 1, subjects 6, repeated 1, '
                "rows in repeated 2, max 2",
                "  rows per subject: 1:5, 2:1, 3-4:0, 5-9:0, 10+:0",
                "  distinct subjects per class: min 2, rows below k 7, rows overstated 3",
            ):
                self.assertIn(line, err)

    def test_rows_over_limit_warns_and_stays_zero(self):
        cfg = json.dumps({"k": 2, "columns": {
            "age": {"role": "qi", "type": "exact"},
            "zip": {"role": "qi", "type": "exact"}}}).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, _, err, a, raw = _audit(d, T31_CSV, cfg, "--max-rows", "3")
            self.assertEqual(rc, 0)
            self.assertIn("rows_over_limit", err)
            self.assertNotIn("rows_over_limit", raw)   # stderr note, not an audit warning
            self.assertEqual([w["code"] for w in a["warnings"]], ["small_classes"])

    def test_help_names_the_subcommand_and_options(self):
        err, out = io.StringIO(), io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(out):
                main(["audit", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        for fragment in ("--subject", "--findings-json", "--lang", "observation"):
            self.assertIn(fragment, text)

    def test_io_and_config_exit_codes(self):
        # aligned with plan: OSError -> 1, invalid config / bad table -> 2
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", T31_CSV)
            rc, _, err = call("audit", src, "-c", os.path.join(d, "missing.json"))
            self.assertEqual(rc, 1)
            cfg = _write(d, "c.json", T31_CFG)
            rc, _, err = call("audit", os.path.join(d, "missing.csv"), "-c", cfg)
            self.assertEqual(rc, 1)
            badcfg = _write(d, "bad.json", b"{ not json")
            rc, _, err = call("audit", src, "-c", badcfg)
            self.assertEqual(rc, 2)
            bad = _write(d, "bad.csv", b"age,zip\n1\n")   # ragged row
            rc, _, err = call("audit", bad, "-c", cfg)
            self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
