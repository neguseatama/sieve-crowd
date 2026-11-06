# Changelog

## [0.9.0] - 2026-11-06

CP932 CSVs and Excel `.xlsx` workbooks read natively, through a new input
layer (`sieve_crowd/tabular.py` + `sieve_crowd/xlsx_reader.py`, standard
library only).

- **Character codes (series-wide policy):** default `auto` adopts the first
  candidate of UTF-8 BOM (`utf-8-sig`) → strict UTF-8 → strict CP932;
  anything else refuses (`unsupported_encoding`, exit 1, nothing written).
  UTF-16/UTF-32 BOMs refuse outright; `errors="replace"/"ignore"` are never
  used.  Adopting CP932 prints one stderr line (`input encoding: cp932
  (auto)` / `(specified)`) that never reaches results, receipts or the scan
  HTML.  `--encoding` (csv only) pins the codec, strictly, no fall-through;
  unknown names exit 2.  UTF-8 outputs are byte-identical to v0.8.2.
- **Safe `.xlsx` reader (Lens's style, stdlib only):** closed refusal codes
  (`InputRefused`, exit 1, code only), Lens-aligned limits (file 64 MiB,
  10,000 entries, 32 MiB per part, 128 MiB total, 1,000,000 elements) counted
  while reading, DOCTYPE/ENTITY refused, encryption/duplicate/namespace
  (by URI — Strict OOXML refuses) checks, sheets streamed row by row.
  Shared/inline/rich strings without furigana (`<rPh>`), raw number text,
  `TRUE`/`FALSE`, error literals, cached formula values (missing caches
  counted on stderr), ISO dates (1900/1904; the phantom serial 60 refuses),
  first-visible-sheet default with `--sheet NAME|INDEX` (hidden included),
  multi-sheet/hidden notices on stderr only, hidden rows/columns read as
  data, merged cells keep the top-left value, empty margins trimmed, header
  parity with CSV (short rows pad, long rows keep the csvio mismatch error),
  zip layout never changes a result.  All subcommands accept `.xlsx`
  (`--in-format xlsx` for stdin); `.xlsx` output stays refused.
- **CLI:** `--encoding` and `--sheet` join `inspect`/`run`/`plan`/`audit`/
  `scan`; `cli.py` is unfrozen for this version only (arguments and the
  read-call swap), its new sha256 pinned in `tests/test_pins_v090.py`;
  `model.py` gains `REFUSAL_CODES`/`InputRefused` (exit 1, code only) and
  `csvio.py` splits the syntax layer (`read_table_text`).
- **Frozen files unchanged** (config/engine/audit/derived/chartable/
  hidden_chars/hintpack + chartable_v1.json); all pack pins unchanged;
  scan/plan/audit pins re-measured at 0.9.0 (the outputs carry the version).
