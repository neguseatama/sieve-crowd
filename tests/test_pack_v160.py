"""jp-basic 1.6.0 tests (T63-T65, v0.7.5).

Two commits carry the code this time — the pack widens the vocabulary and
hintpack.py resolves the v0.7.4 known limitation 6 — so these tests are red
until BOTH the pack and the hintpack commits:

* T63 — the widened column names: jp-phone and jp-phone-hyphen grow from 8
  to 13 (携帯番号, 電話番号1, 電話番号2, phone_number, tel_number), jp-email
  from 6 to 8 (email_address, Eメール), jp-card and jp-card-hyphen from 5 to
  7 (card_no, クレジットカード番号).  The sibling name sets stay equal, an
  added name belongs to its rule (or sibling pair) only, 市区町村 stays out
  of jp-address, and the full-width / upper-case variants normalize onto
  the names (電話番号１, ＰＨＯＮＥ＿ＮＵＭＢＥＲ, ｅメール; the pre-existing
  E-MAIL keeps firing).  The pack stores the names pre-normalization and
  normalizes them at load (NFKC + strip + lower), so Eメール matches as
  eメール.
* T64 — the luhn check evaluates hyphenated card numbers (the v0.7.4
  known-limitation 6 resolved): the luhn evaluation alone re-folds its
  input with dashes=True and, when the result is a run of ASCII digits and
  dashes, luhn runs on the dash-stripped digits.  Valid dashed cards match,
  invalid ones mismatch (full-width and long-vowel dashes included);
  letters, spaces, empty and non-ASCII "digits" (², ⁴, ④ — the current
  code raises int() ValueError on them) stay cannot_check; dashless values
  take the same path unchanged.  On a named dashed-only column jp-card's
  evidence upgrades from name to name+value (the check now matches); the
  candidate order follows.
* T65 — the other checks are unchanged: my_number (a dashed value is still
  cannot_check — the dash-stripping is luhn-only), email_shape, range
  (negative numbers parse as mismatches, not cannot_check) and set; the
  stderr line formats (en/ja) and the findings keys are the v0.7.4 ones,
  and no cell value appears anywhere in the output (sentinel).
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

from sieve_crowd.cli import main

ID = {"role": "id"}

PHONE_ADDED = ["携帯番号", "電話番号1", "電話番号2", "phone_number", "tel_number"]
EMAIL_ADDED = ["email_address", "Eメール"]
CARD_ADDED = ["card_no", "クレジットカード番号"]

PHONES = ["09012345678", "0312345678", "08087654321"]           # dashless, shape-matching
EMAILS = ["tarou@example.co.jp", "hana@foo.bar", "yamada@mail.example.jp"]
CARDS = ["4242424242424242", "4111111111111111", "7992739871304"]
AGES = ["40", "23", "55", "61"]

CARDS_DASHED = ["4242-4242-4242-4242", "4242-4242-4242-4241",
                "4111-1111-1111-1111", ""]                       # valid, invalid, valid, empty


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def _csv(cols):
    """cols: ordered mapping column -> list of values (equal lengths)."""
    n = len(next(iter(cols.values())))
    lines = [",".join(cols)]
    for i in range(n):
        lines.append(",".join(values[i] for values in cols.values()))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _config(roles):
    return json.dumps({"k": 2, "columns": roles}, ensure_ascii=False).encode("utf-8")


def _plan(d, csv_data, cfg_data):
    src = os.path.join(d, "in.csv")
    with open(src, "wb") as fh:
        fh.write(csv_data)
    cfg = os.path.join(d, "c.json")
    with open(cfg, "wb") as fh:
        fh.write(cfg_data)
    fj = os.path.join(d, "f.json")
    if os.path.exists(fj):
        os.unlink(fj)
    rc, out, err = call("plan", src, "-c", cfg, "--findings-json", fj)
    findings = None
    if os.path.exists(fj):
        with open(fj, encoding="utf-8") as fh:
            findings = json.load(fh)
    return rc, out, err, findings


def _cands(findings, col):
    return [(c["rule"], c["evidence"], c["suggest"])
            for c in findings["columns"].get(col, {}).get("candidates", [])]


def _warns(findings):
    return [(w["code"], w.get("rule"), w.get("column"), w.get("declared"),
             w.get("suggested"), w.get("evidence"), w.get("count"),
             w.get("checked"))
            for w in findings["warnings"]]


# --------------------------------------------------------------------------- #
class T63WiderNames(unittest.TestCase):
    """T63: the widened phone/email/card column names — counts, sibling
    equality, ownership (no cross-rule collisions), 市区町村 stays out of
    jp-address, and the normalized variants reach the names."""

    def test_name_counts_and_sibling_equality(self):
        from sieve_crowd.hintpack import load_packs
        packs = load_packs([], include_builtin=True)
        self.assertEqual(packs[0].version, "1.7.0")
        rules = {r.id: r for r in packs[0].rules}
        # 13 / 13 / 8 / 7 / 7 (the request's table)
        self.assertEqual(len(rules["jp-phone"].column_names), 13)
        self.assertEqual(len(rules["jp-phone-hyphen"].column_names), 13)
        self.assertEqual(len(rules["jp-email"].column_names), 8)
        self.assertEqual(len(rules["jp-card"].column_names), 7)
        self.assertEqual(len(rules["jp-card-hyphen"].column_names), 7)
        # the hyphen siblings keep the exact same names as their base rules
        self.assertEqual(rules["jp-phone-hyphen"].column_names,
                         rules["jp-phone"].column_names)
        self.assertEqual(rules["jp-card-hyphen"].column_names,
                         rules["jp-card"].column_names)
        # 見送り: 市区町村 is not added to jp-address this version
        self.assertNotIn("市区町村", rules["jp-address"].column_names)

    def test_added_names_belong_to_their_rules_only(self):
        # the normalized (post-NFKC, lower-cased) name set is a closed map:
        # an added name is owned by its rule alone (the sibling pair counts
        # as the intended duplication)
        from sieve_crowd.hintpack import _norm_name, load_packs
        packs = load_packs([], include_builtin=True)
        owner: dict = {}
        for r in packs[0].rules:
            for n in r.column_names:
                owner.setdefault(n, set()).add(r.id)
        for n in PHONE_ADDED:
            self.assertEqual(owner[_norm_name(n)],
                             {"jp-phone", "jp-phone-hyphen"}, n)
        for n in EMAIL_ADDED:
            self.assertEqual(owner[_norm_name(n)], {"jp-email"}, n)
        for n in CARD_ADDED:
            self.assertEqual(owner[_norm_name(n)],
                             {"jp-card", "jp-card-hyphen"}, n)

    def test_each_added_name_fires_a_candidate(self):
        cols = {n: PHONES for n in PHONE_ADDED}
        cols["age"] = AGES[:3]
        roles = {n: {"role": "keep"} for n in PHONE_ADDED}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in PHONE_ADDED:
                # dashless values: jp-phone carries name+value, the hyphen
                # sibling keeps its name-only candidate
                self.assertEqual(_cands(f, n),
                                 [("jp-phone", "name+value", ID),
                                  ("jp-phone-hyphen", "name", ID)], n)
        cols = {n: EMAILS for n in EMAIL_ADDED}
        cols["age"] = AGES[:3]
        roles = {n: {"role": "keep"} for n in EMAIL_ADDED}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in EMAIL_ADDED:
                self.assertEqual(_cands(f, n),
                                 [("jp-email", "name+value", ID)], n)
        cols = {n: CARDS for n in CARD_ADDED}
        cols["age"] = AGES[:3]
        roles = {n: {"role": "keep"} for n in CARD_ADDED}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in CARD_ADDED:
                # plain luhn-valid cards already evaluate for BOTH rules
                # (the check folds with dashes=False and the values carry no
                # dash), so both candidates carry name+value
                self.assertEqual(_cands(f, n),
                                 [("jp-card", "name+value", ID),
                                  ("jp-card-hyphen", "name+value", ID)], n)

    def test_fullwidth_and_uppercase_variants_reach_the_names(self):
        # the pack stores the names pre-normalization; the load normalizes
        # them (NFKC + strip + lower), so the variants match exactly
        cols = {"電話番号１": PHONES, "ＰＨＯＮＥ＿ＮＵＭＢＥＲ": PHONES,
                "ｅメール": EMAILS, "ＥＭＡＩＬ＿ＡＤＤＲＥＳＳ": EMAILS,
                "E-MAIL": EMAILS, "ＣＡＲＤ＿ＮＯ": CARDS,
                "age": AGES[:3]}
        roles = {c: {"role": "keep"} for c in cols}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in ("電話番号１", "ＰＨＯＮＥ＿ＮＵＭＢＥＲ"):
                self.assertEqual(_cands(f, n)[0],
                                 ("jp-phone", "name+value", ID), n)
            for n in ("ｅメール", "ＥＭＡＩＬ＿ＡＤＤＲＥＳＳ", "E-MAIL"):
                self.assertEqual(_cands(f, n)[0],
                                 ("jp-email", "name+value", ID), n)
            self.assertEqual(_cands(f, "ＣＡＲＤ＿ＮＯ")[0],
                             ("jp-card", "name+value", ID))


# --------------------------------------------------------------------------- #
class T64LuhnDashed(unittest.TestCase):
    """T64: the luhn check evaluates hyphenated card numbers — the v0.7.4
    known-limitation 6 resolved.  The dash-stripped digit run goes to luhn;
    everything else stays cannot_check; dashless values are unchanged."""

    def test_direct_matrix(self):
        from sieve_crowd.hintpack import Check, _eval_check
        chk = Check("luhn")
        # valid dashed cards — half-width, full-width and long-vowel dashes
        for v in ("4242-4242-4242-4242", "4111-1111-1111-1111",
                  "4242－4242－4242－4242", "4242ー4242ー4242ー4242",
                  "４２４２－４２４２－４２４２－４２４２"):
            self.assertEqual(_eval_check(chk, v), "match", v)
        # invalid dashed cards
        for v in ("4242-4242-4242-4241", "4111-1111-1111-1112",
                  "4242ー4242ー4242ー4241"):
            self.assertEqual(_eval_check(chk, v), "mismatch", v)
        # cannot_check: letters, spaces, no digits, non-ASCII digits
        # (², ⁴, ④ are isdigit()-true — the current code raises int()
        # ValueError on them; the whitelist turns them cannot_check)
        for v in ("abc", "4 2", "", "12-34ab", "----", "4242-abcd-4242-4242",
                  "²", "⁴", "④", "½"):
            self.assertEqual(_eval_check(chk, v), "cannot_check", v)
        # dashless values unchanged (same path — the fold is idempotent and
        # ASCII-invariant): valid, invalid, digit-count boundaries
        for v, want in (("4242424242424242", "match"),
                        ("4242424242424241", "mismatch"),
                        ("79927398713", "match"),
                        ("79927398714", "mismatch"),
                        ("42424242424242424", "mismatch"),
                        ("424242424242424", "match"),
                        ("0000000000000000", "match")):
            self.assertEqual(_eval_check(chk, v), want, v)

    def test_checks_on_a_dashed_column(self):
        # dashed-only column + one empty cell: the aggregates evaluate the
        # dashed values (2 match, 1 mismatch), the empty cell stays
        # cannot_check — and jp-card's evidence upgrades from name to
        # name+value (its check now matches the dashed digits)
        cols = {"カード番号": CARDS_DASHED, "age": AGES}
        roles = {"カード番号": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(f["columns"]["カード番号"]["checks"],
                             [{"pack": "jp-basic", "rule": "jp-card",
                               "kind": "luhn", "match": 2, "mismatch": 1,
                               "cannot_check": 1},
                              {"pack": "jp-basic", "rule": "jp-card-hyphen",
                               "kind": "luhn", "match": 2, "mismatch": 1,
                               "cannot_check": 1}])
            self.assertEqual(_cands(f, "カード番号"),
                             [("jp-card", "name+value", ID),
                              ("jp-card-hyphen", "name+value", ID)])

    def test_fullwidth_dash_values_evaluate(self):
        # one script per cell: no mixed_form observation
        cols = {"クレジットカード番号": ["４２４２－４２４２－４２４２－４２４２",
                                         "４２４２－４２４２－４２４２－４２４１",
                                         "４１１１－１１１１－１１１１－１１１１"],
                "age": AGES[:3]}
        roles = {"クレジットカード番号": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(f["columns"]["クレジットカード番号"]["checks"],
                             [{"pack": "jp-basic", "rule": "jp-card",
                               "kind": "luhn", "match": 2, "mismatch": 1,
                               "cannot_check": 0},
                              {"pack": "jp-basic", "rule": "jp-card-hyphen",
                               "kind": "luhn", "match": 2, "mismatch": 1,
                               "cannot_check": 0}])
            self.assertFalse([w for w in f["warnings"]
                              if w["code"] == "mixed_form"])


# --------------------------------------------------------------------------- #
class T65OtherChecksUnchanged(unittest.TestCase):
    """T65: my_number, email_shape, range (negative numbers included) and
    set keep their v0.7.4 results; the stderr formats and the findings keys
    are the v0.7.4 ones; no cell value appears in the output (sentinel)."""

    def test_my_number_dash_stripping_is_luhn_only(self):
        from sieve_crowd.hintpack import Check, _eval_check
        mn = Check("my_number")
        self.assertEqual(_eval_check(mn, "123456789018"), "match")
        self.assertEqual(_eval_check(mn, "123456789019"), "mismatch")
        self.assertEqual(_eval_check(mn, "12345678901"), "cannot_check")
        # the dash-stripping is luhn-only: a dashed or full-width value
        # stays cannot_check for my_number
        self.assertEqual(_eval_check(mn, "1234-5678-9018"), "cannot_check")
        self.assertEqual(_eval_check(mn, "４２４２－４２４２－４２４２－４２４２"),
                         "cannot_check")
        self.assertEqual(_eval_check(mn, "abc"), "cannot_check")

    def test_email_shape_range_set_unchanged(self):
        cols = {"メール": ["tarou@example.co.jp", "not an email", "",
                          "hana@foo.bar", "no-at-sign"],
                "年齢": ["40", "-5", "200", "abc", ""],
                "都道府県": ["東京都", "北京", "", "大阪府", "エリア"],
                "age": ["61", "52", "43", "34", "25"]}
        roles = {"メール": {"role": "keep"}, "年齢": {"role": "keep"},
                 "都道府県": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            # email_shape: match / mismatch / cannot_check (the empty cell)
            self.assertEqual(f["columns"]["メール"]["checks"],
                             [{"pack": "jp-basic", "rule": "jp-email",
                               "kind": "email_shape", "match": 2,
                               "mismatch": 2, "cannot_check": 1}])
            # range: the negative number -5 parses (dashes=False keeps the
            # minus) and lands in mismatch — not cannot_check
            self.assertEqual(f["columns"]["年齢"]["checks"],
                             [{"pack": "jp-basic", "rule": "jp-age",
                               "kind": "range", "match": 1, "mismatch": 2,
                               "cannot_check": 2}])
            # set: match / mismatch / cannot_check
            self.assertEqual(f["columns"]["都道府県"]["checks"],
                             [{"pack": "jp-basic", "rule": "jp-prefecture",
                               "kind": "set", "match": 2, "mismatch": 2,
                               "cannot_check": 1}])

    def test_stderr_formats_keys_and_no_values(self):
        cols = {"カード番号": ["4242-4242-4242-4242", "4242-4242-4242-4241",
                              "4111-1111-1111-1111", "4111111111111111"],
                "age": AGES}
        roles = {"カード番号": {"role": "qi", "type": "exact"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            # the checks row keeps the v0.7.4 key set
            self.assertEqual(sorted(f["columns"]["カード番号"]["checks"][0]),
                             ["cannot_check", "kind", "match", "mismatch",
                              "pack", "rule"])
            # the warnings are the v0.7.4 three lines (2 leak + role_mismatch)
            self.assertEqual(_warns(f),
                             [("leak", "jp-card", "カード番号", None, None,
                               None, 4, 4),
                              ("leak", "jp-card-hyphen", "カード番号", None,
                               None, None, 3, 4),
                              ("role_mismatch", None, "カード番号", "qi",
                               "id", "name+value", None, None)])
            src = os.path.join(d, "in.csv")
            cfg = os.path.join(d, "c.json")
            rc, _, err_en = call("plan", src, "-c", cfg, "--lang", "en")
            self.assertEqual(rc, 0, err_en)
            self.assertIn('  - leak: "カード番号" (declared qi): 4 of 4 '
                          "non-empty cells may contain jp-basic/jp-card",
                          err_en)
            self.assertIn('  - leak: "カード番号" (declared qi): 3 of 4 '
                          "non-empty cells may contain "
                          "jp-basic/jp-card-hyphen", err_en)
            self.assertIn('  - role_mismatch: "カード番号" suggests id but is '
                          "declared qi (evidence: name+value)", err_en)
            rc, _, err_ja = call("plan", src, "-c", cfg, "--lang", "ja")
            self.assertEqual(rc, 0, err_ja)
            self.assertIn("  - leak: 「カード番号」（宣言 qi）: 空でない 4 件の"
                          "うち 4 件に jp-basic/jp-card が含まれる可能性が"
                          "あります", err_ja)
            self.assertIn("  - role_mismatch: 「カード番号」は id を提案しますが、"
                          "設定では qi として宣言されています"
                          "（根拠: name+value）", err_ja)
            # sentinel: no cell value in any output
            for v in ("4242-4242-4242-4242", "4242-4242-4242-4241",
                      "4111-1111-1111-1111", "4111111111111111"):
                self.assertNotIn(v, err_en)
                self.assertNotIn(v, err_ja)
                self.assertNotIn(v, out)
            findings_text = json.dumps(f, ensure_ascii=False)
            for v in ("4242-4242-4242-4242", "4111111111111111"):
                self.assertNotIn(v, findings_text)


if __name__ == "__main__":
    unittest.main()
