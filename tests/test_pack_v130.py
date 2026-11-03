"""jp-basic 1.3.0 tests (T48-T50, v0.7.2).

Two new name-only column rules join ``jp-name-kana``: ``jp-person-name`` and
``jp-address``.  Both fire on the column NAME only (no value condition) and
suggest ``{"role": "id"}`` — the same minimal shape jp-name-kana uses.  The
evidence is the ``name`` stage only, so ``role_mismatch`` can never fire for
them.  The match is exact on the normalized name and the name sets of the
builtin rules are pairwise disjoint, so one column can never match two
builtin rules.  Pack version 1.2.0 -> 1.3.0; BUILTIN_PACK_SHA and
TEMPLATE_SHA2 are re-pinned (T51 owns the new pins; the existing tests
re-pin in place).
"""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# jp-basic 1.6.0 (the wider phone/email/card column names) — the pin,
# re-measured from the bytes.
BUILTIN_PACK_SHA = "79b33a820a3d6d994ef366e1f11be53d3cbd71a4f46a3847987cff147789e34f"

# The name lists of the two new rules.
PERSON_NAME_COLUMNS = ["name", "full_name", "fullname", "first_name", "last_name",
                       "family_name", "given_name", "customer_name",
                       "氏名", "名前", "お名前", "姓名", "姓", "名", "苗字", "顧客名"]
ADDRESS_COLUMNS = ["address", "addr", "address1", "address2", "street", "street_address",
                   "住所", "住所1", "住所2", "現住所", "所在地", "番地"]
# jp-name-kana (1.2.0): none of these may match the new rules.
KANA_COLUMNS = ["furigana", "kana", "name_kana", "last_name_kana", "first_name_kana",
                "フリガナ", "ふりがな", "カナ", "氏名カナ", "氏名フリガナ",
                "姓カナ", "名カナ", "姓フリガナ", "名フリガナ"]
# Near-miss names the exact match must never reach into.
NEGATIVE_COLUMNS = ["filename", "username", "hostname"]


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
    findings = None
    if os.path.exists(fj):
        with open(fj, encoding="utf-8") as fh:
            findings = json.load(fh)
    return rc, out, err, findings


def _keep_config(columns):
    cols = {c: {"role": "keep"} for c in columns}
    cols["age"] = {"role": "qi", "type": "exact"}
    return json.dumps({"k": 3, "columns": cols}, ensure_ascii=False).encode()


def _csv(columns, values=None):
    values = values or {}
    header = ",".join(columns + ["age"])
    row = ",".join(values.get(c, "x") for c in columns) + ",40"
    return (header + "\n" + row + "\n").encode("utf-8")


class T48JpPersonNameAndAddress(unittest.TestCase):
    """T48: every listed column name of the two new rules fires as a candidate
    (English and Japanese lists, plus the full-width / upper-case / padded
    forms through the NFKC + strip + lower normalization), the evidence is
    the name stage only, and role_mismatch never fires."""

    def test_builtin_pack_version_and_bytes(self):
        from sieve_crowd.hintpack import load_packs
        from sieve_crowd.hintpack_builtin import BUILTIN_PACK_BYTES
        self.assertEqual(hashlib.sha256(BUILTIN_PACK_BYTES).hexdigest(),
                         BUILTIN_PACK_SHA)
        packs = load_packs([], include_builtin=True)
        self.assertEqual(packs[0].version, "1.6.0")

    def test_person_name_columns_suggest_id(self):
        csv = _csv(PERSON_NAME_COLUMNS)
        cfg = _keep_config(PERSON_NAME_COLUMNS)
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, csv, cfg)
            self.assertEqual(rc, 0, err)
            for col in PERSON_NAME_COLUMNS:
                cands = [(c["pack"], c["rule"], c["evidence"], c["suggest"])
                         for c in f["columns"][col]["candidates"]]
                self.assertIn(("jp-basic", "jp-person-name", "name", {"role": "id"}),
                              cands, col)
            # name-only evidence can never produce a role_mismatch
            self.assertNotIn("role_mismatch", err)
            self.assertFalse([w for w in f["warnings"]
                              if w["code"] == "role_mismatch"])

    def test_address_columns_suggest_id(self):
        csv = _csv(ADDRESS_COLUMNS)
        cfg = _keep_config(ADDRESS_COLUMNS)
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, csv, cfg)
            self.assertEqual(rc, 0, err)
            for col in ADDRESS_COLUMNS:
                cands = [(c["pack"], c["rule"], c["evidence"], c["suggest"])
                         for c in f["columns"][col]["candidates"]]
                self.assertIn(("jp-basic", "jp-address", "name", {"role": "id"}),
                              cands, col)
            self.assertNotIn("role_mismatch", err)
            self.assertFalse([w for w in f["warnings"]
                              if w["code"] == "role_mismatch"])

    def test_normalized_column_names_match(self):
        # two runs: within one CSV no two headers may share a normalized form
        # (name / full_name / street / 住所 / 住所1 stay distinct).
        run_a = ["NAME", "Full_Name", "ＳＴＲＥＥＴ", "住所１"]
        want_a = {"NAME": "jp-person-name", "Full_Name": "jp-person-name",
                  "ＳＴＲＥＥＴ": "jp-address", "住所１": "jp-address"}
        run_b = ["ＮＡＭＥ", " 住所 "]
        want_b = {"ＮＡＭＥ": "jp-person-name", " 住所 ": "jp-address"}
        for columns, want in ((run_a, want_a), (run_b, want_b)):
            csv = _csv(columns)
            cfg = _keep_config(columns)
            with tempfile.TemporaryDirectory() as d:
                rc, out, err, f = _plan(d, csv, cfg)
                self.assertEqual(rc, 0, err)
                for col in columns:
                    cands = [c["rule"] for c in f["columns"][col]["candidates"]]
                    self.assertIn(want[col], cands, col)


