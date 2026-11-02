"""Derived keep-vs-qi relation tests (T22-T25, v0.6.0).

For every (keep column X, qi column Q) pair, evaluated in both directions,
``plan`` classifies the relation:

  - unchecked  s < 50 compared records (MIN_SUPPORT)
  - trivial    a constant column (either side) or every source value unique
               (s - m == 0): the relation carries no information
  - flagged    s >= 50 and s - m > 0 and 100*v <= s and 10*v <= s - m
               (violations v are the records the source value does not pin
               down to one target value; at most 1% of s and at most 10% of
               the excess s - m)
  - clear      checked, but too many violations to warn about

T22 pins the detection table, T23 the threshold boundaries, T24 the scope and
the class invariant, T25 the sentinels (no cell value anywhere), the additive
findings keys, --no-derived, and the run pins (run never imports hintpack or
derived).  The four classes sum to 2 * (pairs - skipped_pairs) for every input.

Test-number note: the request named these T20-T26; T20/T21 were already taken
by v0.5.2 (candidate order, CI contracts), so the block starts at T22.
"""
import contextlib
import hashlib
import io
import json
import os
import random
import subprocess
import sys
import tempfile
import unittest

from sieve_crowd.cli import main
from sieve_crowd.derived import PAIR_LIMIT

# Golden run sha256, re-pinned for v0.6.0 (derived must not touch the run path).
RUN_TABLE_SHA = "b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138d8ae040061500e"

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def analyze(*args, **kwargs):
    from sieve_crowd.derived import analyze as _analyze
    return _analyze(*args, **kwargs)


class T22DerivedDetection(unittest.TestCase):
    """T22: the detection table - one direction, the reverse, both, the
    violation-ratio line (0.5% warns, 2% does not), constant columns and
    no-repeat columns are trivial, and s < 50 is unchecked."""

    def test_one_way_implied_by_qi(self):
        # 100 records: x = i//4 (25 groups of 4), q = i//2 (50 groups of 2).
        # x -> q: every x group mixes two q values -> clear (50 of 100 unpinned).
        # q -> x: every q group is pure -> flagged with 0 violations.
        rows = [[f"g{i // 4}", f"t{i // 2}"] for i in range(100)]
        warnings, summary = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        self.assertEqual(warnings, [{
            "code": "derived", "column": "x", "declared_role": "keep",
            "qi_column": "q", "relation": "implied_by_qi",
            "support": 100, "violations": 0}])
        self.assertEqual(summary, {"pairs": 1, "skipped_pairs": 0,
                                   "unchecked": 0, "trivial": 0,
                                   "flagged": 1, "clear": 1})

    def test_one_way_reveals_qi(self):
        # the transpose: the keep column is now the pure one
        rows = [[f"g{i // 4}", f"t{i // 2}"] for i in range(100)]
        warnings, summary = analyze(["x", "q"], rows, {"x": "qi", "q": "keep"})
        self.assertEqual(len(warnings), 1)
        w = warnings[0]
        self.assertEqual(w["relation"], "reveals_qi")
        self.assertEqual(w["column"], "q")
        self.assertEqual(w["declared_role"], "keep")
        self.assertEqual(w["qi_column"], "x")
        self.assertEqual(w["support"], 100)
        self.assertEqual(w["violations"], 0)
        self.assertEqual(summary["flagged"], 1)
        self.assertEqual(summary["clear"], 1)

    def test_both_directions_flagged_in_order(self):
        # 20 (x, q) pairs, each three times: pure in both directions
        rows = [[f"x{i}", f"q{i}"] for i in range(20)] * 3
        warnings, summary = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        self.assertEqual([w["relation"] for w in warnings],
                         ["reveals_qi", "implied_by_qi"])   # fixed order
        self.assertEqual(summary["flagged"], 2)
        self.assertEqual(summary["clear"], 0)

    def test_violation_ratio_half_percent_warns_two_percent_does_not(self):
        # 200 records, x = i//10 (20 groups of 10); q = x except k flipped
        # records (one in four different groups).  Direction x -> q: v = k.
        # k = 1 (0.5% of s): 100*1 <= 200 and 10*1 <= 180 -> flagged.
        # k = 4 (2% of s): 100*4 = 400 > 200 -> clear.  The reverse direction
        # stays pure (flagged) in both tables - it is not the one under test.
        for flips, expected in ((1, True), (4, False)):
            marked = {0, 50, 100, 150} if flips == 4 else {0}
            rows = [[f"g{i // 10}", "odd" if i in marked else f"g{i // 10}"]
                    for i in range(200)]
            warnings, summary = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
            rel = {w["relation"]: w for w in warnings}
            self.assertEqual("reveals_qi" in rel, expected, f"flips={flips}")
            if expected:
                self.assertEqual(rel["reveals_qi"]["violations"], flips)
                self.assertEqual(rel["reveals_qi"]["support"], 200)

    def test_constant_column_is_trivial(self):
        # a constant keep column: m == 1 in one direction, the target has a
        # single distinct value in the other - the relation says nothing
        rows = [["same", f"t{i // 10}"] for i in range(200)]
        warnings, summary = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        self.assertEqual(warnings, [])
        self.assertEqual(summary["trivial"], 2)      # both directions
        self.assertEqual(summary["flagged"], 0)

    def test_no_repeats_is_trivial(self):
        # every source value unique (s - m == 0) in both directions
        rows = [[f"x{i}", f"q{i}"] for i in range(200)]
        warnings, summary = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        self.assertEqual(warnings, [])
        self.assertEqual(summary["trivial"], 2)

    def test_below_support_is_unchecked(self):
        # a perfectly pure relation over only 49 records: never evaluated
        rows = [[f"g{i // 5}", f"g{i // 5}"] for i in range(49)]
        warnings, summary = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        self.assertEqual(warnings, [])
        self.assertEqual(summary["unchecked"], 2)
        self.assertEqual(summary["flagged"], 0)


