"""scan tests (T67-T77, v0.8.0).

``sieve-crowd scan INPUT`` assembles one static HTML page that shows how the
table looks right now: the provisional (or configured) roles, the group sizes,
the per-QI-column observations, the derived keep-vs-qi relations and the
repeated subjects — counts only, no cell values, no judgment.  The tests are
written first: they pin the CLI surface (T68), the byte-identical output and
the HTML hygiene rules (T69), the sentinel rule (T70), the provisional roles
and the draft (T71), the -c path (T72), the no-QI guidance (T73), the derived
and hidden-character observations (T74), the escaping/truncation/bars (T75),
the languages and the I/O shapes (T76) and the subject handling (T77).  T67
extends the subprocess import check: run/plan/inspect/audit never import
sieve_crowd.scan, and cli.py imports it function-level only.
"""
import contextlib
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

from sieve_crowd.cli import main

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CSV5 = "name,age,zip,sex,diagnosis\n" + "".join(
    f"Person{i},{20 + i % 6},{1500000 + i % 3},{'M' if i % 2 else 'F'},"
    f"{['flu', 'cold', 'none'][i % 3]}\n" for i in range(60))
CFG4 = {"k": 3, "l": 2, "columns": {
    "name": {"role": "id", "action": "drop"},
    "age": {"role": "qi", "type": "numeric", "widths": [5, 10]},
    "zip": {"role": "qi", "type": "prefix", "length": 3},
    "disease": {"role": "sensitive"}}}
CSV4 = "name,age,zip,disease\n" + "".join(
    f"Person{i},{20 + i % 6},{1500000 + i % 3},{['flu', 'cold', 'none'][i % 3]}\n"
    for i in range(60))
CFG4_ZIP_KEEP = {"k": 3, "l": 2, "columns": {
    "name": {"role": "id", "action": "drop"},
    "age": {"role": "qi", "type": "numeric", "widths": [5, 10]},
    "zip": {"role": "keep"},
    "disease": {"role": "sensitive"}}}
# memo (no candidate -> provisionally keep) and zip (qi) share the grouping;
# name carries invisible characters (provisional id -> never warned, T74) and
# every 20th age cell carries one (qi -> warned, 3 rows).
def _csv74_rows():
    out = ["name,memo,zip,age"]
    for i in range(60):
        age = f"{30 + i % 10}\u200b" if i % 20 == 0 else str(30 + i % 10)
        out.append(f"Person{i}\u200b,MZQ{i // 6},ZQ{i // 6},{age}")
    return "\n".join(out) + "\n"


CSV74 = _csv74_rows().encode()
CSV_NOQI = ("memo\n" + "".join(f"memo text {i}\n" for i in range(60))).encode()
LONG = "z" * 130


def _csv75_rows():
    head = 'a<b>&"\',na\u200bme,src=,zip,' + LONG
    rows = [head]
    for i in range(5):
        rows.append(f",,,{1500000 + i},")
    return "\n".join(rows) + "\n"


CSV75 = _csv75_rows().encode()


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


class _FakeStdin:
    """sys.stdin replacement with the .buffer attribute _read() uses."""

    def __init__(self, data):
        self.buffer = io.BytesIO(data)


class _FakeStdout:
    """sys.stdout replacement with the .buffer attribute '-o -' writes to."""

    def __init__(self):
        self.buffer = io.BytesIO()


def call_stdin(argv, data):
    err = io.StringIO()
    old_in, old_out = sys.stdin, sys.stdout
    fake_out = _FakeStdout()
    sys.stdin = _FakeStdin(data.encode() if isinstance(data, str) else data)
    sys.stdout = fake_out
    try:
        with contextlib.redirect_stderr(err):
            rc = main(list(argv))
    finally:
        sys.stdin, sys.stdout = old_in, old_out
    return rc, fake_out.buffer.getvalue().decode("utf-8"), err.getvalue()


class ScanCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.addCleanup(self._tmp.cleanup)

    def path(self, n):
        return os.path.join(self.d, n)

    def write(self, n, data):
        if isinstance(data, dict):
            data = json.dumps(data).encode()
        with open(self.path(n), "wb") as fh:
            fh.write(data if isinstance(data, bytes) else data.encode())
        return self.path(n)

    def read(self, n):
        with open(self.path(n), "rb") as fh:
            return fh.read()

    def scan(self, src, *extra):
        """Run scan with the default output name; return (rc, err, html)."""
        rc, out, err = call("scan", src, *extra)
        base = os.path.basename(src)
        default = os.path.join(os.path.dirname(src),
                               os.path.splitext(base)[0] + ".scan.html")
        with open(default, "rb") as fh:
            return rc, err, fh.read().decode("utf-8")