class T49NegativeAndOrdering(unittest.TestCase):
    """T49: the exact match never reaches into near-miss names (filename,
    username, hostname), none of the jp-name-kana names matches the new
    rules, no column matches two builtin rules, and when several pack rules
    match one column the candidates are ordered by rule id ascending."""

    def test_near_miss_names_do_not_match(self):
        columns = NEGATIVE_COLUMNS + KANA_COLUMNS
        csv = _csv(columns)
        cfg = _keep_config(columns)
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, csv, cfg)
            self.assertEqual(rc, 0, err)
            # a column with no pack findings is omitted from the JSON entirely
            for col in NEGATIVE_COLUMNS:
                self.assertNotIn(col, f["columns"], col)
            for col in KANA_COLUMNS:
                cands = [c["rule"] for c in f["columns"][col]["candidates"]]
                self.assertIn("jp-name-kana", cands, col)
                self.assertNotIn("jp-person-name", cands, col)
                self.assertNotIn("jp-address", cands, col)

    def test_no_column_matches_two_builtin_rules(self):
        columns = PERSON_NAME_COLUMNS + ADDRESS_COLUMNS + KANA_COLUMNS
        csv = _csv(columns)
        cfg = _keep_config(columns)
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, csv, cfg)
            self.assertEqual(rc, 0, err)
            for col, entry in f["columns"].items():
                rules = {c["rule"] for c in entry["candidates"]}
                hits = rules & {"jp-person-name", "jp-address", "jp-name-kana"}
                self.assertLessEqual(len(hits), 1, (col, sorted(rules)))

    def test_candidates_ordered_by_rule_id_ascending(self):
        # a user pack whose rule id sorts before the builtin's: with both
        # packs loaded, the name column's candidates must be rule-id ascending
        # (evidence and suggest role are equal, so the rule id decides).
        pack = json.dumps({"schema": 1, "id": "extra", "rules": [
            {"id": "aaa-name", "when": {"column_names": ["name"]},
             "suggest": {"role": "id"}}]}).encode()
        csv = _csv(["name"])
        cfg = _keep_config(["name"])
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "extra.json")
            with open(p, "wb") as fh:
                fh.write(pack)
            rc, out, err, f = _plan(d, csv, cfg, "--hint-pack", p)
            self.assertEqual(rc, 0, err)
            cands = [(c["pack"], c["rule"])
                     for c in f["columns"]["name"]["candidates"]]
            self.assertEqual(cands, [("extra", "aaa-name"),
                                     ("jp-basic", "jp-person-name")])


class T50InspectTemplate(unittest.TestCase):
    """T50: on the default inspect route the name column of people.csv gains
    the id suggestion from jp-person-name (the TEMPLATE_SHA2 pin changes for
    exactly this reason); with --no-builtin-hints the column stays hint-only
    and the template bytes keep the TEMPLATE_SHA pin."""

    def test_name_column_carries_the_id_suggestion(self):
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.json")
            rc, out, err = call("inspect", os.path.join(REPO, "examples", "people.csv"),
                                "--config-out", tpl)
            self.assertEqual(rc, 0, err)
            with open(tpl, encoding="utf-8") as fh:
                template = json.load(fh)
            name = template["columns"]["name"]
            self.assertEqual(name["_suggest"], {"role": "id"})
            self.assertIn({"pack": "jp-basic", "rule": "jp-person-name",
                           "evidence": "name", "suggest": {"role": "id"}},
                          name["_candidates"])
            self.assertIn("hint-pack jp-basic/jp-person-name: "
                          "suggests role=id (evidence: name)", out)

    def test_no_builtin_hints_keeps_the_name_column_hint_only(self):
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.json")
            rc, out, err = call("inspect", os.path.join(REPO, "examples", "people.csv"),
                                "--config-out", tpl, "--no-builtin-hints")
            self.assertEqual(rc, 0, err)
            with open(tpl, encoding="utf-8") as fh:
                template = json.load(fh)
            name = template["columns"]["name"]
            self.assertNotIn("_suggest", name)
            self.assertNotIn("_candidates", name)
            self.assertIn("_hint", name)
            with open(tpl, "rb") as fh:
                self.assertEqual(
                    hashlib.sha256(fh.read()).hexdigest(),
                    "66e7eaf4a42d86b15b422eee39fca550b9c7ada0049ba4b6f7dd31e6cc0c4159")


if __name__ == "__main__":
    unittest.main()