class T23DerivedThresholds(unittest.TestCase):
    """T23: the four flagged conditions at their exact boundaries."""

    def test_100v_equal_s_is_flagged(self):
        # 100 records, 10 groups of 10, exactly 1 violation: 100*v == s
        rows = [[f"g{i // 10}", f"g{i // 10}"] for i in range(100)]
        rows[0][1] = "odd"
        warnings, _ = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        rel = {w["relation"]: w for w in warnings}
        self.assertIn("reveals_qi", rel)
        self.assertEqual(rel["reveals_qi"]["violations"], 1)
        self.assertEqual(rel["reveals_qi"]["support"], 100)

    def test_100v_equal_s_plus_one_is_clear(self):
        # 99 records, 10 groups (9x10 + 1x9), exactly 1 violation: 100*v == s + 1
        rows = [[f"g{i // 10}", f"g{i // 10}"] for i in range(99)]
        rows[0][1] = "odd"
        warnings, summary = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        rel = {w["relation"]: w for w in warnings}
        self.assertNotIn("reveals_qi", rel)
        self.assertIn("implied_by_qi", rel)          # the pure side still flags
        self.assertGreaterEqual(summary["clear"], 1)

    def test_10v_equal_s_minus_m_is_flagged(self):
        # 110 records over 100 x-values (10 paired + 90 single), 1 violation
        # in a paired group: s - m == 10 == 10*v -> flagged at the boundary
        xs = [f"g{k}" for k in range(10)] * 2 + [f"s{k}" for k in range(90)]
        rows = [[x, x] for x in xs]
        rows[0][1] = "odd"
        warnings, _ = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        rel = {w["relation"]: w for w in warnings}
        self.assertIn("reveals_qi", rel)
        self.assertEqual(rel["reveals_qi"]["support"], 110)
        self.assertEqual(rel["reveals_qi"]["violations"], 1)

    def test_10v_above_s_minus_m_is_clear(self):
        # 109 records over 100 x-values (9 paired + 91 single), 1 violation:
        # 100*v <= s holds but 10*v == 10 > 9 == s - m -> clear
        xs = [f"g{k}" for k in range(9)] * 2 + [f"s{k}" for k in range(91)]
        rows = [[x, x] for x in xs]
        rows[0][1] = "odd"
        warnings, _ = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        rel = {w["relation"]: w for w in warnings}
        self.assertNotIn("reveals_qi", rel)
        self.assertIn("implied_by_qi", rel)

    def test_support_50_is_checked_49_is_unchecked(self):
        # s == 50: the pure relation is classified (flagged); s == 49: unchecked
        rows50 = [[f"g{i // 5}", f"g{i // 5}"] for i in range(50)]
        w50, summary50 = analyze(["x", "q"], rows50, {"x": "keep", "q": "qi"})
        self.assertEqual(len(w50), 2)
        self.assertEqual(summary50["flagged"], 2)     # classified, both pure
        self.assertEqual(summary50["unchecked"], 0)
        w49, summary49 = analyze(["x", "q"], rows50[:49], {"x": "keep", "q": "qi"})
        self.assertEqual(w49, [])
        self.assertEqual(summary49["unchecked"], 2)
        self.assertEqual(summary49["flagged"], 0)


