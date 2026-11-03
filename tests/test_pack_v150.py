"""jp-basic 1.5.0 tests (T57-T61, v0.7.4).

One commit, pack only (hintpack.py is frozen from this version on; T62
starts its byte pin):

* T57 — ``jp-phone-hyphen``: the dash form ``#{2,4}-#{2,4}-#{3,4}`` of the
  phone number, the same column names, the same ``id`` suggestion and the
  same ``leak`` flag as jp-phone.  Through the fold, full-width digits and
  long-vowel dashes reach the shape.  The third group accepts 3 or 4
  digits, so a 12-digit number written 4-4-4 (``1234-5678-9012``) matches
  too — accepted by the design side: on a column whose name does not
  match, the shape only feeds the leak scan (no candidate, no
  role_mismatch), and tightening the third group would swallow real
  phones (``0120-123-456``, ``0800-123-4567``).
* T58 — ``jp-card-hyphen``: the dash form ``#{4}-#{4}-#{4}-#{4}`` of the
  card number, the same column names, suggestion and leak flag as
  jp-card, and the same ``luhn`` check.  In v0.7.4 the check folded with
  ``dashes=False``, so hyphenated values counted as ``cannot_check``
  (recorded then as a candidate for the next version that touches
  hintpack.py); v0.7.5 resolves it — the luhn evaluation re-folds with
  ``dashes=True`` and strips the dashes, so the expectations moved from
  match=2/cannot_check=2 to match=4/cannot_check=0 (see T64).  The leak
  token scan is unchanged (shape-based, dash-stripped): jp-card counts
  both forms 4/4 while jp-card-hyphen counts only the hyphenated tokens
  2/4.
* T59 — the hyphen columns' standard output on plan: one leak line per
  matching rule plus one role_mismatch — three lines where 1.4.0 printed
  one (jp-phone's shape never matched a hyphenated value).
* T60 — the unchanged mechanics: id/drop columns are never leak-scanned
  and never mismatch; mixed_form stays a cell-level observation and the
  candidate still fires through the fold.
* T61 — the widened postal-code names: jp-zip and jp-zip-hyphen grow from
  6 to 13 names (郵便番号, 〒番号, 郵便番号1, 郵便番号2, zip_code,
  postal_code, post_code); 〒 survives NFKC unchanged and full-width /
  upper-case variants normalize onto the same names.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest

from sieve_crowd.cli import main

ID = {"role": "id"}
PREFIX4 = {"role": "qi", "type": "prefix", "length": 4}

PHONES_HYPHEN = ["03-1234-5678", "090-1234-5678", "045-123-4567", "0120-123-456"]
CARDS_HYPHEN = ["4242-4242-4242-4242", "4111-1111-1111-1111"]   # luhn-valid
CARDS_PLAIN = ["4242424242424242", "4111111111111111"]          # luhn-valid
AGES = ["40", "23", "55", "61"]

ZIP_NAMES = ["zip", "zipcode", "postal", "postcode", "郵便", "〒", "郵便番号",
             "〒番号", "郵便番号1", "郵便番号2", "zip_code", "postal_code",
             "post_code"]
ZIPS = ["1500001", "1500052", "1000001"]
ZIPS_HYPHEN = ["123-4567", "150-0052", "100-0042"]


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
class T57PhoneHyphen(unittest.TestCase):
    """T57: jp-phone-hyphen — the dash form of the phone number.  Same names,
    same id suggestion, same leak flag; the shape matrix, the fold route and
    the candidate gate (dashless values stay with jp-phone; a prose column
    gets leak counts but never a candidate)."""

    def test_rule_attributes_and_shape_matrix(self):
        from sieve_crowd.hintpack import load_packs
        packs = load_packs([], include_builtin=True)
        self.assertEqual(packs[0].version, "1.7.0")
        rules = {r.id: r for r in packs[0].rules}
        self.assertIn("jp-phone-hyphen", rules)
        rule = rules["jp-phone-hyphen"]
        # same names, same suggestion, same leak flag as jp-phone
        self.assertEqual(rule.column_names, rules["jp-phone"].column_names)
        self.assertEqual(dict(rule.suggest), ID)
        self.assertTrue(rule.leak)
        self.assertIsNone(rule.check)
        # the shape matrix (Y = match)
        for v in ("03-1234-5678", "090-1234-5678", "045-123-4567",
                  "0120-123-456", "1234-5678-9012"):
            self.assertTrue(rule.shape.match(v), v)
        for v in ("09012345678", "123-4567", "1500052", "2024-01-15",
                  "2024-01", "10-20", "1-2-3", "1234-5678-9012-3456"):
            self.assertFalse(rule.shape.match(v), v)

    def test_hyphen_values_suggest_id_with_name_plus_value(self):
        cols = {"電話番号": PHONES_HYPHEN, "age": AGES}
        roles = {"電話番号": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            # evidence strength sorts first: the hyphen rule carries
            # name+value, jp-phone keeps its name-only candidate
            self.assertEqual(_cands(f, "電話番号"),
                             [("jp-phone-hyphen", "name+value", ID),
                              ("jp-phone", "name", ID)])

    def test_fullwidth_and_longvowel_dash_reach_the_shape(self):
        cols = {"携帯": ["０９０－１２３４－５６７８", "090ー1234ー5678",
                         "０４５－１２３－４５６７", "０１２０－１２３－４５６"],
                "age": AGES}
        roles = {"携帯": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(_cands(f, "携帯")[0],
                             ("jp-phone-hyphen", "name+value", ID))
            # one script per cell: no mixed-form observation
            self.assertFalse([w for w in f["warnings"]
                              if w["code"] == "mixed_form"])

    def test_dashless_values_stay_with_jp_phone(self):
        cols = {"tel": ["09012345678", "0312345678", "08087654321"],
                "age": AGES[:3]}
        roles = {"tel": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(_cands(f, "tel"),
                             [("jp-phone", "name+value", ID),
                              ("jp-phone-hyphen", "name", ID)])
            # the leak token scan: only jp-phone matches a dashless token
            self.assertEqual([(lk["rule"], lk["count"], lk["checked"])
                              for lk in f["columns"]["tel"]["leaks"]],
                             [("jp-phone", 3, 3)])

    def test_prose_column_leak_counts_never_a_candidate(self):
        # the gate: a suggestion needs a name or a value signal; a leak rule
        # whose name does not match skips the whole-column scan, so the
        # embedded hyphen phone is leak's job only
        cols = {"メモ": ["連絡先は 03-1234-5678 です", "メモのみ",
                         "03-1234-5678 まで"],
                "age": AGES[:3]}
        roles = {"メモ": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            memo = f["columns"]["メモ"]
            self.assertEqual(sorted(memo), ["declared_role", "leaks"])
            self.assertEqual([(lk["rule"], lk["count"]) for lk in memo["leaks"]],
                             [("jp-phone", 2), ("jp-phone-hyphen", 2)])
            self.assertNotIn("candidates", memo)


# --------------------------------------------------------------------------- #
class T58CardHyphen(unittest.TestCase):
    """T58: jp-card-hyphen — the dash form of the card number.  Same names,
    same id suggestion, same leak flag, same luhn check.  v0.7.5: the luhn
    evaluation re-folds with dashes=True and strips the dashes before the
    digit run (the v0.7.4 known-limitation 6 resolved), so the hyphenated
    half is evaluated — match, not cannot_check; the leak token scan
    (shape-based, dash-stripped) matches them directly as before."""

    def test_rule_attributes_and_shape_matrix(self):
        from sieve_crowd.hintpack import load_packs
        rules = {r.id: r for r in load_packs([], include_builtin=True)[0].rules}
        self.assertIn("jp-card-hyphen", rules)
        rule = rules["jp-card-hyphen"]
        self.assertEqual(rule.column_names, rules["jp-card"].column_names)
        self.assertEqual(dict(rule.suggest), ID)
        self.assertTrue(rule.leak)
        self.assertEqual(rule.check.kind, "luhn")
        for v in ("4242-4242-4242-4242", "1234-5678-9012-3456"):
            self.assertTrue(rule.shape.match(v), v)
        for v in ("090-1234-5678", "4242424242424242", "4242-4242-4242",
                  "4242-4242-4242-42424", "123-4567", "2024-01-15"):
            self.assertFalse(rule.shape.match(v), v)

    def test_checks_and_leaks_on_a_mixed_column(self):
        # 2 hyphenated + 2 dashless luhn-valid cards.  v0.7.5: the luhn
        # evaluation re-folds its input with dashes=True and strips the
        # dashes before the digit run (the v0.7.4 known-limitation 6,
        # 3.1/3.2 of the request), so the hyphenated half is evaluated —
        # the v0.7.4 expectations (match=2 / cannot_check=2) move to
        # match=4 / cannot_check=0 for BOTH rules.  The leak token scan is
        # unchanged (shape-based, dash-stripped): the hyphenated tokens
        # match jp-card-hyphen directly and jp-card dash-stripped.
        cols = {"カード番号": CARDS_HYPHEN + CARDS_PLAIN, "age": AGES}
        roles = {"カード番号": {"role": "qi", "type": "exact"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            # v0.7.5 expectations (was match=2 / cannot_check=2 in v0.7.4:
            # the hyphenated half moved from cannot_check into match)
            self.assertEqual(f["columns"]["カード番号"]["checks"],
                             [{"pack": "jp-basic", "rule": "jp-card",
                               "kind": "luhn", "match": 4, "mismatch": 0,
                               "cannot_check": 0},
                              {"pack": "jp-basic", "rule": "jp-card-hyphen",
                               "kind": "luhn", "match": 4, "mismatch": 0,
                               "cannot_check": 0}])
            self.assertEqual([(lk["rule"], lk["count"], lk["checked"],
                               lk["skipped"])
                              for lk in f["columns"]["カード番号"]["leaks"]],
                             [("jp-card", 4, 4, 0),
                              ("jp-card-hyphen", 2, 4, 0)])
            # both rules carry a name+value candidate; rule-id order
            self.assertEqual(_cands(f, "カード番号"),
                             [("jp-card", "name+value", ID),
                              ("jp-card-hyphen", "name+value", ID)])

    def test_fullwidth_hyphen_values_reach_the_shape(self):
        cols = {"クレジットカード": ["４２４２－４２４２－４２４２－４２４２",
                                      "４１１１－１１１１－１１１１－１１１１",
                                      "４２４２－４１１１－１１１１－４２４２"],
                "age": AGES[:3]}
        roles = {"クレジットカード": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            # v0.7.5: the luhn evaluation strips the dashes, so jp-card's
            # check now matches these dashed (luhn-valid) values too — its
            # evidence upgrades from name to name+value and the candidate
            # order follows (rule-id order at equal evidence; both rules
            # still suggest id, so _suggest is unchanged)
            self.assertEqual(_cands(f, "クレジットカード"),
                             [("jp-card", "name+value", ID),
                              ("jp-card-hyphen", "name+value", ID)])
            self.assertFalse([w for w in f["warnings"]
                              if w["code"] == "mixed_form"])


# --------------------------------------------------------------------------- #
class T59LeakAndRoleMismatchStandard(unittest.TestCase):
    """T59: a hyphen-form phone/card column declared keep/qi prints one leak
    line per matching rule plus one role_mismatch — three lines (1.4.0
    printed one: jp-phone's shape never matched a hyphenated value).  The
    en and ja line formats are pinned."""

    def test_phone_keep_three_lines(self):
        cols = {"電話番号": PHONES_HYPHEN, "age": AGES}
        roles = {"電話番号": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(_warns(f),
                             [("leak", "jp-phone", "電話番号", None, None,
                               None, 4, 4),
                              ("leak", "jp-phone-hyphen", "電話番号", None,
                               None, None, 4, 4),
                              ("role_mismatch", None, "電話番号", "keep",
                               "id", "name+value", None, None)])

    def test_phone_lines_en_and_ja(self):
        cols = {"電話番号": PHONES_HYPHEN, "age": AGES}
        roles = {"電話番号": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.csv")
            with open(src, "wb") as fh:
                fh.write(_csv(cols))
            cfg = os.path.join(d, "c.json")
            with open(cfg, "wb") as fh:
                fh.write(_config(roles))
            rc, _, err_en = call("plan", src, "-c", cfg, "--lang", "en")
            self.assertEqual(rc, 0, err_en)
            self.assertIn('  - leak: "電話番号" (declared keep): 4 of 4 '
                          "non-empty cells may contain jp-basic/jp-phone",
                          err_en)
            self.assertIn('  - leak: "電話番号" (declared keep): 4 of 4 '
                          "non-empty cells may contain "
                          "jp-basic/jp-phone-hyphen", err_en)
            self.assertIn('  - role_mismatch: "電話番号" suggests id but is '
                          "declared keep (evidence: name+value)", err_en)
            rc, _, err_ja = call("plan", src, "-c", cfg, "--lang", "ja")
            self.assertEqual(rc, 0, err_ja)
            self.assertIn("  - leak: 「電話番号」（宣言 keep）: 空でない 4 件の"
                          "うち 4 件に jp-basic/jp-phone が含まれる可能性が"
                          "あります", err_ja)
            self.assertIn("  - leak: 「電話番号」（宣言 keep）: 空でない 4 件の"
                          "うち 4 件に jp-basic/jp-phone-hyphen が含まれる可能性"
                          "があります", err_ja)
            self.assertIn("  - role_mismatch: 「電話番号」は id を提案しますが、"
                          "設定では keep として宣言されています"
                          "（根拠: name+value）", err_ja)

    def test_card_qi_three_lines(self):
        cols = {"カード番号": CARDS_HYPHEN + CARDS_PLAIN, "age": AGES}
        roles = {"カード番号": {"role": "qi", "type": "exact"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(_warns(f),
                             [("leak", "jp-card", "カード番号", None, None,
                               None, 4, 4),
                              ("leak", "jp-card-hyphen", "カード番号", None,
                               None, None, 2, 4),
                              ("role_mismatch", None, "カード番号", "qi",
                               "id", "name+value", None, None)])
            self.assertIn('  - leak: "カード番号" (declared qi): 2 of 4 '
                          "non-empty cells may contain "
                          "jp-basic/jp-card-hyphen", err)


# --------------------------------------------------------------------------- #
class T60UnchangedMechanics(unittest.TestCase):
    """T60: id/drop columns are never leak-scanned and never mismatch
    (id/drop is what the user already chose); mixed_form keeps its
    cell-level observation and the candidate still fires through the fold."""

    def test_id_and_drop_never_leak_scan_and_never_mismatch(self):
        cols = {"電話番号": PHONES_HYPHEN, "age": AGES}
        for declared in ("id", "drop"):
            role = ({"role": "id", "action": "drop"} if declared == "id"
                    else {"role": "drop"})
            roles = {"電話番号": role, "age": {"role": "qi", "type": "exact"}}
            with tempfile.TemporaryDirectory() as d:
                rc, out, err, f = _plan(d, _csv(cols), _config(roles))
                self.assertEqual(rc, 0, err)
                self.assertEqual(sorted(f["columns"]["電話番号"]),
                                 ["candidates"], declared)
                self.assertEqual(f["warnings"], [], declared)

    def test_mixed_form_stays_cell_level(self):
        cols = {"電話番号": ["０９０-1234-５６７８", "045-123-4567",
                             "0120-123-456", "03-1234-5678"],
                "age": AGES}
        roles = {"電話番号": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual([(w["column"], w["mixed_values"])
                              for w in f["warnings"]
                              if w["code"] == "mixed_form"],
                             [("電話番号", 1)])
            # the candidate still fires through the fold
            self.assertEqual(_cands(f, "電話番号")[0],
                             ("jp-phone-hyphen", "name+value", ID))


# --------------------------------------------------------------------------- #
class T61ZipNames(unittest.TestCase):
    """T61: the widened postal-code names — jp-zip and jp-zip-hyphen both
    grow from 6 to 13 names.  Each name is pinned one by one on the
    normalized forms: full-width digits fold onto the same name (郵便番号２
    -> 郵便番号2) and upper-case/snake variants normalize too; 〒 is
    NFKC-invariant."""

    def test_thirteen_names_fire_jp_zip(self):
        cols = {n: ZIPS for n in ZIP_NAMES}
        cols["age"] = AGES[:3]
        roles = {n: {"role": "keep"} for n in ZIP_NAMES}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in ZIP_NAMES:
                self.assertEqual(_cands(f, n),
                                 [("jp-zip", "name+value", PREFIX4),
                                  ("jp-zip-hyphen", "name", PREFIX4)], n)

    def test_hyphen_values_on_the_new_names(self):
        cols = {"郵便番号": ZIPS_HYPHEN, "〒番号": ZIPS_HYPHEN,
                "age": AGES[:3]}
        roles = {"郵便番号": {"role": "keep"}, "〒番号": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in ("郵便番号", "〒番号"):
                self.assertEqual(_cands(f, n),
                                 [("jp-zip-hyphen", "name+value", PREFIX4),
                                  ("jp-zip", "name", PREFIX4)], n)

    def test_normalized_variants_reach_the_names(self):
        # separate CSV: 郵便番号２ normalizes onto 郵便番号2, which must not
        # appear as its own column here
        cols = {"郵便番号２": ZIPS, "ＺＩＰ＿ＣＯＤＥ": ZIPS,
                "Postal_Code": ZIPS, "POSTCODE": ZIPS, "age": AGES[:3]}
        roles = {c: {"role": "keep"} for c in cols}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for n in ("郵便番号２", "ＺＩＰ＿ＣＯＤＥ", "Postal_Code", "POSTCODE"):
                self.assertEqual(_cands(f, n)[0],
                                 ("jp-zip", "name+value", PREFIX4), n)


if __name__ == "__main__":
    unittest.main()
