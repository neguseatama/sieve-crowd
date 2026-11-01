"""Hint-pack tests (T1–T13).

T1 pins the run path byte-for-byte: ``run`` never imports :mod:`hintpack`, and
its output table is the v0.4.0 golden (sha256-pinned).  The remaining tests
cover the opt-in feature on ``inspect`` / ``plan`` only.
"""
import contextlib
import hashlib
import io
import json
import os
import sys
import tempfile
import unittest

from sieve_crowd.cli import main
from sieve_crowd.config import parse_config
from sieve_crowd.generalize import make_generalizer
from sieve_crowd.hintpack import _compile_shape, load_packs, scan
from sieve_crowd.model import ConfigError

# Golden sha256 captured from v0.4.0 (run path unchanged; T1 pins it).
RUN_TABLE_SHA = "b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138d8ae040061500e"
# v0.4.0 inspect template (--config-out without hint packs). Since v0.5.1 the
# byte-exact route is reached with --no-builtin-hints (T4/T14); value unchanged.
TEMPLATE_SHA = "66e7eaf4a42d86b15b422eee39fca550b9c7ada0049ba4b6f7dd31e6cc0c4159"
# New pin (v0.5.1): the default-on (builtin loaded) inspect template, people.csv.
TEMPLATE_SHA2 = "06bb4afaad3b7d8d2967842e2a95a5ef6df3a5932a58f67fe9469ea199fbad7b"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        try:
            rc = main(list(argv))
        except SystemExit as exc:          # argparse exits (e.g. --hint-pack on run)
            rc = exc.code if isinstance(exc.code, int) else 2
    return rc, out.getvalue(), err.getvalue()


def _write(d, name, data):
    p = os.path.join(d, name)
    with open(p, "wb") as fh:
        fh.write(data)
    return p


def _minimal_pack(d, name="m.json"):
    """A valid pack whose single rule matches no real column — a carrier so
    that ``--hint-pack`` is given (and the builtin loads unless suppressed)."""
    return _write(d, name, json.dumps(
        {"schema": 1, "id": "minimal", "rules": [
            {"id": "noop", "when": {"column_names": ["__none__"]}}]}).encode())


# --------------------------------------------------------------------------- #
class T1RunUnchanged(unittest.TestCase):
    def test_run_table_matches_golden_sha(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.csv")
            rc, _, _ = call("run", os.path.join(REPO, "examples", "people.csv"),
                            "-c", os.path.join(REPO, "examples", "config.json"),
                            "-o", out, "--quiet")
            self.assertEqual(rc, 0)
            with open(out, "rb") as fh:
                digest = hashlib.sha256(fh.read()).hexdigest()
            self.assertEqual(digest, RUN_TABLE_SHA)

    def test_run_never_imports_hintpack(self):
        import subprocess
        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")
        code = (
            "import sys, os, tempfile; "
            "from sieve_crowd.cli import main; "
            "d = tempfile.mkdtemp(); o = os.path.join(d, 'o.csv'); "
            "main(['run', %r, '-c', %r, '-o', o, '--quiet']); "
            "print('HINTPACK_IMPORTED' if 'sieve_crowd.hintpack' in sys.modules else 'OK')"
        ) % (people, config)
        out = subprocess.check_output([sys.executable, "-c", code], text=True)
        self.assertIn("OK", out)
        self.assertNotIn("HINTPACK_IMPORTED", out)


class T2RunRejectsHintPack(unittest.TestCase):
    def test_run_has_no_hint_pack_flag(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, err = call("run", os.path.join(REPO, "examples", "people.csv"),
                              "-c", os.path.join(REPO, "examples", "config.json"),
                              "--dry-run", "--hint-pack", "/dev/null")
        self.assertEqual(rc, 2)
        self.assertIn("unrecognized arguments", err)


class T3PackLoading(unittest.TestCase):
    def test_utf8_sig_bom_pack_reads(self):
        pack = b"\xef\xbb\xbf" + json.dumps(
            {"schema": 1, "id": "bom", "rules": [
                {"id": "r1", "when": {"column_names": ["x"]}, "leak": True}]}
        ).encode()
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "bom.json", pack)
            packs = load_packs([p], include_builtin=False)
        self.assertEqual([x.id for x in packs], ["bom"])

    def test_bad_json_and_schema_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = _write(d, "bad.json", b"{not json")
            with self.assertRaises(ConfigError):
                load_packs([p], include_builtin=False)
            p2 = _write(d, "sch.json", json.dumps(
                {"schema": 2, "id": "x", "rules": [{"id": "r", "when": {"column_names": ["a"]}}]}).encode())
            with self.assertRaises(ConfigError):
                load_packs([p2], include_builtin=False)
            with self.assertRaises(ConfigError):
                load_packs([os.path.join(d, "missing.json")], include_builtin=False)


class T4TemplateByteEquality(unittest.TestCase):
    # v0.5.1: the default is builtin-on (A), so the v0.4.0 byte-exact template
    # route is reached with --no-builtin-hints; the TEMPLATE_SHA value is unchanged.
    def test_template_without_pack_matches_golden(self):
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.json")
            call("inspect", os.path.join(REPO, "examples", "people.csv"),
                 "--config-out", tpl, "--no-builtin-hints")
            with open(tpl, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), TEMPLATE_SHA)

    def test_template_with_pack_adds_suggest_only_to_candidate_columns(self):
        with tempfile.TemporaryDirectory() as d:
            pack = _write(d, "p.json", json.dumps(
                {"schema": 1, "id": "p", "rules": [
                    {"id": "zip", "when": {"column_names": ["zip"], "value_shape": "#{7}"},
                     "suggest": {"role": "qi", "type": "prefix", "length": 4}}]}).encode())
            tpl = os.path.join(d, "t.json")
            call("inspect", os.path.join(REPO, "examples", "people.csv"),
                 "--config-out", tpl, "--hint-pack", pack, "--no-builtin-hints")
            with open(tpl) as fh:
                t = json.load(fh)
            # candidate column gains _suggest / _candidates
            self.assertIn("_suggest", t["columns"]["zip"])
            self.assertEqual(t["columns"]["zip"]["_suggest"]["length"], 4)
            # non-candidate column is unchanged (role + _hint only, no _suggest)
            self.assertNotIn("_suggest", t["columns"]["name"])
            self.assertNotIn("_candidates", t["columns"]["name"])


