"""scan output pins and the share/boundary tests (T79/T80, v0.8.2).

T79 pins the SHA-256 of the four ``scan`` readings of ``examples/people.csv``
(no config / ``-c examples/config.json`` x ``--lang en`` / ``--lang ja``):

    SCAN_SHA_EN      scan examples/people.csv --lang en
    SCAN_SHA_JA      scan examples/people.csv --lang ja
    SCAN_CFG_SHA_EN  scan examples/people.csv -c examples/config.json --lang en
    SCAN_CFG_SHA_JA  scan examples/people.csv -c examples/config.json --lang ja

RE-PIN ON EVERY VERSION BUMP (the page carries "Sieve Crowd <version>") and
on every change of the builtin pack (the page carries the pack id, version
and sha256 in pack_info), of ``examples/people.csv``, of ``examples/config.json``
or of the scan wording itself.  The values are always re-measured from real
runs, never predicted.  The pinned bytes do not depend on the output path:
``-o`` names the destination only (verified at pin time), so the tests write
to a temporary file.

T79 also fixes the share boundaries as integers: ``_pct`` (the pure
permille -> one-decimal-percent helper) at 0/9/10/99/100/999/1000, and the
bar widths (integer percent, floored — ``rows * 100 // total``, the same
floor a permille takes through ``permille // 10``) at permille 0, 9, 10, 999
and 1000 via three constructed 1000-row tables.

T80 ships the two no-config readings as repository samples
(``docs/samples/people.scan.en.html`` / ``people.scan.ja.html``, the exact
bytes scan writes) and pins their byte-identity plus the README references.
Regenerate the samples on every version bump, next to the T79 re-pin.
"""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest

from sieve_crowd.cli import main
from sieve_crowd.scan import _pct

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEOPLE = os.path.join(REPO, "examples", "people.csv")
CONFIG = os.path.join(REPO, "examples", "config.json")

# The four scan readings of examples/people.csv at Sieve Crowd 0.8.2 with
# builtin jp-basic 1.7.0.  Re-measure on every version/pack/wording change.
SCAN_SHA_EN = "4f64a722dfe3e32c6bcca0606347fc1c5d4ab6cb56acd1d6f742da677de45ba4"
SCAN_SHA_JA = "d107cd8f8aebf8977c41a6005ff1627206d66e6cf3cab6c6feb2575c76be6fd0"
SCAN_CFG_SHA_EN = "208c530d1a675b39b0e6fba7ac9679dc13c4571ca6868e25e75229c5c9e36ec2"
SCAN_CFG_SHA_JA = "e3a1fc40c15d29481d00a4adc83e10d9c4dc459ddf23e4e945cc842f45dcd83d"


def _scan_bytes(*argv):
    """Run scan with -o into a temporary file; return the output bytes."""
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, "page.html")
        err, stdout = io.StringIO(), io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(stdout):
            rc = main(list(argv) + ["-o", out])
        assert rc == 0, (argv, rc, err.getvalue())
        with open(out, "rb") as fh:
            return fh.read()


def _csv1000(sizes):
    """One 'age' column (the jp-age candidate makes it provisional qi) with
    the given group sizes (rows total = sum(sizes))."""
    lines = ["age"]
    for i, size in enumerate(sizes):
        lines.extend([f"g{i}"] * size)
    return ("\n".join(lines) + "\n").encode()


class T79ScanPins(unittest.TestCase):
    """T79: the four pinned scan readings of examples/people.csv."""

    def test_scan_pins_en_ja(self):
        self.assertEqual(hashlib.sha256(
            _scan_bytes("scan", PEOPLE, "--lang", "en")).hexdigest(), SCAN_SHA_EN)
        self.assertEqual(hashlib.sha256(
            _scan_bytes("scan", PEOPLE, "--lang", "ja")).hexdigest(), SCAN_SHA_JA)

    def test_scan_pins_with_the_config(self):
        self.assertEqual(hashlib.sha256(
            _scan_bytes("scan", PEOPLE, "-c", CONFIG,
                        "--lang", "en")).hexdigest(), SCAN_CFG_SHA_EN)
        self.assertEqual(hashlib.sha256(
            _scan_bytes("scan", PEOPLE, "-c", CONFIG,
                        "--lang", "ja")).hexdigest(), SCAN_CFG_SHA_JA)


