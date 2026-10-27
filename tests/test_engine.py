import base64
import hashlib
import hmac
import json
import unicodedata
import unittest

from sieve_crowd import ConfigError, anonymize, parse_config, parse_key

KEY = "00112233445566778899aabbccddeeff" * 2


def cfg(columns, **kw):
    top = {k: kw.pop(k) for k in ("k", "l", "max_suppression") if k in kw}
    return parse_config({"columns": columns, **top}, **kw)


AGE_ZIP = {
    "age": {"role": "qi", "type": "numeric", "widths": [5, 10]},
    "zip": {"role": "qi", "type": "prefix", "length": 2},
}


class ExactOutputs(unittest.TestCase):
    ROWS = [["30", "123"], ["31", "123"], ["32", "124"], ["33", "124"]]

    def test_minimal_generalization(self):
        r = anonymize(["age", "zip"], self.ROWS, cfg(AGE_ZIP, k=2, max_suppression=0.0, shuffle=False))
        self.assertEqual(r.status, "anonymized")
        self.assertEqual(r.rows, [["30-34", "123"], ["30-34", "123"], ["30-34", "124"], ["30-34", "124"]])
        self.assertEqual(r.report.data["privacy"]["k_achieved"], 2)
        self.assertEqual(r.report.data["relaxations"], ["keep_order"])

    def test_outlier_is_suppressed_within_budget(self):
        rows = self.ROWS + [["70", "999"]]
        r = anonymize(["age", "zip"], rows, cfg(AGE_ZIP, k=2, max_suppression=0.2, shuffle=False))
        self.assertEqual(r.report.data["result"]["suppressed"], 1)
        self.assertEqual(len(r.rows), 4)
        self.assertNotIn("70-74", [x[0] for x in r.rows])

    def test_without_budget_nobody_is_dropped(self):
        rows = self.ROWS + [["70", "999"]]
        r = anonymize(["age", "zip"], rows, cfg(AGE_ZIP, k=2, max_suppression=0.0, shuffle=False))
        self.assertEqual(len(r.rows), 5)
        self.assertGreaterEqual(r.report.data["privacy"]["k_achieved"], 2)


