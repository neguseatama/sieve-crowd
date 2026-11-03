# Sieve Crowd — Specification

Version 0.7.0. [日本語版](SPEC.ja.md)

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
| `plan FILE -c CONFIG` | pre-flight profile of the run, before any search: options `--k --l --max-suppression --missing-value-policy --max-rows --max-evals --key-file --lang --delimiter --in-format --report-json --quiet --hint-pack --no-builtin-hints --no-derived --no-hidden-chars --findings-json` |
| `audit FILE -c CONFIG` | observe the table as it is — nothing generalized, judged or written (§13): options `--subject --lang --delimiter --in-format --max-rows --max-evals --findings-json --quiet` |
| `scan INPUT [-c CONFIG] [-o OUT\|-]` | one static HTML page — how the table looks right now (§15): options `--hint-pack --no-builtin-hints --no-hidden-chars --subject --k --max-rows --no-derived --lang` |

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
skips it. Since v0.7.1 it also runs the invisible-character observation (§14); `--no-hidden-chars`
skips it. The plan performs no search, writes no table, and exits 0.

The output is never the input file and an existing output needs `--force`; files are written atomically. Exit codes:
0 ok · 1 I/O · 2 configuration/usage/invalid input · 3 refused. Input is UTF-8 (a BOM is accepted); the output is
UTF-8 with `\n` line ends.

### Formats

CSV, JSON and XML only; since the tool depends on no external library, Excel files (`.xlsx`/`.xls`) remain out of scope for now. A file's format is its extension
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
| — | `audit` reports integers only; row/column permutations and repeated runs are byte-identical, and its class numbers equal `plan`'s level-0 `before` block (same names, same numbers). |
| — | The audit findings carry no cell value (subject values included); `run`/`plan`/`inspect` never import the audit module; `config.py` / `engine.py` are byte-identical (sha256-pinned). |
| — | The fold is a fixed mapping from a sha256-pinned table: printable ASCII is invariant, fold is idempotent, pure-ASCII matching is byte-identical, and `chartable.py` never imports the Unicode database. |
| — | The hidden-character observation reports counts and kind names only (no cell value, no code point); `run` never imports hintpack/derived/audit/chartable/hidden_chars; `config.py` / `engine.py` / `audit.py` / `derived.py` stay byte-identical (sha256-pinned). |

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
* The audit mode shares the run's configuration validation and the engine's `_norm`; it is imported at
  function level in the CLI, so `run`/`plan`/`inspect` never load the module (§13).
* CSV, JSON and XML (UTF-8, header row, one table). Quoted fields and custom delimiters are supported through
  Python's `csv`; the JSON and XML adapters normalize to the same string table, so the engine is format-blind.
* Indicative speed: 100,000 rows × 4 QIs in about 6 s on a laptop-class CPU.
* Positions of randomness: only the shuffle uses a PRNG (SplitMix64, own implementation, portable).

## 12. Hint packs (inspect/plan only)

A hint pack is a JSON object (`schema: 1`, read as `utf-8-sig`; optional `version` string) that suggests roles and checks value shapes for `inspect` and `plan`. Since v0.5.1 the built-in `jp-basic` pack is loaded **by default**; `--no-builtin-hints` excludes it. `run` never imports the hint-pack module, and with `--no-builtin-hints` and no user pack the inspect/plan output is byte-for-byte the v0.4.0 output.

CLI (inspect/plan only): `--hint-pack FILE` (repeatable), `--no-builtin-hints` (exclude the builtin) and `--findings-json FILE` (the findings, written separately from `--report-json`). Load order is the builtin first, then the command-line order; `findings.packs` / `pack_info` follow that order. The candidate order is a contract independent of load order and of the order rules are written in a pack (v0.5.2): evidence strength (name+value → value → name → stat), then role (id → sensitive → qi, roles outside this list last), then rule id ascending (plain string comparison). `_suggest` in the template follows the first sorted candidate. Rewriting the rules of a pack in a different order, or passing packs in a different order, does not change the candidate order or `_suggest` (`packs` / `pack_info` stay a record of load order). Since v0.7.3 a suggestion is only written when the rule reaches the column with a name or a value signal — a leak rule whose name does not match still runs its token scan, but it never hangs a suggestion on the column (without that gate, every scanned column would carry a suggestion from a leak rule that has one).

