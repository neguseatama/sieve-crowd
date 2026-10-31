import base64
import hashlib
import hmac
import json
import unicodedata
import unittest
from unittest import mock

from sieve_crowd import ConfigError, anonymize, parse_config, parse_key, plan_table

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


class Diagnostics(unittest.TestCase):
    """Aggregate-only traces in the receipt: why rows were dropped, why a run was refused."""

    COLS = {
        "age": {"role": "qi", "type": "numeric", "widths": [5, 10]},
        "zip": {"role": "qi", "type": "prefix", "length": 2},
        "dis": {"role": "sensitive"},
    }
    ROWS = [["30", "123", "a"], ["31", "123", "b"], ["32", "124", "a"], ["33", "124", "b"],
            ["40", "130", "a"], ["41", "130", "a"], ["70", "999", "a"], ["72", "998", "b"]]

    def test_suppression_breakdown_is_consistent_and_value_free(self):
        r = anonymize(["age", "zip", "dis"], self.ROWS,
                      cfg(self.COLS, k=2, l=2, max_suppression=0.5, shuffle=False))
        self.assertEqual(r.status, "anonymized")
        sup = r.report.data["diagnostics"]["suppression"]
        self.assertEqual(sup["budget"], 4)
        self.assertEqual(sup["dropped_records"], r.report.data["result"]["suppressed"])
        self.assertEqual(sup["dropped_records"], 4)
        self.assertEqual(sup["dropped_crowds"], 3)
        self.assertEqual(sup["crowd_sizes"], [[1, 2], [2, 1]])
        self.assertFalse(sup["crowd_sizes_truncated"])
        bk, bl = sup["reasons"]["below_k"], sup["reasons"]["below_l"]
        self.assertEqual((bk["crowds"], bk["records"]), (2, 2))
        self.assertEqual((bl["crowds"], bl["records"]), (1, 2))
        self.assertEqual(bl["columns"], {"dis": {"crowds": 1, "records": 2}})
        self.assertEqual(bk["crowds"] + bl["crowds"], sup["dropped_crowds"])
        self.assertEqual(bk["records"] + bl["records"], sup["dropped_records"])
        self.assertEqual(sup["one_level_further"], {"age": 0, "zip": 2})
        blob = r.report.to_json() + r.report.text("en") + r.report.text("ja")
        for marker in ("999", "998", "70-74", "130"):      # dropped crowds' labels/values stay hidden
            self.assertNotIn(marker, blob)
        self.assertIn("Suppression detail: 3 crowd(s), 4 record(s)", r.report.text("en"))
        self.assertIn("除外の内訳", r.report.text("ja"))

    def test_no_diagnostics_when_nothing_is_dropped(self):
        rows = [["30", "123", "a"], ["31", "123", "b"], ["32", "124", "a"], ["33", "124", "b"]]
        r = anonymize(["age", "zip", "dis"], rows, cfg(self.COLS, k=2, shuffle=False))
        self.assertEqual(r.report.data["result"]["suppressed"], 0)
        self.assertNotIn("diagnostics", r.report.data)

    def test_infeasible_diagnostics(self):
        cols = {"a": {"role": "qi", "type": "exact"}, "s": {"role": "sensitive"}}
        rows = [["x", "p"], ["x", "p"], ["x", "q"]]
        r = anonymize(["a", "s"], rows, cfg(cols, k=5, l=4))
        self.assertEqual(r.report.data["reason"], "infeasible")
        dg = r.report.data["diagnostics"]
        self.assertEqual((dg["records"], dg["k_requested"], dg["l_requested"]), (3, 5, 4))
        self.assertEqual(dg["sensitive_distinct"], {"s": 2})
        self.assertIn("Diagnostics: 3 record(s)", r.report.text("en"))
        self.assertIn("診断", r.report.text("ja"))

    def test_resource_limit_diagnostics(self):
        cols = {"a": {"role": "qi", "type": "numeric", "widths": [2, 4, 8, 16, 32, 64]},
                "b": {"role": "qi", "type": "numeric", "widths": [2, 4, 8, 16, 32, 64]}}
        rows = [[str(i), str(i * 7)] for i in range(50)]
        r = anonymize(["a", "b"], rows, cfg(cols, k=50, max_suppression=0.0, max_evals=3))
        self.assertEqual(r.report.data["reason"], "resource_limit_search")
        dg = r.report.data["diagnostics"]
        self.assertEqual((dg["lattice_nodes"], dg["tops"], dg["max_evals"]), (64, [7, 7], 3))
        self.assertGreaterEqual(dg["evaluations"], 3)
        self.assertIn("lattice 64 node(s)", r.report.text("en"))

    def test_verification_failed_diagnostics(self):
        from sieve_crowd import engine
        real = engine.measure

        def lying(*a, **kw):
            m = dict(real(*a, **kw))
            m["k"] = min(m["k"], 1)                  # force the safety net to trip
            return m

        cols = {"a": {"role": "qi", "type": "exact"}, "s": {"role": "sensitive"}}
        rows = [["x", "p"], ["x", "q"], ["x", "p"], ["x", "q"], ["x", "p"]]
        with mock.patch.object(engine, "measure", lying):
            r = anonymize(["a", "s"], rows, cfg(cols, k=2, shuffle=False))
        self.assertEqual((r.status, r.report.data["reason"]), ("refused", "verification_failed"))
        dg = r.report.data["diagnostics"]
        self.assertEqual(dg["levels"], [0])
        self.assertEqual((dg["records"], dg["crowds"], dg["records_alone"]), (5, 1, 0))
        self.assertEqual(dg["crowd_sizes_below_k"], [])
        self.assertIn("Diagnostics: 1 crowd(s) in the output", r.report.text("en"))