class Roles(unittest.TestCase):
    HEADER = ["name", "age", "dis", "memo", "note"]
    ROWS = [[f"SECRET-NAME-{i}", str(30 + i % 4), "ab"[i % 2], f"MEMO-{i}", f"n{i % 3}"] for i in range(12)]
    COLS = {"name": {"role": "id", "action": "drop"},
            "age": {"role": "qi", "type": "exact"},
            "dis": {"role": "sensitive"},
            "memo": {"role": "drop"},
            "note": {"role": "keep"}}

    def test_columns_and_report_hide_values(self):
        r = anonymize(self.HEADER, self.ROWS, cfg(self.COLS, k=3))
        self.assertEqual(r.header, ["age", "dis", "note"])
        blob = r.report.to_json() + r.report.text("en") + r.report.text("ja") + json.dumps(r.rows)
        for marker in ("SECRET-NAME", "MEMO-"):
            self.assertNotIn(marker, blob)
        note = next(c for c in r.report.data["columns"] if c["name"] == "note")
        self.assertAlmostEqual(note["unique_ratio"], 3 / len(r.rows))

    def test_pseudonyms_are_keyed_and_deterministic(self):
        cols = dict(self.COLS, name={"role": "id", "action": "pseudonymize"})
        key = parse_key(KEY)
        r = anonymize(self.HEADER, self.ROWS, cfg(cols, k=3, key=key, shuffle=False))
        want = "p-" + base64.b32encode(hmac.new(bytes.fromhex(KEY), b"name\0SECRET-NAME-0",
                                                 hashlib.sha256).digest()[:10]).decode().lower()
        self.assertEqual(r.rows[0][0], want)
        other = anonymize(self.HEADER, self.ROWS, cfg(cols, k=3, key=parse_key("ff" * 16), shuffle=False))
        self.assertNotEqual(other.rows[0][0], want)
        with self.assertRaises(ConfigError):
            cfg(cols, k=3)                      # no key
        with self.assertRaises(ConfigError):
            parse_key("not hex")

    def test_shuffle_is_deterministic_and_keep_order_is_recorded(self):
        a = anonymize(self.HEADER, self.ROWS, cfg(self.COLS, k=3, shuffle_seed=1))
        b = anonymize(self.HEADER, self.ROWS, cfg(self.COLS, k=3, shuffle_seed=1))
        c = anonymize(self.HEADER, self.ROWS, cfg(self.COLS, k=3, shuffle_seed=2))
        kept = anonymize(self.HEADER, self.ROWS, cfg(self.COLS, k=3, shuffle=False))
        self.assertEqual(a.rows, b.rows)
        self.assertNotEqual(a.rows, c.rows)
        self.assertEqual(sorted(a.rows), sorted(kept.rows))
        self.assertEqual(a.report.data["relaxations"], [])
        self.assertEqual(kept.report.data["relaxations"], ["keep_order"])
        self.assertEqual([r[0] for r in kept.rows], [str(30 + i % 4) for i in range(12)])

    def test_l_diversity(self):
        header, rows = ["age", "dis"], [["30", "a"], ["30", "a"], ["30", "a"], ["40", "a"], ["40", "b"], ["40", "a"]]
        cols = {"age": {"role": "qi", "type": "exact"}, "dis": {"role": "sensitive"}}
        r = anonymize(header, rows, cfg(cols, k=3, l=2, max_suppression=0.5))
        self.assertEqual(r.status, "anonymized")
        self.assertEqual(r.report.data["privacy"]["diversity"], {"dis": 2})
        self.assertEqual(len(r.rows), 3)               # the uniform crowd of 30s was dropped


class UnicodeForms(unittest.TestCase):
    def test_nfc_and_nfd_values_are_one_value(self):
        ga_nfc, ga_nfd = "\u304c", "\u304b\u3099"
        cols = {"c": {"role": "qi", "type": "exact"}, "s": {"role": "sensitive"}}
        r = anonymize(["c", "s"], [[ga_nfc, "x"], [ga_nfd, "y"]], cfg(cols, k=2, l=2, max_suppression=0.0))
        self.assertEqual(r.report.data["privacy"]["k_achieved"], 2)
        self.assertEqual({row[0] for row in r.rows}, {ga_nfc})   # normalized


class Refusals(unittest.TestCase):
    COLS = {"a": {"role": "qi", "type": "exact"}}

    def refused(self, rows, **kw):
        r = anonymize(["a"], rows, cfg(self.COLS, **kw))
        self.assertEqual(r.status, "refused")
        self.assertIsNone(r.rows)
        return r.report.data["reason"]

    def test_reasons(self):
        self.assertEqual(self.refused([], k=2), "no_records")
        self.assertEqual(self.refused([["x"]] * 3, k=5), "infeasible")
        self.assertEqual(self.refused([["x"]] * 10, k=2, max_rows=5), "resource_limit_rows")
        cols = {"a": {"role": "qi", "type": "numeric", "widths": [2, 4, 8, 16, 32, 64]},
                "b": {"role": "qi", "type": "numeric", "widths": [2, 4, 8, 16, 32, 64]}}
        rows = [[str(i), str(i * 7)] for i in range(50)]
        r = anonymize(["a", "b"], rows, cfg(cols, k=50, max_suppression=0.0, max_evals=3))
        self.assertEqual(r.report.data["reason"], "resource_limit_search")

    def test_refused_text_report(self):
        r = anonymize(["a"], [["x"]] * 3, cfg(self.COLS, k=5))
        self.assertIn("refused", r.report.text("en"))
        self.assertIn("拒否", r.report.text("ja"))