class T67ScanImportIsolation(ScanCase):
    """T67: run/plan/inspect/audit never import sieve_crowd.scan; the import
    lives inside the scan handler (function level), never at the top of
    cli.py."""

    def test_scan_is_never_imported_by_the_other_commands(self):
        def probe(cmd, banned):
            code = (
                "import sys; from sieve_crowd.cli import main; main(%r); "
                "hit = %r & set(sys.modules); "
                "print('OK' if not hit else 'IMPORTED:' + ','.join(sorted(hit)))"
            ) % (cmd, banned)
            out = subprocess.check_output([sys.executable, "-c", code], text=True)
            self.assertIn("OK", out, cmd)
            self.assertNotIn("IMPORTED:", out, cmd)

        people = os.path.join(REPO, "examples", "people.csv")
        config = os.path.join(REPO, "examples", "config.json")
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            probe(["run", people, "-c", config, "-o", out, "--quiet"],
                  {"sieve_crowd.hintpack", "sieve_crowd.derived", "sieve_crowd.audit",
                   "sieve_crowd.scan"})
            probe(["plan", people, "-c", config], {"sieve_crowd.audit", "sieve_crowd.scan"})
            probe(["inspect", people], {"sieve_crowd.audit", "sieve_crowd.scan"})
            probe(["audit", people, "-c", config], {"sieve_crowd.scan"})

    def test_cli_imports_scan_function_level_only(self):
        with open(os.path.join(REPO, "sieve_crowd", "cli.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIsNone(re.search(r"^(from \.scan|from sieve_crowd\.scan|"
                                    r"import sieve_crowd\.scan)\b", src, re.M))
        self.assertIn("from .scan import", src)      # inside the handler


class T68ScanCliSurface(ScanCase):
    """T68: the option surface, the default output name (people.tar.csv ->
    people.tar.scan.html), the unconditional overwrite, and the exit codes
    (0 ok, 1 I/O, 2 usage/config/same-path/stdin-without--o)."""

    def test_default_output_name_and_unconditional_overwrite(self):
        src = self.write("people.csv", CSV5)
        rc, err, html = self.scan(src)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(self.path("people.scan.html")))
        self.write("people.scan.html", "old")
        rc, _, _ = call("scan", src)                      # no --force on scan
        self.assertEqual(rc, 0)
        self.assertEqual(self.read("people.scan.html")[:15], b"<!DOCTYPE html>")
        tar = self.write("people.tar.csv", CSV5)
        rc, _, _ = call("scan", tar)
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.isfile(self.path("people.tar.scan.html")))

    def test_help_names_the_options(self):
        err, out = io.StringIO(), io.StringIO()
        with self.assertRaises(SystemExit) as ctx:
            with contextlib.redirect_stdout(out):
                main(["scan", "--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        for fragment in ("--output", "--hint-pack", "--no-builtin-hints",
                         "--no-hidden-chars", "--subject", "--k", "--max-rows",
                         "--no-derived", "--lang", "HTML"):
            self.assertIn(fragment, text)

    def test_stdin_without_output_is_refused(self):
        rc, out, err = call_stdin(["scan", "-"], CSV5)
        self.assertEqual(rc, 2)
        self.assertIn("-o", err)
        self.assertEqual(out, "")

    def test_output_must_differ_from_input_and_config(self):
        src = self.write("people.csv", CSV5)
        cfg = self.write("cfg.json", b"{}")
        before = self.read("people.csv")
        rc, _, err = call("scan", src, "-o", src)
        self.assertEqual(rc, 2)
        self.assertEqual(self.read("people.csv"), before)   # nothing written
        rc, _, _ = call("scan", src, "-c", cfg, "-o", cfg)
        self.assertEqual(rc, 2)
        self.assertEqual(self.read("cfg.json"), b"{}")

    def test_error_exit_codes(self):
        src = self.write("people.csv", CSV5)
        cfg = self.write("cfg.json", b"{}")
        rc, _, _ = call("scan", self.path("missing.csv"))
        self.assertEqual(rc, 1)                            # unreadable input: I/O
        rc, _, _ = call("scan", self.write("ragged.csv", b"a,b\n1\n"))
        self.assertEqual(rc, 2)                            # invalid table
        rc, _, _ = call("scan", src, "-c", self.path("missing.json"))
        self.assertEqual(rc, 1)
        rc, _, _ = call("scan", src, "-c", self.write("bad.json", b"{"))
        self.assertEqual(rc, 2)
        rc, _, _ = call("scan", src, "-c", self.write("norole.json",
                         b'{"columns": {"name": {"role": "keep"}}}'))
        self.assertEqual(rc, 2)                            # needs at least one qi
        badpack = self.write("bad.json", b"{")
        rc, _, _ = call("scan", src, "--hint-pack", badpack)
        self.assertEqual(rc, 2)                            # invalid pack
        rc, _, _ = call("scan", src, "--hint-pack", self.path("missing.json"))
        self.assertEqual(rc, 2)
        rc, _, _ = call("scan", src, "-c", cfg, "--k", "1")
        self.assertEqual(rc, 2)                            # k must be >= 2


class T69ScanDeterminismAndHygiene(ScanCase):
    """T69: the same input yields byte-identical HTML; UTF-8 without BOM, \\n
    ends, the CSP meta, the banned-token list, no environment values, the lang
    attribute follows --lang."""

    def test_same_input_same_bytes_and_no_env_values(self):
        src = self.write("people.csv", CSV5)
        rc, _, html1 = self.scan(src)
        self.assertEqual(rc, 0)
        rc, _, html2 = self.scan(src)
        self.assertEqual(html1, html2)
        raw = html1.encode("utf-8")
        self.assertFalse(raw.startswith(b"\xef\xbb\xbf"))  # no BOM
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\r", raw)
        self.assertIn(hashlib.sha256(CSV5.encode()).hexdigest()[:16], html1)
        self.assertNotIn(self.d, html1)                    # no paths, no host names
        low = html1.lower()
        for token in ("<script", "<link", "src=", "href=", "url(", "@import"):
            self.assertNotIn(token, low)
        self.assertIsNone(re.search(r"\bon[a-z]+\s*=", low))
        self.assertIn('<meta http-equiv="Content-Security-Policy" '
                      "content=\"default-src 'none'; style-src 'unsafe-inline'\">", html1)
        self.assertIn("Sieve Crowd 0.8.2", html1)
        self.assertIn("jp-basic", html1)
        self.assertIn("1.7.0", html1)

    def test_lang_attribute_follows_the_flag(self):
        src = self.write("people.csv", CSV5)
        rc, _, html = self.scan(src)
        self.assertIn('<html lang="en">', html)
        rc, _, html = self.scan(src, "--lang", "ja")
        self.assertIn('<html lang="ja">', html)


class T70ScanSentinels(ScanCase):
    """T70: no cell value ever reaches the HTML — column names, counts, rule
    ids, file names and the input SHA-256 only."""

    SENTINELS = ("MZQ3", "ZQ3", "Person7", "wisp-7q")

    def test_no_cell_values_in_the_report(self):
        lines = ["name,memo,zip,age"]
        for i in range(60):
            memo = f"wisp-7q {i}" if i == 7 else f"MZQ{i // 6}"
            lines.append(f"Person{i},{memo},ZQ{i // 6},{30 + i % 10}")
        src = self.write("people.csv", "\n".join(lines) + "\n")
        rc, _, html = self.scan(src)
        self.assertEqual(rc, 0)
        for s in self.SENTINELS:
            self.assertNotIn(s, html)
        for col in ("name", "memo", "zip", "age"):        # column names do appear
            self.assertIn(col, html)
        self.assertIn("60", html)                          # rows and columns do


class T71ScanProvisionalRoles(ScanCase):
    """T71: without -c the roles are provisional — the first candidate's
    suggestion (v0.5.2 candidate order), unassigned columns provisionally
    keep, id shown as provisional.  The column list is in column-name
    codepoint order with the fixed finding order."""

    def test_roles_evidence_and_fixed_order(self):
        src = self.write("people.csv", CSV5)
        rc, _, html = self.scan(src, "--lang", "ja")
        self.assertEqual(rc, 0)
        self.assertIn("id（仮・出力から除く前提）", html)     # name -> id (provisional)
        # v0.8.2: jp-sex/jp-diagnosis suggest on the CSV5 names too, so no
        # column stays unassigned (the unassigned path lives in T70/T74/T75)
        self.assertNotIn("未割当", html)
        self.assertIn("qi 3 列・id 1 列・sensitive 1 列", html)   # disjoint breakdown
        self.assertNotIn("keep 2 列", html)                 # the double count is gone
        self.assertEqual(html.count(">name+value<"), 2)     # age, zip evidence
        self.assertIn("jp-person-name", html)
        self.assertIn("jp-age", html)
        self.assertIn("jp-zip, jp-zip-hyphen", html)        # candidate rule ids
        self.assertIn(">sex</th><td>qi</td><td>name</td><td>jp-sex</td>", html)
        self.assertIn(">diagnosis</th><td>sensitive</td><td>name</td>"
                      "<td>jp-diagnosis</td>", html)
        for probe in (">age</th>", ">diagnosis</th>", ">name</th>",
                      ">sex</th>", ">zip</th>"):            # codepoint row order
            self.assertIn(probe, html)
        order = [html.index(p) for p in (">age</th>", ">diagnosis</th>", ">name</th>",
                                         ">sex</th>", ">zip</th>")]
        self.assertEqual(order, sorted(order))

    def test_next_step_draft_and_commands(self):
        src = self.write("people.csv", CSV5)
        rc, _, html = self.scan(src)
        self.assertIn('<pre', html)
        self.assertIn('&quot;role&quot;: &quot;id&quot;', html)
        self.assertIn('&quot;type&quot;: &quot;prefix&quot;', html)
        self.assertIn('&quot;length&quot;: 4', html)        # the zip suggestion
        # v0.8.2: every CSV5 column carries a suggestion, so no '?' remains
        self.assertNotIn('&quot;role&quot;: &quot;?&quot;', html)
        self.assertIn('&quot;role&quot;: &quot;sensitive&quot;', html)   # jp-diagnosis
        self.assertIn('&quot;type&quot;: &quot;category&quot;', html)      # jp-sex (no hierarchy)
        self.assertIn("sieve-crowd plan people.csv -c config.json", html)
        self.assertIn("sieve-crowd run people.csv -c config.json -o people.output.csv", html)


class T72ScanWithConfig(ScanCase):
    """T72: with -c the declared roles are used as-is (scan = plan + audit);
    --k overrides the config's k (plan's rule); --subject and --max-rows
    behave as on audit; the draft mirrors the configuration."""

    def test_declared_roles_draft_and_k_override(self):
        src = self.write("people.csv", CSV4)
        cfg = self.write("cfg.json", CFG4)
        rc, _, html = self.scan(src, "-c", cfg)
        self.assertEqual(rc, 0)
        self.assertNotIn("未割当", html)
        self.assertNotIn("（仮", html)
        self.assertIn("qi 2, id 1, sensitive 1 column(s)", html)
        self.assertIn("&quot;k&quot;: 3", html)
        self.assertIn("&quot;l&quot;: 2", html)
        self.assertIn("&quot;max_suppression&quot;: 0.05", html)
        self.assertIn("&quot;type&quot;: &quot;numeric&quot;", html)
        self.assertIn("k = 3", html)
        rc, _, html = self.scan(src, "-c", cfg, "--k", "7")
        self.assertIn("k = 7", html)
        self.assertIn("&quot;k&quot;: 7", html)

    def test_subject_and_max_rows(self):
        src = self.write("people.csv", CSV4)
        cfg = self.write("cfg.json", CFG4)
        rc, _, html = self.scan(src, "-c", cfg, "--subject", "name")
        self.assertEqual(rc, 0)
        self.assertIn('id="subject"', html)
        rc, _, html = self.scan(src, "-c", cfg, "--max-rows", "10")
        self.assertIn("read every row", html)
        rc, _, html = self.scan(src, "-c", cfg)
        self.assertNotIn("read every row", html)

    def test_role_mismatch_is_counted(self):
        src = self.write("people.csv", CSV4)
        cfg = self.write("cfg.json", CFG4_ZIP_KEEP)
        rc, _, html = self.scan(src, "-c", cfg)
        self.assertEqual(rc, 0)
        self.assertIn("role_mismatch 1", html)             # zip suggests qi
        self.assertIn("sensitive 1, keep 1 column(s)", html)   # declared keep, counted once


class T73ScanNoQiCandidates(ScanCase):
    """T73: without any provisional qi candidate the audit and derived
    sections are left out, the guidance is shown, and the exit code is 0."""

    def test_guidance_instead_of_audit_sections(self):
        src = self.write("notes.csv", CSV_NOQI)
        rc, err, html = self.scan(src)
        self.assertEqual(rc, 0)
        self.assertNotIn('id="groups"', html)
        self.assertNotIn('id="percolumn"', html)
        self.assertNotIn('id="derived"', html)
        self.assertIn("No quasi-identifier candidates", html)
        self.assertIn('id="next"', html)
        self.assertIn("&quot;role&quot;: &quot;?&quot;", html)
        rc, err, html = self.scan(src, "--lang", "ja")
        self.assertIn("準識別子の候補が見つからなかった", html)
        self.assertIn("要点", html)

    def test_no_builtin_hints_leaves_no_pack(self):
        src = self.write("notes.csv", CSV_NOQI)
        rc, _, html = self.scan(src, "--no-builtin-hints")
        self.assertEqual(rc, 0)
        self.assertNotIn("jp-basic", html)
        self.assertIn("no hint pack", html)


class T74ScanDerivedAndHidden(ScanCase):
    """T74: the derived relations run on the provisional roles (unassigned
    columns count as keep); --no-derived omits the section; the
    invisible-character counts attach to keep/qi/sensitive columns only — a
    provisional id column is never warned (the confirmed difference)."""

    def test_derived_pairs_on_provisional_roles(self):
        src = self.write("people.csv", CSV74)
        rc, _, html = self.scan(src)
        self.assertEqual(rc, 0)
        self.assertIn('id="derived"', html)
        self.assertIn("reveals_qi", html)
        self.assertIn("implied_by_qi", html)
        self.assertIn('class="n">60</td>', html)           # support 60
        self.assertIn("&quot;role&quot;: &quot;?&quot;", html)   # memo is unassigned

    def test_no_derived_omits_the_section(self):
        src = self.write("people.csv", CSV74)
        rc, _, html = self.scan(src, "--no-derived")
        self.assertNotIn('id="derived"', html)
        self.assertNotIn("reveals_qi", html)

    def test_hidden_chars_counts_and_the_provisional_id_exemption(self):
        src = self.write("people.csv", CSV74)
        rc, _, html = self.scan(src)
        self.assertEqual(rc, 0)
        self.assertEqual(html.count("hidden_chars"), 1)    # age (qi) only
        self.assertIn("hidden_chars 3", html)              # 3 rows carry U+200B
        rc, _, html = self.scan(src, "--no-hidden-chars")
        self.assertEqual(html.count("hidden_chars"), 0)


class T75ScanEscapingTruncationAndBars(ScanCase):
    """T75: user strings are escaped (hostile column names cannot inject
    markup), invisible characters become <U+XXXX>, column names truncate at
    120 code points (display only), and the percentages and bar widths are
    integer-only (floored)."""

    def test_hostile_names_escaping_and_truncation(self):
        src = self.write("odd.csv", CSV75)
        rc, _, html = self.scan(src)
        self.assertEqual(rc, 0)
        cols = html[html.index('id="columns"'):html.index('id="groups"')]
        self.assertIn("a&lt;b&gt;&amp;&quot;&#39;", cols)
        self.assertIn("src&#61;", cols)
        self.assertNotIn("src=", html)
        self.assertIn("na&lt;U+200B&gt;me", cols)
        self.assertIn("z" * 120 + "…", cols)               # truncated display
        self.assertNotIn("z" * 121, cols)
        self.assertIn("z" * 130, html)                     # full name in the draft

    def test_percent_and_bar_widths_are_integer_only(self):
        # v0.8.2 note: this fixture used a `sex` column until jp-basic 1.7.0
        # made sex a real qi candidate (which would split these groups);
        # `color` matches no rule and keeps the age-only grouping.
        lines = ["age,color"]
        for i in range(10):
            lines.append(f"{30 if i < 3 else 40},{'red' if i % 2 else 'blue'}")
        src = self.write("small.csv", "\n".join(lines) + "\n")
        rc, _, html = self.scan(src)
        self.assertEqual(rc, 0)
        self.assertIn("30.0%", html)                       # 1000 * 3 // 10
        self.assertIn("0.0%", html)
        self.assertIn('style="width:30%"', html)           # 3 rows of 10
        self.assertIn('style="width:70%"', html)
        self.assertNotIn("width:30.0%", html)


class T76ScanLanguagesAndIo(ScanCase):
    """T76: --lang switches the page language and the one-line stderr
    summary; -o - writes the HTML to stdout; INPUT - reads stdin (the heading
    says standard input, the SHA-256 is of the bytes read)."""

    def test_japanese_page_and_summary_line(self):
        src = self.write("people.csv", CSV5)
        rc, err, html = self.scan(src, "--lang", "ja")
        self.assertEqual(rc, 0)
        self.assertIn("要点", html)
        self.assertIn("列の一覧", html)
        self.assertIn("グループの大きさ", html)
        about = html[html.index('id="about"'):]            # the three cautions
        self.assertIn("観測であって、安全かどうかの判定ではありません", about)
        self.assertIn("1 人が 1 行の表であることを前提にしています", about)
        self.assertIn("k-匿名性は、別の情報との照合や", about)
        self.assertEqual(err.count("\n"), 1)               # one line only
        self.assertIn("行、", err)
        self.assertIn("people.scan.html", err)

    def test_english_page_and_summary_line(self):
        src = self.write("people.csv", CSV5)
        rc, err, html = self.scan(src)
        self.assertEqual(rc, 0)
        self.assertIn("Summary", html)
        self.assertIn("Group sizes", html)
        about = html[html.index('id="about"'):]            # the three cautions
        self.assertIn("not a judgment of safety", about)
        self.assertIn("one row per person", about)
        self.assertIn("k-anonymity does not prevent", about)
        self.assertEqual(err.count("\n"), 1)
        self.assertIn("scan: wrote", err)

    def test_stdout_and_stdin(self):
        rc, out, err = call_stdin(["scan", "-", "-o", "-"], CSV5)
        self.assertEqual(rc, 0)
        self.assertIn("<!DOCTYPE html>", out)
        self.assertIn("standard output", err)
        self.assertIn("(standard input)", out)
        self.assertIn(hashlib.sha256(CSV5.encode()).hexdigest(), out)
        rc, _, err = call_stdin(["scan", "-", "-o", "-", "--lang", "ja"], CSV5)
        self.assertIn("標準出力", err)
        rc, out, err = call_stdin(["scan", "-", "-o", self.path("in.html")], CSV5)
        self.assertEqual(rc, 0)
        self.assertIn("standard input", self.read("in.html").decode())


class T77ScanSubject(ScanCase):
    """T77: --subject counts the people behind the rows (provisional id
    columns qualify); a provisional qi column is refused; without --subject
    the section guides instead and names example columns."""

    def test_subject_section_with_provisional_id(self):
        lines = ["name,age,zip"]
        for i in range(60):
            lines.append(f"P{i // 3},{20 + i % 6},{1500000 + i % 3}")
        src = self.write("people.csv", "\n".join(lines) + "\n")
        rc, _, html = self.scan(src, "--subject", "name")
        self.assertEqual(rc, 0)
        self.assertIn('id="subject"', html)
        self.assertIn(">3-4</th>", html)                   # 3 rows per subject

    def test_subject_on_provisional_qi_is_refused(self):
        src = self.write("people.csv", CSV5)
        rc, _, err = call("scan", src, "--subject", "zip")
        self.assertEqual(rc, 2)
        self.assertIn("qi", err)
        rc, _, err = call("scan", src, "--subject", "nope")
        self.assertEqual(rc, 2)
        self.assertIn("not declared", err)

    def test_without_subject_the_section_guides(self):
        src = self.write("people.csv", CSV5)
        rc, _, html = self.scan(src)
        self.assertIn('id="subject"', html)
        self.assertIn("could serve as the subject column", html)
        self.assertIn("name", html)                        # the example column

    def test_no_qi_skips_the_subject_section(self):
        src = self.write("notes.csv", CSV_NOQI)
        rc, _, html = self.scan(src, "--subject", "memo")
        self.assertEqual(rc, 0)
        self.assertNotIn('id="subject"', html)
        self.assertIn("No quasi-identifier candidates", html)


if __name__ == "__main__":
    unittest.main()