class T24DerivedScope(unittest.TestCase):
    """T24: only keep x qi pairs, empty cells excluded, row order irrelevant,
    the class invariant, and the pair limit skips the tail."""

    def test_scope_is_keep_times_qi_only(self):
        # sensitive / drop / id never take part, even when the relation is pure
        rows = [[f"p{i // 10}", f"t{i // 10}", f"s{i // 10}", f"d{i // 10}", f"i{i}"]
                for i in range(100)]
        roles = {"p": "keep", "t": "qi", "s": "sensitive", "d": "drop", "i": "id"}
        warnings, summary = analyze(["p", "t", "s", "d", "i"], rows, roles)
        self.assertEqual(summary["pairs"], 1)         # keep(1) x qi(1)
        self.assertEqual({(w["column"], w["qi_column"]) for w in warnings},
                         {("p", "t")})
        self.assertEqual(summary["flagged"], 2)       # p <-> t is pure

    def test_empty_cells_are_excluded(self):
        rows = [[f"g{i // 10}", f"g{i // 10}"] for i in range(100)]
        rows += [["", "g0"], ["g0", ""], ["", ""]]
        warnings, _ = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        rel = {w["relation"]: w for w in warnings}
        self.assertEqual(rel["reveals_qi"]["support"], 100)   # not 103
        self.assertEqual(len(warnings), 2)

    def test_row_order_does_not_matter(self):
        rows = [[f"g{i // 4}", f"t{i // 2}"] for i in range(100)]
        w1, s1 = analyze(["x", "q"], rows, {"x": "keep", "q": "qi"})
        shuffled = rows[:]
        random.Random(7).shuffle(shuffled)
        w2, s2 = analyze(["x", "q"], shuffled, {"x": "keep", "q": "qi"})
        self.assertEqual(w1, w2)
        self.assertEqual(s1, s2)

    def test_class_invariant(self):
        header = ["k1", "k2", "k3", "q1", "q2"]
        rows = [[f"k1_{i // 6}", f"k2_{i % 7}", f"k3_{i}", f"q1_{i // 5}", f"q2_{i % 2}"]
                for i in range(60)]
        roles = {"k1": "keep", "k2": "keep", "k3": "keep", "q1": "qi", "q2": "qi"}
        warnings, summary = analyze(header, rows, roles)
        self.assertEqual(summary["pairs"], 6)
        self.assertEqual(summary["skipped_pairs"], 0)
        self.assertEqual(summary["unchecked"], 0)     # s = 60 everywhere
        self.assertEqual(summary["trivial"], 2)       # k3 is unique: one side each
        total = sum(summary[c] for c in ("unchecked", "trivial", "flagged", "clear"))
        self.assertEqual(total, 2 * (summary["pairs"] - summary["skipped_pairs"]))
        self.assertEqual(len(warnings), summary["flagged"])

    def test_pair_limit_skips_the_tail(self):
        # 21 keep x 20 qi = 420 pairs > PAIR_LIMIT = 400: the tail (k20 x q*)
        # is skipped, and a pure k20/q0 relation therefore raises no warning
        header = [f"k{i}" for i in range(21)] + [f"q{i}" for i in range(20)]
        rows = [[f"k{i // 10}"] * 21 + [f"q{i // 10}"] * 20 for i in range(100)]
        roles = {**{f"k{i}": "keep" for i in range(21)},
                 **{f"q{i}": "qi" for i in range(20)}}
        warnings, summary = analyze(header, rows, roles)
        self.assertEqual(PAIR_LIMIT, 400)
        self.assertEqual(summary["pairs"], 420)
        self.assertEqual(summary["skipped_pairs"], 20)
        total = sum(summary[c] for c in ("unchecked", "trivial", "flagged", "clear"))
        self.assertEqual(total, 2 * PAIR_LIMIT)
        self.assertEqual(len(warnings), summary["flagged"])
        self.assertFalse(any(w["column"] == "k20" for w in warnings))
        self.assertTrue(any(w["column"] == "k19" for w in warnings))


