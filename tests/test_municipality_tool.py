"""Municipality pack generator tests (T27-T28, v0.6.0; T29, v0.6.1).

``tools/make_municipality_pack.py`` turns a Japanese local-government code
CSV into the ``jp-municipality-2026`` hint pack.  Two input contracts are
auto-detected from the header: the prefecture master of the デジタル庁
アドレス・ベース・レジストリ (columns ``lg_code`` / ``pref`` — the source of
the pack committed under ``packs/``, licensed under PDL 1.0 with the
attribution in ``packs/README.md``) and the 総務省 local-government code list
(columns ``団体コード`` / ``都道府県名`` / ``市区町村名`` — terms not
confirmed, such a pack stays local).  The tool is standard-library only,
deterministic (same input -> byte-identical pack), and its error messages
name columns, row numbers and counts — never a cell value.

T27 pins the generated municipality-mode pack (deterministic bytes,
validity, uniqueness, the 5-digit = first-5-of-6 relationship, no id clash
with the builtin, suggests that pass ``parse_config``); T28 pins the input
checks (exit code 2 without cell values).  T29 (v0.6.1) pins the prefecture
mode (rules, the prefecture-level ``000`` guard, the ambiguous header); since
v0.6.2 it also pins the committed pack, which is the merged municipality
edition (pack 1.1.0: regenerating from the two committed extracts reproduces
the committed bytes; content: 1,794 codes / 1,794 code5 / 47 prefecture names
/ 1,714 municipality names) and the attribution for both sources in
``packs/README.md``.  T30 (v0.6.2) pins the merged two-source generation
itself: the four-rule union pack, determinism and input-order independence,
``--pack-version``, and the new contract errors (two inputs of the same
contract, more than two inputs, a cross-source conflicting duplicate).

The classes skip when the tool or the ``packs/`` files are absent (an sdist
ships the tests but neither ``tools/`` nor ``packs/``; from a repository
checkout they always run).

Test-number note: the v0.6.0 request named its block T25/T26; it was shifted
to T27/T28 because T20/T21 were already taken by v0.5.2.  T29 continues the
sequence in v0.6.1 and T30 in v0.6.2.
"""
import csv
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


PREF_HEADER = "lg_code,pref,pref_kana,pref_roma,efct_date,ablt_date,remarks"
PREF_ROWS = [
    ("010006", "北海道", "ホッカイドウ", "Hokkaido", "1947-04-17", "", ""),
    ("110001", "埼玉県", "サイタマケン", "Saitama", "1947-04-17", "", ""),
    ("470007", "沖縄県", "オキナワケン", "Okinawa", "1947-04-17", "", ""),
]
PREF_CSV_SOURCE = REPO / "packs" / "mt_pref_all.csv"
MUNI_CSV_SOURCE = REPO / "packs" / "soumu_city_r611.csv"
PREF_PACK = REPO / "packs" / "jp-municipality-2026.json"
PACKS_README = REPO / "packs" / "README.md"


def _pref_csv(rows=PREF_ROWS, header=PREF_HEADER) -> bytes:
    return (header + "\n" + "".join(",".join(r) + "\n" for r in rows)).encode("utf-8")


@unittest.skipUnless(TOOL.exists(),
                     "the generator ships with the repository, not the sdist")
