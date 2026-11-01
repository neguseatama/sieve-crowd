# Sieve Crowd — Specification

Version 0.5.0. [日本語版](SPEC.ja.md)

Sieve Crowd turns a table about people (CSV, JSON or XML) into a table in which every record belongs to a **crowd**
of at least *k* records that look alike on the columns an outsider could already know, and **measures the result on
the output table itself**. Offline, zero runtime dependencies, deterministic.

## 1. Model

| Term | Definition |
|---|---|
| Roles | Every column has exactly one role: `id`, `qi`, `sensitive`, `keep`, `drop`. A table with a column that has no role is rejected. |
| Quasi-identifiers (QI) | The `qi` columns: what an outsider could already know. The guarantee is relative to this declared set. |
| Crowd | An equivalence class: records with equal QI values (each value NFC-normalized and trimmed). |
| k-anonymity | Every crowd has ≥ *k* records (k ≥ 2). |
| l-diversity (distinct) | Every crowd holds ≥ *l* distinct values of **each** `sensitive` column (l ≥ 1; l = 1 means no requirement). |
| Risk | Per record 1/(crowd size). Reported: maximum = 1/k_achieved, average = crowds / records. |

## 2. Pipeline

```
(CSV / JSON / XML) bytes ─► read (UTF-8, header) ─► generalization tables ─► lattice search ─►
  suppress, drop columns, pseudonymize ─► shuffle ─► MEASURE ─► receipt
```

The format is detected from the file extension and can be forced with `--in-format` / `--out-format` (section 8).
Every adapter normalizes its input to the same string table, so the rest of the pipeline is format-blind.

1. **Generalization tables.** For every QI and every level, the label of each distinct value (section 3).
2. **Lattice search** (section 4) picks one level per QI.
3. **Suppression.** Whole crowds that fail k or l at the chosen node are removed from the output (record suppression).
4. **Columns.** `drop` and `id`+`drop` columns are removed; `id`+`pseudonymize` columns are replaced (section 5);
   `qi` columns carry their generalized label; `sensitive` and `keep` columns are copied unchanged.
5. **Shuffle** (section 6).
6. **Measure** the output table with code independent of the search (`measure.py`). If the measured k or l is below
   the request, or no record remains, the run is **refused** (`verification_failed`) and nothing is written.

A refusal is a result, not an error: `status = "refused"` with a `reason`, and no table.

## 3. Generalization hierarchies

Levels run from 0 (the value itself) to L (`*`, fully suppressed). **Every level coarsens the previous one**: if two
values share a label at level j they share it at every higher level. The search depends on this and each generalizer
enforces or tests it.

| `type` | Parameters | Levels |
|---|---|---|
| `numeric` | `widths`: positive integers, each a **multiple** of the previous (default `[5,10,20,50,100]`) — **or** `bins`: strictly increasing interior edges whose first and last bins are open-ended (`widths` and `bins` are mutually exclusive) | 0 value · `widths`: j: range of width `widths[j-1]` (`30-34`; decimals `[30,35)`) · `bins`: 1 the custom bins (integers `<0`, `0-19`, `65+`; decimals `<0.5`, `[0.5,20)`, `>=65`) · top `*`. Empty or unparseable values become `*` from level 1; fractional `bins` edges on an integer column are rejected. |
| `date` | – | 0 `YYYY-MM-DD` · 1 `YYYY-MM` · 2 `YYYY` · 3 decade `1990s` · 4 `*`. Invalid dates become `*` from level 1. |
| `prefix` | `length` n ≥ 1 | 0 value · j (1..n): last j characters replaced by `*` · n+1 `*` |
| `category` | `hierarchy`: value → [parent, grandparent, …] | 0 value · 1..depth ancestors (shorter chains repeat their last ancestor) · top `*`. Values missing from the hierarchy become `*` from level 1. An inconsistent hierarchy (a group with two parents) or an ancestor named `*` is rejected. |
| `exact` | – | 0 value · 1 `*` (suppression only) |

## 4. Lattice search

A node is a vector of levels, one per QI. Let `S(node)` be the number of records in crowds that violate k or l.
A node is **acceptable** if `S(node) ≤ budget`, where `budget = min(n − 1, ⌊max_suppression × n⌋)`.

*Monotonicity.* If a node is acceptable, so is every node that generalizes at least one QI further (a merged crowd
violates only if all its parts violate). Hence the least total height `h*` with an acceptable node is found by binary
search over heights; the top node (everything `*`) decides feasibility (otherwise `infeasible`).