class MissingValuePolicy(unittest.TestCase):
    """#9: what happens to records whose quasi-identifier value is empty."""

    COLS = {"a": {"role": "qi", "type": "exact"}, "s": {"role": "sensitive"}}

    def test_default_is_star_and_other_policies_are_rejected(self):
        rows = [["x", "p"], ["", "q"], ["y", "p"], ["y", "q"]]
        r = anonymize(["a", "s"], rows, cfg(self.COLS, k=2, shuffle=False))
        self.assertEqual(r.report.data["settings"]["missing_value_policy"], "star")
        self.assertEqual(r.report.data["result"]["missing_suppressed"], 0)
        self.assertEqual(len(r.rows), 4)                       # nothing is dropped up front
        self.assertEqual({row[0] for row in r.rows}, {"*"})    # the missing value generalized
        for bad in ("placeholder", "drop", ""):
            with self.assertRaises(ConfigError):
                parse_config({"columns": self.COLS, "missing_value_policy": bad})

    def test_suppress_drops_missing_rows_and_counts_them(self):
        rows = [["x", "p"], ["x", "q"], ["y", "p"], ["y", "q"], ["", "p"]]
        r = anonymize(["a", "s"], rows,
                      cfg(self.COLS, k=2, max_suppression=0.4, missing_value_policy="suppress",
                          shuffle=False))
        self.assertEqual(r.status, "anonymized")
        self.assertEqual(r.report.data["result"]["missing_suppressed"], 1)
        self.assertEqual(r.report.data["result"]["suppressed"], 1)
        self.assertEqual(len(r.rows), 4)
        self.assertNotIn("", [row[0] for row in r.rows])
        self.assertIn("dropped up front", r.report.text("en"))
        self.assertIn("空値として検索前に除外", r.report.text("ja"))

    def test_missing_over_budget_refuses(self):
        rows = [["", "p"], ["", "q"], ["", "p"], ["x", "p"]]
        r = anonymize(["a", "s"], rows,
                      cfg(self.COLS, k=2, max_suppression=0.25, missing_value_policy="suppress",
                          shuffle=False))
        self.assertEqual((r.status, r.report.data["reason"]), ("refused", "missing_exceeds_budget"))
        dg = r.report.data["diagnostics"]
        self.assertEqual((dg["records"], dg["missing"], dg["budget"]), (4, 3, 1))
        self.assertIn("empty quasi-identifier value", r.report.text("en"))
        self.assertIn("空値", r.report.text("ja"))

    def test_suppress_shares_the_budget_with_the_search(self):
        cols = {"a": {"role": "qi", "type": "exact"}}
        rows = [["s1"], ["s2"], ["a"], ["a"], ["b"], ["b"], ["c"], ["c"]]
        full = anonymize(["a"], rows, cfg(cols, k=2, max_suppression=0.25, shuffle=False))
        self.assertEqual((full.report.data["columns"][0]["level"],
                          full.report.data["result"]["suppressed"]), (0, 2))
        r = anonymize(["a"], rows + [[""]],
                      cfg(cols, k=2, max_suppression=0.25, missing_value_policy="suppress",
                          shuffle=False))
        self.assertEqual(r.report.data["result"]["missing_suppressed"], 1)
        self.assertEqual(r.report.data["columns"][0]["level"], 1)   # one slot eaten: generalize
        self.assertEqual(r.report.data["result"]["suppressed"], 1)

    def test_plan_reports_missing_and_warns_over_budget(self):
        rows = [["", "p"], ["", "q"], ["x", "p"]]
        c = cfg(self.COLS, k=2, max_suppression=0.1, missing_value_policy="suppress")
        p = plan_table(["a", "s"], rows, c)
        self.assertEqual(p["missing"], {"policy": "suppress", "records": 2})
        self.assertEqual([w["code"] for w in p["warnings"]], ["budget_zero", "missing_over_budget"])
        self.assertEqual(p["warnings"][-1]["params"], {"records": 2, "budget": 0})
        star = plan_table(["a", "s"], rows, cfg(self.COLS, k=2, max_suppression=0.1))
        self.assertEqual(star["missing"], {"policy": "star", "records": 2})
        self.assertEqual([w["code"] for w in star["warnings"]], ["budget_zero"])


