import random
import unittest

from sieve_crowd.generalize import CategoryGen, DateGen, NumericGen, PrefixGen, make_generalizer
from sieve_crowd.model import ConfigError


class NumericTests(unittest.TestCase):
    def test_integer_ranges_including_negative(self):
        g = NumericGen([5, 10])
        g.prepare(["-3", "34", "35"])
        self.assertEqual([g.label("34", l) for l in range(4)], ["34", "30-34", "30-39", "*"])
        self.assertEqual(g.label("35", 1), "35-39")
        self.assertEqual(g.label("-3", 1), "-5--1")

    def test_decimal_mode_and_missing(self):
        g = NumericGen([10])
        g.prepare(["1.5", "12"])
        self.assertEqual(g.label("1.5", 1), "[0,10)")
        self.assertEqual(g.label("12", 1), "[10,20)")
        self.assertEqual(g.label("", 1), "*")
        self.assertEqual(g.label("abc", 1), "*")

    def test_width_validation(self):
        for bad in ([], [0], [5, 7], [10, 5], [5, 5], [2.5], [True]):
            with self.assertRaises(ConfigError):
                NumericGen(bad)


class DateTests(unittest.TestCase):
    def test_levels(self):
        g = DateGen()
        self.assertEqual([g.label("1994-07-15", l) for l in range(5)],
                         ["1994-07-15", "1994-07", "1994", "1990s", "*"])
        self.assertEqual(g.label("1994-02-30", 1), "*")   # not a real date
        self.assertEqual(g.label("July 1994", 2), "*")


class PrefixTests(unittest.TestCase):
    def test_levels(self):
        g = PrefixGen(3)
        self.assertEqual([g.label("1500001", l) for l in range(5)],
                         ["1500001", "150000*", "15000**", "1500***", "*"])
        self.assertEqual(g.label("12", 2), "**")
        with self.assertRaises(ConfigError):
            PrefixGen(0)


class CategoryTests(unittest.TestCase):
    H = {"Tokyo": ["Kanto", "Japan"], "Saitama": ["Kanto", "Japan"], "Osaka": ["Kansai", "Japan"], "Naha": ["Okinawa"]}

    def test_levels_and_padding(self):
        g = CategoryGen(self.H)
        self.assertEqual(g.levels, 3)
        self.assertEqual([g.label("Tokyo", l) for l in range(4)], ["Tokyo", "Kanto", "Japan", "*"])
        self.assertEqual([g.label("Naha", l) for l in range(4)], ["Naha", "Okinawa", "Okinawa", "*"])
        self.assertEqual(g.label("Paris", 1), "*")   # not in the hierarchy

    def test_exact_has_only_suppression(self):
        g = make_generalizer({"type": "exact"})
        self.assertEqual((g.levels, g.label("x", 0), g.label("x", 1)), (1, "x", "*"))

    def test_inconsistent_or_reserved(self):
        with self.assertRaises(ConfigError):
            CategoryGen({"a": ["X", "P"], "b": ["X", "Q"]})   # group X has two parents
        with self.assertRaises(ConfigError):   # a short chain is padded with its last ancestor; here that clashes
            CategoryGen({"Osaka": ["Kansai", "Japan"], "Kyoto": ["Kansai"]})
        with self.assertRaises(ConfigError):
            CategoryGen({"a": ["*"]})
        with self.assertRaises(ConfigError):
            CategoryGen({"a": []})
        with self.assertRaises(ConfigError):
            make_generalizer({"type": "nope"})


class CoarseningProperty(unittest.TestCase):
    """If two values share a label at level j they share it at every higher level."""

    def check(self, gen, values):
        gen.prepare(values)
        for j in range(gen.levels):
            seen = {}
            for v in values:
                a, b = gen.label(v, j), gen.label(v, j + 1)
                self.assertEqual(seen.setdefault(a, b), b, (j, v))

    def test_random_values(self):
        rnd = random.Random(11)
        ints = [str(rnd.randint(-200, 200)) for _ in range(300)] + [""]
        self.check(NumericGen([2, 10, 20, 100]), ints)
        decs = [f"{rnd.uniform(-50, 50):.2f}" for _ in range(300)]
        self.check(NumericGen([5, 10]), decs)
        dates = [f"{rnd.randint(1950, 2020)}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}" for _ in range(300)] + ["x"]
        self.check(DateGen(), dates)
        words = ["".join(rnd.choice("0123") for _ in range(rnd.randint(1, 5))) for _ in range(300)] + [""]
        self.check(PrefixGen(4), words)
        self.check(CategoryGen(CategoryTests.H), list(CategoryTests.H) + ["Paris"])


if __name__ == "__main__":
    unittest.main()
