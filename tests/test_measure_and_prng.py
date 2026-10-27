import unittest

from sieve_crowd.measure import measure
from sieve_crowd.prng import SplitMix64


class PrngTests(unittest.TestCase):
    def test_reference_vectors(self):
        r = SplitMix64(0)
        self.assertEqual([r.next_u64() for _ in range(3)],
                         [0xE220A8397B1DCDAF, 0x6E789E6AA1B965F4, 0x06C45D188009454F])

    def test_shuffle_is_a_deterministic_permutation(self):
        a, b, c = list(range(50)), list(range(50)), list(range(50))
        SplitMix64(3).shuffle(a); SplitMix64(3).shuffle(b); SplitMix64(4).shuffle(c)
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertEqual(sorted(a), list(range(50)))


class MeasureTests(unittest.TestCase):
    def test_k_diversity_and_risk(self):
        header = ["a", "b", "s"]
        rows = [["x", "1", "u"], ["x", "1", "v"], ["x", "1", "u"], ["y", "2", "u"], ["y", "2", "u"]]
        m = measure(header, rows, ["a", "b"], ["s"])
        self.assertEqual((m["k"], m["crowds"], m["smallest_crowds"]), (2, 2, [2, 3]))
        self.assertEqual(m["diversity"], {"s": 1})
        self.assertAlmostEqual(m["max_risk"], 0.5)
        self.assertAlmostEqual(m["average_risk"], 0.4)
        self.assertEqual(m["records_in_crowd_of_1"], 0)

    def test_unicode_forms_are_one_value(self):
        ga_nfc, ga_nfd = "\u304c", "\u304b\u3099"
        m = measure(["a", "s"], [[ga_nfc, "1"], [ga_nfd, "2"]], ["a"], ["s"])
        self.assertEqual((m["k"], m["diversity"]["s"]), (2, 2))


if __name__ == "__main__":
    unittest.main()