*Objective* (lexicographic): least normalized loss `Σ level_i / L_i`, then fewest suppressed records, then the smallest
level vector. Phase 1 finds `h*` and its best node; phase 2 walks the region `height ≥ h*, loss ≤ that node's loss`
depth-first, most general node first (when the lattice has ≤ 200,000 nodes). Three prunes skip what provably cannot
beat the incumbent: subtrees that can no longer reach `h*`, subtrees already heavier than the incumbent, and every
node at or below a rejected node (monotonicity: suppressing less never fixes a crowd). Nothing is materialised; the
result is the optimum. The receipt reports `refinement_truncated` if the evaluation limit stopped phase 2. Evaluation
counts are informational and may differ between versions.

*Limits.* `max_rows` (default 200,000) and `max_evals` node evaluations (default 20,000). Exceeding them refuses with
`resource_limit_rows` / `resource_limit_search`. All tie-breaks are deterministic.

## 5. Direct identifiers

`id` columns are removed (`drop`, default) or replaced (`pseudonymize`) by
`p-` + base32(HMAC-SHA256(key, column ‖ NUL ‖ NFC(value).strip())[:10]), lower case, 16 characters; an empty value stays
empty. The key is at least 16 random bytes in hex (`sieve-crowd keygen`) and is never part of the configuration or the
receipt. Same key ⇒ same pseudonym, so releases made with one key can be linked to each other.

## 6. Row order

The output rows are shuffled with SplitMix64 (Fisher–Yates, `below(n)` by rejection sampling), `shuffle_seed`
default 0. Keeping the input order (`--keep-order`) is a **relaxation** and is listed under `relaxations` in the receipt.

## 7. Configuration

```json
{ "k": 5, "l": 2, "max_suppression": 0.05, "missing_value_policy": "star",
  "columns": { "<column>": { "role": "...", ... } } }
```

Strict: unknown keys, an unknown role, a role of `?` (the template written by `inspect`), `k < 2`, `max_suppression`
outside [0, 1), a `missing_value_policy` other than `star` or `suppress`, no `qi` column, `l > 1` without a `sensitive`
column, `pseudonymize` without a key, and any mismatch between the table's columns and the configuration are rejected
(messages name columns, never cell values). Settings may be overridden on the command line (`--k`, `--l`,
`--max-suppression`, `--missing-value-policy`). Keys beginning with `_` are comments and are ignored.

`missing_value_policy` decides what happens to records whose quasi-identifier value is empty after normalization and
trim. `star` (default) keeps them: the value takes part like any value and generalizes to `*` from level 1, so records
with missing values form crowds of their own at low levels. `suppress` removes them before the search and counts them
against the suppression budget; when they alone exceed the budget the run refuses with `missing_exceeds_budget`. A
placeholder policy is deliberately not offered: filled-in values would make the missing pattern itself a
quasi-identifier.

## 8. Command line

| Command | Purpose |
|---|---|
| `inspect FILE [--config-out F] [--in-format F] [--lang]` | per column: distinct values, empties, share of unique values, apparent shape, and a *hint* (from the column name and the values, e.g. "looks like a direct identifier"); writes a template with role `?` and the hint as a `_hint` comment. Roles are never assigned automatically |
| `keygen -o F` | writes a random key (file mode 600); never replaces an existing file without `--force` |
| `run FILE -c CONFIG (-o OUT \| --dry-run)` | anonymize; options `--key-file --k --l --max-suppression --missing-value-policy --keep-order --shuffle-seed --lang --delimiter --in-format --out-format --max-rows --max-evals --report-json --quiet --force` |
| `plan FILE -c CONFIG` | pre-flight profile of the run, before any search: options `--k --l --max-suppression --missing-value-policy --max-rows --max-evals --key-file --lang --delimiter --in-format --report-json --quiet --hint-pack --no-builtin-hints --no-derived --findings-json` |

