import contextlib
import io
import json
import os
import sys
import tempfile
import types
import unittest

from sieve_crowd.cli import main
from sieve_crowd.jsonio import read_json, write_json
from sieve_crowd.model import InputError
from sieve_crowd.tableio import detect_format, read_any, write_any
from sieve_crowd.xmlio import read_xml, write_xml

HEADER = ["name", "age", "zip", "disease"]
ROWS = [["Alice", "30", "1500001", "flu"],
        ["Bob", "31", "1500002", "cold"],
        ["Carol", "32", "1500001", "flu"]]
CONFIG = {"k": 2, "l": 2, "columns": {
    "name": {"role": "id", "action": "drop"},
    "age": {"role": "qi", "type": "numeric", "widths": [5]},
    "zip": {"role": "qi", "type": "prefix", "length": 3},
    "disease": {"role": "sensitive"}}}

RECORDS = [{"name": "Alice", "age": 30, "zip": "1500001", "disease": "flu"},
           {"name": "Bob", "age": 31, "zip": "1500002", "disease": "cold"},
           {"name": "Carol", "age": 32, "zip": "1500001", "disease": "flu"}]


def csv_bytes():
    return ("name,age,zip,disease\n"
            + "".join(",".join(r) + "\n" for r in ROWS)).encode()


def call(*argv):
    err, out = io.StringIO(), io.StringIO()
    with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
        rc = main(list(argv))
    return rc, out.getvalue(), err.getvalue()


def call_with_stdin(data: bytes, *argv):
    err, out = io.StringIO(), io.StringIO()
    original = sys.stdin
    sys.stdin = io.TextIOWrapper(io.BytesIO(data))
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(out):
            rc = main(list(argv))
    finally:
        sys.stdin = original
    return rc, out.getvalue(), err.getvalue()


class JsonTests(unittest.TestCase):
    def test_records_form(self):
        data = json.dumps(RECORDS).encode()
        self.assertEqual(read_json(data), (HEADER, ROWS))

    def test_explicit_form(self):
        data = json.dumps({"header": HEADER, "rows": ROWS}).encode()
        self.assertEqual(read_json(data), (HEADER, ROWS))

    def test_records_and_explicit_forms_agree(self):
        # age 30 (number) and "30" (string) normalize to the same table
        a = read_json(json.dumps(RECORDS).encode())
        b = read_json(json.dumps({"header": HEADER, "rows": ROWS}).encode())
        self.assertEqual(a, b)

    def test_key_order_may_vary_after_the_first_record(self):
        data = json.dumps([{"a": 1, "b": 2}, {"b": 3, "a": 4}]).encode()
        self.assertEqual(read_json(data), (["a", "b"], [["1", "2"], ["4", "3"]]))

    def test_empty_input_has_no_header(self):
        with self.assertRaises(InputError):
            read_json(b"[]")
        with self.assertRaises(InputError):
            read_json(b"[{}]")

    def test_key_set_mismatch_is_rejected(self):
        data = json.dumps([{"a": 1}, {"a": 1, "b": 2}]).encode()
        with self.assertRaises(InputError):
            read_json(data)

    def test_nested_value_is_rejected_and_not_echoed(self):
        data = b'[{"a": {"secret": "SECRETVALUE"}}]'
        with self.assertRaises(InputError) as ctx:
            read_json(data)
        self.assertNotIn("SECRETVALUE", str(ctx.exception))

    def test_null_boolean_and_numbers(self):
        doc = [{"e": None, "t": True, "f": False, "i": 30, "x": 30.5, "s": "hi"}]
        header, rows = read_json(json.dumps(doc).encode())
        self.assertEqual(header, ["e", "t", "f", "i", "x", "s"])
        self.assertEqual(rows, [["", "true", "false", "30", "30.5", "hi"]])

    def test_int_and_float_stay_distinct(self):
        _, rows = read_json(json.dumps([{"a": 30}, {"a": 30.0}]).encode())
        self.assertEqual(rows, [["30"], ["30.0"]])

    def test_duplicate_key_is_rejected(self):
        with self.assertRaises(InputError):
            read_json(b'[{"a": 1, "a": 2}]')

    def test_non_rfc8259_numbers_are_rejected(self):
        for literal in (b'[{"a": NaN}]', b'[{"a": Infinity}]', b'[{"a": 1e400}]'):
            with self.assertRaises(InputError):
                read_json(literal)

    def test_wrong_top_level_shape_is_rejected(self):
        for data in (b'{"a": 1}', b'"x"', b"5", b'{"header": ["a"]}'):
            with self.assertRaises(InputError):
                read_json(data)

    def test_explicit_form_row_width_and_header(self):
        with self.assertRaises(InputError):
            read_json(b'{"header": ["a", "b"], "rows": [["1"]]}')
        with self.assertRaises(InputError):
            read_json(b'{"header": [], "rows": []}')
        with self.assertRaises(InputError):
            read_json(b'{"header": ["a", 2], "rows": [["1", "2"]]}')

    def test_write_output_is_records_form_without_null(self):
        out = write_json(["a", "b"], [["x", ""], ["y&", "z"]])
        self.assertEqual(json.loads(out), [{"a": "x", "b": ""}, {"a": "y&", "b": "z"}])
        self.assertNotIn(b"null", out)
        self.assertTrue(out.endswith(b"\n"))