class T29PrefectureModeAndCommittedPack(unittest.TestCase):
    """T29 (v0.6.1): the prefecture mode (lg_code/pref); since v0.6.2 the
    committed pack is the merged municipality edition (pack 1.1.0), pinned by
    byte-identity with a regeneration from the two committed extracts and by
    its content; plus the attribution in packs/README.md."""

    @unittest.skipUnless(TOOL.exists(),
                         "the generator ships with the repository, not the sdist")
    def test_prefecture_mode_generates_the_prefecture_rules(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _pref_csv())])
            self.assertEqual(r.returncode, 0, r.stderr)
        pack = load_pack_bytes(r.stdout, source="<generated>", origin="file")
        self.assertEqual(pack.id, "jp-municipality-2026")
        self.assertEqual(pack.version, "1.0.0")
        self.assertEqual([rule.id for rule in pack.rules],
                         ["jp-municipality-code", "jp-municipality-code5",
                          "jp-prefecture-name"])
        rules = {rule.id: rule for rule in pack.rules}
        self.assertIn("lg_code", rules["jp-municipality-code"].column_names)
        self.assertIn("都道府県コード", rules["jp-municipality-code"].column_names)
        self.assertIn("pref", rules["jp-prefecture-name"].column_names)
        codes = sorted(rules["jp-municipality-code"].check.values)
        code5 = sorted(rules["jp-municipality-code5"].check.values)
        names = sorted(rules["jp-prefecture-name"].check.values)
        self.assertEqual(codes, sorted(c for c, *_ in PREF_ROWS))
        self.assertEqual(code5, sorted(c[:5] for c, *_ in PREF_ROWS))
        self.assertEqual(names, sorted({row[1] for row in PREF_ROWS}))
        self.assertEqual(rules["jp-prefecture-name"].suggest,
                         {"role": "qi", "type": "category"})

    @unittest.skipUnless(TOOL.exists(),
                         "the generator ships with the repository, not the sdist")
    def test_prefecture_mode_rejects_municipality_level_code(self):
        rows = [("011002", "北海道", "ホッカイドウ", "Hokkaido", "1947-04-17", "", "")]
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _pref_csv(rows=rows))])
        self.assertEqual(r.returncode, 2)
        err = r.stderr.decode()
        self.assertIn("lg_code: expected a prefecture-level code", err)
        self.assertIn("(row 2)", err)
        self.assertNotIn("011002", err)

    @unittest.skipUnless(TOOL.exists(),
                         "the generator ships with the repository, not the sdist")
    def test_ambiguous_header_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run([_write(d, "in.csv", _pref_csv(
                header="lg_code,団体コード,都道府県名,市区町村名,pref",
                rows=[("010006", "010006", "北海道", "哨兵市", "北海道")]))])
        self.assertEqual(r.returncode, 2)
        err = r.stderr.decode()
        self.assertIn("ambiguous input", err)
        self.assertIn("found: lg_code, 団体コード, 都道府県名, 市区町村名, pref", err)
        self.assertNotIn("010006", err)

    @unittest.skipUnless(TOOL.exists() and PREF_CSV_SOURCE.exists()
                         and MUNI_CSV_SOURCE.exists() and PREF_PACK.exists(),
                         "the generator and the committed packs/ files ship "
                         "with the repository, not the sdist")
    def test_committed_pack_matches_regeneration(self):
        args = ["--pack-version", "1.1.0"]
        r = _run([str(PREF_CSV_SOURCE), str(MUNI_CSV_SOURCE)] + args)
        self.assertEqual(r.returncode, 0, r.stderr)
        r_swapped = _run([str(MUNI_CSV_SOURCE), str(PREF_CSV_SOURCE)] + args)
        self.assertEqual(r_swapped.returncode, 0, r_swapped.stderr)
        self.assertEqual(r.stdout, r_swapped.stdout)   # input order independent
        with open(PREF_PACK, "rb") as fh:
            committed = fh.read()
        self.assertEqual(committed, r.stdout)      # byte-identical regeneration

    @unittest.skipUnless(PREF_PACK.exists() and MUNI_CSV_SOURCE.exists(),
                         "the committed packs/ files ship with the repository, "
                         "not the sdist")
    def test_committed_pack_pins_the_municipality_edition(self):
        with open(PREF_PACK, "rb") as fh:
            pack = load_pack_bytes(fh.read(), source="<committed>", origin="file")
        self.assertEqual(pack.id, "jp-municipality-2026")
        self.assertEqual(pack.version, "1.1.0")
        self.assertEqual([rule.id for rule in pack.rules],
                         ["jp-municipality-code", "jp-municipality-code5",
                          "jp-prefecture-name", "jp-municipality-name"])
        rules = {rule.id: rule for rule in pack.rules}
        codes = sorted(rules["jp-municipality-code"].check.values)
        code5 = sorted(rules["jp-municipality-code5"].check.values)
        pref_names = sorted(rules["jp-prefecture-name"].check.values)
        muni_names = sorted(rules["jp-municipality-name"].check.values)
        self.assertEqual(len(codes), 1794)                     # 47 + 1747
        self.assertEqual(len(set(codes)), len(codes))          # unique
        self.assertTrue(all(len(c) == 6 and c.isdigit() for c in codes))
        self.assertTrue(all(1 <= int(c[:2]) <= 47 for c in codes))   # 01..47
        self.assertEqual(len(code5), 1794)                     # all distinct
        self.assertEqual(len([c for c in code5 if c.endswith("000")]), 47)
        self.assertEqual(len(pref_names), 47)
        self.assertEqual(len(set(pref_names)), len(pref_names))
        self.assertEqual(len(muni_names), 1714)                # 府中市 etc. collapse
        # the committed municipality extract carries exactly these rows
        with open(MUNI_CSV_SOURCE, encoding="utf-8", newline="") as fh:
            rows = list(csv.reader(fh))
        self.assertEqual(len(rows), 1748)                      # header + 1747
        self.assertEqual(rows[0],
                         ["団体コード", "都道府県名", "市区町村名",
                          "都道府県名（カナ）", "市区町村名（カナ）"])
        for rule in pack.rules:          # every suggest passes parse_config
            spec = {k: v for k, v in rule.suggest.items() if k != "role"}
            cfg = parse_config({"k": 2, "columns": {
                "dummy": {"role": "qi", **spec}}})
            self.assertEqual(cfg.names(cfg.columns["dummy"].role), ["dummy"])

    @unittest.skipUnless(PACKS_README.exists(),
                         "packs/README.md ships with the repository, not the sdist")
    def test_packs_readme_carries_the_required_attribution(self):
        text = PACKS_README.read_text(encoding="utf-8")
        for needle in (
                "base_registry_address",          # 出典 URL (アドレス・ベース・レジストリ)
                "public_data_license_v1.0",       # PDL 1.0 license URL
                "PDL 1.0",                        # the license name
                "加工・作成",                       # the edited-data statement (1.1)
                "sieve-crowd",                    # the entity that edited it
                "soumu.go.jp/denshijiti",         # the 総務省 source page (v0.6.2)
                "menu_kyotsuu/policy/tyosaku",    # the 総務省 site policy (PDL 1.0)
                "000925835",                      # the obtained 総務省 xlsx
                ):
            self.assertIn(needle, text)


