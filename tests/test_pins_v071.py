"""v0.7.1 pin tests (T46).

The golden outputs, the frozen cores and the import block are unchanged by the
fold work: ``run`` must never import hintpack/derived/audit/chartable/
hidden_chars, ``plan`` must never import audit, ``inspect`` must never import
audit or hidden_chars, and ``audit`` must never import hintpack/derived/
chartable/hidden_chars.  The builtin pack bytes are re-pinned to jp-basic 1.2.0
(the jp-name-kana addition changes them on purpose).  The shared chartable
file is re-pinned here as well (T40 owns the full content contract).
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

# Golden SHAs, re-pinned for v0.7.1 (unchanged values).
RUN_TABLE_SHA = "b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138d8ae040061500e"
TEMPLATE_SHA = "66e7eaf4a42d86b15b422eee39fca550b9c7ada0049ba4b6f7dd31e6cc0c4159"
TEMPLATE_SHA2 = "4d8db025feae99273c9d4d22bea4af6b937d010d238eb7ad164eecaf6de47ae6"
# jp-basic 1.2.0: the pack bytes change on purpose (jp-name-kana added).
BUILTIN_PACK_SHA = "e863edfcb7597882098b300d7bd7a7a98c185af57bd8a21296bdc7a0f0cab291"
CHARTABLE_SHA = "c5ae4757bc9d07a2dcd1507d662460c3412c932d73318e54912569608242e605"
# The frozen cores: byte-for-byte, nothing in v0.7.1 may edit them.
CONFIG_PY_SHA = "3fc0b1f9e95b7f05c88b4bf00f37faa6f529fd9e1c3fa000c54c137bd16d3a3d"
ENGINE_PY_SHA = "d7384c5eb5c6012f731ab9af04e0483ca92316b6b73b980f4a88a3541616dc5d"
AUDIT_PY_SHA = "ccbe07c7f0e1a647bea7b64aaa785264b517484961bfdc6e1a62253ac4f21684"
DERIVED_PY_SHA = "2123cc0d4b2ef5dc5e2ecccf718827512278339e7cf3e02379fa4518e82076f8"


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class T46Pins(unittest.TestCase):
    """T46: golden outputs, frozen cores, import block, pack bytes."""

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

    def test_builtin_pack_bytes_are_pinned_to_1_2_0(self):
        from sieve_crowd.hintpack_builtin import BUILTIN_PACK_BYTES
        self.assertEqual(hashlib.sha256(BUILTIN_PACK_BYTES).hexdigest(),
                         BUILTIN_PACK_SHA)

    def test_chartable_file_is_pinned(self):
        with open(os.path.join(REPO, "sieve_crowd", "chartable_v1.json"), "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), CHARTABLE_SHA)

    def test_import_block_of_every_subcommand(self):
        def probe(cmd, banned):
            code = (
                "import sys; from sieve_crowd.cli import main; main(%r); "
                "hit = %r & set(sys.modules); "
                "print('OK' if not hit else 'IMPORTED:' + ','.join(sorted(hit)))"
            ) % (cmd, banned)
            out = subprocess.check_output([sys.executable, "-c", code], text=True)
            self.assertIn("OK", out, cmd)
            self.assertNotIn("IMPORTED:", out, cmd)

        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            probe(["run", people, "-c", config, "-o", out, "--quiet"],
                  {"sieve_crowd.hintpack", "sieve_crowd.derived", "sieve_crowd.audit",
                   "sieve_crowd.chartable", "sieve_crowd.hidden_chars"})
            probe(["plan", people, "-c", config], {"sieve_crowd.audit"})
            probe(["inspect", people],
                  {"sieve_crowd.audit", "sieve_crowd.hidden_chars"})
            probe(["audit", people, "-c", config],
                  {"sieve_crowd.hintpack", "sieve_crowd.derived",
                   "sieve_crowd.chartable", "sieve_crowd.hidden_chars"})

    def test_frozen_cores_are_byte_identical(self):
        for rel, sha in (("sieve_crowd/config.py", CONFIG_PY_SHA),
                         ("sieve_crowd/engine.py", ENGINE_PY_SHA),
                         ("sieve_crowd/audit.py", AUDIT_PY_SHA),
                         ("sieve_crowd/derived.py", DERIVED_PY_SHA)):
            with open(os.path.join(REPO, rel), "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), sha, rel)


if __name__ == "__main__":
    unittest.main()
