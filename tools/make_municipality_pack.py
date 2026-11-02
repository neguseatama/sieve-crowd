#!/usr/bin/env python3
"""Generate the ``jp-municipality-2026`` hint pack from Japanese
local-government code CSVs.

One or two input files are accepted (auto-detected per file from the header
row):

* **prefecture mode** — the デジタル庁 アドレス・ベース・レジストリ
  prefecture master: columns ``lg_code`` and ``pref`` (extra columns such
  as ``pref_kana`` / ``pref_roma`` / ``efct_date`` / ``ablt_date`` /
  ``remarks`` are ignored).  Every ``lg_code`` must be a prefecture-level
  code (its first five digits end in ``000``).

* **municipality mode** — the 総務省 local-government code list
  (全国地方公共団体コード): columns ``団体コード``, ``都道府県名``,
  ``市区町村名``.  The 総務省 publishes its site content under the
  公共データ利用規約 (第1.0版) — PDL 1.0 (per its site policy; see
  packs/README.md) — so the committed edition merges both sources.

**Merged generation** — two inputs, exactly one prefecture source and one
municipality source (either order): the two code rules union both sources and
the name rules are per-source (``jp-prefecture-name`` over prefecture names,
``jp-municipality-name`` over municipality names), so the merged pack carries
four rules.  The output does not depend on the input order.  A code appearing
in both sources must carry identical details, or the generation fails.

If the header contains both ``lg_code`` and ``団体コード`` the input is
rejected as ambiguous; with neither, the municipality contract's missing-
column message is used.

The code is the 6-digit local-government code (a 5-digit code plus one
check digit, as published by 総務省; the check digit is NOT verified here).
Column order does not matter and extra columns are ignored.  A single input
generates three rules (the third one is ``jp-prefecture-name`` or
``jp-municipality-name`` depending on the mode):

    jp-municipality-code   6-digit codes       -> qi, prefix 5 (drop the check digit)
    jp-municipality-code5  5-digit codes       -> qi, prefix 2 (prefecture)
    name rule              prefecture or municipality names  -> qi, category
        (no hierarchy: several names exist in more than one prefecture, e.g.
        府中市, so a name -> prefecture ladder would be wrong for them)

Deterministic: the same input yields byte-identical output (sorted value
lists, fixed key order, 2-space indent, \\n line endings, ensure_ascii=False),
and the merged output does not depend on the input order.  Rows that repeat
exactly are collapsed; the same code with different details is rejected.
Error messages name columns, row numbers and counts — never a cell value.

Exit codes: 0 ok; 1 the input cannot be read; 2 the input does not match the
contract (missing or misnamed columns, an ambiguous header, a code that is
not 6 digits, a non-prefecture code in prefecture mode, a conflicting
duplicate — within or across sources, an empty name, more than two inputs,
two inputs of the same contract).

The generated pack is never part of the wheel or the sdist.  Which edition is
committed under packs/, and the attribution required by each source, is
recorded in packs/README.md.

Usage:
    python3 tools/make_municipality_pack.py INPUT.csv [INPUT2.csv] [-o OUTPUT.json] [--pack-version VERSION]

Without ``-o`` the pack JSON goes to stdout.  ``--pack-version`` sets the
version written into the pack (default: 1.0.0).  The committed merged edition
is regenerated with:

    python3 tools/make_municipality_pack.py packs/mt_pref_all.csv packs/soumu_city_r611.csv -o packs/jp-municipality-2026.json --pack-version 1.1.0
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from typing import NoReturn

PACK_ID = "jp-municipality-2026"
PACK_VERSION = "1.0.0"
MUNI_MODE, PREF_MODE = "municipality", "prefecture"
CODE_COL, PREF_COL, NAME_COL = "団体コード", "都道府県名", "市区町村名"
LG_COL, PREF_NAME_COL = "lg_code", "pref"
MUNI_REQUIRED = (CODE_COL, PREF_COL, NAME_COL)
PREF_REQUIRED = (LG_COL, PREF_NAME_COL)

CODE_NAMES = ["municipality_code", "city_code", "local_government_code",
              "団体コード", "市区町村コード", "自治体コード"]
PREF_CODE_NAMES = CODE_NAMES + ["lg_code", "都道府県コード"]
CODE5_NAMES = ["municipality_code5", "city_code5", "市区町村コード5桁"]
NAME_NAMES = ["municipality", "city", "municipality_name", "市区町村名", "自治体名"]
PREF_NAME_NAMES = ["pref", "prefecture", "prefecture_name", "pref_name",
                   "都道府県名", "都道府県"]

EXIT_OK, EXIT_IO, EXIT_CONTRACT = 0, 1, 2


def _fail(message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(EXIT_CONTRACT)


def _read_rows(path: str):
    """Returns (mode, rows); rows are (code, prefecture, name) triples — in
    prefecture mode the prefecture fills both name slots."""
    try:
        with open(path, newline="", encoding="utf-8-sig") as fh:
            rows = [r for r in csv.reader(fh) if r and any(c.strip() for c in r)]
    except OSError as exc:
        print(f"error: cannot read the input ({exc.strerror})", file=sys.stderr)
        raise SystemExit(EXIT_IO) from None
    if not rows:
        _fail("the input has no header row")
    header = [c.strip() for c in rows[0]]
    muni, pref = CODE_COL in header, LG_COL in header
    if muni and pref:
        _fail("ambiguous input: both 団体コード and lg_code are in the header "
              "(pick one contract; found: " + ", ".join(header) + ")")
    if not muni and not pref:
        # no code column at all: keep the municipality contract's message
        missing = [c for c in MUNI_REQUIRED if c not in header]
        _fail(f"missing column(s): {', '.join(missing)} "
              f"(needed: {', '.join(MUNI_REQUIRED)}; found: {', '.join(header)})")
    mode = MUNI_MODE if muni else PREF_MODE
    required = MUNI_REQUIRED if muni else PREF_REQUIRED
    missing = [c for c in required if c not in header]
    if missing:
        _fail(f"missing column(s): {', '.join(missing)} "
              f"(needed: {', '.join(required)}; found: {', '.join(header)})")
    idx = {c: header.index(c) for c in required}
    data = []
    for r in rows[1:]:
        cell = lambda c: r[idx[c]].strip() if idx[c] < len(r) else ""
        if mode == MUNI_MODE:
            data.append((cell(CODE_COL), cell(PREF_COL), cell(NAME_COL)))
        else:
            name = cell(PREF_NAME_COL)
            data.append((cell(LG_COL), name, name))
    return mode, data


def build(mode, rows, version=PACK_VERSION) -> dict:
    """rows: (code, prefecture, name) triples.  Returns the pack dict."""
    code_col = CODE_COL if mode == MUNI_MODE else LG_COL
    empty_col = f"{PREF_COL}/{NAME_COL}" if mode == MUNI_MODE else PREF_NAME_COL
    seen: dict[str, tuple[str, str]] = {}
    for n, (code, pref, name) in enumerate(rows, start=2):
        if not (len(code) == 6 and code.isascii() and code.isdigit()):
            _fail(f"{code_col}: expected 6 digits (row {n})")
        if mode == PREF_MODE and not code[:5].endswith("000"):
            _fail(f"{code_col}: expected a prefecture-level code "
                  f"(digits 1-5 end in 000) (row {n})")
        if code in seen and seen[code] != (pref, name):
            _fail(f"{code_col}: the same code appears twice with different "
                  f"details (row {n})")
        if not pref or not name:
            _fail(f"empty {empty_col} (row {n})")
        seen[code] = (pref, name)
    if not seen:
        _fail("the input has no data rows")
    codes = sorted(seen)
    code5 = sorted({c[:5] for c in codes})
    if mode == MUNI_MODE:
        comment = (
            "Generated by tools/make_municipality_pack.py from the 総務省 "
            "local-government code list (全国地方公共団体コード).  Basis date "
            "and terms of use: see packs/README.md.  Regenerate rather than "
            "hand-edit.")
        code_names, name_id, name_names = CODE_NAMES, "jp-municipality-name", NAME_NAMES
    else:
        comment = (
            "Generated by tools/make_municipality_pack.py from the デジタル庁 "
            "アドレス・ベース・レジストリ prefecture master (PDL 1.0; the "
            "committed source extract is packs/mt_pref_all.csv).  Source and "
            "attribution: packs/README.md.  Regenerate rather than hand-edit.")
        code_names, name_id, name_names = PREF_CODE_NAMES, "jp-prefecture-name", PREF_NAME_NAMES
    return {
        "schema": 1,
        "id": PACK_ID,
        "version": version,
        "_comment": comment,
        "rules": [
            {
                "id": "jp-municipality-code",
                "when": {"column_names": code_names, "value_shape": "#{6}"},
                "check": {"kind": "set", "values": codes},
                "suggest": {"role": "qi", "type": "prefix", "length": 5},
            },
            {
                "id": "jp-municipality-code5",
                "when": {"column_names": CODE5_NAMES, "value_shape": "#{5}"},
                "check": {"kind": "set", "values": code5},
                "suggest": {"role": "qi", "type": "prefix", "length": 2},
            },
            {
                "id": name_id,
                "when": {"column_names": name_names},
                "check": {"kind": "set", "values": sorted({name for _, name in seen.values()})},
                "suggest": {"role": "qi", "type": "category"},
            },
        ],
    }


def build_merged(sources, version=PACK_VERSION) -> dict:
    """sources: [(mode, rows)] — exactly one prefecture and one municipality
    source (the caller enforces this).  Returns the merged pack dict: the two
    code rules union both sources, the name rules are per-source."""
    seen: dict[str, tuple[str, str]] = {}
    pref_names: set[str] = set()
    muni_names: set[str] = set()
    for k, (mode, rows) in enumerate(sources):
        code_col = CODE_COL if mode == MUNI_MODE else LG_COL
        empty_col = f"{PREF_COL}/{NAME_COL}" if mode == MUNI_MODE else PREF_NAME_COL
        bucket = pref_names if mode == PREF_MODE else muni_names
        for n, (code, pref, name) in enumerate(rows, start=2):
            if not (len(code) == 6 and code.isascii() and code.isdigit()):
                _fail(f"{code_col}: expected 6 digits (input {k + 1}, row {n})")
            if mode == PREF_MODE and not code[:5].endswith("000"):
                _fail(f"{code_col}: expected a prefecture-level code "
                      f"(digits 1-5 end in 000) (input {k + 1}, row {n})")
            if not pref or not name:
                _fail(f"empty {empty_col} (input {k + 1}, row {n})")
            if code in seen and seen[code] != (pref, name):
                _fail(f"{code_col}: the same code appears twice with different "
                      f"details (input {k + 1}, row {n})")
            seen[code] = (pref, name)
            bucket.add(name)
    if not seen:
        _fail("the inputs have no data rows")
    codes = sorted(seen)
    code5 = sorted({c[:5] for c in codes})
    comment = (
        "Generated by tools/make_municipality_pack.py from two sources: the "
        "デジタル庁 アドレス・ベース・レジストリ prefecture master (PDL 1.0; "
        "the committed source extract is packs/mt_pref_all.csv) and the 総務省 "
        "local-government code list, 全国地方公共団体コード R6.1.1 = 2024-01-01 "
        "(the committed source extract is packs/soumu_city_r611.csv).  "
        "jp-prefecture-name comes from the prefecture master, "
        "jp-municipality-name from the 総務省 list, and the two code rules "
        "merge both sources.  Source and attribution: packs/README.md.  "
        "Regenerate rather than hand-edit.")
    return {
        "schema": 1,
        "id": PACK_ID,
        "version": version,
        "_comment": comment,
        "rules": [
            {
                "id": "jp-municipality-code",
                "when": {"column_names": PREF_CODE_NAMES, "value_shape": "#{6}"},
                "check": {"kind": "set", "values": codes},
                "suggest": {"role": "qi", "type": "prefix", "length": 5},
            },
            {
                "id": "jp-municipality-code5",
                "when": {"column_names": CODE5_NAMES, "value_shape": "#{5}"},
                "check": {"kind": "set", "values": code5},
                "suggest": {"role": "qi", "type": "prefix", "length": 2},
            },
            {
                "id": "jp-prefecture-name",
                "when": {"column_names": PREF_NAME_NAMES},
                "check": {"kind": "set", "values": sorted(pref_names)},
                "suggest": {"role": "qi", "type": "category"},
            },
            {
                "id": "jp-municipality-name",
                "when": {"column_names": NAME_NAMES},
                "check": {"kind": "set", "values": sorted(muni_names)},
                "suggest": {"role": "qi", "type": "category"},
            },
        ],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Generate the jp-municipality-2026 hint pack from a "
                    "local-government code CSV (アドレス・ベース・レジストリ "
                    "prefecture master lg_code/pref, or the 総務省 list "
                    "団体コード/都道府県名/市区町村名); two inputs (one "
                    "prefecture + one municipality source, either order) are "
                    "merged into the four-rule pack.")
    ap.add_argument("input", nargs="+",
                    help="one or two code lists as CSV (lg_code/pref, or "
                         "団体コード/都道府県名/市区町村名; two inputs must be "
                         "one of each contract)")
    ap.add_argument("-o", "--output", help="write the pack JSON here (default: stdout)")
    ap.add_argument("--pack-version", default=PACK_VERSION,
                    help="the version written into the pack (default: "
                         "%(default)s; the committed merged edition is 1.1.0)")
    a = ap.parse_args(argv)
    if len(a.input) > 2:
        _fail(f"expected one or two inputs (found {len(a.input)})")
    sources = [_read_rows(path) for path in a.input]
    if len(sources) == 1:
        mode, rows = sources[0]
        pack = build(mode, rows, a.pack_version)
    else:
        modes = sorted(m for m, _ in sources)
        if modes != [MUNI_MODE, PREF_MODE]:
            _fail("the two inputs use the same contract (both are "
                  f"{modes[0]} mode); the merged generation expects exactly "
                  "one prefecture source (lg_code/pref) and one municipality "
                  "source (団体コード/都道府県名/市区町村名)")
        pack = build_merged(sources, a.pack_version)
    data = (json.dumps(pack, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if a.output:
        try:
            with open(a.output, "wb") as fh:
                fh.write(data)
        except OSError as exc:
            print(f"error: cannot write ({exc.strerror})", file=sys.stderr)
            return EXIT_IO
    else:
        sys.stdout.buffer.write(data)
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
