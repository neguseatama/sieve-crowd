"""chartable tests (T40-T41, v0.7.1).

T40 pins the shared character table ``sieve_crowd/chartable_v1.json``: the
file is byte-exact (sha256), the required keys and types hold, the invisible
set equals the Sieve Lens v0.18.0 constants (hard-coded here, not read from
``unicodedata``), twins carries exactly 102 entries and never contradicts the
fullwidth_ascii range, every tamper or defect is a hard error (no silent
fallback table), the wheel ships the data file (pyproject text pin), and
``chartable.py`` never imports ``unicodedata``.

T41 pins the fold itself: fullwidth digits/letters/symbols, U+3000/U+00A0,
every dash of the table, invisible removal — and that every printable ASCII
character is invariant, that fold is idempotent, and that ``dashes=False``
keeps U+30FC (the long-vowel mark) untouched.
"""
import hashlib
import json
import os
import unittest

from sieve_crowd import chartable
from sieve_crowd.chartable import ChartableError, load_table, parse_table

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TABLE_PATH = os.path.join(REPO, "sieve_crowd", "chartable_v1.json")

# The shared table is a replica of the Sieve Lens canonical file, pinned by
# sha256 (the request, section 2).  One byte off is a hard error.
CHARTABLE_SHA = "c5ae4757bc9d07a2dcd1507d662460c3412c932d73318e54912569608242e605"

# Sieve Lens v0.18.0 invisible constants, hard-coded (the request, T40).
LENS_ZERO_WIDTH = {0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}
LENS_BIDI = {0x202A, 0x202B, 0x202C, 0x202D, 0x202E,
             0x2066, 0x2067, 0x2068, 0x2069}
LENS_TAG = set(range(0xE0000, 0xE007F + 1))
LENS_VS = set(range(0xFE00, 0xFE0F + 1)) | set(range(0xE0100, 0xE01EF + 1))


def _raw():
    with open(TABLE_PATH, "rb") as fh:
        return fh.read()


def _defect(mutate):
    """Return the table with one mutation applied (a parsed, valid-JSON object)."""
    data = json.loads(_raw().decode("utf-8"))
    mutate(data)
    return data