class T5SuggestAppears(unittest.TestCase):
    """A pack rule that matches a column offers a suggestion (red-first: was
    absent before the hint-pack feature)."""
    def test_suggest_for_matching_column(self):
        csv = b"name,zip\nA,1500001\nB,1500002\nC,1500003\n"
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            pack = _write(d, "p.json", json.dumps(
                {"schema": 1, "id": "p", "rules": [
                    {"id": "zip", "when": {"column_names": ["zip"], "value_shape": "#{7}"},
                     "suggest": {"role": "qi", "type": "prefix", "length": 4}}]}).encode())
            tpl = os.path.join(d, "t.json")
            rc, out, _ = call("inspect", src, "--config-out", tpl, "--hint-pack", pack,
                              "--no-builtin-hints")
            self.assertEqual(rc, 0)
            self.assertIn("hint-pack p/zip", out)
            with open(tpl) as fh:
                t = json.load(fh)
            self.assertEqual(t["columns"]["zip"]["_suggest"],
                             {"role": "qi", "type": "prefix", "length": 4})


class T6LeakCheck(unittest.TestCase):
    """A Luhn-passing card-shaped value in a scanned column is a leak (count, no value).
    v0.5.1 (B): only keep/sensitive/qi columns are scanned on plan, so the card
    column is declared qi here; T15 pins the role scoping itself."""
    def test_card_leak_counted_without_value(self):
        # 4242424242424242 passes Luhn; the leak count is reported, never the value.
        csv = b"memo,card\nx,4242424242424242\ny,4242424242424242\nz,not-a-card\n"
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            cfg = _write(d, "c.json", json.dumps(
                {"k": 2, "columns": {"memo": {"role": "qi", "type": "exact"},
                                     "card": {"role": "qi", "type": "exact"}}}).encode())
            pack = _write(d, "p.json", json.dumps(
                {"schema": 1, "id": "p", "rules": [
                    {"id": "card", "when": {"value_shape": "#{13,19}"},
                     "check": {"kind": "luhn"}, "leak": True}]}).encode())
            fj = _write(d, "f.json", b"")
            rc, _, _ = call("plan", src, "-c", cfg, "--hint-pack", pack,
                            "--no-builtin-hints", "--findings-json", fj, "--quiet")
            self.assertEqual(rc, 0)
            with open(fj) as fh:
                f = json.load(fh)
            leaks = f["columns"]["card"]["leaks"]
            self.assertEqual(leaks[0]["count"], 2)
            # no cell value anywhere in the findings
            with open(fj) as fh:
                self.assertNotIn("4242424242424242", fh.read())