class T79ShareBoundaries(unittest.TestCase):
    """T79: shares are floored per-mille with one decimal; bars are integer
    percents floored — permille 0/9/10 -> width 0%/0%/1%, 999 -> 99%,
    1000 -> 100%."""

    def test_pct_permille_boundaries(self):
        self.assertEqual(_pct(0), "0.0")
        self.assertEqual(_pct(9), "0.9")
        self.assertEqual(_pct(10), "1.0")
        self.assertEqual(_pct(99), "9.9")
        self.assertEqual(_pct(100), "10.0")
        self.assertEqual(_pct(999), "99.9")
        self.assertEqual(_pct(1000), "100.0")

    def _page(self, tmp_csv_name, data):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, tmp_csv_name)
            with open(src, "wb") as fh:
                fh.write(data)
            out = os.path.join(d, "page.html")
            err, stdout = io.StringIO(), io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(stdout):
                rc = main(["scan", src, "-o", out])
            self.assertEqual(rc, 0, err.getvalue())
            with open(out, encoding="utf-8") as fh:
                return fh.read()

    def test_bar_width_floors_the_permille(self):
        # 999 rows in one group + 1 alone: permille 999 -> 99%, 1 -> 0%,
        # the empty buckets stay 0%
        html = self._page("big.csv", _csv1000([999, 1]))
        self.assertIn('style="width:99%"', html)
        self.assertIn('style="width:0%"', html)
        self.assertNotIn("width:99.9", html)
        # the one-decimal shares render from the same integers: 0.1% alone
        self.assertIn("0.1%", html)
        # everything in one group: permille 1000 -> 100%, below-k 0 -> 0.0%
        html = self._page("big.csv", _csv1000([1000]))
        self.assertIn('style="width:100%"', html)
        self.assertIn("0.0%", html)
        # permille 9 (9 rows in the 5-9 bucket) -> 0%, permille 10 (10
        # singleton rows) -> 1%
        html = self._page("big.csv", _csv1000([1] * 10 + [9] + [109] * 9))
        self.assertIn('style="width:1%"', html)
        self.assertIn('style="width:0%"', html)
        self.assertIn('style="width:98%"', html)   # the 50+ bucket, 981 rows
        self.assertIn("1.0%", html)


class T80Samples(unittest.TestCase):
    """T80: docs/samples carries the two no-config readings byte-exactly,
    and the READMEs point at them.  Regenerate on every version bump."""

    def test_samples_match_the_generated_bytes(self):
        for name, lang in (("people.scan.en.html", "en"),
                           ("people.scan.ja.html", "ja")):
            path = os.path.join(REPO, "docs", "samples", name)
            with open(path, "rb") as fh:
                shipped = fh.read()
            self.assertTrue(shipped.startswith(b"<!DOCTYPE html>"))
            self.assertTrue(shipped.endswith(b"\n"))
            self.assertEqual(hashlib.sha256(shipped).hexdigest(),
                             hashlib.sha256(
                                 _scan_bytes("scan", PEOPLE,
                                             "--lang", lang)).hexdigest(),
                             name)

    def test_readmes_reference_the_samples(self):
        with open(os.path.join(REPO, "README.md"), encoding="utf-8") as fh:
            readme_en = fh.read()
        with open(os.path.join(REPO, "README.ja.md"), encoding="utf-8") as fh:
            readme_ja = fh.read()
        for name in ("docs/samples/people.scan.en.html",
                     "docs/samples/people.scan.ja.html"):
            self.assertIn(name, readme_en, name)
            self.assertIn(name, readme_ja, name)


if __name__ == "__main__":
    unittest.main()
