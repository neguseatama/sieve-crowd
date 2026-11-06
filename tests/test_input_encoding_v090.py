"""Character-code policy of the input layer (T82..T88, v0.9.0).

T82 is the 金型 (golden mould): the UTF-8 family -- a plain UTF-8 file, a
BOM-prefixed UTF-8 file and an ASCII-only file -- must keep producing the
byte-identical outputs of v0.8.2 through every subcommand, with no encoding
notice on stderr.  The goldens below were measured on the v0.8.2 tree
(unittest, in-process main()); they are never predicted.

T83..T88 pin the series-wide character-code policy (design 3.1):

    auto = BOM UTF-8 (utf-8-sig) -> strict UTF-8 -> strict CP932 -> refuse.

  T83  a CP932 CSV (①㈱髙...) reads as the same table as its UTF-8 twin;
       outputs are byte-identical, only the stderr notice differs
  T84  bytes that are neither UTF-8 nor CP932 -> exit 1, the code
       unsupported_encoding only, no file written, no U+FFFD anywhere
  T85  the detection order is fixed and deterministic
  T86  --encoding pins the codec (no auto fall-through); unknown names exit 2
  T87  UTF-16 / UTF-32 BOMs are refused as unsupported_encoding
  T88  exactly one stderr notice line when CP932 is adopted, none for the
       UTF-8 family, and the notice never reaches results/receipts/HTML
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
PEOPLE = os.path.join(REPO, "examples", "people.csv")
CONFIG = os.path.join(REPO, "examples", "config.json")

# Goldens.  inspect stdout and the run output are byte-identical to v0.8.2
# (measured on the untouched tree and re-measured at 0.9.0: same values --
# the run output equals the RUN_TABLE_SHA pin).  plan / audit stderr and the
# scan HTML carry the "Sieve Crowd <version>" line, so those four pins were
# re-measured at 0.9.0 on the UTF-8 family (the T79 note: re-pin on every
# version bump).  The BOM scan pin is its own because the page carries the
# input SHA-256.
GOLDEN_INSPECT_PEOPLE = ("acea6c5a20350210f5d04d94edd94e3ae316d477"
                         "e11a88bd18a46c9e0e53404b")     # = v0.8.2 value
GOLDEN_RUN_PEOPLE = ("b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138"
                     "d8ae040061500e")           # = the RUN_TABLE_SHA pin
GOLDEN_PLAN_PEOPLE = ("3deb5a9331af3ac99814c576f5ac10ab53a1ad2193273170c"
                      "a3832f8b38ac426")
GOLDEN_AUDIT_PEOPLE = ("6cdc6afd90f68d2c41488c47729107761f6742c3668bc3144"
                       "a62e0478482dc2f")
GOLDEN_SCAN_PEOPLE_EN = ("81e0d25211201056e8573f819a50476046a8ddf41a6636c"
                         "fc1531460db951d9a")  # = SCAN_SHA_EN at 0.9.0
GOLDEN_SCAN_PEOPLE_BOM = ("b2fdf286d0ace551a69793dbfa9eefa9da02ed857c2f655"
                          "a095f11a7c0f36a24")
# the non-ASCII UTF-8 twin (名前/住所/年齢 with ①㈱髙); its CP932 twin must
# produce the same table (T83), so its outputs are pinned here too
GOLDEN_INSPECT_JP = ("cce5efebeeb10765f5f879413ccff357e948f22cef5640dcba1a"
                     "1a3d37aa93c0")
GOLDEN_RUN_JP = ("3c503d87eb50033c7514a33101a99a554667619a370989ace0d1ff42"
                 "14a2e5dc")
GOLDEN_PLAN_JP = ("28f1a2f8089dae4e6056112f452cc5bcdac487de8c4c73605334b6"
                  "561351c0b9")
GOLDEN_AUDIT_JP = ("08cedc70f3b8ddedb2d1d6b57514756d62b3e32f676fce62f07dd"
                   "6aea08baf3a")

NOTICE_CP932_AUTO = "input encoding: cp932 (auto)"
NOTICE_CP932_SPEC = "input encoding: cp932 (specified)"

JP_ROWS = [
    ["名前", "住所", "年齢"],
    ["髙橋 ①郎", "㈱東京都港区①-1", "40"],
    ["鈴木実", "大阪府大阪市南区㈱-2", "23"],
    ["佐藤花子", "北海道札幌市①丁目", "35"],
]


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def cli(argv, stdin_bytes=None):
    """In-process main(); returns (code, stdout_bytes, stderr_bytes).

    argparse usage errors raise SystemExit(2), which is folded into the
    return code like a real process exit.
    """
    out, err = io.StringIO(), io.StringIO()
    code = 0
    if stdin_bytes is not None:
        old_stdin = sys.stdin
        sys.stdin = io.TextIOWrapper(io.BytesIO(stdin_bytes), encoding="utf-8")
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = main(argv)
        except SystemExit as exc:              # argparse usage error
            code = exc.code if isinstance(exc.code, int) else 2
        finally:
            sys.stdin = old_stdin
    else:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = main(argv)
            except SystemExit as exc:          # argparse usage error
                code = exc.code if isinstance(exc.code, int) else 2
    return code, out.getvalue().encode("utf-8"), err.getvalue().encode("utf-8")


def subproc(argv, stdin_bytes=None):
    """Subprocess main() for stdin reads; same triple as cli()."""
    p = subprocess.run([sys.executable, "-m", "sieve_crowd"] + argv,
                       cwd=REPO, input=stdin_bytes, capture_output=True)
    return p.returncode, p.stdout, p.stderr


def write(path, data):
    with open(path, "wb") as fh:
        fh.write(data)
    return path


class T82GoldenMould(unittest.TestCase):
    """金型: UTF-8 family outputs stay byte-identical to v0.8.2."""

    def test_plain_utf8_and_bom_and_ascii_are_byte_identical(self):
        # examples/people.csv is pure ASCII (verified when the goldens were
        # measured), so it is simultaneously the UTF-8 and the ASCII-only
        # case; the BOM copy covers the utf-8-sig case.
        with tempfile.TemporaryDirectory() as d:
            # keep the basename people_bom.csv: the scan page carries the
            # input file name, so the BOM pin was measured under this name
            with open(PEOPLE, "rb") as fh:
                bom = write(os.path.join(d, "people_bom.csv"),
                            b"\xef\xbb\xbf" + fh.read())
            for path in (PEOPLE, bom):
                code, out, err = cli(["inspect", path])
                self.assertEqual(code, 0)
                self.assertEqual(sha256_bytes(out), GOLDEN_INSPECT_PEOPLE)
                self.assertNotIn(b"input encoding:", err)
            for path in (PEOPLE, bom):
                out_csv = os.path.join(d, "o_" + os.path.basename(path))
                code, _, err = cli(["run", path, "-c", CONFIG,
                                    "-o", out_csv, "--quiet"])
                self.assertEqual(code, 0)
                self.assertEqual(sha256_file(out_csv), GOLDEN_RUN_PEOPLE)
                self.assertNotIn(b"input encoding:", err)
            for path in (PEOPLE, bom):
                code, _, err = cli(["plan", path, "-c", CONFIG])
                self.assertEqual(code, 0)
                self.assertEqual(sha256_bytes(err), GOLDEN_PLAN_PEOPLE)
                self.assertNotIn(b"input encoding:", err)
                code, _, err = cli(["audit", path, "-c", CONFIG])
                self.assertEqual(code, 0)
                self.assertEqual(sha256_bytes(err), GOLDEN_AUDIT_PEOPLE)
                self.assertNotIn(b"input encoding:", err)
            pins = {PEOPLE: GOLDEN_SCAN_PEOPLE_EN, bom: GOLDEN_SCAN_PEOPLE_BOM}
            for path, want in pins.items():
                html = os.path.join(d, "s_" + os.path.basename(path) + ".html")
                code, _, _ = cli(["scan", path, "--lang", "en", "-o", html])
                self.assertEqual(code, 0)
                self.assertEqual(sha256_file(html), want)
                with open(html, "rb") as fh:
                    self.assertNotIn(b"input encoding:", fh.read())


class T83Cp932ReadsAsTheSameTable(unittest.TestCase):
    """CP932 twin == UTF-8 twin as a table; outputs byte-identical."""

    def test_cp932_matches_the_utf8_twin(self):
        utf8_csv = ""
        cp932_csv = ""
        with tempfile.TemporaryDirectory() as d:
            for enc, suffix in (("utf-8", "u"), ("cp932", "c")):
                path = os.path.join(d, f"twin_{suffix}.csv")
                with open(path, "w", encoding=enc, newline="") as fh:
                    for row in JP_ROWS:
                        fh.write(",".join(row) + "\n")
                if enc == "utf-8":
                    utf8_csv = path
                else:
                    cp932_csv = path
            cfg = os.path.join(d, "cfg.json")
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump({"k": 2, "columns": {
                    "名前": {"role": "keep"},
                    "住所": {"role": "keep"},
                    "年齢": {"role": "qi", "type": "numeric",
                             "widths": [5, 10, 20]},
                }}, fh, ensure_ascii=False)
            code, out, _ = cli(["inspect", utf8_csv])
            self.assertEqual((code, sha256_bytes(out)), (0, GOLDEN_INSPECT_JP))
            code, out2, err2 = cli(["inspect", cp932_csv])
            self.assertEqual(code, 0)
            self.assertEqual(out2, out)                    # same table
            self.assertIn(NOTICE_CP932_AUTO.encode(), err2)
            run_out = {}
            for tag, path in (("utf8", utf8_csv), ("cp932", cp932_csv)):
                dest = os.path.join(d, f"run_{tag}.csv")
                code, _, _ = cli(["run", path, "-c", cfg, "-o", dest,
                                  "--quiet"])
                self.assertEqual(code, 0)
                run_out[tag] = sha256_file(dest)
            self.assertEqual(run_out["cp932"], run_out["utf8"])
            self.assertEqual(run_out["utf8"], GOLDEN_RUN_JP)
            for cmd, extra in (("plan", []), ("audit", ["--subject", "名前"])):
                _, _, err_u = cli([cmd, utf8_csv, "-c", cfg] + extra)
                _, _, err_c = cli([cmd, cp932_csv, "-c", cfg] + extra)
                want = GOLDEN_PLAN_JP if cmd == "plan" else GOLDEN_AUDIT_JP
                self.assertEqual(sha256_bytes(err_u), want)
                lines = err_c.split(b"\n")
                self.assertEqual(lines[0], NOTICE_CP932_AUTO.encode())
                self.assertEqual(sha256_bytes(b"\n".join(lines[1:])), want)


class T84RefuseBothEncodings(unittest.TestCase):
    """Undecodable bytes -> exit 1, code only, nothing written."""

    def test_neither_utf8_nor_cp932(self):
        # 0xE9 is a CP932 lead byte, but 0x2C cannot trail it, and 0xE9 alone
        # is not valid UTF-8 either: both candidates fail.
        data = b"caf\xe9,name\n1,x\n"
        code, out, err = subproc(["inspect", "-"], stdin_bytes=data)
        self.assertEqual(code, 1)
        self.assertEqual(err, b"error: unsupported_encoding\n")
        self.assertNotIn("�".encode(), err)
        with tempfile.TemporaryDirectory() as d:
            src = write(os.path.join(d, "bad.csv"), data)
            dest = os.path.join(d, "out.csv")
            code, _, err = cli(["run", src, "-c", CONFIG, "-o", dest,
                                "--quiet"])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: unsupported_encoding\n")
            self.assertFalse(os.path.exists(dest))     # nothing is written
            code, _, err = cli(["scan", src, "-o", os.path.join(d, "s.html")])
            self.assertEqual(code, 1)
            self.assertEqual(err, b"error: unsupported_encoding\n")
            self.assertFalse(os.path.exists(os.path.join(d, "s.html")))


class T85DetectionOrder(unittest.TestCase):
    """BOM utf-8-sig, then strict utf-8, then strict cp932; deterministic."""

    def test_bom_wins_utf8_sig(self):
        data = b"\xef\xbb\xbfname,age\nalice,40\n"
        with tempfile.TemporaryDirectory() as d:
            path = write(os.path.join(d, "bom.csv"), data)
            code, out, err = cli(["inspect", path])
            self.assertEqual(code, 0)
            self.assertNotIn(b"input encoding:", err)
            self.assertIn(b"name:", out)               # BOM stripped cleanly
            self.assertNotIn(b"\xef\xbb\xbf", out)

    def test_utf8_before_cp932_on_dual_decodable_bytes(self):
        # "ああ" is valid UTF-8 (2 chars) AND valid CP932 (3 chars); UTF-8
        # wins, so the header reads ああ, not the CP932 mojibake.
        with tempfile.TemporaryDirectory() as d:
            path = write(os.path.join(d, "dual.csv"),
                         "ああ,x\n1,2\n".encode("utf-8"))
            code, out, err = cli(["inspect", path])
            self.assertEqual(code, 0)
            self.assertNotIn(b"input encoding:", err)
            self.assertIn("ああ".encode(), out)
            self.assertNotIn("縺".encode(), out)

    def test_cp932_only_bytes_reach_cp932(self):
        with tempfile.TemporaryDirectory() as d:
            path = write(os.path.join(d, "cp.csv"),
                         b"name\n\x82\x60\n")   # Ａ fullwidth A, CP932 only
            code, out, err = cli(["inspect", path])
            self.assertEqual(code, 0)
            self.assertIn(NOTICE_CP932_AUTO.encode(), err)

    def test_same_bytes_same_result(self):
        data = "ああ,x\n1,2\n".encode("utf-8")
        with tempfile.TemporaryDirectory() as d:
            path = write(os.path.join(d, "d.csv"), data)
            first = cli(["inspect", path])
            second = cli(["inspect", path])
            self.assertEqual(first, second)


class T86ExplicitEncoding(unittest.TestCase):
    """--encoding pins the codec; no auto fall-through; unknown exits 2."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        self.cp_only = write(os.path.join(d, "cp.csv"), b"name\n\x82\x60\n")
        self.bom = write(os.path.join(d, "bom.csv"),
                         b"\xef\xbb\xbfname,age\nalice,40\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_explicit_cp932_decodes_strictly(self):
        # 0x82 0x60 is Ａ in CP932; put it in the header so inspect shows it
        path = write(os.path.join(self.tmp.name, "hdr.csv"),
                     b"\x82\x60\nx\n")
        code, out, err = cli(["inspect", path, "--encoding", "cp932"])
        self.assertEqual(code, 0)
        self.assertIn("Ａ".encode(), out)

    def test_explicit_utf8_does_not_fall_through(self):
        code, _, err = cli(["inspect", self.cp_only, "--encoding", "utf-8"])
        self.assertEqual(code, 1)
        self.assertEqual(err, b"error: unsupported_encoding\n")

    def test_explicit_utf8_sig_strips_the_bom(self):
        code, out, err = cli(["inspect", self.bom,
                              "--encoding", "utf-8-sig"])
        self.assertEqual(code, 0)
        self.assertIn(b"name:", out)
        self.assertNotIn(b"\xef\xbb\xbf", out)

    def test_explicit_cp932_on_ascii_is_fine(self):
        code, out, err = cli(["inspect", PEOPLE, "--encoding", "cp932"])
        self.assertEqual(code, 0)

    def test_auto_matches_the_default(self):
        a = cli(["inspect", self.cp_only])
        b = cli(["inspect", self.cp_only, "--encoding", "auto"])
        self.assertEqual(a, b)

    def test_unknown_name_exits_2(self):
        for name in ("utf-16", "shift_jis", "sjis", "latin-1"):
            code, _, err = cli(["inspect", self.cp_only, "--encoding", name])
            self.assertEqual(code, 2, name)
            self.assertIn(b"invalid choice", err, name)

    def test_encoding_applies_to_csv_only(self):
        with open(PEOPLE, "rb") as fh:
            data = fh.read()
        code, _, err = cli(["inspect", "-", "--in-format", "json",
                            "--encoding", "cp932"], stdin_bytes=b"[]")
        self.assertEqual(code, 2)
        self.assertIn(b"--encoding applies to csv only", err)


class T87Utf16AndUtf32BomsAreRefused(unittest.TestCase):
    def test_utf16le_utf16be_utf32le_utf32be(self):
        cases = {
            "utf16le": b"\xff\xfe" + "あ".encode("utf-16-le"),
            "utf16be": b"\xfe\xff" + "あ".encode("utf-16-be"),
            "utf32le": b"\xff\xfe\x00\x00" + "あ".encode("utf-32-le"),
            "utf32be": b"\x00\x00\xfe\xff" + "あ".encode("utf-32-be"),
        }
        with tempfile.TemporaryDirectory() as d:
            for tag, data in cases.items():
                path = write(os.path.join(d, tag + ".csv"), data)
                code, _, err = cli(["inspect", path])
                self.assertEqual(code, 1, tag)
                self.assertEqual(err, b"error: unsupported_encoding\n", tag)


class T88NoticeBehaviour(unittest.TestCase):
    """One stderr line when CP932 is adopted; never in results/receipts."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = self.tmp.name
        rows = "\n".join(",".join(r) for r in JP_ROWS) + "\n"
        self.cp = write(os.path.join(d, "t.csv"), rows.encode("cp932"))
        self.u8 = write(os.path.join(d, "u.csv"), rows.encode("utf-8"))
        self.bom = write(os.path.join(d, "b.csv"),
                         b"\xef\xbb\xbf" + rows.encode("utf-8"))
        self.cfg = os.path.join(d, "cfg.json")
        with open(self.cfg, "w", encoding="utf-8") as fh:
            json.dump({"k": 2, "columns": {
                "名前": {"role": "keep"},
                "住所": {"role": "keep"},
                "年齢": {"role": "qi", "type": "numeric",
                         "widths": [5, 10, 20]},
            }}, fh, ensure_ascii=False)

    def tearDown(self):
        self.tmp.cleanup()

    def test_notice_is_one_stderr_line_only_for_cp932(self):
        _, _, err = cli(["inspect", self.cp])
        self.assertEqual(err, (NOTICE_CP932_AUTO + "\n").encode())
        _, _, err = cli(["inspect", self.u8])
        self.assertEqual(err, b"")
        _, _, err = cli(["inspect", self.bom])
        self.assertEqual(err, b"")
        _, _, err = cli(["inspect", self.cp, "--encoding", "cp932"])
        self.assertEqual(err, (NOTICE_CP932_SPEC + "\n").encode())
        _, _, err = cli(["inspect", self.u8, "--encoding", "utf-8"])
        self.assertEqual(err, b"")

    def test_notice_never_reaches_results_receipts_or_html(self):
        out_csv = os.path.join(self.tmp.name, "o.csv")
        findings = os.path.join(self.tmp.name, "f.json")
        report = os.path.join(self.tmp.name, "r.json")
        html = os.path.join(self.tmp.name, "s.html")
        code, _, _ = cli(["run", self.cp, "-c", self.cfg, "-o", out_csv,
                          "--report-json", report, "--quiet"])
        self.assertEqual(code, 0)
        with open(out_csv, "rb") as fh:
            self.assertNotIn(b"input encoding", fh.read())
        with open(report, "rb") as fh:
            self.assertNotIn(b"input encoding", fh.read())
        code, _, _ = cli(["audit", self.cp, "-c", self.cfg,
                          "--findings-json", findings])
        self.assertEqual(code, 0)
        with open(findings, "rb") as fh:
            self.assertNotIn(b"input encoding", fh.read())
        code, _, _ = cli(["scan", self.cp, "--lang", "en", "-o", html])
        self.assertEqual(code, 0)
        with open(html, "rb") as fh:
            self.assertNotIn(b"input encoding", fh.read())


if __name__ == "__main__":
    unittest.main()