The plan is a receipt of its own (`status = "plan"`). It reports only **exact** numbers: the lattice
size and maximum height follow from the configuration alone (each QI contributes `levels + 1` nodes),
the suppression budget is `min(n − 1, ⌊max_suppression × n⌋)`, the per-column observations and the
level-0 crowd statistics (crowds, singletons, records in crowds smaller than k) come from one pass
over the table, and every `sensitive` column's distinct-value count decides l-reachability. It never
estimates: nothing about the search itself is predicted. Warnings (codes with parameters):
`rows_over_limit`, `k_unreachable`, `l_unreachable`, `budget_zero` (no suppression allowed while
records already sit in too-small crowds at level 0), `missing_over_budget` (under `suppress`: more empty-QI records
than the budget), `lattice_large` (above the refinement cap, so
phase 2 is skipped), `evals_tight` (lattice larger than `max_evals`) and `many_singletons` (≥ 50% of
records alone at level 0 — a heuristic). The plan also reports how many records have an empty QI value under the
current policy. Since v0.6.0 the plan also runs the derived keep-vs-qi analysis (§12); `--no-derived`
skips it. The plan performs no search, writes no table, and exits 0.

The output is never the input file and an existing output needs `--force`; files are written atomically. Exit codes:
0 ok · 1 I/O · 2 configuration/usage/invalid input · 3 refused. Input is UTF-8 (a BOM is accepted); the output is
UTF-8 with `\n` line ends.

### Formats

CSV, JSON and XML only; Excel files (`.xlsx`/`.xls`) are deliberately unsupported. A file's format is its extension
(`.csv`, `.json`, `.xml`); `--in-format` / `--out-format` override it (and make stdin/stdout or extension-less names
unambiguous — `-` is CSV unless told otherwise). `--delimiter` applies to CSV only and is rejected for JSON/XML.

