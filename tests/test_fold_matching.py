"""fold-applied matching tests (T42, v0.7.1).

The hint pack's value matching and the leak scan fold their inputs through the
shared chartable before matching: value_shape and the leak scan use
``dashes=True`` (shape matching), the value checks (set/range/luhn/my_number/
email_shape) use ``dashes=False``.  Full-width digits, full-width symbols,
long-vowel dashes and invisible characters therefore reach the existing
matchers — the v0.5.2 "full-width never matches" documented limitation is
resolved without touching ``engine.py``.

Every test here pins behavior that is NEW (red before the fold commit) or
explicitly UNCHANGED for pure-ASCII input (the last test).
"""
import contextlib
import io
import json
import os
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _cfg(**cols):
    return json.dumps({"k": 3, "columns": cols}, ensure_ascii=False).encode()


QI = {"role": "qi", "type": "exact"}
KEEP = {"role": "keep"}


class T42FoldedMatching(unittest.TestCase):
    """T42: full-width and invisible-laden values now reach the matchers."""

    def test_fullwidth_zip_matches_by_value(self):
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, "zip,age\n\uff11\uff12\uff13\uff14\uff15\uff16\uff17,40\n".encode(),
                _cfg(zip=QI, age=QI))
            self.assertEqual(rc, 0, err)
            cands = {(c["rule"], c["evidence"]) for c in f["columns"]["zip"]["candidates"]}
            self.assertIn(("jp-zip", "name+value"), cands)

    def test_fullwidth_phone_in_prose_is_found_by_leak(self):
        # the SPEC-documented constraint "full-width digits and dashes never
        # form a token" is resolved: the cell is folded before tokenizing
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, "memo,age\n\uff10\uff19\uff10\uff0d\uff11\uff12\uff13\uff14\uff0d\uff15\uff16\uff17\uff18\u3067\u3059,40\n".encode(),
                _cfg(memo=KEEP, age=QI))
            self.assertEqual(rc, 0, err)
            leaks = f["columns"]["memo"]["leaks"]
            self.assertEqual([(l["rule"], l["count"]) for l in leaks],
                             [("jp-phone", 1)])
            self.assertIn("jp-basic/jp-phone", err)

    def test_long_vowel_phone_in_prose_is_found_by_leak(self):
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, "memo,age\n090\u30FC1234\u30FC5678,40\n".encode(),
                _cfg(memo=KEEP, age=QI))
            self.assertEqual(rc, 0, err)
            leaks = f["columns"]["memo"]["leaks"]
            self.assertEqual([(l["rule"], l["count"]) for l in leaks],
                             [("jp-phone", 1)])
            self.assertIn("jp-basic/jp-phone", err)

    def test_fullwidth_email_matches(self):
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, "email,age\n\uff49\uff53\uff4e\uff52\uff20\uff45\uff58\uff41\uff4d\uff50\uff4c\uff45\uff0e\uff43\uff4f\uff4d,40\n".encode(),
                _cfg(email=KEEP, age=QI))
            self.assertEqual(rc, 0, err)
            checks = f["columns"]["email"]["checks"]
            self.assertEqual([(c["rule"], c["kind"], c["match"]) for c in checks],
                             [("jp-email", "email_shape", 1)])
            leaks = f["columns"]["email"]["leaks"]
            self.assertEqual([(l["rule"], l["count"]) for l in leaks],
                             [("jp-email", 1)])

    def test_fullwidth_card_and_my_number_in_prose_are_found(self):
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, ("memo,age\n"
                    "\uff14\uff12\uff14\uff12\uff0d\uff14\uff12\uff14\uff12\uff0d\uff14\uff12\uff14\uff12\uff0d\uff14\uff12\uff14\uff12,40\n"
                    "\uff11\uff12\uff13\uff14\uff15\uff16\uff17\uff18\uff19\uff10\uff11\uff18,40\n").encode(),
                _cfg(memo=KEEP, age=QI))
            self.assertEqual(rc, 0, err)
            leaks = f["columns"]["memo"]["leaks"]
            got = sorted((l["rule"], l["count"]) for l in leaks)
            self.assertEqual(got, [("jp-card", 1), ("jp-mynumber", 1)])
            self.assertIn("jp-basic/jp-card", err)
            self.assertIn("jp-basic/jp-mynumber", err)

    def test_fullwidth_age_reaches_the_range_check(self):
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, "age,zip\n\uff14\uff10,1111111\n".encode(),
                _cfg(age={"role": "qi", "type": "numeric", "widths": [5, 10]}, zip=QI))
            self.assertEqual(rc, 0, err)
            checks = f["columns"]["age"]["checks"]
            self.assertEqual([(c["rule"], c["kind"], c["match"]) for c in checks],
                             [("jp-age", "range", 1)])
            cands = {(c["rule"], c["evidence"]) for c in f["columns"]["age"]["candidates"]}
            self.assertIn(("jp-age", "name+value"), cands)

    def test_invisible_characters_inside_a_value(self):
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, "memo,age\n090\u200B1234\u200B5678,40\n".encode(),
                _cfg(memo=KEEP, age=QI))
            self.assertEqual(rc, 0, err)
            leaks = f["columns"]["memo"]["leaks"]
            self.assertEqual([(l["rule"], l["count"]) for l in leaks],
                             [("jp-phone", 1)])

    def test_pure_ascii_behavior_is_unchanged(self):
        with tempfile_dir() as d:
            rc, _, err, f = _plan(
                d, ("memo,zip,age\n"
                    "call 03-1234-5678 or 4242-4242-4242-4242,1500052,40\n").encode(),
                _cfg(memo=KEEP, zip=QI, age=QI))
            self.assertEqual(rc, 0, err)
            leaks = f["columns"]["memo"]["leaks"]
            self.assertEqual(sorted((l["rule"], l["count"]) for l in leaks),
                             [("jp-card", 1), ("jp-phone", 1)])
            zip_cands = {(c["rule"], c["evidence"])
                         for c in f["columns"]["zip"]["candidates"]}
            self.assertIn(("jp-zip", "name+value"), zip_cands)


class tempfile_dir:
    """Minimal context manager (the suite stays standard-library only)."""

    def __enter__(self):
        import tempfile
        self._tmp = tempfile.TemporaryDirectory()
        return self._tmp.name

    def __exit__(self, *exc):
        self._tmp.cleanup()
        return False


if __name__ == "__main__":
    unittest.main()