M_HEADER = "lg_code,pref"
M_ROWS = [("010006", "北海道"), ("110001", "埼玉県")]
C_HEADER = "団体コード,都道府県名,市区町村名"
C_ROWS = [("011002", "北海道", "札幌市"), ("131016", "東京都", "千代田区")]


@unittest.skipUnless(TOOL.exists(),
                     "the generator ships with the repository, not the sdist")
class T30MergedGeneration(unittest.TestCase):
    """T30 (v0.6.2): the merged two-source generation — the four-rule union
    pack, determinism and input-order independence, ``--pack-version``, and
    the new contract errors (same contract twice, more than two inputs, a
    cross-source conflicting duplicate).  Error messages never carry values."""

    def _m(self, d, name="pref.csv", rows=M_ROWS):
        return _write(d, name, (M_HEADER + "\n"
                      + "".join(",".join(r) + "\n" for r in rows)).encode("utf-8"))

    def _c(self, d, name="city.csv", rows=C_ROWS):
        return _write(d, name, (C_HEADER + "\n"
                      + "".join(",".join(r) + "\n" for r in rows)).encode("utf-8"))

    def test_merged_generation_produces_the_four_rule_union(self):
        with tempfile.TemporaryDirectory() as d:
            r = _run([self._m(d), self._c(d)])
            self.assertEqual(r.returncode, 0, r.stderr)
        pack = load_pack_bytes(r.stdout, source="<generated>", origin="file")
        self.assertEqual(pack.id, "jp-municipality-2026")
        self.assertEqual(pack.version, "1.0.0")            # the default
        self.assertEqual([rule.id for rule in pack.rules],
                         ["jp-municipality-code", "jp-municipality-code5",
                          "jp-prefecture-name", "jp-municipality-name"])
        rules = {rule.id: rule for rule in pack.rules}
        codes = sorted(rules["jp-municipality-code"].check.values)
        code5 = sorted(rules["jp-municipality-code5"].check.values)
        self.assertEqual(codes, ["010006", "011002", "110001", "131016"])
        self.assertEqual(code5, ["01000", "01100", "11000", "13101"])
        # the code rule matches both contracts' columns
        self.assertIn("lg_code", rules["jp-municipality-code"].column_names)
        self.assertIn("団体コード", rules["jp-municipality-code"].column_names)
        self.assertEqual(sorted(rules["jp-prefecture-name"].check.values),
                         ["北海道", "埼玉県"])
        self.assertEqual(sorted(rules["jp-municipality-name"].check.values),
                         ["千代田区", "札幌市"])

    def test_merged_bytes_are_deterministic_and_order_independent(self):
        with tempfile.TemporaryDirectory() as d:
            m, c = self._m(d), self._c(d)
            r1 = _run([m, c])
            r2 = _run([m, c])
            r3 = _run([c, m])
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertEqual(r3.returncode, 0, r3.stderr)
            self.assertEqual(r1.stdout, r2.stdout)
            self.assertEqual(r1.stdout, r3.stdout)
            v11 = _run([m, c, "--pack-version", "1.1.0"])
            v11b = _run([c, m, "--pack-version", "1.1.0"])
            self.assertEqual(v11.returncode, 0, v11.stderr)
            self.assertEqual(v11.stdout, v11b.stdout)
        self.assertIn('"version": "1.0.0"', r1.stdout.decode())
        self.assertIn('"version": "1.1.0"', v11.stdout.decode())

    def test_two_inputs_of_the_same_contract_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            m, c = self._m(d), self._c(d)
            r = _run([m, self._m(d, name="pref2.csv")])
            r2 = _run([c, self._c(d, name="city2.csv")])
        for run in (r, r2):
            self.assertEqual(run.returncode, 2)
            err = run.stderr.decode()
            self.assertIn("the two inputs use the same contract", err)
        self.assertNotIn("010006", r.stderr.decode())
        self.assertNotIn("011002", r2.stderr.decode())

    def test_three_inputs_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            m, c = self._m(d), self._c(d)
            r = _run([m, c, m])
        self.assertEqual(r.returncode, 2)
        self.assertIn("expected one or two inputs (found 3)", r.stderr.decode())

    def test_cross_source_conflicting_duplicate_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._m(d)
            c = self._c(d, rows=[("010006", "北海道", "哨兵市")])
            r = _run([m, c])
        self.assertEqual(r.returncode, 2)
        err = r.stderr.decode()
        self.assertIn("the same code appears twice with different details", err)
        self.assertIn("(input 2, row 2)", err)
        self.assertNotIn("010006", err)
        self.assertNotIn("哨兵市", err)

    def test_cross_source_identical_duplicate_collapses(self):
        with tempfile.TemporaryDirectory() as d:
            m = self._m(d)
            c = self._c(d, rows=[("010006", "北海道", "北海道"),
                                 ("011002", "北海道", "札幌市")])
            r = _run([m, c])
            self.assertEqual(r.returncode, 0, r.stderr)
        pack = load_pack_bytes(r.stdout)
        codes = next(rule for rule in pack.rules
                     if rule.id == "jp-municipality-code").check.values
        self.assertEqual(sorted(codes), ["010006", "011002", "110001"])


if __name__ == "__main__":
    unittest.main()