**Uniqueness.** Pack ids and rule ids are unique across the whole set, builtin included; a duplicate is a `ConfigError` (exit code 2) whose message names the file and the clashing id and points to `--no-builtin-hints` for replacing the builtin. Cell values never appear in messages.

A pack lists rules. A rule's `when` matches a column by `column_names` (NFKC + lower-case — the old `hint()` comparison with NFKC added; the old `hint()` itself is unchanged) and/or `value_shape`. The shape language is bounded: `#` digit, `@` ASCII letter, `\X` literal, only `{m}` / `{m,n}` quantifiers; no alternation or nesting, so no catastrophic backtracking. A rule may carry a `check` (`set` / `range` / `luhn` / `my_number` / `email_shape`; each returns three values: match / mismatch / cannot-check, with official test vectors for Luhn and the My Number residue-11 check digit), a `leak` flag, and a `suggest` (role + generalizer settings, written into the template under `_suggest` / `_candidates` for that column only, and only when the rule shows a name or a value signal on the column — v0.7.3). Evidence strength is one of name+value, value, name, stat — strongest first.

**Value matching folds through the shared chartable (v0.7.1).** The value inputs of `value_shape`, the checks and the leak scan are folded through `sieve_crowd/chartable_v1.json` (§14) before matching: `value_shape` and the leak scan fold with `dashes=True` (shape matching — the long-vowel mark and the other folding dashes become `-`, so `090ー1234ー5678` becomes one dashed token and the existing dash-strip fallback applies), the value checks fold with `dashes=False` (since v0.7.5 the luhn evaluation alone re-folds with `dashes=True` afterwards and, when the result is a run of ASCII digits and dashes, matches the dash-stripped digits — the other checks are unchanged, and dashless values take the same path unchanged). The fold is a fixed mapping, so pure-ASCII matching is byte-identical to the pre-0.7.1 behavior, and full-width digits/symbols, long-vowel dashes and invisible characters now reach the matchers — the v0.5.2 "full-width never matches" limitation is resolved. A dashed full-width postal code in a zip column still does not match the `#{7}` shape (the hyphen stays; removing dashes is not part of the shape language — the leak scan's dash-strip is the only dash-removing path, and `jp-zip` is not a leak rule). Since v0.7.3 the dash form has its own rule: `jp-zip-hyphen` (`#{3}-#{4}`; suggest `prefix` length 4 — the same partial levels as `#{7}` with the same remaining digits 6·5·4·3, the dash never masked; a length of 5 would add a redundant level that only hides the dash). Full-width `１２３－４５６７` reaches the hyphen shape through the fold. Column names keep their NFKC normalization (unchanged; the one remaining Unicode-database dependency, by the v0.5.0 decision).

**Leak checks (v0.5.1).** A `leak: true` rule scans a scanned column for identifier-shaped values as tokens: a cell is split on whitespace and punctuation (`-` `+` `@` `.` `_` `%` stay inside a token), so a number inside prose is found; a dashed token is also tried without its dashes (`03-1234-5678` → `0312345678`). Space-separated pieces never combine (`03 1234 5678` is not detected — documented constraint). Since v0.7.1 the cell is folded (dashes=True) before tokenizing, so full-width digits and dashes (`０９０－１２３４－５６７８`) and long-vowel dashes (`090ー1234ー5678`) form tokens and are detected — the earlier "full-width never forms a token" constraint is resolved by the fold (§14). Cells longer than 4096 characters are not scanned and are counted as `skipped`. On `plan` only the columns whose declared role is `keep`, `sensitive` or `qi` are scanned (id/drop are never scanned); `inspect` has no roles and records every column. The counts go to `columns.<col>.leaks[]` as `{pack, rule, count, checked, skipped}` (`checked` = non-empty cells actually scanned; an element appears when a count or the skip count is positive). On `plan` the column also carries `declared_role`, and a count ≥ 1 adds a warning line on stderr and a `warnings` element `code: "leak"` (with column, declared role, pack, rule, count, checked); `inspect` prints one candidates-format line instead. The numbers are possibilities, not proof; warnings never change the exit code.

**Derived keep-vs-qi relations (v0.6.0, plan only).** Independent of any pack, `plan` crosses every keep column X with every qi column Q (X ≠ Q, table order) and evaluates both directions from one cross-tabulation over the rows where both values are non-empty (values compared with the engine's `_norm`: NFC + strip). `reveals_qi` = the kept column nearly determines the raw qi value (X is published verbatim, so generalizing Q does not hide it); `implied_by_qi` = the qi value nearly determines the kept value. Per direction, with s = compared records, m = distinct source values, v = records the source value does not pin down to one target value (s − Σ per-group max target count), the direction is `unchecked` when s < 50, `trivial` when either column is constant or s − m = 0 (a unique source — plain uniqueness, not a relation), `flagged` when s ≥ 50 and s − m > 0 and 100·v ≤ s and 10·v ≤ s − m, and `clear` otherwise. The thresholds (50, 1%, 10%) and `PAIR_LIMIT = 400` are code constants; pairs beyond the limit are skipped (`skipped_pairs`). Flagged directions emit a stderr line `  - derived: …` (after the hint-pack findings, no heading of its own, `--quiet` suppresses it) and a `warnings` element `{code: "derived", column, declared_role, qi_column, relation, support, violations}`; the findings top level gains `derived_summary = {pairs, skipped_pairs, unchecked, trivial, flagged, clear}` with the invariant `unchecked + trivial + flagged + clear = 2 × (pairs − skipped_pairs)`. The analysis runs with or without packs (in the no-pack state the findings JSON is `packs: []` / `pack_info: []` + the derived result); `--no-derived` removes every derived trace. Column names and counts only — never a cell value.

Findings carry aggregates and column names only — **never a cell value**. `findings.packs` remains a plain list of pack ids (readers unchanged); the top-level `pack_info` lists `{id, version, source, sha256}` per pack in load order (`sha256` of the exact loaded bytes; the builtin's is the hash of the built-in string constant; a pack without `version` reports `null`). `inspect` and `plan` print one leading line naming the loaded packs (`--quiet` on plan suppresses it; with no pack loaded nothing is printed). Four warnings are emitted when scanning: `role_mismatch` (a column suggested `qi` with name+value/value evidence but declared `keep` / `sensitive`, or suggested `id` with name+value evidence but declared `keep` / `qi` / `sensitive` — the `id` warning fires when the column name matches and the value has the shape; a column whose name does not match is the leak scan's job, and id/drop declarations are never a mismatch; the element keys stay `{code, column, declared, suggested, evidence}`), `mixed_form` (a column with values mixing full/half-width forms — NFC does not fold them, so they form separate crowds), `japanese_era` (values in a 和暦 form), and, on `plan` only, `leak` (see above). The built-in `jp-basic` pack (version 1.6.0 since v0.7.5) covers postal codes (`jp-zip`, `#{7}`, and since v0.7.3 `jp-zip-hyphen`, `#{3}-#{4}` — both suggest `prefix` length 4; since v0.7.4 the column names are 13: `郵便番号`, `〒番号`, `郵便番号1`, `郵便番号2`, `zip_code`, `postal_code` and `post_code` join `zip`/`zipcode`/`postal`/`postcode`/`郵便`/`〒`), birth dates (`#{4}-#{2}-#{2}` → suggest `qi`, `type: date`; v0.6.0), kana name columns (`jp-name-kana`, name-only, suggests `role: id` — the direct-identifier treatment; v0.7.1), person-name columns (`jp-person-name`, name-only, suggests `role: id` — a person-name-looking column; kept in the output, it identifies the person; v0.7.2), address columns (`jp-address`, name-only, suggests `role: id` — an address-looking column; combined with the other columns it reaches a person; v0.7.2), and since v0.7.3 four value rules also suggest `role: id` — email columns (`jp-email`: `email`/`mail`/`e-mail`/`メール` plus `mail_address`/`メールアドレス` (v0.7.3) and `email_address`/`Eメール` (v0.7.5), the `email_shape` check), phone columns (`jp-phone`: `phone`/`tel`/`telephone`/`mobile`/`電話`/`携帯` plus `電話番号`/`携帯電話` (v0.7.3) and `携帯番号`/`電話番号1`/`電話番号2`/`phone_number`/`tel_number` (v0.7.5), shape `#{10,11}`) with their dash form `jp-phone-hyphen` (`#{2,4}-#{2,4}-#{3,4}`; v0.7.4 — same names, suggestion and leak flag), My Number columns (`jp-mynumber`: `my_number`/`mynumber`/`マイナンバー`/`個人番号`, shape `#{12}` and the official check digit) and card-number columns (`jp-card`: `card`/`card_number`/`credit_card`/`カード番号`/`クレジットカード` plus `card_no`/`クレジットカード番号` (v0.7.5), shape `#{13,19}` and Luhn) with their dash form `jp-card-hyphen` (`#{4}-#{4}-#{4}-#{4}`; v0.7.4 — since v0.7.5 hyphenated values are luhn-checked too, the dashes stripped after the fold) — each of them still a leak rule; the 47 prefectures as a `category` hierarchy (one regional standard fixed in the pack: 三重 = 近畿, 新潟 = 中部), and ages.

**The `packs/` directory (v0.6.0; municipality edition distributed since v0.6.2).** Packs that ship separately from the wheel live in `packs/`; neither `packs/` nor `tools/` is packaged (the wheel contains only the `sieve_crowd` package). The `jp-municipality-2026` pack is generated with `tools/make_municipality_pack.py`, which auto-detects the input contract from the header: the デジタル庁 アドレス・ベース・レジストリ prefecture master (`lg_code` / `pref`; extra columns ignored; every code must be prefecture-level — digits 1-5 end in `000` — or exit 2) or the 総務省 local-government code list (`団体コード` / `都道府県名` / `市区町村名`); a header containing both code columns is rejected as ambiguous. One input generates three rules; two inputs — exactly one prefecture and one municipality source, in either order — are merged into four rules (the two code rules union both sources, the name rules are per-source), the merged output is independent of the input order, and two inputs of the same contract or more than two inputs exit with code 2. `--pack-version` sets the version written into the pack (default 1.0.0). The tool is standard-library only, deterministic (byte-identical output for the same input; sorted value lists, fixed key order, 2-space indent), exact duplicate rows collapse (across sources too; a conflicting duplicate exits 2), and contract violations (missing/misnamed columns, a code that is not 6 digits, a non-prefecture code in prefecture mode, a conflicting duplicate, an empty name) exit with code 2 naming columns and row numbers — never a cell value. The rules (`jp-municipality-code` 6 digits → suggest prefix 5, `jp-municipality-code5` 5 digits → suggest prefix 2, `jp-prefecture-name` and `jp-municipality-name` → suggest category) co-load with the builtin (no id clash) and pass `parse_config`. The municipality edition ships with the repository (pack 1.1.0): `packs/mt_pref_all.csv` (the committed 47-row ABR extract; line endings normalized CRLF → LF at commit time), `packs/soumu_city_r611.csv` (the committed 1,747-row 総務省 extract, basis date R6.1.1 = 2024-01-01, converted from the obtained xlsx with the sheet's 47 prefecture rows removed) and the generated `packs/jp-municipality-2026.json`; regenerating from the two committed extracts with `--pack-version 1.1.0` reproduces the committed bytes (T29). Both sources follow PDL 1.0 — the 総務省 applies the 公共データ利用規約（第1.0版） to its site content — and the required attribution (source citation + edited-data statement, no logo) is recorded in packs/README.md. The town-level master (156 MB) and the 総務省 政令指定都市 sheet are not redistributed.

## 13. audit (v0.7.0, observe only)

`audit FILE -c CONFIG [--subject COLUMN] [--findings-json FILE] [--lang]` observes the table as it is: nothing is generalized, nothing is suppressed, nothing is refused and nothing is judged. Where `plan` estimates a run and `run` transforms the table, `audit` only counts — and every number it reports is an integer: ratios are per-mille values floored with integer division (`1000 * count // n`, `0` for `n = 0`), so the same table produces byte-identical output on every platform and no float is ever computed. The configuration's `qi` columns, `k`, `l` and the column roles (for the subject check) are used — and nothing else: **no generalization level is applied**, the values are observed as they sit in the table. Options `--delimiter --in-format --max-rows --max-evals --findings-json --quiet --lang` behave as on `plan`; the human report goes to stderr (like the plan report), stdout stays empty, and the only file written is the optional `--findings-json`. Exit codes: 0 (observation complete, warnings included) · 1 (I/O) · 2 (configuration/usage/invalid input). There is no refused state.

**Alignment.** Values are compared with the engine's `_norm` (NFC + strip), and the classes are built exactly like `measure`/`diagnose` at level 0: every row takes part, an empty QI value acts as the empty value, and `missing_value_policy` is **not** applied (suppressing rows would be a transformation, not an observation). These are therefore the same numbers `plan` reports as its level-0 `before` block — `count` = `crowds`, `min_size` = `smallest_crowd`, `unique_rows` = `records_alone`, `rows_below_k` = `records_below_k` — same names, same numbers (pinned by T31).

**A — equivalence classes** (`classes`): `count`, `min_size`, `unique_rows` (rows in classes of size 1), `rows_below_k` (rows in classes smaller than k), `unique_permille` / `below_k_permille` (floored per-mille of n), and `size_buckets` — rows per fixed bucket `"1" "2" "3" "4" "5-9" "10-49" "50+"` (keys always present, 0 when empty; the buckets count rows, not classes).

**B — per QI column** (`qi_columns`, canonical order: sorted by column name): `distinct` (distinct values, empty cells excluded — `inspect`'s `distinct` counts the empty value, audit's does not: an empty cell contributes no value), `unique_rows` (rows whose normalized value is non-empty and appears exactly once in that column), and `rows_below_k_without` — `rows_below_k` recomputed on the tuple with that column dropped (O(n) per column). With a single QI column the drop leaves one class of size n, so the value is `n` when `n < k`, else `0`.

**C — repeated subjects** (`subject`, only with `--subject COLUMN`): k-anonymity speaks about rows, but a person can sit in several of them. The subject column must be a configured column whose role is neither `qi` nor `sensitive` (`id`, `keep`, `drop` are allowed — the id column is the typical subject); otherwise audit exits 2 with a message naming the column, never a cell value. The observation reports `rows_with_subject` / `rows_missing_subject`, `subjects`, `repeated_subjects` (subjects on ≥ 2 rows), `rows_in_repeated_subjects`, `max_rows_per_subject`, `rows_per_subject_buckets` (subjects per fixed bucket `"1" "2" "3-4" "5-9" "10+"`), and `class_subjects`: per class the number of **distinct subjects** — `min_distinct`, `rows_below_k` (rows in classes holding fewer than k distinct subjects — the person-level below-k) and `rows_overstated` (rows in classes of size ≥ k with fewer than k distinct subjects — safe-looking on rows, short on people). **An empty subject value is a person of its own**: two empty cells cannot be told apart, so every empty-subject row is one person with one row, in every subject item alike (it can therefore never repeat). Without `--subject` the C items are absent and `subject` is `null`.

**Determinism.** Row order and column order change nothing: the QI columns are reported in sorted order, every aggregate is order-free, and repeated runs over the same input are byte-identical (T36).

**Warnings.** Two observation warnings, phrased as counts and never as verdicts, emitted in the established `  - code: …` stderr form in both languages and as `warnings` elements `{code, rows}`: `small_classes` (when `rows_below_k > 0`) and `subject_overstated` (when `rows_overstated > 0`). Warnings never change the exit code (0). When `n` exceeds `--max-rows`, a `rows_over_limit` note is printed on stderr like plan's (audit performs no search, so the observation simply reads every row); it is not an audit warning and does not enter the findings.

**Findings** (`--findings-json`): a file of its own, `{"audit": {...}}` with `schema: 1` and fixed key sets — top level `schema, rows, k, qi, classes, qi_columns, subject, warnings`; aggregates and column names only, **never a cell value, subject values included** (T37). It is written atomically and unconditionally, like plan's findings.

**Scope notes.** No entropy: a logarithm would put a float into the output, and floats can differ in their last digits across environments — integers cannot; entropy stays out until its reproducibility is measured (a later release may add it). `l` is parsed but no audit item uses it (an l/t observation is out of scope). The audit module is imported only by the audit handler — `run`, `plan` and `inspect` never import it (T38 extends the subprocess check; the frozen `config.py` / `engine.py` are untouched and their sha256 is pinned by T38). Measured cost (section 4.6 of the request): 100,000 rows × 4 QI columns in about 0.4 s without a subject and about 0.6 s with one (laptop-class CPU; the per-column drop pass adds roughly O(#QI × n)).

## 14. The shared chartable and the invisible-character observation (v0.7.1)

**The chartable.** `sieve_crowd/chartable_v1.json` is a byte-exact replica of the Sieve Lens canonical character table (the Lens owns the standard; Crowd treats its copy as a replica pinned by sha256 `c5ae4757…e605`, re-verified on every load). Changes to the standard are made upstream on the Lens side, not by local edits. `sieve_crowd/chartable.py` builds two fixed translation maps from it — base (invisible removal, twins, the fullwidth ASCII range, folding spaces) and base+dashes — and exposes `fold(text, dashes=False)`, applied in this order: (1) invisible characters (all four kinds) are removed; (2) twins and the fullwidth ASCII range (U+FF01–U+FF5E → U+0021–U+007E) are replaced; (3) the folding spaces (U+00A0, U+3000) become the ASCII space; (4) only with `dashes=True` the folding dashes (U+2010–U+2015, U+2212, U+30FC, U+FF70) become the ASCII hyphen-minus. The steps share no code point (validated), every target is printable ASCII, so the fold is idempotent and every printable ASCII character is invariant — pure-ASCII input folds to itself. There are **no Unicode-database lookups anywhere in the fold**: identical input folds to identical output on every Python build (the table version, not the runtime Unicode data, decides the result). The table loads lazily, once; a missing, tampered or malformed table is a hard `ChartableError` — never a silent fallback. The wheel ships the JSON through `package-data` (verified by a real build). `run` never reaches the module (function-level imports all the way down; the subprocess check of T46 covers chartable and hidden_chars).

**The invisible-character observation (`plan` only).** Independent of any pack, `plan` scans every cell of every column — the rows plan already reads, so plan's `max_rows` guard stays the only cap — for characters from the chartable's `invisible` categories (zero-width U+200B/200C/200D/2060/FEFF, bidi controls, tag characters, variation selectors). Per column it records `rows` (rows containing at least one), `chars` (total occurrences) and `kinds` (sorted names of the kinds seen). One warning per column whose declared role is `keep`, `qi` or `sensitive` with `rows > 0`, in column-name sort order; `id` and `drop` columns are counted in the summary only (their values never reach the output verbatim, or are dropped). This is an observation, not a change: no cell is rewritten, and the outputs carry counts and kind names only — **no cell value and no code point ever appears** (T45 uses invisible-char sentinels). A file-leading BOM is decoded away by the readers (`utf-8-sig`) and never counted; a U+FEFF inside a cell is counted.

The warning line follows the established `  - code: …` form in both languages, e.g. keep: `  - hidden_chars: "memo" (declared keep): 12 row(s) contain invisible characters (zero_width); they stay in the output` / 「memo」（宣言 keep）: 12 行に不可視文字（zero_width）が含まれています。出力にそのまま残ります。 For `qi` the tail says what the observation means: `values that look identical form separate groups` / 見た目が同じ値が別のグループに分かれます（`keep`/`sensitive` は「出力にそのまま残ります」）. The findings JSON gains `warnings` elements `{code: "hidden_chars", column, declared_role, rows, chars, kinds}` and a top-level `hidden_chars_summary = {columns_checked, columns_flagged}` — key additions only (the additive-keys contract), present whenever the findings are written and the scan ran. `--no-hidden-chars` skips the whole observation (no lines, no elements, no summary). Pure-ASCII cells take an `isascii()` fast path; the cost on 100,000 rows × 10 columns is measured in the release report.

## 15. scan (v0.8.0, one static HTML page)

`scan INPUT [-c CONFIG] [--hint-pack FILE]... [--no-builtin-hints] [--no-hidden-chars] [--subject COLUMN] [--k N] [--max-rows N] [--no-derived] [--lang en|ja] [-o PATH|-]` assembles what the read-only commands already measure into **one static HTML page** — a reading document: "this table, as it looks right now". It creates **no new measurement**: without `-c` the roles are provisional (the first hint-pack candidate per column in the v0.5.2 order — evidence strength, then role, then rule id; columns without a candidate are `unassigned (provisionally keep)`, a suggested `id` displays as provisional with its output exclusion stated); with `-c` the declared roles are used as they are (scan = plan + audit in one reading). The internal configuration for the provisional path generalizes every qi `exact` and is written nowhere; the draft in the "next steps" section uses the suggestion's own generalizer and marks undecided columns `?`.

**The page, top to bottom.** Heading (base name — or "(standard input)" / 「（標準入力）」—, rows × columns, the input SHA-256, the version, the loaded packs with their versions, k) · a summary in plain sentences (3–5 lines) · the column list (role, the top candidate's evidence, the candidate rule ids, and the five finding kinds as counts only — `hidden_chars`, `japanese_era`, `leak`, `mixed_form`, `role_mismatch`; a kind that is not listed is 0) · the group sizes (`audit`'s `size_buckets`, integer-floored bars with the numbers) · the per-QI-column observations (`audit`'s `qi_columns`) · the derived keep-vs-qi pairs (`--no-derived` omits the section) · the repeated subjects (`--subject` runs `audit`'s C observation; without it a note names columns that could serve) · next steps (the configuration draft and `plan`/`run` command examples in `<pre>`; file names in the examples are the input's base name and `config.json` — or the config's base name with `-c`; for stdin the examples say `input.csv`) · about this report. Every section opens with 1–2 lines on how to read it. With no provisional qi candidate at all, the group/observation/derived sections are left out, a guidance paragraph takes their place, and the exit code stays 0; `--subject` is then unused (there are no classes to relate it to).

**Wording and numbers.** An observation, not a verdict: no "safe", "unsafe", "danger", "pass" or "fail" anywhere; positive-first. Shares are floored per-mille (`1000 * count // n`, `0` for `n = 0`) rendered with one decimal (integer math only — no float is ever computed). Bars use integer-floored percents. Findings are listed in a fixed order: code ascending, then column name in codepoint order, then the source order — approved as an amendment to the request's §11.

**HTML hygiene.** One file, UTF-8 without BOM, `\n` ends, `<html lang>` follows `--lang`. No `<script>`, no `on*=` attributes, no `src=`/`href=`/`url(`/`@import`/`<link>` anywhere; a CSP meta of `default-src 'none'; style-src 'unsafe-inline'`; inline CSS only, light/dark via `prefers-color-scheme`, print and phone-width friendly, neutral colors (color never carries information — bars always carry their numbers). User-derived strings (column names, base names, pack ids and versions, rule ids, the draft JSON) are HTML-escaped — `= ( ) @` included, so a hostile name cannot assemble any banned token — and their invisible/control characters display as `<U+XXXX>` (the chartable's invisible categories plus C0 with tab and newline excepted, C1 and DEL). Column names display at most 120 code points (display only — the draft keeps the full names so it stays copy-pasteable). No timestamps, no randomness, no environment values (paths, host names, locales); file names appear as base names only; the same input yields byte-identical bytes. Cell values never appear — the sentinel rule of every other report applies to the page as a whole.

**I/O and exit codes.** The output defaults to `INPUT` with the last extension replaced by `.scan.html` (`people.tar.csv` → `people.tar.scan.html`), written atomically and unconditionally — there is no `--force`. `-o PATH` names any path; `-o -` writes the page to stdout. The command refuses (exit 2, nothing written) when the output resolves to the input file or the `-c` file, and when the input is stdin without `-o`. Options otherwise follow their plan/audit meanings: `--k` sets k for the provisional roles (default 5; with `-c` it overrides the configured k like on plan), `--max-rows` (default 200,000) keeps audit's meaning — the observation reads every row and the page notes when the table is larger — `--no-hidden-chars` skips the invisible-character observation (its counts attach to keep/qi/sensitive columns only; a provisional `id` column is never counted), `--hint-pack`/`--no-builtin-hints` follow §12. There is no `--delimiter`/`--in-format` (stdin is CSV; formats follow the extension otherwise). Exit codes: 0 ok (a finding-free table included) · 1 I/O · 2 usage/config/input. The stderr completion is one line (output path and a count summary, either language); the browser is never opened; the page is read-only for the reader too. The `scan` module (`sieve_crowd/scan.py`) is imported only by the scan handler — `run`, `plan`, `inspect` and `audit` never import it (T67 extends the subprocess check; tests T67–T77).

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
| — | The character fold is a fixed table (a sha256-pinned Lens replica), not a Unicode-database call | identical input folds to identical output on every Python build; the standard is owned, not probed |
| — | Invisible characters are observed (plan, counts only), never rewritten | removing them would change the data; warning where they matter (keep/qi/sensitive) is the honest half |
