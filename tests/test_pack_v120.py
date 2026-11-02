"""jp-basic 1.2.0 tests (T47, v0.7.1).

The new ``jp-name-kana`` rule fires on the column NAME only (no value
condition): kana name columns — furigana/kana/name_kana/last_name_kana/
first_name_kana/フリガナ/ふりがな/カナ/氏名カナ/氏名フリガナ/姓カナ/名カナ/
姓フリガナ/名フリガナ — suggest ``role: id`` (the treatment the direct-
identifier hint tradition uses).  The evidence is the ``name`` stage only, so
``role_mismatch`` can never fire for it.  The pack version is 1.4.0 since
v0.7.3 (id suggestions, the requested column names and jp-zip-hyphen added)
and its bytes are re-pinned (BUILTIN_PACK_SHA changes on purpose).
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# jp-basic 1.4.0 (id suggestions, requested column names, jp-zip-hyphen) —
# the pin, re-measured from the bytes.
BUILTIN_PACK_SHA = "f164af7018e8cfa2d08ead08f79d16b125bda2128c2fc2c30b1918e0812fd235"


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


class T47JpNameKana(unittest.TestCase):
    """T47: name-only rule, id suggestion, no role_mismatch, version 1.4.0."""

    def test_builtin_pack_version_and_bytes(self):
        from sieve_crowd.hintpack import load_packs
        from sieve_crowd.hintpack_builtin import BUILTIN_PACK_BYTES
        import hashlib
        self.assertEqual(hashlib.sha256(BUILTIN_PACK_BYTES).hexdigest(),
                         BUILTIN_PACK_SHA)
        packs = load_packs([], include_builtin=True)
        self.assertEqual(packs[0].version, "1.4.0")  # v0.7.3 re-pin

    def test_kana_name_columns_suggest_id_with_name_evidence(self):
        csv = ("フリガナ,furigana,name,age\n"
               "ヤマダハナカ,Yamada Hanika,Doe,40\n").encode()
        cfg = json.dumps({"k": 3, "columns": {
            "フリガナ": {"role": "keep"},
            "furigana": {"role": "keep"},
            "name": {"role": "keep"},
            "age": {"role": "qi", "type": "exact"}}},
            ensure_ascii=False).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, csv, cfg)
            self.assertEqual(rc, 0, err)
            for col in ("フリガナ", "furigana"):
                cands = [(c["pack"], c["rule"], c["evidence"], c["suggest"])
                         for c in f["columns"][col]["candidates"]]
                self.assertIn(("jp-basic", "jp-name-kana", "name", {"role": "id"}),
                              cands, col)
            # the plain "name" column does not match (kana-specific list); a
            # column with no pack findings is omitted from the JSON entirely
            cands = [c["rule"] for c in f["columns"].get("name", {}).get("candidates", [])]
            self.assertNotIn("jp-name-kana", cands)
            # name-only evidence can never produce a role_mismatch
            self.assertNotIn("role_mismatch", err)
            self.assertFalse([w for w in f["warnings"]
                              if w["code"] == "role_mismatch"])

    def test_halfwidth_kana_column_name_matches_via_nfkc(self):
        # the column-NAME path keeps its NFKC normalization (v0.5.0 decision)
        csv = ("\uFF8C\uFF98\uFF76\uFF9E\uFF85,age\n"
               "ヤマダ,40\n").encode()
        cfg = json.dumps({"k": 3, "columns": {
            "\uFF8C\uFF98\uFF76\uFF9E\uFF85": {"role": "keep"},
            "age": {"role": "qi", "type": "exact"}}},
            ensure_ascii=False).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, csv, cfg)
            self.assertEqual(rc, 0, err)
            col = "\uFF8C\uFF98\uFF76\uFF9E\uFF85"
            cands = [c["rule"] for c in f["columns"][col]["candidates"]]
            self.assertIn("jp-name-kana", cands)

    def test_empty_values_still_suggest(self):
        csv = "furigana,age\n,40\n".encode()
        cfg = json.dumps({"k": 3, "columns": {
            "furigana": {"role": "keep"},
            "age": {"role": "qi", "type": "exact"}}}).encode()
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, csv, cfg)
            self.assertEqual(rc, 0, err)
            cands = [(c["rule"], c["evidence"])
                     for c in f["columns"]["furigana"]["candidates"]]
            self.assertIn(("jp-name-kana", "name"), cands)

    def test_inspect_template_carries_the_suggestion(self):
        csv = "furigana,age\nヤマダ,40\n".encode()
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.csv")
            with open(src, "wb") as fh:
                fh.write(csv)
            tpl = os.path.join(d, "t.json")
            rc, out, err = call("inspect", src, "--config-out", tpl)
            self.assertEqual(rc, 0, err)
            with open(tpl, encoding="utf-8") as fh:
                template = json.load(fh)
            self.assertEqual(template["columns"]["furigana"]["_suggest"],
                             {"role": "id"})


if __name__ == "__main__":
    unittest.main()
