"""The engine's lattice search against a brute-force oracle written independently."""
import itertools
import math
import random
import unittest
from collections import defaultdict
from fractions import Fraction

from sieve_crowd import Config, anonymize, parse_config
from sieve_crowd.generalize import NumericGen, PrefixGen, CategoryGen

HEADER = ["age", "zip", "sex", "dis"]
COLS = {
    "age": {"role": "qi", "type": "numeric", "widths": [2, 4, 8]},
    "zip": {"role": "qi", "type": "prefix", "length": 2},
    "sex": {"role": "qi", "type": "exact"},
    "dis": {"role": "sensitive"},
}


def make_gens(rows):
    gens = [NumericGen([2, 4, 8]), PrefixGen(2), CategoryGen(None)]
    for i, g in enumerate(gens):
        g.prepare(list(dict.fromkeys(r[i] for r in rows)))
    return gens


def oracle(rows, k, l, ms):
    n = len(rows)
    budget = min(n - 1, math.floor(ms * n))
    gens = make_gens(rows)
    tops = [g.levels for g in gens]

    def suppressed(vec):
        groups = defaultdict(list)
        for r in rows:
            groups[tuple(g.label(r[i], vec[i]) for i, g in enumerate(gens))].append(r[3])
        return sum(len(m) for m in groups.values() if len(m) < k or len(set(m)) < l)

    nodes = list(itertools.product(*[range(t + 1) for t in tops]))
    ok = [v for v in nodes if suppressed(v) <= budget]
    if not ok:
        return None
    best = min(ok, key=lambda v: (sum((Fraction(a, t) for a, t in zip(v, tops)), Fraction(0)), suppressed(v), v))
    return best, suppressed(best), suppressed, nodes, budget


def random_rows(rnd):
    n = rnd.randint(8, 36)
    return [[str(rnd.randint(20, 35)), rnd.choice(["10", "11", "12", "20", "21"]) + rnd.choice("ab"),
             rnd.choice(["F", "M"]), rnd.choice(["x", "y", "z"])] for _ in range(n)]


class OracleTests(unittest.TestCase):
    def test_engine_matches_brute_force(self):
        rnd = random.Random(2026)
        compared = refused = 0
        for _ in range(250):
            rows = random_rows(rnd)
            k, l, ms = rnd.choice([2, 3, 4]), rnd.choice([1, 2]), rnd.choice([0.0, 0.1, 0.25])
            cfg = parse_config({"columns": COLS}, k=k, l=l, max_suppression=ms)
            res = anonymize(HEADER, rows, cfg)
            expected = oracle(rows, k, l, ms)
            if expected is None:
                self.assertEqual((res.status, res.report.data["reason"]), ("refused", "infeasible"))
                refused += 1
                continue
            best, sup, *_ = expected
            self.assertEqual(res.status, "anonymized", (rows, k, l, ms))
            levels = tuple(c["level"] for c in res.report.data["columns"] if c["role"] == "qi")
            self.assertEqual(levels, best)
            self.assertEqual(res.report.data["result"]["suppressed"], sup)
            self.assertEqual(len(res.rows), len(rows) - sup)
            self.assertGreaterEqual(res.report.data["privacy"]["k_achieved"], k)
            compared += 1
        self.assertGreater(compared, 100)

    def test_acceptability_is_monotone(self):
        rnd = random.Random(99)
        for _ in range(60):
            rows = random_rows(rnd)
            k, l, ms = rnd.choice([2, 3]), rnd.choice([1, 2]), rnd.choice([0.0, 0.2])
            _best, _s, suppressed, nodes, budget = oracle(rows, k, l, ms) or (None,) * 5
            if suppressed is None:
                continue
            tops = [t for t in (4, 3, 1)]
            for v in nodes:
                if suppressed(v) <= budget:
                    for i in range(3):
                        if v[i] < tops[i]:
                            w = v[:i] + (v[i] + 1,) + v[i + 1:]
                            self.assertLessEqual(suppressed(w), budget, (v, w))


if __name__ == "__main__":
    unittest.main()
