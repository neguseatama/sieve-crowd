"""v0.7.2 pin tests (T51).

The run path and the opt-in template are unchanged by the pack work:
RUN_TABLE_SHA and TEMPLATE_SHA keep their values, ``run`` still imports none
of the hint/derived/audit machinery, and the four frozen cores stay
byte-for-byte.  TEMPLATE_SHA2 and BUILTIN_PACK_SHA carry the latest re-pin (jp-basic 1.4.0,
v0.7.3; v0.7.2 re-pinned them to 1.3.0 for jp-person-name and jp-address) —
the pack additions change the pack bytes and, through the default-on inspect
template (people.csv gains the jp-zip-hyphen candidate on its zip column),
the template bytes on purpose.
"""
import contextlib
import hashlib
import io
import os
import subprocess
import sys
import tempfile
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Golden SHAs, re-pinned for v0.7.3 (RUN_TABLE_SHA and TEMPLATE_SHA unchanged).
RUN_TABLE_SHA = "b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138d8ae040061500e"
TEMPLATE_SHA = "66e7eaf4a42d86b15b422eee39fca550b9c7ada0049ba4b6f7dd31e6cc0c4159"
# jp-basic 1.4.0: both pins change on purpose (id suggestions on the four
# rules, the requested column names, jp-zip-hyphen; the zip column of
# people.csv gains the jp-zip-hyphen candidate).
TEMPLATE_SHA2 = "870a30b80ad93021160c38e38c5c0841234d7dc0035556b9fa5f6703d177d07b"
BUILTIN_PACK_SHA = "f164af7018e8cfa2d08ead08f79d16b125bda2128c2fc2c30b1918e0812fd235"
CHARTABLE_SHA = "c5ae4757bc9d07a2dcd1507d662460c3412c932d73318e54912569608242e605"
# The frozen cores: byte-for-byte, nothing in v0.7.2 may edit them.
CONFIG_PY_SHA = "3fc0b1f9e95b7f05c88b4bf00f37faa6f529fd9e1c3fa000c54c137bd16d3a3d"
ENGINE_PY_SHA = "d7384c5eb5c6012f731ab9af04e0483ca92316b6b73b980f4a88a3541616dc5d"
AUDIT_PY_SHA = "ccbe07c7f0e1a647bea7b64aaa785264b517484961bfdc6e1a62253ac4f21684"
DERIVED_PY_SHA = "2123cc0d4b2ef5dc5e2ecccf718827512278339e7cf3e02379fa4518e82076f8"


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class T51Pins(unittest.TestCase):
    """T51: golden outputs, frozen cores, run import block, pack bytes."""

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
        self.assertEqual(packs[0].version, "1.4.0")

    def test_chartable_file_is_pinned(self):
        with open(os.path.join(REPO, "sieve_crowd", "chartable_v1.json"), "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), CHARTABLE_SHA)

    def test_run_imports_none_of_the_hint_machinery(self):
        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            code = (
                "import sys; from sieve_crowd.cli import main; "
                "main(%r); hit = %r & set(sys.modules); "
                "print('OK' if not hit else 'IMPORTED:' + ','.join(sorted(hit)))"
            ) % (["run", people, "-c", config, "-o", out, "--quiet"],
                 {"sieve_crowd.hintpack", "sieve_crowd.derived", "sieve_crowd.audit",
                  "sieve_crowd.chartable", "sieve_crowd.hidden_chars"})
            out = subprocess.check_output([sys.executable, "-c", code], text=True)
            self.assertIn("OK", out)
            self.assertNotIn("IMPORTED:", out)

    def test_frozen_cores_are_byte_identical(self):
        for rel, sha in (("sieve_crowd/config.py", CONFIG_PY_SHA),
                         ("sieve_crowd/engine.py", ENGINE_PY_SHA),
                         ("sieve_crowd/audit.py", AUDIT_PY_SHA),
                         ("sieve_crowd/derived.py", DERIVED_PY_SHA)):
            with open(os.path.join(REPO, rel), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sha, rel)


if __name__ == "__main__":
    unittest.main()