class T40ChartableFile(unittest.TestCase):
    """T40: the file, its content contract, its error paths, its shipping."""

    def test_file_is_byte_exact(self):
        with open(TABLE_PATH, "rb") as fh:
            self.assertEqual(hashlib.sha256(fh.read()).hexdigest(), CHARTABLE_SHA)

    def test_required_keys_and_types(self):
        data = json.loads(_raw().decode("utf-8"))
        self.assertEqual(data["schema"], "sieve-chartable/1")
        self.assertEqual(data["version"], 1)
        self.assertIsInstance(data["description"], str)
        inv = data["invisible"]
        self.assertIsInstance(inv["zero_width"], list)
        self.assertIsInstance(inv["bidi_control"], list)
        self.assertIsInstance(inv["tag"], list)
        self.assertIsInstance(inv["variation_selector"], list)
        for item in inv["zero_width"] + inv["bidi_control"]:
            self.assertRegex(item, r"^[0-9A-F]{4,6}$")
        for lo, hi in inv["tag"] + inv["variation_selector"]:
            self.assertRegex(lo, r"^[0-9A-F]{4,6}$")
            self.assertRegex(hi, r"^[0-9A-F]{4,6}$")
        fa = data["fullwidth_ascii"]
        self.assertEqual(fa, {"base": "0021", "from": "FF01", "to": "FF5E"})
        self.assertIsInstance(data["spaces"], list)
        self.assertEqual(data["spaces"], ["00A0", "3000"])
        self.assertIsInstance(data["dashes"], list)
        self.assertEqual(data["dashes"],
                         ["2010", "2011", "2012", "2013", "2014", "2015",
                          "2212", "30FC", "FF70"])

    def test_invisible_matches_lens_v18_constants(self):
        cats = chartable.invisible_categories()
        self.assertEqual(cats["zero_width"], LENS_ZERO_WIDTH)
        self.assertEqual(cats["bidi_control"], LENS_BIDI)
        self.assertEqual(cats["tag"], LENS_TAG)
        self.assertEqual(cats["variation_selector"], LENS_VS)

    def test_twins_has_102_entries_and_agrees_with_fullwidth_range(self):
        with open(TABLE_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        twins = data["twins"]
        self.assertEqual(len(twins), 102)
        for src, dst in twins.items():
            self.assertRegex(src, r"^[0-9A-F]{4,6}$")
            self.assertIsInstance(dst, str)
            self.assertEqual(len(dst), 1)
            self.assertLessEqual(ord(dst), 0x7E)      # every target is ASCII
        # inside the fullwidth range the twins must agree with the range fold
        lo, hi, base = 0xFF01, 0xFF5E, 0x0021
        for src, dst in twins.items():
            cp = int(src, 16)
            if lo <= cp <= hi:
                self.assertEqual(ord(dst), base + (cp - lo), src)
        # and the ASCII printable range is never a key (invariant by design)
        for src in list(twins) + data["spaces"] + data["dashes"]:
            self.assertFalse(0x20 <= int(src, 16) <= 0x7E, src)

    def test_tampered_bytes_are_rejected(self):
        raw = _raw()
        tampered = raw.replace(b'"2010"', b'"201A"', 1)   # one byte, still JSON
        self.assertNotEqual(tampered, raw)
        with self.assertRaises(ChartableError):
            load_table(tampered)

    def test_defects_are_rejected(self):
        def drop_spaces(data):
            del data["spaces"]

        def bad_schema(data):
            data["schema"] = "sieve-chartable/2"

        def spaces_as_string(data):
            data["spaces"] = "00A0"

        def bad_hex(data):
            data["invisible"]["zero_width"] = ["20G0"]

        def reversed_range(data):
            data["invisible"]["tag"] = [["E007F", "E0000"]]

        def ascii_key(data):
            data["twins"]["0041"] = "B"

        def non_ascii_target(data):
            data["twins"]["0391"] = "\u03A9"

        def two_char_target(data):
            data["twins"]["0391"] = "AB"

        def overlaps_invisible(data):
            data["twins"]["FEFF"] = "F"

        for mutate in (drop_spaces, bad_schema, spaces_as_string, bad_hex,
                       reversed_range, ascii_key, non_ascii_target,
                       two_char_target, overlaps_invisible):
            with self.assertRaises(ChartableError, msg=mutate.__name__):
                parse_table(_defect(mutate))

    def test_pyproject_ships_the_data_file(self):
        with open(os.path.join(REPO, "pyproject.toml"), encoding="utf-8") as fh:
            pyproject = fh.read()
        self.assertIn("[tool.setuptools.package-data]", pyproject)
        self.assertIn('sieve_crowd = ["chartable_v1.json"]', pyproject)

    def test_chartable_module_never_imports_unicodedata(self):
        with open(os.path.join(REPO, "sieve_crowd", "chartable.py"),
                  encoding="utf-8") as fh:
            self.assertNotIn("unicodedata", fh.read())

    def test_module_fold_uses_the_pinned_file(self):
        # the lazy singleton loads the package file and verifies the sha first
        self.assertEqual(chartable.fold("\uFF21\uFF22"), "AB")
        self.assertEqual(chartable.fold("1\u200B2"), "12")


class T41Fold(unittest.TestCase):
    """T41: the fold is a fixed mapping — fullwidth, spaces, dashes,
    invisible removal, ASCII invariant, idempotent."""

    def test_fullwidth_digits_letters_and_symbols(self):
        self.assertEqual(chartable.fold("\uFF11\uFF12\uFF13"), "123")
        self.assertEqual(chartable.fold("\uFF10\u3000\uFF19"), "0 9")
        self.assertEqual(chartable.fold("\uFF21\uFF42\uFF3A"), "AbZ")
        self.assertEqual(chartable.fold("\uFF20\uFF0E\uFF05"), "@.%")
        self.assertEqual(chartable.fold("\uFF11\uFF12\uFF13\uFF0D\uFF14\uFF15\uFF16\uFF17"),
                         "123-4567")          # U+FF0D folds via the fullwidth range

    def test_spaces_fold_to_ascii_space(self):
        self.assertEqual(chartable.fold("a\u00A0b\u3000c"), "a b c")

    def test_dashes_fold_only_when_asked(self):
        s = "a\u2010b\u2015c\u2212d\u30FCe\uFF70f"
        self.assertEqual(chartable.fold(s, dashes=False), s)
        self.assertEqual(chartable.fold(s, dashes=True), "a-b-c-d-e-f")
        # the long-vowel-marked phone number folds only with dashes=True
        self.assertEqual(chartable.fold("090\u30FC1234\u30FC5678", dashes=True),
                         "090-1234-5678")
        self.assertIn("\u30FC", chartable.fold("090\u30FC1234\u30FC5678"))

    def test_invisible_characters_are_removed(self):
        self.assertEqual(chartable.fold("1\u200B2\u200C3\u200D4\u20605\uFEFF6"),
                         "123456")
        self.assertEqual(chartable.fold("a\u202Eb\u2066c\u2069d"), "abcd")
        self.assertEqual(chartable.fold("\U000E0001x\U000E007Fy"), "xy")
        self.assertEqual(chartable.fold("\u7532\uFE0F\u4E59\U000E01EF\u4E19"), "\u7532\u4E59\u4E19")

    def test_twins_fold_to_ascii(self):
        self.assertEqual(chartable.fold("\u0410\u0412\u0415\u041A\u041C\u041D"
                                        "\u041E\u0420\u0421\u0422\u0423\u0425"),
                         "ABEKMHOPCTYX")
        self.assertEqual(chartable.fold("\u0456\u0430\u0435\u0440"), "iaep")
        self.assertEqual(chartable.fold("\u03B9\u03BD\u03BF\u03C1\u03C5\u03C7"), "ivopux")
        # look-alikes that are NOT in the table stay untouched
        self.assertEqual(chartable.fold("\u03B1\u0432"), "\u03B1\u0432")

    def test_ascii_printable_is_invariant(self):
        for cp in range(0x20, 0x7F):
            ch = chr(cp)
            self.assertEqual(chartable.fold(ch), ch, hex(cp))
            self.assertEqual(chartable.fold(ch, dashes=True), ch, hex(cp))

    def test_fold_is_idempotent(self):
        samples = ["\uFF11\uFF12\uFF0D\uFF14\u3000\u2015\u200B\u30FC",
                   "090\u30FC1234\u30FC5678\u00A0\u202E",
                   "\u0410\u0412\uFF21\uFF22\uFEFF\uE0001"]
        for s in samples:
            for dashes in (False, True):
                once = chartable.fold(s, dashes=dashes)
                self.assertEqual(chartable.fold(once, dashes=dashes), once)


if __name__ == "__main__":
    unittest.main()