class T7ValueShape(unittest.TestCase):
    def test_shape_atoms_and_quantifiers(self):
        seven = _compile_shape("#{7}")
        self.assertTrue(seven.match("1500001"))
        self.assertFalse(seven.match("1500001".replace("0", "a")))  # not digits
        ph = _compile_shape("#{2,4}-#{3,4}-#{4}")
        self.assertTrue(ph.match("03-1234-5678"))
        self.assertFalse(ph.match("03-1234-567"))          # too short after last -
        letter = _compile_shape("@{3}")
        self.assertTrue(letter.match("ABC"))
        self.assertFalse(letter.match("AB1"))
        esc = _compile_shape("\\###")                      # literal '#', then 2 digits
        self.assertTrue(esc.match("#12"))
        self.assertFalse(esc.match("12"))                  # missing literal '#'

    def test_shape_three_valued_via_scan(self):
        csv = b"col\n1500001\nabc\nxyz\n"
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            pack = _write(d, "p.json", json.dumps(
                {"schema": 1, "id": "p", "rules": [
                    {"id": "s", "when": {"value_shape": "#{7}"},
                     "check": {"kind": "set", "values": ["1500001"]}}]}).encode())
            from sieve_crowd.engine import inspect_table
            from sieve_crowd.tableio import read_any
            with open(src, "rb") as fh:
                header, rows = read_any(fh.read(), "csv", None)
            packs = load_packs([pack], include_builtin=False)
            f = scan(header, rows, inspect_table(header, rows), packs)
            chk = f.columns["col"].checks[0]
            # set: 1500001 in set -> match; abc, xyz not in set -> mismatch.
            self.assertEqual(chk["match"], 1)
            self.assertEqual(chk["mismatch"], 2)
            self.assertEqual(chk["cannot_check"], 0)


class T8SetRangeChecks(unittest.TestCase):
    def test_set_and_range_aggregates(self):
        csv = "pref,age\n東京都,40\n大阪府,150\nUnknown,5\n,\n".encode()
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            pack = _write(d, "p.json", json.dumps(
                {"schema": 1, "id": "p", "rules": [
                    {"id": "pref", "when": {"column_names": ["pref"]},
                     "check": {"kind": "set", "values": ["東京都", "大阪府"]}},
                    {"id": "age", "when": {"column_names": ["age"]},
                     "check": {"kind": "range", "min": 0, "max": 120}}]}).encode())
            from sieve_crowd.engine import inspect_table
            from sieve_crowd.tableio import read_any
            with open(src, "rb") as fh:
                header, rows = read_any(fh.read(), "csv", None)
            packs = load_packs([pack], include_builtin=False)
            f = scan(header, rows, inspect_table(header, rows), packs)
            pref = next(c for c in f.columns["pref"].checks if c["rule"] == "pref")
            self.assertEqual(pref["match"], 2)            # 東京都, 大阪府
            self.assertEqual(pref["mismatch"], 1)         # Unknown
            self.assertEqual(pref["cannot_check"], 1)     # empty
            age = next(c for c in f.columns["age"].checks if c["rule"] == "age")
            self.assertEqual(age["match"], 2)             # 40, 5
            self.assertEqual(age["mismatch"], 1)          # 150
            self.assertEqual(age["cannot_check"], 1)      # empty


class T9CheckVectors(unittest.TestCase):
    def test_luhn_vectors(self):
        from sieve_crowd.hintpack import _luhn
        self.assertTrue(_luhn("4242424242424242"))   # Stripe test card (valid)
        self.assertFalse(_luhn("4242424242424241"))  # one digit off (invalid)

    def test_my_number_vectors(self):
        from sieve_crowd.hintpack import _my_number_ok
        # 11-digit body 12345678901 -> check digit 8 (official residue-11 algorithm).
        self.assertTrue(_my_number_ok("123456789018"))
        self.assertFalse(_my_number_ok("123456789019"))   # wrong check digit
        self.assertFalse(_my_number_ok("1234567890"))      # too short

    def test_email_shape_vectors(self):
        from sieve_crowd.hintpack import _EMAIL
        self.assertTrue(_EMAIL.match("a@example.co"))
        self.assertFalse(_EMAIL.match("not-an-email"))


class T10SuggestPin(unittest.TestCase):
    """jp-basic jp-zip suggests prefix length 4 -> PrefixGen levels 5;
    the coarsest non-trivial level is 150**** (the next is *)."""
    def test_zip_suggest_prefixgen(self):
        packs = load_packs([], include_builtin=True)
        jp = next(p for p in packs if p.id == "jp-basic")
        rule = next(r for r in jp.rules if r.id == "jp-zip")
        self.assertEqual(rule.suggest, {"role": "qi", "type": "prefix", "length": 4})
        g = make_generalizer({k: v for k, v in rule.suggest.items() if k != "role"})
        self.assertEqual(g.levels, 5)
        self.assertEqual(g.label("1500001", 4), "150****")   # coarsest non-trivial
        self.assertEqual(g.label("1500001", 5), "*")         # the next (final) level

    def test_prefecture_hierarchy_is_a_valid_generalizer(self):
        packs = load_packs([], include_builtin=True)
        jp = next(p for p in packs if p.id == "jp-basic")
        rule = next(r for r in jp.rules if r.id == "jp-prefecture")
        g = make_generalizer({k: v for k, v in rule.suggest.items() if k != "role"})
        self.assertEqual(g.levels, 2)                       # value -> region -> *
        self.assertEqual(g.label("東京都", 1), "関東")
        self.assertEqual(g.label("三重県", 1), "近畿")       # 案 A: 三重 = 近畿
        self.assertEqual(g.label("新潟県", 1), "中部")       # 案 A: 新潟 = 中部


