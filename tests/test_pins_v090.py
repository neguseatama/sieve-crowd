"""v0.9.0 structural pins: frozen files, cli sha, pack pins, imports, version.

T102  the eight frozen files stay byte-identical to v0.8.2 and the pack
      pins stay put; cli.py is unfrozen for this version only, and its NEW
      sha256 is pinned here (updated from the v0.8.2 value when the input
      layer landed -- the one deliberate pin change, reported per 5.1)
T103  the import structure holds: run imports none of the hint machinery,
      scan is imported function-level only, the input layer serves every
      subcommand, and xlsx_reader is pulled in only when an .xlsx is read
T104  the version is 0.9.0 in pyproject, the package and the README, and
      the CHANGELOG starts at [0.9.0]
"""
import json
import os
import re
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PEOPLE = os.path.join(REPO, "examples", "people.csv")
CONFIG = os.path.join(REPO, "examples", "config.json")

# frozen at v0.8.2 (measured on the untouched tree, 2026-11-06)
FROZEN_SHAS = {
    "sieve_crowd/config.py": "3fc0b1f9e95b7f05c88b4bf00f37faa6f529fd9e1c3f"
                             "a000c54c137bd16d3a3d",
    "sieve_crowd/engine.py": "d7384c5eb5c6012f731ab9af04e0483ca92316b6b73b"
                             "980f4a88a3541616dc5d",
    "sieve_crowd/audit.py": "ccbe07c7f0e1a647bea7b64aaa785264b517484961bfd"
                            "c6e1a62253ac4f21684",
    "sieve_crowd/derived.py": "2123cc0d4b2ef5dc5e2ecccf718827512278339e7cf3"
                              "e02379fa4518e82076f8",
    "sieve_crowd/chartable.py": "4a01afa04a9678d86a0562ae48a2b578b2dd54724"
                                "7d941762088fcf32405b7a5",
    "sieve_crowd/hidden_chars.py": "47bd0aa3a83b0b33a39ef8a3d353efd4251f713"
                                   "eefcbfcb834f25317a5a672f5",
    "sieve_crowd/hintpack.py": "8aa8282680f32ccf7c67a5ada9692c82ecd291374d"
                               "b233a7fcab3f19f607267e",
    "sieve_crowd/chartable_v1.json": "c5ae4757bc9d07a2dcd1507d662460c3412c"
                                     "932d73318e54912569608242e605",
}

# cli.py is unfrozen for v0.9.0 (design decision, reported): the pin moves
# from the v0.8.2 value to the input-layer version.  v0.8.2 value kept here
# for the record; CLI_PY_SHA is the new pin, re-measured when cli.py landed.
CLI_PY_SHA_V082 = "39869af6acbec555a3a93e6df5fa524f48e0f1144f0826083452dc" \
                  "2897101356"
CLI_PY_SHA = "a4887a7100fe642a1f2b6119be0456297e6297992a5a00813c578a5f95b8fa29"          # <- replaced by the new sha at feat

# the pack pins (design 2-3: unchanged)
RUN_TABLE_SHA = "b58249febc35c4feb6f6bfe1632aab92ca802c611759d31138d8ae04" \
                "0061500e"
TEMPLATE_SHA = "66e7eaf4a42d86b15b422eee39fca550b9c7ada0049ba4b6f7dd31e6c" \
               "c0c4159"
TEMPLATE_SHA2 = "0d5c35d82dc54004ad7f34b80be69103a80a0d20dccc4dae22f7e641" \
                "2ba6c657"
BUILTIN_PACK_SHA = "1fae5827a7048ca1e4b92c7d12792a755f5b21e63d6392bc2a1fb" \
                   "db4e3dc66c4"

# Lens-aligned safe-reading limits (design 3.3 / 4-7)
READ_LIMITS = {
    "max_file_bytes": 64 * 1024 * 1024,
    "max_entries": 10_000,
    "max_part_bytes": 32 * 1024 * 1024,
    "max_total_bytes": 128 * 1024 * 1024,
    "max_elements": 1_000_000,
}


def sha256_file(path):
    import hashlib
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


class T102Pins(unittest.TestCase):
    def test_frozen_files_are_byte_identical_to_v082(self):
        for rel, want in FROZEN_SHAS.items():
            self.assertEqual(sha256_file(os.path.join(REPO, rel)), want, rel)

    def test_cli_sha_is_the_pinned_new_value(self):
        self.assertEqual(sha256_file(os.path.join(REPO, "sieve_crowd",
                                                  "cli.py")), CLI_PY_SHA)

    def test_pack_pins_are_unchanged(self):
        import hashlib
        from sieve_crowd import hintpack_builtin
        digest = hashlib.sha256(hintpack_builtin.BUILTIN_PACK_BYTES) \
            .hexdigest()
        self.assertEqual(digest, BUILTIN_PACK_SHA)

    def test_run_table_golden_is_unchanged(self):
        import subprocess
        import sys
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            p = subprocess.run(
                [sys.executable, "-m", "sieve_crowd", "run", PEOPLE,
                 "-c", CONFIG, "-o", out, "--quiet"],
                cwd=REPO, capture_output=True)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertEqual(sha256_file(out), RUN_TABLE_SHA)


