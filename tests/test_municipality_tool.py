"""Municipality pack generator tests (T27-T28, v0.6.0).

``tools/make_municipality_pack.py`` turns the 総務省 local-government code
list (a CSV with the columns 団体コード / 都道府県名 / 市区町村名) into the
``jp-municipality-2026`` hint pack.  The tool is standard-library only,
deterministic (same input -> byte-identical pack), and its error messages
name columns, row numbers and counts — never a cell value.

T27 pins the generated pack (deterministic bytes, validity, uniqueness, the
5-digit = first-5-of-6 relationship, no id clash with the builtin, suggests
that pass ``parse_config``); T28 pins the input checks (exit code 2 without
cell values).  The pack itself is NOT distributed: the generator and these
tests are (see packs/README.md).  The classes skip when the tool is absent
(an sdist ships the tests but not ``tools/``; from a repository checkout they
always run).

Test-number note: the request named these T25/T26; the block was shifted to
T27/T28 because T20/T21 were already taken by v0.5.2.
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from sieve_crowd.config import parse_config
from sieve_crowd.hintpack import load_pack_bytes, load_packs
from sieve_crowd.model import ConfigError

REPO = Path(__file__).resolve().parent.parent
TOOL = REPO / "tools" / "make_municipality_pack.py"

HEADER = "団体コード,都道府県名,市区町村名"
# 6-digit local-government codes (5 digits + check digit; the tool does not
# verify the check digit).  First two digits: prefecture codes 01..47.
ROWS = [
    ("011002", "北海道", "函館市"),
    ("012025", "北海道", "旭川市"),
    ("040107", "宮城県", "仙台市"),
    ("111007", "埼玉県", "さいたま市"),
    ("131016", "東京都", "千代田区"),
    ("131041", "東京都", "中央区"),
    ("141003", "神奈川県", "横浜市"),
    ("151009", "新潟県", "新潟市"),
    ("172014", "石川県", "金沢市"),
    ("231002", "愛知県", "名古屋市"),
    ("271004", "大阪府", "大阪市"),
    ("281065", "兵庫県", "神戸市"),
    ("331007", "岡山県", "岡山市"),
    ("401307", "福岡県", "福岡市"),
    ("472011", "沖縄県", "那覇市"),
]


def _csv(rows=ROWS, header=HEADER) -> bytes:
    return (header + "\n" + "".join(",".join(r) + "\n" for r in rows)).encode("utf-8")


def _run(args):
    return subprocess.run([sys.executable, str(TOOL)] + args,
                          capture_output=True, timeout=60)


def _write(d, name, data) -> str:
    p = os.path.join(d, name)
    with open(p, "wb") as fh:
        fh.write(data)
    return p


@unittest.skipUnless(TOOL.exists(),
                     "the generator ships with the repository, not the sdist")
class T27MunicipalityPackGeneration(unittest.TestCase):
    """T27: the generated pack — deterministic bytes, validity, uniqueness,
    code relationships, no id clash with the builtin, parseable suggests."""

    def test_deterministic_bytes(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", _csv())
            r1 = _run([src])
            r2 = _run([src])
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertEqual(r1.stdout, r2.stdout)          # byte-identical
            out1 = _run([src, "-o", os.path.join(d, "p1.json")])
            out2 = _run([src, "-o", os.path.join(d, "p2.json")])
            self.assertEqual(out1.returncode, 0)
            with open(os.path.join(d, "p1.json"), "rb") as fh:
                f1 = fh.read()
            with open(os.path.join(d, "p2.json"), "rb") as fh:
                f2 = fh.read()
            self.assertEqual(f1, f2)
            self.assertEqual(f1, r1.stdout)                 # -o equals stdout

    def test_pack_is_valid_and_rules_are_unique(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", _csv())
            r = _run([src])
            self.assertEqual(r.returncode, 0, r.stderr)
        pack = load_pack_bytes(r.stdout, source="<generated>", origin="file")
        self.assertEqual(pack.id, "jp-municipality-2026")
        self.assertEqual(pack.version, "1.0.0")
        self.assertEqual([rule.id for rule in pack.rules],
                         ["jp-municipality-code", "jp-municipality-code5",
                          "jp-municipality-name"])

    def test_codes_unique_prefecture_range_and_code5_relationship(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _csv())])
            self.assertEqual(r.returncode, 0, r.stderr)
        pack = load_pack_bytes(r.stdout)
        rules = {rule.id: rule for rule in pack.rules}
        codes = sorted(rules["jp-municipality-code"].check.values)
        code5 = sorted(rules["jp-municipality-code5"].check.values)
        names = sorted(rules["jp-municipality-name"].check.values)
        self.assertEqual(len(codes), len(ROWS))                     # unique
        self.assertEqual(len(set(codes)), len(codes))
        self.assertTrue(all(len(c) == 6 and c.isdigit() for c in codes))
        self.assertTrue(all(1 <= int(c[:2]) <= 47 for c in codes))  # 01..47
        self.assertEqual(code5, sorted({c[:5] for c in codes}))     # 5 = 6[:5]
        self.assertEqual(len(set(code5)), len(code5))
        self.assertEqual(names, sorted({name for _, _, name in ROWS}))
        # every value list is sorted (part of the determinism contract)
        self.assertEqual(codes, sorted(codes))

    def test_coloads_with_the_builtin_without_id_clash(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _csv())])
            self.assertEqual(r.returncode, 0, r.stderr)
            pack_file = _write(d, "muni.json", r.stdout)
            packs = load_packs([pack_file], include_builtin=True)   # raises on clash
        self.assertEqual([p.id for p in packs], ["jp-basic", "jp-municipality-2026"])

    def test_suggestions_pass_parse_config(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _csv())])
            self.assertEqual(r.returncode, 0, r.stderr)
        pack = load_pack_bytes(r.stdout)
        seen = set()
        for rule in pack.rules:
            if rule.suggest is None:
                continue
            seen.add(rule.id)
            spec = {k: v for k, v in rule.suggest.items() if k != "role"}
            cfg = parse_config({"k": 2, "columns": {
                "dummy": {"role": "qi", **spec}}})
            self.assertEqual(cfg.names(cfg.columns["dummy"].role), ["dummy"])
        self.assertEqual(seen, {"jp-municipality-code", "jp-municipality-code5",
                                "jp-municipality-name"})


@unittest.skipUnless(TOOL.exists(),
                     "the generator ships with the repository, not the sdist")
class T28MunicipalityToolInputChecks(unittest.TestCase):
    """T28: contract violations exit with code 2 and the message names
    columns / rows — never a cell value."""

    def test_missing_columns_exit_2_without_cell_values(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", _csv(header="CODE,CITY,PREF",
                                           rows=[("XX9999", "PREF哨兵", "CITY哨兵")]))
            r = _run([src])
        self.assertEqual(r.returncode, 2)
        self.assertIn("missing column(s): 団体コード, 都道府県名, 市区町村名", r.stderr.decode())
        self.assertIn("found: CODE, CITY, PREF", r.stderr.decode())
        for sentinel in ("XX9999", "PREF哨兵", "CITY哨兵"):
            self.assertNotIn(sentinel, r.stderr.decode())

    def test_extra_columns_are_fine_missing_are_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "extra.csv",
                         _csv(header=HEADER + ",備考",
                              rows=[(c, p, n, "note") for c, p, n in ROWS]))
            self.assertEqual(_run([src]).returncode, 0)
            src2 = _write(d, "short.csv", _csv(header="団体コード,市区町村名"))
            r = _run([src2])
        self.assertEqual(r.returncode, 2)
        self.assertIn("missing column(s): 都道府県名", r.stderr.decode())

    def test_bad_code_exits_2_and_names_the_row_not_the_value(self):
        rows = list(ROWS[:2]) + [("12X345", "東京都", "八角区")]
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _csv(rows=rows))])
        self.assertEqual(r.returncode, 2)
        err = r.stderr.decode()
        self.assertIn("団体コード: expected 6 digits (row 4)", err)
        self.assertNotIn("12X345", err)

    def test_conflicting_duplicate_exits_2_exact_duplicates_collapse(self):
        rows = list(ROWS[:2]) + [("131016", "東京都", "千代田区"),
                                 ("131016", "東京都", "中央区")]
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _csv(rows=rows))])
            self.assertEqual(r.returncode, 2)
            err = r.stderr.decode()
            self.assertIn("the same code appears twice with different details (row 5)", err)
            self.assertNotIn("千代田区", err)
            self.assertNotIn("中央区", err)
            dup = list(ROWS[:2]) + [("131016", "東京都", "千代田区")]
            r2 = _run([_write(d, "dup.csv", _csv(rows=dup))])
        self.assertEqual(r2.returncode, 0)
        pack = load_pack_bytes(r2.stdout)
        codes = next(rule for rule in pack.rules
                     if rule.id == "jp-municipality-code").check.values
        self.assertEqual(len(codes), 3)                    # exact duplicate collapsed

    def test_unreadable_input_exits_1(self):
        r = _run([os.path.join(tempfile.gettempdir(), "sieve-crowd-missing-input.csv")])
        self.assertEqual(r.returncode, 1)
        self.assertIn("cannot read the input", r.stderr.decode())


if __name__ == "__main__":
    unittest.main()
