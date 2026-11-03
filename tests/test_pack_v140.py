"""jp-basic 1.4.0 tests (T52-T55, v0.7.3).

Three changes land together (one commit, pack + hintpack.py):

* T52 — ``jp-email``/``jp-phone``/``jp-mynumber``/``jp-card`` gain
  ``suggest {"role": "id"}``.  Their existing ``when``/``check``/``leak``
  stay as they are; the rules that had no ``column_names`` get the requested
  name lists (jp-mynumber, jp-card) and the rules that already had one get
  only the missing names from the request (mail_address/メールアドレス,
  電話番号/携帯電話).  With a suggestion on leak rules the candidate gate
  matters: a candidate now needs a name or a value signal, so an unrelated
  column (sex, diagnosis, prose) never carries one even though the leak scan
  still runs on it.
* T53/T54 — ``role_mismatch`` also fires for ``id`` suggestions: declared
  keep/qi/sensitive, evidence name+value (a column whose name does not match
  is leak's job — value-only evidence never fires it; name-only evidence
  never fires it).  id/drop declarations never fire it.  The qi behaviour is
  untouched.  The warning element keeps the exact current key set and the
  current line format with only the role word changed.
* T55 — ``jp-zip-hyphen``: the dash form ``#{3}-#{4}`` of the postal code.
  Its suggestion is ``{"role": "qi", "type": "prefix", "length": 4}`` — the
  same as jp-zip, so a column mixing both forms always suggests prefix 4
  (rule-id order puts jp-zip first and the two suggestion dicts are equal).
  Length 4 keeps the four partial levels of ``#{7}`` with the same remaining
  digit counts (6·5·4·3): 123-456* · 123-45** · 123-4*** · 123-****, then
  whole suppression.  Length 5 would add a redundant level that only hides
  the dash.  Full-width １２３－４５６７ reaches the shape through the
  v0.7.1 fold (dashes=True).
"""
import contextlib
import hashlib
import io
import json
import os
import tempfile
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# jp-basic 1.6.0 (the wider phone/email/card column names) — the pin,
# re-measured from the bytes.
BUILTIN_PACK_SHA = "79b33a820a3d6d994ef366e1f11be53d3cbd71a4f46a3847987cff147789e34f"

EMAILS = ["hina@example.co.jp", "haruto@example.ne.jp", "aoi@example.com"]
TEL_PLAIN = ["09012345678", "0312345678", "08087654321"]   # dashless 10/11 digits
MYNUMBERS = ["100000000005", "100000079191", "100000158385"]   # valid check digits
CARD = "4242424242424242"                                   # luhn-valid
AGES = ["40", "23", "55"]

RULE_OF = {"email": "jp-email", "tel": "jp-phone",
           "my_number": "jp-mynumber", "card_number": "jp-card"}


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def _csv(cols):
    """cols: ordered mapping column -> list of 3 values."""
    lines = [",".join(cols)]
    for i in range(3):
        lines.append(",".join(values[i] for values in cols.values()))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _config(roles):
    return json.dumps({"k": 2, "columns": roles}, ensure_ascii=False).encode("utf-8")


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


def _cands(findings, col):
    return [(c["rule"], c["evidence"], c["suggest"])
            for c in findings["columns"].get(col, {}).get("candidates", [])]


