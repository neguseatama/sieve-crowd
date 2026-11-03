"""jp-basic 1.7.0 tests (T78/T81, v0.8.2).

The pack grows from 14 to 16 rules: ``jp-sex`` (sex/gender column names —
`sex`, `gender`, `性別`, `性`, `男女`, `ジェンダー` — suggest `role: qi` with
`type: category` and **no hierarchy**: the pack holds no value standard for
sex, so the category generalization is the exact→suppress ladder, the same
behavior the examples/config.json `exact` declaration has; a hierarchy can be
added by the user later) and ``jp-diagnosis`` (diagnosis/disease column names
— `diagnosis`, `diagnoses`, `disease`, `condition`, `病名`, `診断`, `診断名`,
`疾患`, `疾患名`, `傷病名` — suggest `role: sensitive`).  Both are name-only
rules: no value condition, no leak, no check — and name-only evidence never
fires `role_mismatch` (the v0.5.1/v0.7.3 conditions require name+value or
value evidence for a qi suggestion, name+value for an id one), so a column
that merely looks like a sex/diagnosis column stays a proposal, never a
warning.  Written first: red until the pack commit.

* T78 — the two rules: name counts and the closed ownership map (each of the
  16 names belongs to its rule alone, full-width/upper-case/whitespace
  variants normalize onto the names), every name fires exactly one candidate
  with the exact suggest shape and `name` evidence, no `role_mismatch`/leak/
  check is ever produced by them, `--no-builtin-hints` offers nothing, and the
  people.csv inspect template carries the suggestions on `sex`/`diagnosis`.
* T81 — the pins: RUN_TABLE_SHA and TEMPLATE_SHA keep their values (run never
  reads a pack; the opt-in template embeds no pack output), TEMPLATE_SHA2 and
  BUILTIN_PACK_SHA are re-pinned (the pack bytes change on purpose and
  people.csv's `sex`/`diagnosis` gain `_suggest`/`_candidates` in the
  default-on template), the pack version claims 1.7.0 and the application
  version 0.8.2, `run` still imports none of the hint machinery, `scan` stays
  unimported by run/plan/inspect/audit, and the eight frozen cores
  (config, engine, audit, derived, chartable, hidden_chars, hintpack, cli)
  plus `chartable_v1.json` stay byte-identical.
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

import sieve_crowd
from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SEX_NAMES = ["sex", "gender", "性別", "性", "男女", "ジェンダー"]
DX_NAMES = ["diagnosis", "diagnoses", "disease", "condition",
            "病名", "診断", "診断名", "疾患", "疾患名", "傷病名"]
ALL16 = SEX_NAMES + DX_NAMES
SEX_SUGGEST = {"role": "qi", "type": "category"}   # 案 1: no hierarchy (approved)
DX_SUGGEST = {"role": "sensitive"}

# Pins (v0.8.2).  RUN_TABLE_SHA and TEMPLATE_SHA keep their values — run never
# reads a pack and the --no-builtin-hints template embeds no pack output.
RUN_TABLE_SHA = "b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138d8ae040061500e"
TEMPLATE_SHA = "66e7eaf4a42d86b15b422eee39fca550b9c7ada0049ba4b6f7dd31e6cc0c4159"
# Re-pinned for jp-basic 1.7.0: the pack bytes change on purpose (the two
# name-only rules), and people.csv's sex/diagnosis gain _suggest/_candidates
# in the default-on inspect template.  Re-pinned on every pack change.
TEMPLATE_SHA2 = "0d5c35d82dc54004ad7f34b80be69103a80a0d20dccc4dae22f7e6412ba6c657"
BUILTIN_PACK_SHA = "1fae5827a7048ca1e4b92c7d12792a755f5b21e63d6392bc2a1fbdb4e3dc66c4"
CHARTABLE_SHA = "c5ae4757bc9d07a2dcd1507d662460c3412c932d73318e54912569608242e605"
# The frozen cores: byte-for-byte, nothing in v0.8.2 may edit them.
CONFIG_PY_SHA = "3fc0b1f9e95b7f05c88b4bf00f37faa6f529fd9e1c3fa000c54c137bd16d3a3d"
ENGINE_PY_SHA = "d7384c5eb5c6012f731ab9af04e0483ca92316b6b73b980f4a88a3541616dc5d"
AUDIT_PY_SHA = "ccbe07c7f0e1a647bea7b64aaa785264b517484961bfdc6e1a62253ac4f21684"
DERIVED_PY_SHA = "2123cc0d4b2ef5dc5e2ecccf718827512278339e7cf3e02379fa4518e82076f8"
CHARTABLE_PY_SHA = "4a01afa04a9678d86a0562ae48a2b578b2dd547247d941762088fcf32405b7a5"
HIDDEN_CHARS_PY_SHA = "47bd0aa3a83b0b33a39ef8a3d353efd4251f713eefcbfcb834f25317a5a672f5"
HINTPACK_PY_SHA = "8aa8282680f32ccf7c67a5ada9692c82ecd291374db233a7fcab3f19f607267e"
CLI_PY_SHA = "39869af6acbec555a3a93e6df5fa524f48e0f1144f0826083452dc2897101356"


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def _csv(cols):
    """cols: ordered mapping column -> list of values (equal lengths)."""
    n = len(next(iter(cols.values())))
    lines = [",".join(cols)]
    for i in range(n):
        lines.append(",".join(values[i] for values in cols.values()))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _config(roles):
    return json.dumps({"k": 2, "columns": roles}, ensure_ascii=False).encode("utf-8")


def _plan(d, csv_data, cfg_data):
    src = os.path.join(d, "in.csv")
    with open(src, "wb") as fh:
        fh.write(csv_data)
    cfg = os.path.join(d, "c.json")
    with open(cfg, "wb") as fh:
        fh.write(cfg_data)
    fj = os.path.join(d, "f.json")
    if os.path.exists(fj):
        os.unlink(fj)
    rc, out, err = call("plan", src, "-c", cfg, "--findings-json", fj)
    findings = None
    if os.path.exists(fj):
        with open(fj, encoding="utf-8") as fh:
            findings = json.load(fh)
    return rc, out, err, findings


def _cands(findings, col):
    return [(c["rule"], c["evidence"], c["suggest"])
            for c in findings["columns"].get(col, {}).get("candidates", [])]


# --------------------------------------------------------------------------- #
class T78SexAndDiagnosisRules(unittest.TestCase):
    """T78: the two name-only rules — names, ownership, candidates, no
    warnings, --no-builtin-hints, and the people.csv template suggestions."""

    def test_name_counts_ownership_and_version(self):
        from sieve_crowd.hintpack import _norm_name, load_packs
        packs = load_packs([], include_builtin=True)
        self.assertEqual(packs[0].version, "1.7.0")
        rules = {r.id: r for r in packs[0].rules}
        self.assertEqual(len(rules), 16)                     # 14 -> 16
        self.assertEqual(sorted(rules["jp-sex"].column_names), sorted(SEX_NAMES))
        self.assertEqual(sorted(rules["jp-diagnosis"].column_names), sorted(DX_NAMES))
        # closed ownership map: each of the 16 names is owned by its rule
        # alone (normalized), and no other rule carries any of them
        owner: dict = {}
        for r in packs[0].rules:
            for n in r.column_names:
                owner.setdefault(_norm_name(n), set()).add(r.id)
        for n in SEX_NAMES:
            self.assertEqual(owner[_norm_name(n)], {"jp-sex"}, n)
        for n in DX_NAMES:
            self.assertEqual(owner[_norm_name(n)], {"jp-diagnosis"}, n)
        # the two rules carry no value condition, no leak, no check
        self.assertIsNone(rules["jp-sex"].shape)
        self.assertIsNone(rules["jp-sex"].check)
        self.assertFalse(rules["jp-sex"].leak)
        self.assertIsNone(rules["jp-diagnosis"].shape)
        self.assertIsNone(rules["jp-diagnosis"].check)
        self.assertFalse(rules["jp-diagnosis"].leak)

    def test_each_name_fires_exactly_one_candidate(self):
        cols = {n: [f"v{i}" for i in range(30)] for n in ALL16}
        cols["age"] = [str(20 + i % 6) for i in range(30)]
        roles = {n: {"role": "keep"} for n in ALL16}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in SEX_NAMES:
                self.assertEqual(_cands(f, n),
                                 [("jp-sex", "name", SEX_SUGGEST)], n)
            for n in DX_NAMES:
                self.assertEqual(_cands(f, n),
                                 [("jp-diagnosis", "name", DX_SUGGEST)], n)
            # name-only evidence never contradicts a declaration: no
            # role_mismatch anywhere, and the two rules leak and check nothing
            # (the findings JSON carries leaks/checks only when non-empty)
            self.assertEqual([w for w in f["warnings"]
                              if w["code"] == "role_mismatch"], [])
            for n in ALL16:
                self.assertEqual(f["columns"][n].get("leaks", []), [], n)
                self.assertEqual(f["columns"][n].get("checks", []), [], n)

    def test_declared_keep_stays_warning_free(self):
        # the request's wording: the evidence is name-only, so even a keep
        # declaration never turns the proposal into a warning
        cols = {"sex": ["M", "F", "M"], "gender": ["F", "M", "F"],
                "diagnosis": ["flu", "cold", "none"], "condition": ["x", "y", "z"],
                "age": ["20", "30", "40"]}
        roles = {n: {"role": "keep"} for n in ("sex", "gender", "diagnosis",
                                               "condition")}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(f["warnings"], [])
            # the candidates are visible in the findings (plan stdout carries
            # no per-candidate lines) and stay name-only proposals
            self.assertEqual(_cands(f, "sex"), [("jp-sex", "name", SEX_SUGGEST)])
            self.assertEqual(_cands(f, "gender"), [("jp-sex", "name", SEX_SUGGEST)])
            self.assertEqual(_cands(f, "diagnosis"),
                             [("jp-diagnosis", "name", DX_SUGGEST)])
            self.assertEqual(_cands(f, "condition"),
                             [("jp-diagnosis", "name", DX_SUGGEST)])

    def test_fullwidth_and_uppercase_variants_reach_the_names(self):
        cols = {"ＳＥＸ": ["M", "F", "M"], " Gender ": ["F", "M", "F"],
                "ＧＥＮＤＥＲ": ["M", "F", "M"], "性別": ["M", "F", "M"],
                "ＤＩＡＧＮＯＳＩＳ": ["flu", "cold", "none"],
                "DIAGNOSES": ["flu", "cold", "none"],
                " Disease ": ["flu", "cold", "none"], "傷病名": ["flu", "cold", "none"],
                "診断名": ["flu", "cold", "none"], "age": ["20", "30", "40"]}
        roles = {c: {"role": "keep"} for c in cols}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in ("ＳＥＸ", " Gender ", "ＧＥＮＤＥＲ", "性別"):
                self.assertEqual(_cands(f, n), [("jp-sex", "name", SEX_SUGGEST)], n)
            for n in ("ＤＩＡＧＮＯＳＩＳ", "DIAGNOSES", " Disease ", "傷病名", "診断名"):
                self.assertEqual(_cands(f, n),
                                 [("jp-diagnosis", "name", DX_SUGGEST)], n)

    def test_no_builtin_hints_offers_nothing(self):
        cols = {"sex": ["M", "F"], "diagnosis": ["flu", "cold"], "age": ["1", "2"]}
        data = _csv(cols)
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.csv")
            with open(src, "wb") as fh:
                fh.write(data)
            rc, out, _ = call("inspect", src)
            self.assertEqual(rc, 0)
            self.assertIn("hint-pack jp-basic/jp-sex", out)
            self.assertIn("hint-pack jp-basic/jp-diagnosis", out)
            rc, out, _ = call("inspect", src, "--no-builtin-hints")
            self.assertEqual(rc, 0)
            self.assertNotIn("hint-pack", out)
            self.assertNotIn("jp-basic", out)

    def test_people_csv_template_carries_the_suggestions(self):
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.json")
            rc, _, _ = call("inspect", os.path.join(REPO, "examples", "people.csv"),
                            "--config-out", tpl)
            self.assertEqual(rc, 0)
            with open(tpl, encoding="utf-8") as fh:
                t = json.load(fh)
            self.assertEqual(t["columns"]["sex"]["_suggest"], SEX_SUGGEST)
            self.assertEqual(t["columns"]["diagnosis"]["_suggest"], DX_SUGGEST)
            self.assertEqual(t["columns"]["sex"]["_candidates"],
                             [{"pack": "jp-basic", "rule": "jp-sex",
                               "evidence": "name", "suggest": SEX_SUGGEST}])
            self.assertEqual(t["columns"]["diagnosis"]["_candidates"],
                             [{"pack": "jp-basic", "rule": "jp-diagnosis",
                               "evidence": "name", "suggest": DX_SUGGEST}])


# --------------------------------------------------------------------------- #
class T81Pins(unittest.TestCase):
    """T81: golden outputs unchanged, the re-pinned pack/template bytes, the
    version claims, the import blocks, and the eight frozen cores."""

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

    def test_builtin_pack_bytes_and_version_are_pinned(self):
        from sieve_crowd.hintpack import load_packs
        from sieve_crowd.hintpack_builtin import BUILTIN_PACK_BYTES
        self.assertEqual(hashlib.sha256(BUILTIN_PACK_BYTES).hexdigest(),
                         BUILTIN_PACK_SHA)
        packs = load_packs([], include_builtin=True)
        self.assertEqual(packs[0].version, "1.7.0")

    def test_application_version_is_0_8_2(self):
        self.assertEqual(sieve_crowd.__version__, "0.8.2")

    def test_chartable_file_is_pinned(self):
        with open(os.path.join(REPO, "sieve_crowd", "chartable_v1.json"), "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), CHARTABLE_SHA)

    def test_frozen_cores_are_byte_identical(self):
        for rel, sha in (("sieve_crowd/config.py", CONFIG_PY_SHA),
                         ("sieve_crowd/engine.py", ENGINE_PY_SHA),
                         ("sieve_crowd/audit.py", AUDIT_PY_SHA),
                         ("sieve_crowd/derived.py", DERIVED_PY_SHA),
                         ("sieve_crowd/chartable.py", CHARTABLE_PY_SHA),
                         ("sieve_crowd/hidden_chars.py", HIDDEN_CHARS_PY_SHA),
                         ("sieve_crowd/hintpack.py", HINTPACK_PY_SHA),
                         ("sieve_crowd/cli.py", CLI_PY_SHA)):
            with open(os.path.join(REPO, rel), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sha, rel)

    def test_import_blocks_hold(self):
        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")

        def probe(cmd, banned):
            code = (
                "import sys; from sieve_crowd.cli import main; main(%r); "
                "hit = %r & set(sys.modules); "
                "print('OK' if not hit else 'IMPORTED:' + ','.join(sorted(hit)))"
            ) % (cmd, banned)
            out = subprocess.check_output([sys.executable, "-c", code], text=True)
            self.assertIn("OK", out, cmd)
            self.assertNotIn("IMPORTED:", out, cmd)

        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            # run imports none of the hint/derived/audit machinery
            probe(["run", people, "-c", config, "-o", out, "--quiet"],
                  {"sieve_crowd.hintpack", "sieve_crowd.derived", "sieve_crowd.audit",
                   "sieve_crowd.chartable", "sieve_crowd.hidden_chars",
                   "sieve_crowd.scan"})
            # scan stays unimported by run/plan/inspect/audit
            probe(["plan", people, "-c", config], {"sieve_crowd.audit", "sieve_crowd.scan"})
            probe(["inspect", people], {"sieve_crowd.audit", "sieve_crowd.scan"})
            probe(["audit", people, "-c", config], {"sieve_crowd.scan"})


if __name__ == "__main__":
    unittest.main()