class T11ParseConfigPasses(unittest.TestCase):
    """A template carrying _suggest / _candidates (after the user fills roles)
    passes parse_config: the _ keys are stripped, not rejected as unknown."""
    def test_suggest_keys_stripped(self):
        tmpl = {
            "k": 5, "l": 1, "max_suppression": 0.05,
            "columns": {
                "zip": {"role": "qi", "type": "prefix", "length": 4,
                        "_suggest": {"role": "qi", "type": "prefix", "length": 4},
                        "_candidates": [{"pack": "jp-basic", "rule": "jp-zip",
                                         "evidence": "name+value"}]},
                "name": {"role": "id", "action": "drop"},
            },
        }
        cfg = parse_config(tmpl)   # must not raise on the _ keys
        self.assertIn("zip", cfg.columns)


class T12FindingsNoCellValues(unittest.TestCase):
    def test_role_mismatch_and_no_values(self):
        # zip is declared 'keep' but jp-basic suggests 'qi' (evidence name+value).
        # age is qi so the config is valid (parse_config needs >= 1 qi column).
        csv = b"name,zip,age\nA,1500001,40\nB,1500002,40\nC,1500003,40\n"
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            cfg = _write(d, "c.json", json.dumps(
                {"k": 2, "columns": {"name": {"role": "id", "action": "drop"},
                                     "zip": {"role": "keep"},
                                     "age": {"role": "qi", "type": "numeric", "widths": [5, 10]}}}).encode())
            m = _minimal_pack(d)
            fj = _write(d, "f.json", b"")
            rc, _, err = call("plan", src, "-c", cfg, "--hint-pack", m,
                              "--findings-json", fj, "--quiet")
            self.assertEqual(rc, 0)
            with open(fj) as fh:
                raw = fh.read()
            f = json.loads(raw)
            codes = [w["code"] for w in f["warnings"]]
            self.assertIn("role_mismatch", codes)
            # no cell value leaks into findings
            for v in ("1500001", "1500002", "1500003"):
                self.assertNotIn(v, raw)

    def test_mixed_form_and_era_warnings(self):
        # full-width and half-width digits in one value; a Japanese-era value.
        csv = "col\n１２abc\n令和5年\n100\n".encode()
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            cfg = _write(d, "c.json", json.dumps(
                {"k": 2, "columns": {"col": {"role": "qi", "type": "exact"}}}).encode())
            m = _minimal_pack(d)
            fj = _write(d, "f.json", b"")
            call("plan", src, "-c", cfg, "--hint-pack", m, "--no-builtin-hints",
                 "--findings-json", fj, "--quiet")
            with open(fj) as fh:
                f = json.load(fh)
            codes = [w["code"] for w in f["warnings"]]
            self.assertIn("mixed_form", codes)
            self.assertIn("japanese_era", codes)


class T13NoBuiltinAndDuplicates(unittest.TestCase):
    # NOTE (v0.5.1): load order is builtin first, then the command-line order,
    # so test_multiple_packs_compose expects ["jp-basic", "extra"] (was the reverse).
    def test_no_builtin_hints_excludes_jp_basic(self):
        # A user pack alone, with --no-builtin-hints: jp-basic is absent.
        csv = b"zip\n1500001\n"
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            cfg = _write(d, "c.json", json.dumps(
                {"k": 2, "columns": {"zip": {"role": "qi", "type": "prefix", "length": 4}}}).encode())
            pack = _write(d, "p.json", json.dumps(
                {"schema": 1, "id": "only", "rules": [
                    {"id": "z", "when": {"column_names": ["zip"]},
                     "suggest": {"role": "id"}}]}).encode())
            fj = _write(d, "f.json", b"")
            call("plan", src, "-c", cfg, "--hint-pack", pack, "--no-builtin-hints",
                 "--findings-json", fj, "--quiet")
            with open(fj) as fh:
                f = json.load(fh)
            self.assertEqual(f["packs"], ["only"])

    def test_duplicate_pack_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = _write(d, "a.json", json.dumps(
                {"schema": 1, "id": "dup", "rules": [
                    {"id": "r", "when": {"column_names": ["x"]}}]}).encode())
            p2 = _write(d, "b.json", json.dumps(
                {"schema": 1, "id": "dup", "rules": [
                    {"id": "r2", "when": {"column_names": ["y"]}}]}).encode())
            with self.assertRaises(ConfigError):
                load_packs([p1, p2], include_builtin=False)

    def test_multiple_packs_compose(self):
        csv = b"zip\n1500001\n"
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            cfg = _write(d, "c.json", json.dumps(
                {"k": 2, "columns": {"zip": {"role": "qi", "type": "prefix", "length": 4}}}).encode())
            p1 = _write(d, "a.json", json.dumps(
                {"schema": 1, "id": "extra", "rules": [
                    {"id": "z", "when": {"column_names": ["zip"]},
                     "suggest": {"role": "id"}}]}).encode())
            fj = _write(d, "f.json", b"")
            call("plan", src, "-c", cfg, "--hint-pack", p1, "--findings-json", fj, "--quiet")
            with open(fj) as fh:
                f = json.load(fh)
            # v0.5.1 load order: builtin first, then the command-line order (T18 pins pack_info likewise)
            self.assertEqual(f["packs"], ["jp-basic", "extra"])


