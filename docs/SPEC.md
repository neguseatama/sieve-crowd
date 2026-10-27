# Sieve Crowd — Specification

Version 0.2.0. [日本語版](SPEC.ja.md)

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
| `numeric` | `widths`: positive integers, each a **multiple** of the previous (default `[5,10,20,50,100]`) | 0 value · j: range of width `widths[j-1]` (`30-34`; decimals `[30,35)`) · top `*`. Empty or unparseable values become `*` from level 1. |
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
level vector. Phase 1 finds `h*` and its best node; phase 2 inspects every node with height ≥ `h*` whose loss does not
exceed that node's loss (when the lattice has ≤ 200,000 nodes), so the result is the optimum. The receipt reports
`refinement_truncated` if the evaluation limit stopped phase 2.

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
{ "k": 5, "l": 2, "max_suppression": 0.05,
  "columns": { "<column>": { "role": "...", ... } } }
```

Strict: unknown keys, an unknown role, a role of `?` (the template written by `inspect`), `k < 2`, `max_suppression`
outside [0, 1), no `qi` column, `l > 1` without a `sensitive` column, `pseudonymize` without a key, and any mismatch
between the table's columns and the configuration are rejected (messages name columns, never cell values).
Settings may be overridden on the command line (`--k`, `--l`, `--max-suppression`). Keys beginning with `_` are comments and are ignored.

## 8. Command line

| Command | Purpose |
|---|---|
| `inspect FILE [--config-out F] [--in-format F] [--lang]` | per column: distinct values, empties, share of unique values, apparent shape, and a *hint* (from the column name and the values, e.g. "looks like a direct identifier"); writes a template with role `?` and the hint as a `_hint` comment. Roles are never assigned automatically |
| `keygen -o F` | writes a random key (file mode 600); never replaces an existing file without `--force` |
| `run FILE -c CONFIG (-o OUT \| --dry-run)` | anonymize; options `--key-file --k --l --max-suppression --keep-order --shuffle-seed --lang --delimiter --in-format --out-format --max-rows --max-evals --report-json --quiet --force` |

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
table is written), settings, result (records out, suppressed, rate), privacy (QI list, `before`: records that were
one-of-a-kind on the QI columns in the input, `k_requested`, `k_achieved`, crowds, five smallest crowd sizes, records
alone in a crowd, maximum and average risk, achieved diversity per sensitive column), information loss (height /
maximum height, precision loss), per-column disposition (for QIs: level and a description; for `keep` columns: the
share of unique values), row order, `relaxations`, search statistics and `verification`. **Cell values never appear
in the receipt**, only column names and aggregates.

## 10. Invariants checked by the tests

| | |
|---|---|
| — | The measured k of the output is ≥ the requested k, and measured diversity ≥ l (plain counting in the test). |
| — | The search equals a brute-force oracle over the whole lattice (objective of section 4). |
| — | Acceptability is monotone along every generalization step. |
| — | Every hierarchy coarsens (tested on random values for every generalizer). |
| — | Same table + settings ⇒ same output; SplitMix64 and pseudonym vectors fixed (`tests/vectors`). |
| — | The receipt contains no cell values. |
| — | NFC and NFD spellings of a value form one crowd. |
| — | The same logical table produces the same output whatever format carried it; JSON and XML round-trip. |

## 11. Implementation notes

* The statement a run supports is: *each record is one of ≥ k look-alikes on the declared QI columns*. Columns with
  role `keep` are outside that model; the receipt shows their share of unique values so that an identifier-like column
  is easy to notice.
* l-diversity is the *distinct* variant. Record suppression removes whole crowds; values are not masked in place.
* Missing and unparseable values are generalized straight to `*`, so they form crowds of their own at low levels.
* CSV, JSON and XML (UTF-8, header row, one table). Quoted fields and custom delimiters are supported through
  Python's `csv`; the JSON and XML adapters normalize to the same string table, so the engine is format-blind.
* Indicative speed: 100,000 rows × 4 QIs in about 6 s on a laptop-class CPU.
* Positions of randomness: only the shuffle uses a PRNG (SplitMix64, own implementation, portable).

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
| — | Formats by extension with explicit `--in-format` / `--out-format`; no Excel support | predictable files, unambiguous exceptions, and no third-party readers |
| — | JSON as records or `{"header", "rows"}`; cells normalize to strings at the door | the engine stays format-blind; strict rejection keeps tables unambiguous |
| — | XML fields carry a `name` attribute; DOCTYPE and namespaces are rejected outright | column names are arbitrary strings (element names are not), and a privacy tool must not parse entity-expanding input |
| — | A missing value is an empty cell in every format (`null` → `""`, empty element → `""`) | round-trips stay stable; output never invents `null` |
| — | format independence is a tested invariant | the guarantee must not depend on how the table was carried |
