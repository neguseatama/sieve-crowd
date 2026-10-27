import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

from sieve_crowd.cli import main

CSV = "name,age,zip,disease\n" + "".join(
    f"Person{i},{20 + i % 6},{['1500001', '1500002'][i % 2]},{['flu', 'cold', 'none'][i % 3]}\n" for i in range(60))
CONFIG = {"k": 5, "l": 2, "columns": {
    "name": {"role": "id", "action": "drop"},
    "age": {"role": "qi", "type": "numeric", "widths": [5, 10]},
    "zip": {"role": "qi", "type": "prefix", "length": 3},
    "disease": {"role": "sensitive"}}}


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self.csv = self.write("in.csv", CSV.encode())
        self.cfg = self.write("cfg.json", json.dumps(CONFIG).encode())

    def path(self, n):
        return os.path.join(self.d, n)

    def write(self, n, data):
        with open(self.path(n), "wb") as fh:
            fh.write(data)
        return self.path(n)

    def read(self, n):
        with open(self.path(n), "rb") as fh:
            return fh.read()

    def test_run_and_receipt(self):
        rc, _, err = call("run", self.csv, "-c", self.cfg, "-o", self.path("out.csv"),
                          "--report-json", self.path("r.json"))
        self.assertEqual(rc, 0)
        out = self.read("out.csv").decode()
        self.assertTrue(out.startswith("age,zip,disease\n"))
        self.assertNotIn("Person", out)
        self.assertIn("Crowd size", err)
        report = json.loads(self.read("r.json"))
        self.assertGreaterEqual(report["privacy"]["k_achieved"], 5)
        self.assertNotIn(b"Person", self.read("r.json"))

    def test_japanese_report_and_bom_input(self):
        src = self.write("bom.csv", b"\xef\xbb\xbf" + CSV.encode())
        rc, _, err = call("run", src, "-c", self.cfg, "--dry-run", "--lang", "ja")
        self.assertEqual(rc, 0)
        self.assertIn("群れの大きさ", err)
        self.assertFalse(os.path.exists(self.path("out.csv")))

    def test_inspect_writes_a_template_that_run_refuses(self):
        rc, out, _ = call("inspect", self.csv, "--config-out", self.path("t.json"))
        self.assertEqual(rc, 0)
        self.assertIn("name: 60 distinct", out)
        rc, _, err = call("run", self.csv, "-c", self.path("t.json"), "--dry-run")
        self.assertEqual(rc, 2)
        self.assertIn("no role yet", err)

    def test_keygen_and_pseudonymize(self):
        rc, _, _ = call("keygen", "-o", self.path("key.txt"))
        self.assertEqual(rc, 0)
        self.assertEqual(oct(os.stat(self.path("key.txt")).st_mode & 0o777), "0o600")
        rc, _, _ = call("keygen", "-o", self.path("key.txt"))
        self.assertEqual(rc, 1)                                   # never silently replaced
        cfg = json.loads(json.dumps(CONFIG))
        cfg["columns"]["name"] = {"role": "id", "action": "pseudonymize"}
        c2 = self.write("c2.json", json.dumps(cfg).encode())
        rc, _, err = call("run", self.csv, "-c", c2, "--dry-run")
        self.assertEqual(rc, 2)                                   # no key
        rc, _, _ = call("run", self.csv, "-c", c2, "--key-file", self.path("key.txt"),
                        "-o", self.path("out.csv"), "--quiet")
        self.assertEqual(rc, 0)
        self.assertRegex(self.read("out.csv").decode().splitlines()[1], r"^p-[a-z2-7]{16},")

    def test_file_safety(self):
        rc, _, _ = call("run", self.csv, "-c", self.cfg, "-o", self.csv, "--force")
        self.assertEqual(rc, 2)
        self.write("out.csv", b"old")
        rc, _, _ = call("run", self.csv, "-c", self.cfg, "-o", self.path("out.csv"))
        self.assertEqual(rc, 1)
        self.assertEqual(self.read("out.csv"), b"old")
        rc, _, _ = call("run", self.csv, "-c", self.cfg)
        self.assertEqual(rc, 2)                                   # neither -o nor --dry-run

    def test_refused_run_writes_no_table(self):
        rc, _, err = call("run", self.csv, "-c", self.cfg, "-o", self.path("o.csv"), "--k", "500")
        self.assertEqual(rc, 3)
        self.assertFalse(os.path.exists(self.path("o.csv")))
        self.assertIn("refused", err)

    def test_bad_inputs(self):
        rc, _, _ = call("run", self.path("missing.csv"), "-c", self.cfg, "--dry-run")
        self.assertEqual(rc, 1)
        bad = self.write("bad.csv", b"a,b\n1\n")
        rc, _, _ = call("run", bad, "-c", self.cfg, "--dry-run")
        self.assertEqual(rc, 2)
        bin_ = self.write("bin.csv", b"a,b\n\xff,1\n")
        rc, _, _ = call("run", bin_, "-c", self.cfg, "--dry-run")
        self.assertEqual(rc, 2)
        notjson = self.write("n.json", b"{")
        rc, _, _ = call("run", self.csv, "-c", notjson, "--dry-run")
        self.assertEqual(rc, 2)

    def test_keep_order_flag_is_recorded(self):
        rc, _, err = call("run", self.csv, "-c", self.cfg, "--dry-run", "--keep-order")
        self.assertEqual(rc, 0)
        self.assertIn("Relaxations: keep_order", err)


class InspectHintTests(unittest.TestCase):
    def test_hints_template_and_comment_keys(self):
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.csv")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write("name,age,zip,diagnosis,memo\n" + "".join(
                    f"P{i},{20 + i % 7},{1500000 + i % 3},{['flu', 'cold'][i % 2]},m{i}\n" for i in range(40)))
            tpl = os.path.join(d, "t.json")
            rc, out, _ = call("inspect", src, "--config-out", tpl)
            self.assertEqual(rc, 0)
            self.assertIn("postal codes: type prefix", out)
            self.assertIn("usually role sensitive", out)
            self.assertIn("every value is different", out)          # memo: no keyword, all unique
            with open(tpl, encoding="utf-8") as fh:
                t = json.load(fh)
            self.assertIn("_hint", t["columns"]["name"])
            self.assertEqual(t["columns"]["name"]["role"], "?")
            t["_note"] = "comments are ignored"
            t["columns"]["name"]["role"] = "drop"
            t["columns"]["age"].update(role="qi", type="numeric", widths=[5, 10])
            t["columns"]["zip"].update(role="qi", type="prefix", length=3)
            t["columns"]["diagnosis"]["role"] = "sensitive"
            t["columns"]["memo"]["role"] = "drop"
            t["k"], t["l"] = 3, 2
            cfg = os.path.join(d, "c.json")
            with open(cfg, "w", encoding="utf-8") as fh:
                json.dump(t, fh)
            rc, _, err = call("run", src, "-c", cfg, "--dry-run")
            self.assertEqual(rc, 0)
            self.assertIn("Before:", err)


if __name__ == "__main__":
    unittest.main()