class Plan(unittest.TestCase):
    """The pre-flight profile: exact search-space numbers, level-0 statistics, warnings."""

    COLS = {"age": {"role": "qi", "type": "numeric", "widths": [5, 10]},
            "zip": {"role": "qi", "type": "prefix", "length": 2},
            "dis": {"role": "sensitive"}}

    def test_plan_numbers_are_exact_and_value_free(self):
        rows = [["30", "123", "a"], ["31", "123", "b"], ["32", "124", "a"], ["70", "999", "a"]]
        c = parse_config({"columns": self.COLS}, k=5, max_suppression=0.25)
        p = plan_table(["age", "zip", "dis"], rows, c)
        self.assertEqual(p["status"], "plan")
        self.assertEqual((p["lattice"]["tops"], p["lattice"]["nodes"], p["lattice"]["max_height"]),
                         ([3, 3], 16, 6))
        self.assertEqual(p["budget"]["records"], 1)
        self.assertEqual(p["before"]["records_alone"], 4)
        self.assertEqual(p["before"]["records_below_k"], 4)
        self.assertEqual([w["code"] for w in p["warnings"]], ["k_unreachable", "many_singletons"])
        self.assertEqual(p["warnings"][0]["params"], {"records": 4, "k": 5})
        blob = json.dumps(p, ensure_ascii=False)
        for marker in ("999", "130"):
            self.assertNotIn(marker, blob)
        self.assertEqual(p, plan_table(["age", "zip", "dis"], rows, c))   # deterministic

    def test_plan_matches_the_search_contract(self):
        rows = [["30", "123", "a"], ["31", "123", "b"], ["32", "124", "a"], ["70", "999", "a"]]
        c = parse_config({"columns": self.COLS}, k=2, max_suppression=0.25)
        p = plan_table(["age", "zip", "dis"], rows, c)
        r = anonymize(["age", "zip", "dis"], rows, parse_config({"columns": self.COLS},
                                                                k=2, max_suppression=0.25, shuffle=False))
        self.assertEqual(p["budget"]["records"], min(len(rows) - 1, int(0.25 * len(rows))))
        self.assertEqual(r.status, "anonymized")
        self.assertNotIn("warnings", r.report.data)     # plan-only section stays out of run receipts

    def test_plan_warnings_cover_limits_and_l(self):
        rows = [["30", "123", "a"], ["31", "123", "a"], ["32", "124", "a"], ["70", "999", "a"]]
        c = parse_config({"columns": self.COLS}, k=2, l=3, max_suppression=0.0, max_rows=2, max_evals=10)
        p = plan_table(["age", "zip", "dis"], rows, c)
        codes = [w["code"] for w in p["warnings"]]
        self.assertIn("rows_over_limit", codes)
        self.assertIn("l_unreachable", codes)
        self.assertIn("budget_zero", codes)
        self.assertIn("evals_tight", codes)
        lw = next(w for w in p["warnings"] if w["code"] == "l_unreachable")
        self.assertEqual(lw["params"], {"column": "dis", "distinct": 1, "l": 3})

    def test_plan_refuses_mismatched_columns(self):
        c = parse_config({"columns": self.COLS})
        with self.assertRaises(ConfigError):
            plan_table(["age", "zip"], [["30", "123"]], c)


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