class ConfigErrors(unittest.TestCase):
    def bad(self, obj, **kw):
        with self.assertRaises(ConfigError):
            parse_config(obj, **kw)

    def test_errors(self):
        qi = {"role": "qi", "type": "exact"}
        self.bad({"columns": {"a": qi}, "bogus": 1})
        self.bad({"columns": {"a": {"role": "?"}}})
        self.bad({"columns": {"a": {"role": "king"}}})
        self.bad({"columns": {"a": dict(qi, nope=1)}})
        self.bad({"columns": {"a": {"role": "keep"}}})                      # no qi
        self.bad({"columns": {"a": qi}, "k": 1})
        self.bad({"columns": {"a": qi}, "l": 2})                            # needs a sensitive column
        self.bad({"columns": {"a": qi}, "max_suppression": 1})
        self.bad({"columns": {"a": {"role": "qi", "type": "numeric", "widths": [5, 7]}}})
        self.bad({"columns": {"a": {"role": "id", "action": "shred"}, "b": qi}})
        self.bad({"columns": {"a": qi}}, lang="fr")

    def test_table_must_match_the_config(self):
        c = cfg({"a": {"role": "qi", "type": "exact"}, "b": {"role": "drop"}})
        with self.assertRaises(ConfigError):
            anonymize(["a"], [["x"]], c)                  # b missing from the table
        with self.assertRaises(ConfigError):
            anonymize(["a", "b", "z"], [["x", "y", "z"]], c)   # z has no role
        with self.assertRaises(ConfigError):
            anonymize(["a", "a"], [["x", "y"]], c)         # duplicate names


class Independent(unittest.TestCase):
    def test_output_k_by_plain_counting(self):
        import random
        rnd = random.Random(8)
        header = ["age", "zip", "sex", "dis"]
        rows = [[str(rnd.randint(18, 90)), rnd.choice(["1500001", "1500002", "1600023", "2310001"]),
                 rnd.choice("FM"), rnd.choice(["a", "b", "c"])] for _ in range(500)]
        cols = {"age": {"role": "qi", "type": "numeric", "widths": [5, 10, 20]},
                "zip": {"role": "qi", "type": "prefix", "length": 4},
                "sex": {"role": "qi", "type": "exact"}, "dis": {"role": "sensitive"}}
        r = anonymize(header, rows, cfg(cols, k=7, l=2))
        counts, sens = {}, {}
        for row in r.rows:
            key = tuple(unicodedata.normalize("NFC", x) for x in row[:3])
            counts[key] = counts.get(key, 0) + 1
            sens.setdefault(key, set()).add(row[3])
        self.assertGreaterEqual(min(counts.values()), 7)
        self.assertGreaterEqual(min(len(s) for s in sens.values()), 2)
        self.assertEqual(r.report.data["privacy"]["k_achieved"], min(counts.values()))


class BeforeAfter(unittest.TestCase):
    def test_receipt_shows_how_many_stood_out_before(self):
        rows = [[str(i), "x"] for i in range(40)]             # everybody is one-of-a-kind on `a`
        cols = {"a": {"role": "qi", "type": "numeric", "widths": [10]}, "b": {"role": "keep"}}
        r = anonymize(["a", "b"], rows, cfg(cols, k=5))
        before = r.report.data["privacy"]["before"]
        self.assertEqual((before["records_alone"], before["records_alone_ratio"]), (40, 1.0))
        self.assertEqual(r.report.data["privacy"]["records_alone_in_crowd"], 0)
        self.assertIn("Before: 40 of 40 records (100%)", r.report.text("en"))
        self.assertIn("処理前", r.report.text("ja"))

    def test_comment_keys_are_ignored_everywhere(self):
        c = parse_config({"_about": "x", "columns": {"a": {"role": "qi", "type": "exact", "_why": "y"}}})
        self.assertEqual(c.k, 5)


if __name__ == "__main__":
    unittest.main()