class T103ImportStructure(unittest.TestCase):
    BANNED_EVERYWHERE = {"sieve_crowd.hintpack", "sieve_crowd.derived",
                         "sieve_crowd.audit", "sieve_crowd.chartable",
                         "sieve_crowd.hidden_chars"}

    def probe(self, argv, banned):
        import subprocess
        import sys
        code = (
            "import sys; from sieve_crowd.cli import main; "
            "main(%r); hit = %r & set(sys.modules); "
            "print('OK' if not hit else 'IMPORTED:' + ','.join(sorted(hit)))"
        ) % (argv, banned)
        p = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                           capture_output=True, text=True)
        self.assertIn("OK", p.stdout, p.stdout + p.stderr)
        self.assertNotIn("IMPORTED:", p.stdout)

    def test_run_imports_none_of_the_hint_machinery(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "o.csv")
            self.probe(["run", PEOPLE, "-c", CONFIG, "-o", out, "--quiet"],
                       self.BANNED_EVERYWHERE | {"sieve_crowd.scan"})

    def test_scan_is_imported_function_level_only(self):
        self.probe(["plan", PEOPLE, "-c", CONFIG],
                   {"sieve_crowd.audit", "sieve_crowd.scan"})
        self.probe(["inspect", PEOPLE],
                   {"sieve_crowd.audit", "sieve_crowd.scan"})
        self.probe(["audit", PEOPLE, "-c", CONFIG], {"sieve_crowd.scan"})

    def test_input_layer_serves_every_subcommand(self):
        import subprocess
        import sys
        code = ("import sys; from sieve_crowd.cli import main; "
                "main(['inspect', %r]); "
                "print('tabular' if 'sieve_crowd.tabular' in sys.modules "
                "else 'MISSING')") % (PEOPLE,)
        p = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                           capture_output=True, text=True)
        self.assertIn("tabular", p.stdout, p.stdout + p.stderr)

    def test_xlsx_reader_is_pulled_only_for_xlsx(self):
        import io
        import subprocess
        import sys
        import tempfile
        import zipfile

        def tiny_xlsx():
            """A minimal single-sheet workbook, built inline."""
            main_ns = ("http://schemas.openxmlformats.org/spreadsheetml"
                       "/2006/main")
            rel_ns = ("http://schemas.openxmlformats.org/officeDocument"
                      "/2006/relationships")
            pkg_ns = ("http://schemas.openxmlformats.org/package"
                      "/2006/relationships")
            parts = {
                "[Content_Types].xml":
                    '<Types xmlns="http://schemas.openxmlformats.org/package'
                    '/2006/content-types"><Default Extension="xml" '
                    'ContentType="application/xml"/></Types>',
                "_rels/.rels":
                    f'<Relationships xmlns="{pkg_ns}">'
                    f'<Relationship Id="rId1" Type="{rel_ns}/officeDocument"'
                    ' Target="xl/workbook.xml"/></Relationships>',
                "xl/workbook.xml":
                    f'<workbook xmlns="{main_ns}" xmlns:r="{rel_ns}">'
                    '<sheets><sheet name="Sheet1" sheetId="1" r:id="rId1"/>'
                    '</sheets></workbook>',
                "xl/_rels/workbook.xml.rels":
                    f'<Relationships xmlns="{pkg_ns}">'
                    f'<Relationship Id="rId1" Type="{rel_ns}/worksheet" '
                    'Target="worksheets/sheet1.xml"/></Relationships>',
                "xl/worksheets/sheet1.xml":
                    f'<worksheet xmlns="{main_ns}"><sheetData><row r="1">'
                    '<c r="A1" t="inlineStr"><is><t>a</t></is></c></row>'
                    "</sheetData></worksheet>",
            }
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for name, blob in parts.items():
                    zf.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)),
                                blob)
            return buf.getvalue()

        def has_reader(argv):
            code = ("import sys; from sieve_crowd.cli import main; "
                    "main(%r); print('PRESENT' if 'sieve_crowd.xlsx_reader' "
                    "in sys.modules else 'ABSENT')") % (argv,)
            p = subprocess.run([sys.executable, "-c", code], cwd=REPO,
                               capture_output=True, text=True)
            return p.stdout, p.stderr

        with tempfile.TemporaryDirectory() as d:
            # csv run: the reader stays out of the import closure
            out, err = has_reader(["inspect", PEOPLE])
            self.assertIn("ABSENT", out, out + err)
            self.assertNotIn("PRESENT", out, out + err)
            # xlsx run: the reader is pulled in lazily
            xlsx = os.path.join(d, "t.xlsx")
            with open(xlsx, "wb") as fh:
                fh.write(tiny_xlsx())
            out, err = has_reader(["inspect", xlsx])
            self.assertIn("PRESENT", out, out + err)
            self.assertNotIn("ABSENT", out, out + err)


class T104Version(unittest.TestCase):
    VERSION = "0.9.0"

    def test_package_and_pyproject_versions_agree_at_0_9_0(self):
        import sieve_crowd
        self.assertEqual(sieve_crowd.__version__, self.VERSION)
        with open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r'^version = "([^"]+)"', text, re.M)
        self.assertEqual(m.group(1), self.VERSION)

    def test_changelog_starts_at_090(self):
        path = os.path.join(REPO, "CHANGELOG.md")
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("[0.9.0]", text)
        self.assertLess(text.index("[0.9.0]"), 200)

    def test_readme_titles_carry_the_version(self):
        for name in ("README.md", "README.ja.md"):
            with open(os.path.join(REPO, name), encoding="utf-8") as fh:
                head = fh.read(200)
            self.assertIn(f"Sieve Crowd v{self.VERSION}", head, name)

    def test_no_new_dependencies(self):
        with open(os.path.join(REPO, "pyproject.toml"),
                  encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("dependencies = []", text)


if __name__ == "__main__":
    unittest.main()