class T25DerivedSentinelsAndPins(unittest.TestCase):
    """T25 (v0.6.0): derived outputs carry no cell values, findings gains keys
    only, --no-derived silences everything derived (also in the no-pack state),
    and the run path (RUN_TABLE_SHA, no hintpack/derived import) is untouched."""

    SENTINELS = ("MZQ3", "ZQ3")
    # memo (keep) and zip (qi) share the grouping -> pure, flagged in both
    # directions; memo x age is clear.  Cell values never leave the table.
    CSV = ("memo,zip,age\n" +
           "".join(f"MZQ{i // 6},ZQ{i // 6},{30 + i % 10}\n" for i in range(60))).encode()
    CFG = json.dumps({"k": 2, "columns": {
        "memo": {"role": "keep"},
        "zip": {"role": "qi", "type": "exact"},
        "age": {"role": "qi", "type": "numeric", "widths": [5, 10]}}}).encode()

    def _plan(self, d, *extra):
        src = os.path.join(d, "in.csv")
        with open(src, "wb") as fh:
            fh.write(self.CSV)
        cfg = os.path.join(d, "c.json")
        with open(cfg, "wb") as fh:
            fh.write(self.CFG)
        fj = os.path.join(d, "f.json")
        rc, out, err = call("plan", src, "-c", cfg, "--findings-json", fj, *extra)
        self.assertEqual(rc, 0)
        with open(fj) as fh:
            raw = fh.read()
        return json.loads(raw), raw, err

    def test_no_cell_values_in_derived_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            f, raw, err = self._plan(d)
            self.assertIn("derived:", err)                       # lines are shown
            for s in self.SENTINELS:
                self.assertNotIn(s, err)
                self.assertNotIn(s, raw)
            rel = {(w["column"], w["relation"]) for w in f["warnings"]
                   if w["code"] == "derived"}
            self.assertIn(("memo", "reveals_qi"), rel)
            self.assertIn(("memo", "implied_by_qi"), rel)
            for w in f["warnings"]:
                if w["code"] == "derived":
                    self.assertEqual(set(w), {"code", "column", "declared_role",
                                              "qi_column", "relation", "support",
                                              "violations"})

    def test_derived_lines_in_both_languages(self):
        with tempfile.TemporaryDirectory() as d:
            _, _, err = self._plan(d)
            self.assertIn('  - derived: "memo" (declared keep) reveals qi "zip": '
                          "support 60, violations 0", err)
            self.assertIn('  - derived: "memo" (declared keep) is implied by qi "zip": '
                          "support 60, violations 0", err)
            self.assertNotIn("Hint pack findings:", err)   # no pack warnings here
        with tempfile.TemporaryDirectory() as d:
            _, _, err = self._plan(d, "--lang", "ja")
            self.assertIn("  - derived: 「memo」（宣言 keep）から準識別子「zip」が"
                          "ほぼ推定できます: 支持 60 件、違反 0 件", err)
            self.assertIn("  - derived: 準識別子「zip」から「memo」（宣言 keep）が"
                          "ほぼ推定できます: 支持 60 件、違反 0 件", err)

    def test_findings_keys_are_additive_and_summary_shape_is_fixed(self):
        with tempfile.TemporaryDirectory() as d:
            f, _, _ = self._plan(d)
            # v0.7.1: the invisible-character scan runs by default on plan, so
            # its summary key joins the additive set (key addition only)
            self.assertEqual(set(f), {"packs", "pack_info", "columns", "warnings",
                                      "derived_summary", "hidden_chars_summary"})
            self.assertEqual(f["derived_summary"],
                             {"pairs": 2, "skipped_pairs": 0, "unchecked": 0,
                              "trivial": 0, "flagged": 2, "clear": 2})

    def test_no_pack_state_still_reports_derived(self):
        # 確認事項 3: without any hint pack the findings JSON is still written
        # (packs: [] / pack_info: []) and carries the derived result
        with tempfile.TemporaryDirectory() as d:
            f, raw, err = self._plan(d, "--no-builtin-hints")
            self.assertEqual(f["packs"], [])
            self.assertEqual(f["pack_info"], [])
            self.assertIn("derived_summary", f)
            self.assertIn("derived:", err)
            for s in self.SENTINELS:
                self.assertNotIn(s, raw)

    def test_no_derived_silences_everything_derived(self):
        with tempfile.TemporaryDirectory() as d:
            f, raw, err = self._plan(d, "--no-derived")
            # v0.7.1: the hidden-character summary stays (independent of derived)
            self.assertEqual(set(f), {"packs", "pack_info", "columns", "warnings",
                                      "hidden_chars_summary"})
            self.assertNotIn("derived_summary", f)
            self.assertNotIn("derived", raw)
            self.assertNotIn("derived:", err)
            for s in self.SENTINELS:
                self.assertNotIn(s, raw)

    def test_run_table_and_import_block_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "out.csv")
            rc, _, _ = call("run", os.path.join(REPO, "examples", "people.csv"),
                            "-c", os.path.join(REPO, "examples", "config.json"),
                            "-o", out, "--quiet")
            self.assertEqual(rc, 0)
            with open(out, "rb") as fh:
                self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), RUN_TABLE_SHA)
        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")
        code = (
            "import sys, os, tempfile; "
            "from sieve_crowd.cli import main; "
            "d = tempfile.mkdtemp(); o = os.path.join(d, 'o.csv'); "
            "main(['run', %r, '-c', %r, '-o', o, '--quiet']); "
            "blocked = {'sieve_crowd.hintpack', 'sieve_crowd.derived'} & set(sys.modules); "
            "print('OK' if not blocked else 'IMPORTED:' + ','.join(sorted(blocked)))"
        ) % (people, config)
        out = subprocess.check_output([sys.executable, "-c", code], text=True)
        self.assertIn("OK", out)
        self.assertNotIn("IMPORTED:", out)


if __name__ == "__main__":
    unittest.main()