# --------------------------------------------------------------------------- #
class T52IdSuggestions(unittest.TestCase):
    """T52: the four rules suggest id on their column names (name+value or
    name evidence), the normalized full-width forms reach them, unrelated
    columns never gain a candidate, and --no-builtin-hints stays silent."""

    def test_builtin_pack_version_and_bytes(self):
        from sieve_crowd.hintpack import load_packs
        from sieve_crowd.hintpack_builtin import BUILTIN_PACK_BYTES
        self.assertEqual(hashlib.sha256(BUILTIN_PACK_BYTES).hexdigest(),
                         BUILTIN_PACK_SHA)
        packs = load_packs([], include_builtin=True)
        self.assertEqual(packs[0].version, "1.6.0")

    def test_four_rules_suggest_id_on_name_and_value(self):
        cols = {"email": EMAILS, "tel": TEL_PLAIN,
                "my_number": MYNUMBERS, "card_number": [CARD] * 3, "age": AGES}
        roles = {c: {"role": "keep"} for c in cols}
        roles["age"] = {"role": "qi", "type": "exact"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for col, rule in RULE_OF.items():
                self.assertIn((rule, "name+value", {"role": "id"}),
                              _cands(f, col), col)
            # nothing else fires on these columns; the hyphen twins
            # (jp-basic 1.5.0) also carry their name-only candidates on the
            # dashless values — same id suggestion, weaker evidence
            twin = {"tel": "jp-phone-hyphen", "card_number": "jp-card-hyphen"}
            for col, rule in RULE_OF.items():
                rules = [c[0] for c in _cands(f, col)]
                self.assertEqual(rules, [rule] + ([twin[col]] if col in twin else []),
                                 col)

    def test_requested_column_names_fire_as_name_evidence(self):
        # the names the request adds: full lists for the two rules that had
        # no column_names, only the missing names for the two that had one
        cols = {"mail_address": ["x"] * 3, "メールアドレス": ["x"] * 3,
                "電話番号": ["x"] * 3, "携帯電話": ["x"] * 3,
                "mynumber": ["x"] * 3, "マイナンバー": ["x"] * 3, "個人番号": ["x"] * 3,
                "card": ["x"] * 3, "クレジットカード": ["x"] * 3, "age": AGES}
        roles = {c: {"role": "keep"} for c in cols}
        roles["age"] = {"role": "qi", "type": "exact"}
        want = {"mail_address": "jp-email", "メールアドレス": "jp-email",
                "電話番号": "jp-phone", "携帯電話": "jp-phone",
                "mynumber": "jp-mynumber", "マイナンバー": "jp-mynumber",
                "個人番号": "jp-mynumber",
                "card": "jp-card", "クレジットカード": "jp-card"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for col, rule in want.items():
                self.assertIn((rule, "name", {"role": "id"}),
                              _cands(f, col), col)

    def test_fullwidth_uppercase_names_match(self):
        cols = {"ＥＭＡＩＬ": EMAILS, "ＴＥＬ": TEL_PLAIN,
                "ＭＹＮＵＭＢＥＲ": MYNUMBERS, "ＣＡＲＤ": [CARD] * 3,
                "Mail_Address": EMAILS, "age": AGES}
        roles = {c: {"role": "keep"} for c in cols}
        roles["age"] = {"role": "qi", "type": "exact"}
        want = {"ＥＭＡＩＬ": "jp-email", "ＴＥＬ": "jp-phone",
                "ＭＹＮＵＭＢＥＲ": "jp-mynumber", "ＣＡＲＤ": "jp-card",
                "Mail_Address": "jp-email"}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            for col, rule in want.items():
                self.assertIn((rule, "name+value", {"role": "id"}),
                              _cands(f, col), col)

    def test_unrelated_columns_never_gain_a_candidate(self):
        # the gate: a suggestion needs a name or a value signal.  sex and
        # diagnosis produce no findings at all; the prose column still gets
        # its leak count but no candidate (jp-email is a leak rule with a
        # suggestion — without the gate it would carry a bogus one).
        cols = {"sex": ["M", "F", "M"], "diagnosis": ["flu", "none", "flu"],
                "メモ": ["連絡先は hina@example.co.jp です", "メモのみ", "メモのみ"],
                "age": AGES}
        roles = {"sex": {"role": "qi", "type": "exact"},
                 "diagnosis": {"role": "sensitive"},
                 "メモ": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertNotIn("sex", f["columns"])
            self.assertNotIn("diagnosis", f["columns"])
            memo = f["columns"]["メモ"]
            self.assertIn("leaks", memo)
            self.assertEqual([lk["rule"] for lk in memo["leaks"]], ["jp-email"])
            self.assertNotIn("candidates", memo)
            self.assertNotIn("_suggest", memo)

    def test_no_builtin_hints_stays_silent(self):
        cols = {"email": EMAILS, "age": AGES}
        with tempfile.TemporaryDirectory() as d:
            src = os.path.join(d, "in.csv")
            with open(src, "wb") as fh:
                fh.write(_csv(cols))
            tpl = os.path.join(d, "t.json")
            rc, out, err = call("inspect", src, "--config-out", tpl,
                                "--no-builtin-hints")
            self.assertEqual(rc, 0, err)
            self.assertNotIn("hint-pack", out)
            with open(tpl, encoding="utf-8") as fh:
                template = json.load(fh)
            self.assertNotIn("_suggest", template["columns"]["email"])
            self.assertNotIn("_candidates", template["columns"]["email"])


# --------------------------------------------------------------------------- #
class T53RoleMismatchId(unittest.TestCase):
    """T53: role_mismatch fires for id suggestions on keep/qi/sensitive with
    name+value evidence; never on id/drop declarations; never for name-only
    columns (name, address); the note column (a card value under an
    unrelated name) is leak's job and gets no candidate at all from the
    builtin leak rules; a user-pack value-only candidate never fires it
    either.  The qi behaviour is exactly as before."""

    CSV_COLS = {"name": ["Takahashi Hina", "Kobayashi Haruto", "Yamamoto Aoi"],
                "email": EMAILS,
                "address": ["東京都渋谷区神宮前1-2-3", "東京都新宿区四谷2-4-1",
                            "大阪府大阪市北区梅田3-1-1"],
                "note": [CARD, "備考なし", "備考なし"],
                "birth_date": ["1986-11-02", "2003-01-03", "1971-10-04"],
                "age": AGES}

    def _roles(self, email_role, birth_role):
        roles = {c: {"role": "keep"} for c in self.CSV_COLS}
        roles["name"] = {"role": "id", "action": "drop"}
        roles["age"] = {"role": "qi", "type": "exact"}
        roles["birth_date"] = ({"role": "qi", "type": "date"}
                               if birth_role == "qi" else {"role": birth_role})
        roles["email"] = ({"role": "qi", "type": "exact"}
                          if email_role == "qi" else
                          {"role": "id", "action": "drop"}
                          if email_role == "id" else {"role": email_role})
        return roles

    def _rm(self, f):
        return [(w["column"], w["declared"], w["suggested"], w["evidence"])
                for w in f["warnings"] if w["code"] == "role_mismatch"]

    def test_keep_fires_for_id_and_still_for_qi(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(self.CSV_COLS),
                                    _config(self._roles("keep", "keep")))
            self.assertEqual(rc, 0, err)
            self.assertEqual(self._rm(f),
                             [("email", "keep", "id", "name+value"),
                              ("birth_date", "keep", "qi", "name+value")])
            # name-only candidates (name, address) never contradict a
            # declaration; the note column (a card value under an unrelated
            # name) gets its leak count but no candidate at all — a leak rule
            # skips the whole-column scan where its name does not match, so
            # value-only evidence never arises for the builtin id rules
            self.assertIn(("jp-person-name", "name", {"role": "id"}),
                          _cands(f, "name"))
            self.assertIn(("jp-address", "name", {"role": "id"}),
                          _cands(f, "address"))
            self.assertNotIn("candidates", f["columns"]["note"])
            self.assertIn("leaks", f["columns"]["note"])

    def test_qi_and_sensitive_fire_id_does_not(self):
        for declared in ("qi", "sensitive"):
            with tempfile.TemporaryDirectory() as d:
                rc, out, err, f = _plan(d, _csv(self.CSV_COLS),
                                        _config(self._roles(declared, "qi")))
                self.assertEqual(rc, 0, err)
                self.assertEqual(self._rm(f),
                                 [("email", declared, "id", "name+value")],
                                 declared)

    def test_id_and_drop_never_fire(self):
        for declared in ("id", "drop"):
            with tempfile.TemporaryDirectory() as d:
                rc, out, err, f = _plan(d, _csv(self.CSV_COLS),
                                        _config(self._roles(declared, "qi")))
                self.assertEqual(rc, 0, err)
                self.assertEqual(self._rm(f), [], declared)

    def test_qi_name_only_evidence_stays_silent(self):
        # slash dates: the candidate survives on the name evidence alone;
        # role_mismatch keeps not firing for it (current qi behaviour).  The
        # email column (declared qi here) still fires its id warning.
        cols = dict(self.CSV_COLS)
        cols["birth_date"] = ["1986/11/02", "2003/01/03", "1971/10/04"]
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols),
                                    _config(self._roles("qi", "keep")))
            self.assertEqual(rc, 0, err)
            self.assertIn(("jp-birthdate", "name", {"role": "qi", "type": "date"}),
                          _cands(f, "birth_date"))
            self.assertEqual(self._rm(f), [("email", "qi", "id", "name+value")])

    def test_value_only_candidate_never_fires(self):
        # the division of labour pinned on the value path: a USER-pack rule
        # without leak produces a value-only candidate on a column whose name
        # it does not know, and even a keep declaration gets no role_mismatch
        # — the warning is reserved for name+value (leak covers the column).
        pack = json.dumps({"schema": 1, "id": "extra", "rules": [
            {"id": "up-card", "when": {"value_shape": "#{13,19}"},
             "check": {"kind": "luhn"}, "suggest": {"role": "id"}}]}).encode()
        cols = {"note": [CARD, "備考なし", "備考なし"], "age": AGES}
        roles = {"note": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "extra.json")
            with open(p, "wb") as fh:
                fh.write(pack)
            rc, out, err, f = _plan(d, _csv(cols), _config(roles),
                                    "--hint-pack", p)
            self.assertEqual(rc, 0, err)
            self.assertIn(("up-card", "value", {"role": "id"}),
                          _cands(f, "note"))
            self.assertEqual(self._rm(f), [])


# --------------------------------------------------------------------------- #
class T54WarningShape(unittest.TestCase):
    """T54: the warning element keeps the current key set, the current line
    format with only the role word changed (en and ja), no cell value ever
    reaches the output, and the warnings follow the column order."""

    def _run(self, d, order):
        cols = {"email": EMAILS, "birth_date":
                ["1986-11-02", "2003-01-03", "1971-10-04"], "age": AGES}
        cols = {c: cols[c] for c in order}
        roles = {"email": {"role": "keep"},
                 "birth_date": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        return _plan(d, _csv(cols), _config(roles))

    def test_warning_element_keys_are_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = self._run(d, ["email", "birth_date", "age"])
            self.assertEqual(rc, 0, err)
            rm = [w for w in f["warnings"] if w["code"] == "role_mismatch"]
            self.assertEqual(len(rm), 2)
            for w in rm:
                self.assertEqual(set(w),
                                 {"code", "column", "declared", "suggested",
                                  "evidence"})

    def test_en_and_ja_lines_keep_the_format(self):
        with tempfile.TemporaryDirectory() as d:
            self._run(d, ["email", "birth_date", "age"])
            src, cfg = os.path.join(d, "in.csv"), os.path.join(d, "c.json")
            rc, _, err_en = call("plan", src, "-c", cfg, "--lang", "en")
            self.assertEqual(rc, 0, err_en)
            self.assertIn('  - role_mismatch: "email" suggests id but is '
                          "declared keep (evidence: name+value)", err_en)
            self.assertIn('  - role_mismatch: "birth_date" suggests qi but is '
                          "declared keep (evidence: name+value)", err_en)
            rc, _, err_ja = call("plan", src, "-c", cfg, "--lang", "ja")
            self.assertEqual(rc, 0, err_ja)
            self.assertIn("  - role_mismatch: 「email」は id を提案しますが、"
                          "設定では keep として宣言されています"
                          "（根拠: name+value）", err_ja)
            self.assertIn("  - role_mismatch: 「birth_date」は qi を提案しますが、"
                          "設定では keep として宣言されています"
                          "（根拠: name+value）", err_ja)

    def test_no_cell_value_reaches_the_output(self):
        cols = {"email": ["sentinel-addr@example.invalid"] * 3,
                "name": ["Sentinel Person"] * 3, "age": AGES}
        roles = {"email": {"role": "keep"}, "name": {"role": "keep"},
                 "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            blob = err + json.dumps(f, ensure_ascii=False)
            self.assertNotIn("sentinel-addr", blob)
            self.assertNotIn("Sentinel Person", blob)
            # the id warning itself is there
            self.assertIn(("email", "keep", "id", "name+value"),
                          [(w["column"], w["declared"], w["suggested"],
                            w["evidence"]) for w in f["warnings"]
                           if w["code"] == "role_mismatch"])

    def test_warnings_follow_the_column_order(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = self._run(d, ["email", "birth_date", "age"])
            rm = [w["column"] for w in f["warnings"]
                  if w["code"] == "role_mismatch"]
            self.assertEqual(rm, ["email", "birth_date"])
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = self._run(d, ["birth_date", "email", "age"])
            rm = [w["column"] for w in f["warnings"]
                  if w["code"] == "role_mismatch"]
            self.assertEqual(rm, ["birth_date", "email"])


# --------------------------------------------------------------------------- #
class T55HyphenZip(unittest.TestCase):
    """T55: jp-zip-hyphen recognises #{3}-#{4} (half-width and, through the
    fold, full-width), suggests exactly what jp-zip suggests (prefix 4), the
    partial levels keep jp-zip's remaining-digit structure (6·5·4·3) with the
    dash never masked, and mixed_form keeps its current observation."""

    def test_rule_shape_and_suggestion_match_jp_zip(self):
        from sieve_crowd.hintpack import load_packs
        packs = load_packs([], include_builtin=True)
        rules = {r.id: r for r in packs[0].rules}
        self.assertIn("jp-zip-hyphen", rules)
        self.assertIsNotNone(rules["jp-zip-hyphen"].shape)
        self.assertTrue(rules["jp-zip-hyphen"].shape.match("123-4567"))
        self.assertFalse(rules["jp-zip-hyphen"].shape.match("1234567"))
        self.assertFalse(rules["jp-zip-hyphen"].shape.match("1234-567"))
        # the suggestion is the same object of values as jp-zip's: prefix 4
        self.assertEqual(rules["jp-zip-hyphen"].suggest,
                         {"role": "qi", "type": "prefix", "length": 4})
        self.assertEqual(rules["jp-zip-hyphen"].suggest,
                         rules["jp-zip"].suggest)

    def test_partial_levels_pin(self):
        from sieve_crowd.generalize import PrefixGen
        g = PrefixGen(4)
        self.assertEqual([g.label("123-4567", k) for k in (1, 2, 3, 4)],
                         ["123-456*", "123-45**", "123-4***", "123-****"])
        self.assertEqual(g.label("123-4567", 5), "*")       # whole suppression
        self.assertEqual(g.describe(5, "ja"), "全体を隠す")
        # #{7} keeps its four levels with the same remaining digits 6·5·4·3
        self.assertEqual([g.label("1234567", k) for k in (1, 2, 3, 4)],
                         ["123456*", "12345**", "1234***", "123****"])
        self.assertEqual(g.label("1234567", 5), "*")

    def test_hyphen_values_candidate_name_plus_value(self):
        cols = {"〒": ["123-4567", "150-0052", "100-0042"], "age": AGES}
        roles = {"〒": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            cands = _cands(f, "〒")
            self.assertEqual(cands[0], ("jp-zip-hyphen", "name+value",
                                        {"role": "qi", "type": "prefix",
                                         "length": 4}))
            self.assertIn(("jp-zip", "name", {"role": "qi", "type": "prefix",
                                              "length": 4}), cands)

    def test_fullwidth_hyphen_values_match_through_the_fold(self):
        cols = {"〒": ["１２３－４５６７", "１５０－００５２", "１００－００４２"],
                "age": AGES}
        roles = {"〒": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            self.assertEqual(_cands(f, "〒")[0],
                             ("jp-zip-hyphen", "name+value",
                              {"role": "qi", "type": "prefix", "length": 4}))
            # one script per cell: no mixed-form observation
            self.assertFalse([w for w in f["warnings"]
                              if w["code"] == "mixed_form"])

    def test_mixed_column_always_suggests_prefix_4(self):
        cols = {"〒": ["1234567", "123-4567", "１２３－４５６７"], "age": AGES}
        roles = {"〒": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            cands = _cands(f, "〒")
            self.assertEqual([c[0] for c in cands], ["jp-zip", "jp-zip-hyphen"])
            self.assertEqual(cands[0][2], cands[1][2])   # identical suggestion
            self.assertEqual(cands[0][1], cands[1][1])   # both name+value

    def test_mixed_form_observation_is_unchanged(self):
        # a cell mixing full-width and half-width digits is observed (count 1)
        # while the candidate still fires through the fold
        cols = {"〒": ["１２３-4567", "150-0052", "100-0042"], "age": AGES}
        roles = {"〒": {"role": "keep"}, "age": {"role": "qi", "type": "exact"}}
        with tempfile.TemporaryDirectory() as d:
            rc, out, err, f = _plan(d, _csv(cols), _config(roles))
            self.assertEqual(rc, 0, err)
            mixed = [w for w in f["warnings"] if w["code"] == "mixed_form"]
            self.assertEqual([(w["column"], w["mixed_values"]) for w in mixed],
                             [("〒", 1)])
            self.assertEqual(_cands(f, "〒")[0][0], "jp-zip-hyphen")


if __name__ == "__main__":
    unittest.main()