class T14DefaultOn(unittest.TestCase):
    """A (v0.5.1): the builtin jp-basic pack is loaded by default on inspect/plan.
    --no-builtin-hints keeps the byte-exact v0.4.0 route (TEMPLATE_SHA, value
    unchanged); the default-on template has its own new pin (TEMPLATE_SHA2).
    The leading pack line and pack_info are pinned in T18 (item D)."""

    CSV = b"zip\n1500001\n"
    CFG = json.dumps({"k": 2, "columns": {"zip": {"role": "qi", "type": "prefix", "length": 4}}}).encode()

    def test_default_on_inspect_suggests_builtin(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            rc, out, _ = call("inspect", src)
            self.assertEqual(rc, 0)
            self.assertIn("hint-pack jp-basic/jp-zip", out)   # builtin candidate offered

    def test_default_on_plan_reads_builtin(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            cfg = _write(d, "c.json", self.CFG)
            fj = _write(d, "f.json", b"")
            rc, _, err = call("plan", src, "-c", cfg, "--findings-json", fj, "--quiet")
            self.assertEqual(rc, 0, err)
            with open(fj) as fh:
                f = json.load(fh)
            self.assertEqual(f["packs"], ["jp-basic"])        # builtin loaded without options
            self.assertEqual(err, "")                          # quiet plan stays silent (no pack line)

    def test_no_builtin_hints_template_still_golden(self):
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.json")
            call("inspect", os.path.join(REPO, "examples", "people.csv"),
                 "--config-out", tpl, "--no-builtin-hints")
            with open(tpl, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), TEMPLATE_SHA)

    def test_default_on_template_is_pinned(self):
        with tempfile.TemporaryDirectory() as d:
            tpl = os.path.join(d, "t.json")
            call("inspect", os.path.join(REPO, "examples", "people.csv"), "--config-out", tpl)
            with open(tpl, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), TEMPLATE_SHA2)

    def test_hint_pack_file_adds_to_builtin(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            pack = _write(d, "p.json", json.dumps(
                {"schema": 1, "id": "p", "rules": [
                    {"id": "r", "when": {"column_names": ["__none__"]}}]}).encode())
            fj = _write(d, "f.json", b"")
            call("inspect", src, "--hint-pack", pack, "--findings-json", fj)
            with open(fj) as fh:
                f = json.load(fh)
            self.assertEqual(f["packs"], ["jp-basic", "p"])   # builtin + the given pack


class T15LeakRoles(unittest.TestCase):
    """B (v0.5.1): the leak scan follows declared roles on plan — only
    keep/sensitive/qi columns are scanned (id/drop are not), and a stderr
    warning line plus a findings.warnings element (code leak) appear when a
    count is 1 or more.  Inspect has no roles: every column is recorded in
    findings, there is no stderr leak line and no leak in warnings, and the
    candidates-format stdout line carries the count instead."""

    CSV = ("memo,secret,age\n"
           "call 03-1234-5678 please,03-1234-5678,40\n"
           "nothing here,plain text,41\n").encode()
    CFG = json.dumps({"k": 2, "columns": {
        "memo": {"role": "keep"},
        "secret": {"role": "id", "action": "drop"},
        "age": {"role": "qi", "type": "numeric", "widths": [5, 10]}}}).encode()

    def test_plan_scans_keep_sensitive_qi_only_and_warns(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            cfg = _write(d, "c.json", self.CFG)
            fj = _write(d, "f.json", b"")
            rc, out, err = call("plan", src, "-c", cfg, "--findings-json", fj)
            self.assertEqual(rc, 0)
            with open(fj) as fh:
                f = json.load(fh)
            memo = f["columns"]["memo"]
            leak = next(l for l in memo["leaks"] if l["rule"] == "jp-phone")
            self.assertEqual(leak["count"], 1)
            self.assertEqual(leak["checked"], 2)            # both non-empty cells scanned
            self.assertEqual(memo["declared_role"], "keep") # new key (plan only)
            # secret is id/drop: not scanned at all — no leaks, no declared_role
            self.assertNotIn("leaks", f["columns"].get("secret", {}))
            self.assertNotIn("declared_role", f["columns"].get("secret", {}))
            codes = [w["code"] for w in f["warnings"]]
            self.assertIn("leak", codes)
            w = next(w for w in f["warnings"] if w["code"] == "leak")
            self.assertEqual((w["column"], w["rule"], w["count"]), ("memo", "jp-phone", 1))
            self.assertIn('leak: "memo"', err)               # stderr warning line
            self.assertIn("may contain jp-basic/jp-phone", err)
            self.assertNotIn("03-1234-5678", err)            # no cell value anywhere
            with open(fj) as fh:
                self.assertNotIn("03-1234-5678", fh.read())

    def test_inspect_records_all_columns_without_stderr_warning(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            fj = _write(d, "f.json", b"")
            rc, out, err = call("inspect", src, "--findings-json", fj)
            self.assertEqual(rc, 0)
            with open(fj) as fh:
                f = json.load(fh)
            self.assertIn("leaks", f["columns"]["memo"])
            self.assertIn("leaks", f["columns"]["secret"])   # inspect records every column
            self.assertNotIn("declared_role", f["columns"]["memo"])
            self.assertNotIn("leak", [w["code"] for w in f["warnings"]])
            self.assertNotIn('leak: "memo"', err)            # no stderr leak line on inspect
            self.assertIn("may contain jp-basic/jp-phone", out)  # stdout line, candidate format
            self.assertNotIn("03-1234-5678", out)


class T16SubstringScan(unittest.TestCase):
    """B (v0.5.1): leak rules match tokens inside prose.  A token is a run of
    ASCII alphanumerics plus - + @ . _ %; whitespace and punctuation separate
    tokens; a dashed token is also tried without its dashes, so formatted
    numbers (03-1234-5678, 4242-4242-4242-4242) reach the digit shapes/checks.
    Space-separated phone pieces stay separate tokens and are NOT detected
    (documented constraint).  Cells over 4096 chars are skipped (counted)."""

    PROSE = ("memo,age\n"
             "連絡先は03-1234-5678まで,40\n"
             "email: a@example.co.jp,41\n"
             "card 4242-4242-4242-4242 ok,42\n"
             "no. 123456789018,43\n").encode()
    CFG = json.dumps({"k": 2, "columns": {
        "memo": {"role": "qi", "type": "exact"},
        "age": {"role": "qi", "type": "numeric", "widths": [5, 10]}}}).encode()

    def _leaks_for(self, csv):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", csv)
            cfg = _write(d, "c.json", self.CFG)
            fj = _write(d, "f.json", b"")
            rc, _, err = call("plan", src, "-c", cfg, "--findings-json", fj, "--quiet")
            self.assertEqual(rc, 0, err)
            with open(fj) as fh:
                f = json.load(fh)
            return f["columns"]["memo"].get("leaks", [])

    def test_numbers_inside_prose_are_detected(self):
        rules = {l["rule"]: l["count"] for l in self._leaks_for(self.PROSE)}
        for rule in ("jp-phone", "jp-email", "jp-card", "jp-mynumber"):
            self.assertGreaterEqual(rules.get(rule, 0), 1, rule)
        self.assertEqual(rules.get("jp-phone"), 1)          # one cell carries a phone

    def test_whitespace_separated_phone_is_not_detected(self):
        csv = b"memo,age\ncall 03 1234 5678 today,40\nnothing,41\n"
        rules = {l["rule"]: l["count"] for l in self._leaks_for(csv)}
        self.assertNotIn("jp-phone", rules)                  # separate tokens never combine

    def test_oversized_cells_are_skipped(self):
        long_cell = "x" * 5000 + " 0312345678"               # > 4096 chars, holds a phone
        csv = ("memo,age\n" + long_cell + ",40\ncall 0312345678 now,41\n").encode()
        leaks = self._leaks_for(csv)
        phone = next(l for l in leaks if l["rule"] == "jp-phone")
        self.assertEqual(phone["count"], 1)                  # only the small cell counted
        self.assertEqual(phone["checked"], 1)
        self.assertEqual(phone["skipped"], 1)                # oversized cell: skipped, counted


class T17DuplicateIdsRefused(unittest.TestCase):
    """C (v0.5.1): no silent override of ids.  Pack ids and rule ids are unique
    across the whole set, builtin included; --no-builtin-hints is the way to
    replace the builtin.  Messages name files and ids, never cell values."""

    CSV = b"zip\n1500001\n"
    CFG = json.dumps({"k": 2, "columns": {"zip": {"role": "qi", "type": "prefix", "length": 4}}}).encode()

    def test_pack_id_clash_with_builtin_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            cfg = _write(d, "c.json", self.CFG)
            pack = _write(d, "mypack.json", json.dumps(
                {"schema": 1, "id": "jp-basic", "rules": [
                    {"id": "mine", "when": {"column_names": ["zip"]},
                     "suggest": {"role": "id"}}]}).encode())
            rc, _, err = call("plan", src, "-c", cfg, "--hint-pack", pack, "--quiet")
            self.assertEqual(rc, 2)                     # ConfigError -> EXIT_CONFIG
            self.assertIn('pack id "jp-basic" is already used by the built-in pack', err)
            self.assertIn("--no-builtin-hints", err)
            self.assertIn("mypack.json", err)
            self.assertNotIn("1500001", err)            # no cell value in the message

    def test_no_builtin_hints_allows_reusing_jp_basic(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            cfg = _write(d, "c.json", self.CFG)
            pack = _write(d, "mypack.json", json.dumps(
                {"schema": 1, "id": "jp-basic", "rules": [
                    {"id": "mine", "when": {"column_names": ["zip"]},
                     "suggest": {"role": "id"}}]}).encode())
            fj = _write(d, "f.json", b"")
            rc, _, err = call("plan", src, "-c", cfg, "--hint-pack", pack, "--no-builtin-hints",
                              "--findings-json", fj, "--quiet")
            self.assertEqual(rc, 0, err)
            with open(fj) as fh:
                f = json.load(fh)
            self.assertEqual(f["packs"], ["jp-basic"])   # the user copy, builtin absent

    def test_rule_id_clash_with_builtin_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            cfg = _write(d, "c.json", self.CFG)
            pack = _write(d, "mypack.json", json.dumps(
                {"schema": 1, "id": "mine", "rules": [
                    {"id": "jp-phone", "when": {"column_names": ["zip"]}}]}).encode())
            rc, _, err = call("plan", src, "-c", cfg, "--hint-pack", pack, "--quiet")
            self.assertEqual(rc, 2)
            self.assertIn('rule id "jp-phone" is already used by the built-in pack', err)
            self.assertIn("--no-builtin-hints", err)

    def test_rule_id_clash_between_user_packs_refused(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            cfg = _write(d, "c.json", self.CFG)
            p1 = _write(d, "a.json", json.dumps(
                {"schema": 1, "id": "a", "rules": [
                    {"id": "shared", "when": {"column_names": ["zip"]}}]}).encode())
            p2 = _write(d, "b.json", json.dumps(
                {"schema": 1, "id": "b", "rules": [
                    {"id": "shared", "when": {"column_names": ["zip"]}}]}).encode())
            rc, _, err = call("plan", src, "-c", cfg, "--hint-pack", p1, "--hint-pack", p2, "--quiet")
            self.assertEqual(rc, 2)
            self.assertIn('rule id "shared" is already used by pack "a"', err)

    def test_pack_id_clash_between_user_packs_names_the_first_file(self):
        with tempfile.TemporaryDirectory() as d:
            p1 = _write(d, "a.json", json.dumps(
                {"schema": 1, "id": "dup", "rules": [
                    {"id": "r", "when": {"column_names": ["x"]}}]}).encode())
            p2 = _write(d, "b.json", json.dumps(
                {"schema": 1, "id": "dup", "rules": [
                    {"id": "r2", "when": {"column_names": ["y"]}}]}).encode())
            with self.assertRaises(ConfigError) as cm:
                load_packs([p1, p2], include_builtin=False)
            self.assertIn('pack id "dup" is already used by pack "dup"', str(cm.exception))
            self.assertIn("b.json", str(cm.exception))   # names the duplicate file (full path)


class T18PackInfo(unittest.TestCase):
    """D (v0.5.1): findings gains a top-level pack_info list — one element per
    loaded pack ({id, version, source, sha256}) in load order (builtin, then
    the command-line order).  packs stays a plain list of strings, so existing
    readers are unchanged.  The leading one-line pack note (recommended) is
    pinned here too."""

    CSV = b"zip\n1500001\n"

    def test_pack_info_shape_version_source_sha(self):
        with tempfile.TemporaryDirectory() as d:
            pack = _write(d, "mypack.json", json.dumps(
                {"schema": 1, "id": "mypack", "version": "0.1.0", "rules": [
                    {"id": "r", "when": {"column_names": ["__none__"]}}]}).encode())
            src = _write(d, "in.csv", self.CSV)
            fj = _write(d, "f.json", b"")
            call("inspect", src, "--hint-pack", pack, "--findings-json", fj)
            with open(fj) as fh:
                f = json.load(fh)
            info = f["pack_info"]
            self.assertEqual([p["id"] for p in info], ["jp-basic", "mypack"])  # load order
            b = info[0]
            self.assertEqual(b["source"], "builtin")
            self.assertEqual(b["version"], "1.0.0")
            self.assertEqual(set(b), {"id", "version", "source", "sha256"})
            m = info[1]
            self.assertEqual(m["source"], "file")
            self.assertEqual(m["version"], "0.1.0")
            with open(pack, "rb") as fh:
                self.assertEqual(m["sha256"], hashlib.sha256(fh.read()).hexdigest())

    def test_pack_info_stable_across_runs_and_packs_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            fj1 = _write(d, "f1.json", b"")
            fj2 = _write(d, "f2.json", b"")
            call("inspect", src, "--findings-json", fj1)
            call("inspect", src, "--findings-json", fj2)
            with open(fj1) as fh:
                f1 = json.load(fh)
            with open(fj2) as fh:
                f2 = json.load(fh)
            self.assertEqual(f1["pack_info"], f2["pack_info"])   # same input -> same bytes
            self.assertEqual(f1["packs"], ["jp-basic"])          # packs stays a string list

    def test_leading_pack_line(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            rc, out, _ = call("inspect", src)
            self.assertEqual(rc, 0)
            self.assertTrue(out.startswith("hint packs: jp-basic (builtin)\n"))
            rc, out, _ = call("inspect", src, "--lang", "ja")
            self.assertTrue(out.startswith("ヒントパック: jp-basic (内蔵)\n"))
            # --no-builtin-hints and no pack: no pack line (v0.4.0 output)
            rc, out, err = call("inspect", src, "--no-builtin-hints")
            self.assertNotIn("hint packs:", out)
            self.assertNotIn("ヒントパック:", out)


class T19SentinelsAndPins(unittest.TestCase):
    """T19 (v0.5.1): no cell value (sentinel) appears anywhere in the new
    outputs (findings, warning lines, candidate/leak lines, pack line, template),
    and the run pins (RUN_TABLE_SHA, run-never-imports-hintpack) are unchanged."""

    SENTINELS = ("03-1234-5678", "0312345678", "4242-4242-4242-4242",
                 "4242424242424242", "123456789018", "a@example.co.jp")
    CSV = ("memo,secret,age\n"
           "call 03-1234-5678 please,03-1234-5678,40\n"
           "card 4242-4242-4242-4242,123456789018,41\n"
           "mail a@example.co.jp,x,42\n").encode()
    CFG = json.dumps({"k": 2, "columns": {
        "memo": {"role": "keep"},
        "secret": {"role": "id", "action": "drop"},
        "age": {"role": "qi", "type": "numeric", "widths": [5, 10]}}}).encode()

    def _sentinel_free(self, *texts):
        for s in self.SENTINELS:
            for t in texts:
                self.assertNotIn(s, t, s)

    def test_no_cell_values_in_any_new_output(self):
        with tempfile.TemporaryDirectory() as d:
            src = _write(d, "in.csv", self.CSV)
            cfg = _write(d, "c.json", self.CFG)
            fj = _write(d, "f.json", b"")
            rc, out, err = call("plan", src, "-c", cfg, "--findings-json", fj)
            self.assertEqual(rc, 0)
            with open(fj) as fh:
                self._sentinel_free(out, err, fh.read())
            # inspect too: stdout, stderr, findings, and the template
            # (the template path must NOT pre-exist: --config-out refuses existing files)
            tpl = os.path.join(d, "t.json")
            rc, out, err = call("inspect", src, "--config-out", tpl, "--findings-json", fj)
            self.assertEqual(rc, 0)
            with open(fj) as fh, open(tpl) as fh2:
                self._sentinel_free(out, err, fh.read(), fh2.read())

    def test_run_table_and_import_block_unchanged(self):
        # explicit re-pin of T1 for v0.5.1 (run is untouched by A/B/C/D)
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.csv")
            rc, _, _ = call("run", os.path.join(REPO, "examples", "people.csv"),
                            "-c", os.path.join(REPO, "examples", "config.json"),
                            "-o", out, "--quiet")
            self.assertEqual(rc, 0)
            with open(out, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), RUN_TABLE_SHA)
        import subprocess
        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")
        code = (
            "import sys, os, tempfile; "
            "from sieve_crowd.cli import main; "
            "d = tempfile.mkdtemp(); o = os.path.join(d, 'o.csv'); "
            "main(['run', %r, '-c', %r, '-o', o, '--quiet']); "
            "print('HINTPACK_IMPORTED' if 'sieve_crowd.hintpack' in sys.modules else 'OK')"
        ) % (people, config)
        out = subprocess.check_output([sys.executable, "-c", code], text=True)
        self.assertIn("OK", out)
        self.assertNotIn("HINTPACK_IMPORTED", out)


if __name__ == "__main__":
    unittest.main()