class XmlTests(unittest.TestCase):
    DOC = (b"<root><r><f name=\"name\">Alice</f><f name=\"zip\">150&amp;1</f></r>"
           b"<r><f name=\"zip\">150002</f><f name=\"name\">Bob</f></r></root>")

    def test_read_maps_fields_by_name(self):
        header, rows = read_xml(self.DOC)
        self.assertEqual(header, ["name", "zip"])       # field order may vary later on
        self.assertEqual(rows, [["Alice", "150&1"], ["Bob", "150002"]])

    def test_empty_element_is_an_empty_cell(self):
        _, rows = read_xml(b"<t><r><f name=\"a\"/></r></t>")
        self.assertEqual(rows, [[""]])

    def test_text_is_preserved_verbatim(self):
        _, rows = read_xml(b"<t><r><f name=\"a\">  spaced  </f></r></t>")
        self.assertEqual(rows, [["  spaced  "]])

    def test_empty_root_is_rejected(self):
        with self.assertRaises(InputError):
            read_xml(b"<t></t>")

    def test_missing_name_attribute(self):
        with self.assertRaises(InputError):
            read_xml(b"<t><r><f>1</f></r></t>")

    def test_unexpected_attributes_are_rejected(self):
        with self.assertRaises(InputError):
            read_xml(b"<t><r id=\"7\"><f name=\"a\">1</f></r></t>")
        with self.assertRaises(InputError):
            read_xml(b"<t><r><f name=\"a\" type=\"n\">1</f></r></t>")

    def test_duplicate_and_unknown_columns_are_rejected(self):
        with self.assertRaises(InputError):
            read_xml(b"<t><r><f name=\"a\">1</f><f name=\"a\">2</f></r></t>")
        with self.assertRaises(InputError):
            read_xml(b"<t><r><f name=\"a\">1</f></r><r><f name=\"a\">1</f>"
                     b"<f name=\"b\">2</f></r></t>")

    def test_nested_field_is_rejected(self):
        with self.assertRaises(InputError):
            read_xml(b"<t><r><f name=\"a\"><x>1</x></f></r></t>")

    def test_doctype_is_rejected(self):
        with self.assertRaises(InputError):
            read_xml(b"<!DOCTYPE t [<!ENTITY a \"x\">]><t><r><f name=\"a\">&a;</f></r></t>")

    def test_billion_laughs_is_rejected(self):
        bomb = (b"<!DOCTYPE r [\n<!ENTITY a0 \"aaaa\">\n"
                + b"".join(f"<!ENTITY a{i} \"&a{i-1};&a{i-1};\">\n".encode()
                           for i in range(1, 10))
                + b"]>\n<t><r><f name=\"a\">&a9;</f></r></t>")
        with self.assertRaises(InputError) as ctx:
            read_xml(bomb)
        self.assertIn("DOCTYPE", str(ctx.exception))

    def test_namespace_is_rejected(self):
        with self.assertRaises(InputError):
            read_xml(b'<t xmlns="urn:x"><r><f name="a">1</f></r></t>')

    def test_stray_text_is_rejected(self):
        with self.assertRaises(InputError):
            read_xml(b"<t>stray<r><f name=\"a\">1</f></r></t>")
        with self.assertRaises(InputError):
            read_xml(b"<t><r><f name=\"a\">1</f></r>stray</t>")

    def test_write_is_deterministic_and_escaped(self):
        out = write_xml(["a", "b"], [["x&y", "<z>"], ["", ""]])
        self.assertEqual(out, b"<?xml version='1.0' encoding='UTF-8'?>\n"
                              b"<table>\n  <row>\n    <f name=\"a\">x&amp;y</f>\n"
                              b"    <f name=\"b\">&lt;z&gt;</f>\n  </row>\n"
                              b"  <row>\n    <f name=\"a\" />\n"
                              b"    <f name=\"b\" />\n  </row>\n</table>\n")
        self.assertEqual(read_xml(out), (["a", "b"], [["x&y", "<z>"], ["", ""]]))

    def test_write_round_trips_whitespace(self):
        out = write_xml(["a"], [["  spaced  "]])
        self.assertEqual(read_xml(out), (["a"], [["  spaced  "]]))

    def test_write_rejects_control_characters_without_echoing_them(self):
        with self.assertRaises(InputError) as ctx:
            write_xml(["a"], [["bad\x0bvalue"]])
        self.assertIn("row 1", str(ctx.exception))
        self.assertIn("'a'", str(ctx.exception))
        self.assertNotIn("\x0b", str(ctx.exception))
        with self.assertRaises(InputError):
            write_xml(["na\x0bme"], [["x"]])