* **CSV** — one header row, then records (quoted fields and custom delimiters through Python's `csv`).
* **JSON** — either an array of records `[{"col": value, ...}, ...]` (the first record fixes the column order; every
  record must list exactly the same columns) or an object `{"header": [...], "rows": [[...], ...]}`. Cell values:
  strings pass through, numbers become their decimal text (`30` → `"30"`, `30.0` → `"30.0"`), booleans become
  `true`/`false`, `null` becomes an empty cell. Rejected: nested objects/arrays, duplicate keys, the non-standard
  `NaN`/`Infinity` literals, numbers that overflow to infinity. Output is an array of records (2-space indented);
  an empty cell is written as `""`, never as `null`.
* **XML** — the root element's name (and its attributes) are ignored; each child element of the root is a record;
  each field is an empty-or-text element carrying the column name in a `name` attribute, which is how arbitrary
  column names survive. Rejected: a DOCTYPE declaration (this is what rules out entity-expansion attacks such as
  "billion laughs" — no DTD, no entities), namespaces, nested fields, unexpected attributes, duplicate, missing or
  extra columns, and text where elements belong. Output is `<table><row><f name="col">value</f>...</row></table>`,
  indented with two spaces; an empty cell is a self-closed field. A value XML 1.0 cannot represent (a control
  character) is refused, naming the row and column, never the value.

The same logical table gives the same result in every format (a tested invariant), so a run may read one format and write
another: `run people.csv -c config.json -o people_safe.json`.

## 9. Receipt

Machine part (`--report-json`, English identifiers) and human part (`--lang en|ja`) come from one object: version,
Unicode data version, `status`, `reason` (if refused), input size, `io` (`input_format`, and `output_format` when a
table is written), settings, result (records out, suppressed, rate; and, under the `suppress` missing-value policy,
`missing_suppressed` — the records dropped before the search), privacy (QI list, `before`: records that were
one-of-a-kind on the QI columns in the input, `k_requested`, `k_achieved`, crowds, five smallest crowd sizes, records
alone in a crowd, maximum and average risk, achieved diversity per sensitive column), information loss (height /
maximum height, precision loss), per-column disposition (for QIs: level and a description; for `keep` columns: the
share of unique values), row order, `relaxations`, search statistics and `verification`. **Cell values never appear
in the receipt**, only column names and aggregates.

When suppression removed records, the receipt also carries `diagnostics.suppression`: the budget, the number of
dropped crowds and records, a crowd-size histogram (capped at 20 entries), the split of dropped crowds into
*smaller than k* vs *short of l-diversity* (per sensitive column), and `one_level_further` — per QI that is not yet
at its top level, how many dropped records one coarsening step would rescue. Refused runs carry reason-specific
`diagnostics`: `infeasible` (records vs k; per sensitive column distinct values vs l), `resource_limit_search`
(lattice size, levels per QI, evaluations used vs the limit), `verification_failed` (crowd-size histogram of the
output, per-column l shortfalls, the tested level vector), `missing_exceeds_budget` (records, missing records, budget).
Diagnostics name columns and report sizes and counts
only — the labels of individual crowds (which are derived from cell values) are never reported.

## 10. Invariants checked by the tests

| | |
|---|---|
| — | The measured k of the output is ≥ the requested k, and measured diversity ≥ l (plain counting in the test). |
| — | The search equals a brute-force oracle over the whole lattice (objective of section 4), including the pruned phase-2 walk. |
| — | `suppress` drops exactly the records with an empty QI value, inside the budget; more than that refuses with `missing_exceeds_budget`. |
| — | Acceptability is monotone along every generalization step. |
| — | Every hierarchy coarsens (tested on random values for every generalizer). |
| — | Same table + settings ⇒ same output; SplitMix64 and pseudonym vectors fixed (`tests/vectors`). |
| — | The receipt contains no cell values. |
| — | Diagnostics and plans contain aggregates and column names only: never a crowd's QI labels. |
| — | The plan's lattice size, tops and budget equal the search's own numbers (exact, not estimated). |
| — | NFC and NFD spellings of a value form one crowd. |
| — | The same logical table produces the same output whatever format carried it; JSON and XML round-trip. |

## 11. Implementation notes

* The statement a run supports is: *each record is one of ≥ k look-alikes on the declared QI columns*. Columns with
  role `keep` are outside that model; the receipt shows their share of unique values so that an identifier-like column
  is easy to notice.
* l-diversity is the *distinct* variant. Record suppression removes whole crowds; values are not masked in place.
* Missing and unparseable values are generalized straight to `*`, so they form crowds of their own at low levels.
  The `suppress` policy removes records with an empty QI value before the search instead, within the same budget.
* `numeric` custom `bins` choose their label text from the edges as configured; the column's integer/decimal mode
  (decided from the data, as for `widths`) only picks between `0-19` / `[0,20)` styles.
* The plan mode shares the run's configuration validation and reads the table once; it never runs the lattice search.
* CSV, JSON and XML (UTF-8, header row, one table). Quoted fields and custom delimiters are supported through
  Python's `csv`; the JSON and XML adapters normalize to the same string table, so the engine is format-blind.
* Indicative speed: 100,000 rows × 4 QIs in about 6 s on a laptop-class CPU.
* Positions of randomness: only the shuffle uses a PRNG (SplitMix64, own implementation, portable).

## 12. Hint packs (inspect/plan only)

A hint pack is a JSON object (`schema: 1`, read as `utf-8-sig`; optional `version` string) that suggests roles and checks value shapes for `inspect` and `plan`. Since v0.5.1 the built-in `jp-basic` pack is loaded **by default**; `--no-builtin-hints` excludes it. `run` never imports the hint-pack module, and with `--no-builtin-hints` and no user pack the inspect/plan output is byte-for-byte the v0.4.0 output.

CLI (inspect/plan only): `--hint-pack FILE` (repeatable), `--no-builtin-hints` (exclude the builtin) and `--findings-json FILE` (the findings, written separately from `--report-json`). Load order is the builtin first, then the command-line order; `findings.packs` / `pack_info` follow that order. The candidate order is a contract independent of load order and of the order rules are written in a pack (v0.5.2): evidence strength (name+value → value → name → stat), then role (id → sensitive → qi, roles outside this list last), then rule id ascending (plain string comparison). `_suggest` in the template follows the first sorted candidate. Rewriting the rules of a pack in a different order, or passing packs in a different order, does not change the candidate order or `_suggest` (`packs` / `pack_info` stay a record of load order).

**Uniqueness.** Pack ids and rule ids are unique across the whole set, builtin included; a duplicate is a `ConfigError` (exit code 2) whose message names the file and the clashing id and points to `--no-builtin-hints` for replacing the builtin. Cell values never appear in messages.

A pack lists rules. A rule's `when` matches a column by `column_names` (NFKC + lower-case — the old `hint()` comparison with NFKC added; the old `hint()` itself is unchanged) and/or `value_shape`. The shape language is bounded: `#` digit, `@` ASCII letter, `\X` literal, only `{m}` / `{m,n}` quantifiers; no alternation or nesting, so no catastrophic backtracking. A rule may carry a `check` (`set` / `range` / `luhn` / `my_number` / `email_shape`; each returns three values: match / mismatch / cannot-check, with official test vectors for Luhn and the My Number residue-11 check digit), a `leak` flag, and a `suggest` (role + generalizer settings, written into the template under `_suggest` / `_candidates` for that column only). Evidence strength is one of name+value, value, name, stat — strongest first.

**Leak checks (v0.5.1).** A `leak: true` rule scans a scanned column for identifier-shaped values as tokens: a cell is split on whitespace and punctuation (`-` `+` `@` `.` `_` `%` stay inside a token), so a number inside prose is found; a dashed token is also tried without its dashes (`03-1234-5678` → `0312345678`). Space-separated pieces never combine (`03 1234 5678` is not detected — documented constraint). Tokens are runs of ASCII alphanumerics plus the gluing symbols, so full-width digits and dashes (`０９０－１２３４－５６７８`) never form a token and are not detected as-is (same kind of documented constraint). Cells longer than 4096 characters are not scanned and are counted as `skipped`. On `plan` only the columns whose declared role is `keep`, `sensitive` or `qi` are scanned (id/drop are never scanned); `inspect` has no roles and records every column. The counts go to `columns.<col>.leaks[]` as `{pack, rule, count, checked, skipped}` (`checked` = non-empty cells actually scanned; an element appears when a count or the skip count is positive). On `plan` the column also carries `declared_role`, and a count ≥ 1 adds a warning line on stderr and a `warnings` element `code: "leak"` (with column, declared role, pack, rule, count, checked); `inspect` prints one candidates-format line instead. The numbers are possibilities, not proof; warnings never change the exit code.

**Derived keep-vs-qi relations (v0.6.0, plan only).** Independent of any pack, `plan` crosses every keep column X with every qi column Q (X ≠ Q, table order) and evaluates both directions from one cross-tabulation over the rows where both values are non-empty (values compared with the engine's `_norm`: NFC + strip). `reveals_qi` = the kept column nearly determines the raw qi value (X is published verbatim, so generalizing Q does not hide it); `implied_by_qi` = the qi value nearly determines the kept value. Per direction, with s = compared records, m = distinct source values, v = records the source value does not pin down to one target value (s − Σ per-group max target count), the direction is `unchecked` when s < 50, `trivial` when either column is constant or s − m = 0 (a unique source — plain uniqueness, not a relation), `flagged` when s ≥ 50 and s − m > 0 and 100·v ≤ s and 10·v ≤ s − m, and `clear` otherwise. The thresholds (50, 1%, 10%) and `PAIR_LIMIT = 400` are code constants; pairs beyond the limit are skipped (`skipped_pairs`). Flagged directions emit a stderr line `  - derived: …` (after the hint-pack findings, no heading of its own, `--quiet` suppresses it) and a `warnings` element `{code: "derived", column, declared_role, qi_column, relation, support, violations}`; the findings top level gains `derived_summary = {pairs, skipped_pairs, unchecked, trivial, flagged, clear}` with the invariant `unchecked + trivial + flagged + clear = 2 × (pairs − skipped_pairs)`. The analysis runs with or without packs (in the no-pack state the findings JSON is `packs: []` / `pack_info: []` + the derived result); `--no-derived` removes every derived trace. Column names and counts only — never a cell value.

Findings carry aggregates and column names only — **never a cell value**. `findings.packs` remains a plain list of pack ids (readers unchanged); the top-level `pack_info` lists `{id, version, source, sha256}` per pack in load order (`sha256` of the exact loaded bytes; the builtin's is the hash of the built-in string constant; a pack without `version` reports `null`). `inspect` and `plan` print one leading line naming the loaded packs (`--quiet` on plan suppresses it; with no pack loaded nothing is printed). Four warnings are emitted when scanning: `role_mismatch` (a column suggested `qi` with name+value/value evidence but declared `keep` / `sensitive`), `mixed_form` (a column with values mixing full/half-width forms — NFC does not fold them, so they form separate crowds), `japanese_era` (values in a 和暦 form), and, on `plan` only, `leak` (see above). The built-in `jp-basic` pack (version 1.1.0) covers postal codes (`prefix` length 4), birth dates (`#{4}-#{2}-#{2}` → suggest `qi`, `type: date`; v0.6.0), phone / My Number / email / card leak checks, the 47 prefectures as a `category` hierarchy (one regional standard fixed in the pack: 三重 = 近畿, 新潟 = 中部), and ages.

**The `packs/` directory (v0.6.0; prefecture edition distributed since v0.6.1).** Packs that ship separately from the wheel live in `packs/`; neither `packs/` nor `tools/` is packaged (the wheel contains only the `sieve_crowd` package). The `jp-municipality-2026` pack is generated with `tools/make_municipality_pack.py`, which auto-detects the input contract from the header: the デジタル庁 アドレス・ベース・レジストリ prefecture master (`lg_code` / `pref`; extra columns ignored; every code must be prefecture-level — digits 1-5 end in `000` — or exit 2) or the 総務省 local-government code list (`団体コード` / `都道府県名` / `市区町村名`); a header containing both code columns is rejected as ambiguous. The tool is standard-library only, deterministic (byte-identical output for the same input; sorted value lists, fixed key order, 2-space indent), exact duplicate rows collapse, and contract violations (missing/misnamed columns, a code that is not 6 digits, a non-prefecture code in prefecture mode, a conflicting duplicate) exit with code 2 naming columns and row numbers — never a cell value. Three rules (`jp-municipality-code` 6 digits → suggest prefix 5, `jp-municipality-code5` 5 digits → suggest prefix 2, and `jp-prefecture-name` (prefecture mode) / `jp-municipality-name` (municipality mode) → suggest category) co-load with the builtin (no id clash) and pass `parse_config`. The prefecture edition ships with the repository: `packs/mt_pref_all.csv` (the committed 47-row extract; line endings normalized CRLF → LF at commit time) and the generated `packs/jp-municipality-2026.json`; regenerating from the committed extract reproduces the committed bytes (T29). The source is licensed under PDL 1.0 and the required attribution (source citation + edited-data statement, no logo) is recorded in packs/README.md. The town-level master (156 MB) is not redistributed; a municipality-mode pack stays local until the terms of use for the 総務省 list are confirmed.

## Appendix — design decisions taken autonomously

| # | Decision | Reason |
|---|---|---|
| — | k-anonymity + distinct l-diversity, measured on the output | a guarantee that can be counted, unlike text anonymization |
| — | Every column needs a role; templates carry `?` and are rejected | no guessing of what is sensitive |
| — | Refusal is a first-class result | never emit a table that only looks safe |
| — | Global recoding + whole-crowd suppression | simple, monotone, provably correct |
| — | Nested hierarchies only (validated) | binary search needs monotonicity |
| — | Shuffle by default; keeping order is a recorded relaxation | the input order often encodes identity |
| — | Pseudonyms are opt-in, keyed, and described as linkable | pseudonymization is not anonymization |
| — | NFC + trim before comparing | identical-looking values must share a crowd |
| — | Limits: 200,000 rows, 20,000 evaluations | bounded time |
| — | Receipt has aggregates and column names only | the receipt can be shared |
| — | `inspect` gives hints, never roles; the receipt shows the situation before and after | explain the value in terms the reader cares about, without guessing for them |
| — | Custom `bins` for numeric columns (interior edges, open ends) | legal and practical classifications are non-uniform; the multiple-of rule stays for `widths` |
| — | Diagnostics are aggregate-only (sizes, counts, levels — never crowd labels) | tuning must not cost confidentiality; the receipt stays shareable |
| — | `missing_value_policy` is `star` (default) or `suppress`; no placeholder | a filled-in value would make the missing pattern itself a quasi-identifier; suppression stays inside a counted budget |
| — | Phase 2 walks the region depth-first with monotone pruning and materialises nothing | the optimum is pinned by the brute-force oracle; no region-sized lists in memory; evaluation counts are informational |
| — | `plan` reports only exact numbers and performs no search | an estimate would erode the measured-guarantee stance; the exact lattice size is already decidable from the configuration |
| — | Formats by extension with explicit `--in-format` / `--out-format`; no Excel support | predictable files, unambiguous exceptions, and no third-party readers |
| — | JSON as records or `{"header", "rows"}`; cells normalize to strings at the door | the engine stays format-blind; strict rejection keeps tables unambiguous |
| — | XML fields carry a `name` attribute; DOCTYPE and namespaces are rejected outright | column names are arbitrary strings (element names are not), and a privacy tool must not parse entity-expanding input |
| — | A missing value is an empty cell in every format (`null` → `""`, empty element → `""`) | round-trips stay stable; output never invents `null` |
| — | format independence is a tested invariant | the guarantee must not depend on how the table was carried |