class DetectionTests(unittest.TestCase):
    def test_by_extension(self):
        self.assertEqual(detect_format(".csv"), "csv")
        self.assertEqual(detect_format(".json"), "json")
        self.assertEqual(detect_format(".xml"), "xml")
        self.assertEqual(detect_format(".JSON"), "json")

    def test_spreadsheet_formats_are_refused_with_guidance(self):
        with self.assertRaises(InputError) as ctx:
            detect_format(".xlsx")
        self.assertIn("Excel", str(ctx.exception))
        with self.assertRaises(InputError):
            detect_format(".xls")

    def test_unknown_extension_names_the_overrides(self):
        with self.assertRaises(InputError) as ctx:
            detect_format(".parquet")
        self.assertIn("--in-format", str(ctx.exception))


class FormatIndependence(unittest.TestCase):
    """I8: the same logical table gives byte-identical output, whatever carried it."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self.cfg = self.write("cfg.json", json.dumps(CONFIG).encode())
        self.write("in.csv", csv_bytes())
        self.write("in.json", json.dumps(RECORDS).encode())
        self.write("in.xml", write_xml(HEADER, ROWS))

    def write(self, name, data):
        with open(os.path.join(self.d, name), "wb") as fh:
            fh.write(data)
        return os.path.join(self.d, name)

    def read(self, name):
        with open(os.path.join(self.d, name), "rb") as fh:
            return fh.read()

    def _run(self, src, dst):
        rc, _, err = call("run", os.path.join(self.d, src), "-c", self.cfg, "-o",
                          os.path.join(self.d, dst))
        self.assertEqual(rc, 0, err)
        return self.read(dst)

    def test_three_formats_one_output(self):
        outs = [self._run(f"in.{f}", f"out-{f}.csv") for f in ("csv", "json", "xml")]
        self.assertEqual(outs[0], outs[1])
        self.assertEqual(outs[1], outs[2])
        self.assertTrue(outs[0].startswith(b"age,zip,disease\n"))

    def test_adapters_round_trip(self):
        table = read_any(csv_bytes(), "csv")
        for fmt, writer in (("json", write_json), ("xml", write_xml)):
            self.assertEqual(read_any(writer(*table), fmt), table)

    def test_csv_in_json_out_and_receipt(self):
        rc, _, err = call("run", os.path.join(self.d, "in.csv"), "-c", self.cfg,
                          "-o", os.path.join(self.d, "out.json"),
                          "--report-json", os.path.join(self.d, "r.json"))
        self.assertEqual(rc, 0, err)
        records = json.loads(self.read("out.json"))
        self.assertIsInstance(records, list)
        self.assertGreater(len(records), 0)
        self.assertTrue(all(isinstance(rec, dict) for rec in records))
        self.assertEqual(len({tuple(rec) for rec in records}), 1)   # one column set
        self.assertNotIn("name", records[0])                       # the id column is gone
        report = json.loads(self.read("r.json"))
        self.assertEqual(report["io"], {"input_format": "csv", "output_format": "json"})
        self.assertIn("Format: csv in, json out", err)

    def test_japanese_format_line(self):
        rc, _, err = call("run", os.path.join(self.d, "in.xml"), "-c", self.cfg,
                          "--dry-run", "--lang", "ja")
        self.assertEqual(rc, 0, err)
        self.assertIn("形式: 入力 xml", err)


class CliFormats(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.addCleanup(self._tmp.cleanup)
        self.cfg = self.write("cfg.json", json.dumps(CONFIG).encode())
        self.write("in.json", json.dumps(RECORDS).encode())
        self.write("in.xml", write_xml(HEADER, ROWS))

    def write(self, name, data):
        with open(os.path.join(self.d, name), "wb") as fh:
            fh.write(data)
        return os.path.join(self.d, name)

    def path(self, name):
        return os.path.join(self.d, name)

    def test_inspect_json_and_xml(self):
        for name in ("in.json", "in.xml"):
            rc, out, err = call("inspect", self.path(name), "--lang", "en")
            self.assertEqual(rc, 0, err)
            self.assertIn("records: 3", out)

    def test_extension_must_be_known(self):
        self.write("in.txt", json.dumps(RECORDS).encode())
        rc, _, err = call("run", self.path("in.txt"), "-c", self.cfg, "--dry-run")
        self.assertEqual(rc, 2)
        self.assertIn("--in-format", err)
        rc, _, err = call("run", self.path("in.txt"), "-c", self.cfg, "--dry-run",
                          "--in-format", "json")
        self.assertEqual(rc, 0, err)
        rc, _, err = call("run", self.path("in.json"), "-c", self.cfg,
                          "-o", self.path("out.txt"))
        self.assertEqual(rc, 2)
        self.assertIn("--out-format", err)
        rc, _, _ = call("run", self.path("in.json"), "-c", self.cfg,
                        "-o", self.path("out.xlsx"))
        self.assertEqual(rc, 2)

    def test_delimiter_is_csv_only(self):
        rc, _, err = call("run", self.path("in.json"), "-c", self.cfg, "--dry-run",
                          "--delimiter", ";")
        self.assertEqual(rc, 2)
        self.assertIn("csv only", err)

    def test_stdin_json_and_default_csv(self):
        data = json.dumps(RECORDS).encode()
        rc, _, err = call_with_stdin(data, "run", "-", "-c", self.cfg, "--dry-run")
        self.assertEqual(rc, 2)                      # stdin is csv unless told otherwise
        self.assertTrue(err.startswith("error:"))
        rc, _, err = call_with_stdin(data, "run", "-", "-c", self.cfg, "--dry-run",
                                     "--in-format", "json")
        self.assertEqual(rc, 0, err)

    def test_broken_json_and_xml_are_exit_2(self):
        for name, blob in (("b.json", b"{"), ("b.xml", b"<t><r></t>")):
            self.write(name, blob)
            rc, _, err = call("run", self.path(name), "-c", self.cfg, "--dry-run")
            self.assertEqual(rc, 2, err)
            self.assertTrue(err.startswith("error:"))


if __name__ == "__main__":
    unittest.main()
