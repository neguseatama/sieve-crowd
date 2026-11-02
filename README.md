# Sieve Crowd v0.7.3

English | [日本語](README.ja.md)

**Table data anonymization and privacy protection engine**

[![PyPI Version](https://img.shields.io/pypi/v/sieve-crowd.svg)](https://pypi.org/project/sieve-crowd/)
[![Python Version](https://img.shields.io/pypi/pyversions/sieve-crowd.svg)](https://pypi.org/project/sieve-crowd/)
[![CI](https://github.com/neguseatama/sieve-crowd/actions/workflows/test.yml/badge.svg)](https://github.com/neguseatama/sieve-crowd/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

> Sieve Crowd is a table-data processing engine that suppresses the risk of identifying individuals in tabular data, so that the data can be shared safely. Building on the principles of k-anonymity and l-diversity, it deterministically performs attribute rounding (generalization) and partial record removal (suppression).

A fully local, zero-dependency, deterministic (100% reproducible) mathematical transformation engine that anonymizes tabular data and disables re-identification. It extends the design philosophy of [Sieve-Core](https://github.com/neguseatama/sieve-core) into the tabular-data domain.

---

## 💡 Concept and design philosophy

Even when personal data is kept safely on your own machine, you sometimes have to provide or publish tabular data that contains it — or you face the risk of leakage. From a statistical standpoint, the combination of attributes such as age, postal code and sex always carries a risk of identifying individuals.

Consider, for example, a dataset of about 600 people. The risk structure becomes clear:

- **Before**: 574 of the 600 people (96%) were "alone" on the combination of age, postal code and sex — no one else shared their exact values, so an outsider could single them out easily.
- **How the transformation works**: rather than leaving these isolated records as they are, the engine groups similar records together (by rounding and generalization) so that everyone is hidden inside a safe crowd.
- **After**: every person belongs to a group of at least 5 (4 look-alikes besides themselves). Even an outsider who tries to identify someone can be right at most 1 in 5 times (20%).

Sieve Crowd does not rely on probabilistic inference or black-box AI. It transforms tabular data into a state in which no one stands out, deterministically, on the basis of the rigorous mathematical models of k-anonymity and l-diversity.

- **Deterministic approach**: the same input and settings always produce the same output. The result never depends on the execution environment, the clock, or random numbers.
- **A measurement, not a promise**: after the transformation, the finished table is re-counted to check whether it meets the target safety level. If it falls short, the reason is given on a receipt and the table is not written.
- **Explainability**: a receipt records the data processing performed for anonymization, so that what was done can be fully traced.

---

## 🧩 Sieve series

Sieve is a family of engines that share three design principles — deterministic, zero-dependency, fully local. Each engine handles one observation or one removal, and they connect to each other:

| Package | Role | Connection |
| :--- | :--- | :--- |
| [sieve-core-engine](https://github.com/neguseatama/sieve-core) | Ecosystem base logic / plugin host | — |
| [sieve-lens](https://github.com/neguseatama/sieve-lens) | Observes invisible content and hidden prompts in documents | — |
| [sieve-scope](https://github.com/neguseatama/sieve-scope) | Detects structurally similar code pairs | — |
| [sieve-referee](https://github.com/neguseatama/sieve-referee) | Detects paraphrased or reused text pairs | — |
| [sieve-redact](https://github.com/neguseatama/sieve-redact) | Masks sensitive regions with a receipt (text & PNG) | ← lens, → tray |
| [sieve-crowd](https://github.com/neguseatama/sieve-crowd) | Observes and anonymizes re-identification risk in tabular data (k-anonymity) | — |
| [sieve-tray](https://github.com/neguseatama/sieve-tray) | Desktop front-end that routes files to the right engine | ← all engines |

---

## 🔥 Main features

- **k-anonymity and l-diversity**
  Attributes are generalized so that each record has at least k−1 look-alikes, and the diversity of sensitive values is also guaranteed.
- **Zero dependencies, fully local**
  Implemented with the Python standard library only. Data never leaves your computer (no account, offline, no upload).
- **Minimal generalization and suppression**
  Data is not rounded more than necessary; resolution is preserved as much as possible while grouping. Records that still cannot form a group are safely removed (suppressed) rather than distorted.
- **Role suggestions (hint packs)**
  `inspect` / `plan` read the built-in `jp-basic` pack (on by default since v0.5.1, `--no-builtin-hints` to exclude) and suggest a role and check value shapes for each column. Japanese personal columns — person names, kana names, addresses, birth dates, emails, phone numbers, My Numbers, card numbers, postal codes (dash forms — `123-4567` since v0.7.3, phone `090-1234-5678` and card `4242-4242-4242-4242` since v0.7.4) — are matched by name and by value, and the pack proposes direct identifiers (`id`) and quasi-identifiers (`qi`). A suggestion is written only when the rule shows a name or a value signal on the column (since v0.7.3), and a mismatch with the declared role is observed as `role_mismatch`. Hints never touch anonymization.
- **Pre-flight plan**
  `sieve-crowd plan` reports, before any search, the exact search-space size (lattice nodes), the suppression budget, the level-0 risk profile and warnings (unreachable k/l, tight limits, many isolated records) — plus, since v0.6.0, the derived keep-vs-qi relations (does a kept column nearly determine a quasi-identifier, in either direction) — so tuning happens before the run, not after.
- **Audit the table as it is**
  `sieve-crowd audit` observes the current table in integers only — equivalence classes and size buckets, which QI column carries the grouping, and, with `--subject`, the people behind the rows: a class can reach k on rows and still hold fewer than k distinct people, and audit counts those rows instead of judging them.
- **Diagnostics in the receipt**
  When records are suppressed, the receipt explains why — crowd sizes, "smaller than k" vs "short of diversity", and a per-column hint of which quasi-identifier one more generalization step would rescue. In aggregates only; never a cell value.
- **Custom bins for numeric columns**
  Non-uniform classifications such as `0-19, 20-39, 40-64, 65+` (legal age brackets, income bands) can be given directly as bin edges.
- **A policy for missing values**
  `missing_value_policy` decides what happens to records whose quasi-identifier is empty: `star` (default) generalizes the value to `*`; `suppress` removes the record up front, inside the same counted suppression budget (and refuses with `missing_exceeds_budget` when they exceed it). No placeholder option — filling values in would turn the missing pattern itself into an identifier.
- **Receipt for the record**
  A machine-readable receipt records what was done (rules applied, suppression count, measurements). The receipt contains no personal information.
- **Supported formats**
  CSV, JSON and XML (UTF-8). Since the tool does not depend on external libraries, Excel remains out of scope for now.

---

## 🎯 Use cases

- Keeping data on hand for internal use or in-house sharing, stored and managed safely
- Providing survey or customer data to a university, agency, or analytics contractor
- Publishing statistics or open data from hospitals, schools, or local governments
- Feeding realistic test data into a development environment, safely
- Keeping a record of anonymization and processing for legal or audit purposes

---

## 📦 Install

```bash
pip install git+https://github.com/neguseatama/sieve-crowd.git
```

Or from a local clone:

```bash
git clone https://github.com/neguseatama/sieve-crowd.git
cd sieve-crowd
pip install .
```

---

## 💻 Quick start

### 1. Inspect the structure

Reads the file and writes a configuration file that proposes a role for each column (name, quasi-identifier, sensitive value, etc.).

```bash
sieve-crowd inspect people.csv --config-out config.json
```

### 2. Review and edit the configuration

Edit the generated `config.json` to define the role of each column.

### 3. Preview the plan (optional)

Before running, check the size of the search, the suppression budget and the level-0 risk profile — no search is performed, nothing is written:

```bash
sieve-crowd plan people.csv -c config.json
```

### 4. Run anonymization

```bash
sieve-crowd run people.csv -c config.json -o people_safe.csv --report-json receipt.json
```

Input and output example:

```
people.csv                                       people_safe.csv   (rows shuffled)
name,birth_date,age,zip,sex,diagnosis            age,zip,sex,diagnosis
Takahashi Hina,1986-11-02,40,1500052,M,none     20-24,15100**,F,cold
Kobayashi Haruto,2003-01-03,23,1000042,F,flu    20-24,16000**,M,none
Yamamoto Aoi,1971-10-04,55,1510061,M,flu        55-59,15100**,M,asthma
```

---

## 🔍 Audit the table as it is (v0.7.0)

`sieve-crowd audit` observes what the table looks like **right now**. It generalizes nothing, suppresses nothing, refuses nothing — and judges nothing. Where `plan` estimates a run and `run` transforms the table, `audit` only counts, and every number it reports is an integer: ratios are floored per-mille values (integer division, no floats), so the same table yields byte-identical output everywhere.

```bash
sieve-crowd audit people.csv -c config.json                       # the rows
sieve-crowd audit people.csv -c config.json --subject id          # the people behind the rows
sieve-crowd audit people.csv -c config.json --findings-json a.json
```

- **Equivalence classes** — how many groups the QI tuple forms, the smallest one, the rows that are alone, the rows below `k`, the floored per-mille of both, and the rows per fixed size bucket (`1`, `2`, `3`, `4`, `5-9`, `10-49`, `50+`). These are the same numbers `plan` reports as its level-0 `before` block — same names, same numbers.
- **Per QI column** — distinct values (empty cells excluded), rows whose value is unique in that column, and how many rows would still sit below `k` with that column dropped from the tuple: which column carries the grouping, in integers.
- **Repeated subjects** (with `--subject COLUMN`) — k-anonymity speaks about rows, but a person can sit in several of them. `audit` counts the people: rows per subject and their buckets, and, per class, the number of **distinct subjects** — including `rows_overstated`, the rows in classes that look safe on rows (size ≥ k) but hold fewer than k distinct people.

The subject column must be a configured column whose role is not `qi`/`sensitive` (an `id` column is typical); anything else exits with code 2, naming the column. **An empty subject value is treated as a person of its own** — two empty cells cannot be told apart, so every empty-subject row is one person with one row, in every subject observation alike. Without `--subject` the people counts are skipped (`subject: null`). Warnings restate observations without judging — `small_classes` (rows below k) and `subject_overstated` (the overstated rows), in the usual `  - code: …` form, exit code 0. The table is only read; nothing is written except the optional `--findings-json` (schema 1, aggregates and column names only, **never a cell value** — subject values included). `audit` deliberately has no entropy metric: a logarithm would put a float into the output, and floats can differ in their last digits across environments — integers cannot.

---

## 🧪 Hint packs (built-in on by default)

`inspect` and `plan` load **hint packs** — JSON files that suggest a role and a generalizer for a column and check value shapes, without ever touching the anonymization. Since v0.5.1 the built-in `jp-basic` pack is loaded **by default**; `--no-builtin-hints` turns it off. `run` never reads a pack: the run path stays byte-for-byte unchanged from v0.4.0 (pass `--no-builtin-hints` and give no pack, and even the inspect template is the exact v0.4.0 bytes).

```bash
sieve-crowd inspect people.csv --config-out config.json              # builtin jp-basic included
sieve-crowd plan   people.csv -c config.json    --findings-json f.json
sieve-crowd inspect people.csv --hint-pack my.json                   # builtin + my.json
sieve-crowd inspect people.csv --config-out t.json --no-builtin-hints  # v0.4.0 byte-exact route
```

- `--hint-pack FILE` — load a pack in addition to the built-in (may be given more than once). Load order: the builtin first, then the command-line order; `findings.packs` / `pack_info` follow that order. The candidate order is its own contract (v0.5.2), independent of load order and of the order rules are written in a pack: evidence strength (name+value → value → name → stat), then role (id → sensitive → qi, roles outside this list last), then rule id ascending. `_suggest` follows the first sorted candidate.
- `--no-builtin-hints` — exclude `jp-basic` (use only the packs you named; with none named, nothing is loaded and the v0.4.0 byte-exact output survives).
- `--findings-json FILE` — write the findings as JSON: aggregates and column names only, **never a cell value**. `packs` stays a list of pack ids; `pack_info` adds `{id, version, source, sha256}` per pack in load order. On `plan` the file also carries the derived result (`derived_summary`, v0.6.0) and the invisible-character summary (`hidden_chars_summary`, v0.7.1) even when no pack is loaded.

**Ids are unique across all packs, the builtin included.** A user pack reusing `jp-basic` (or a rule id like `jp-phone`) is refused with exit code 2; to replace the builtin, give `--no-builtin-hints` and then reuse its id.

A pack (`schema: 1`, read as `utf-8-sig`; optional `version` string) lists rules. Each rule has a `when` (matching the column by `column_names` and/or `value_shape`), an optional `suggest` (role + generalizer settings, written into the template under `_suggest` for that column only — since v0.7.3 only when the rule shows a name or a value signal on the column), an optional `check` (`set` / `range` / `luhn` / `my_number` / `email_shape`, each three-valued: match / mismatch / cannot-check), and an optional `leak` flag. The `value_shape` language is bounded on purpose: `#` one digit, `@` one ASCII letter, `\X` a literal escape, only `{m}` / `{m,n}` quantifiers — no alternation, no nesting, so it cannot describe a catastrophic-backtracking pattern.

**Value matching folds through the shared chartable (v0.7.1).** The value inputs of `value_shape`, the checks and the leak scan are folded through `sieve_crowd/chartable_v1.json` — a byte-exact replica of the Sieve Lens canonical table, pinned by sha256 and re-verified on every load — before matching. The fold is a fixed mapping, applied in this order: invisible characters are removed; twins (Cyrillic/Greek look-alikes) and the fullwidth ASCII range (`１２３` → `123`, `＠` → `@`) are replaced; the folding spaces (U+00A0, U+3000) become the ASCII space; and only for shape matching (`value_shape` and the leak scan) the folding dashes — the long-vowel mark `ー` included — become the ASCII hyphen. There are no Unicode-database lookups anywhere in the fold, so identical input folds to identical output on every Python build; every printable ASCII character is invariant, so pure-ASCII matching is byte-identical to the pre-0.7.1 behavior. Column-name matching keeps its NFKC normalization (unchanged, still Unicode-database dependent by the v0.5.0 decision — see known limitations).

**Leak checks (v0.5.1).** A `leak: true` rule scans each scanned column for identifier-shaped values as *tokens*: a cell is split on whitespace and punctuation (dashes, `+`, `@`, `.`, `_`, `%` stay inside a token), so a number inside prose is found (`03-1234-5678` is also tried without its dashes). Space-separated pieces never combine — `03 1234 5678` is **not** detected (documented constraint). Since v0.7.1 the cell is folded before tokenizing (above), so full-width digits and dashes (`０９０－１２３４－５６７８`) and long-vowel dashes (`090ー1234ー5678`) form tokens and are detected — the earlier "full-width never forms a token" constraint is resolved by the fold. Cells longer than 4096 characters are skipped and counted as `skipped`. On `plan` only the columns whose declared role is `keep`, `sensitive` or `qi` are scanned (id/drop are never scanned); `inspect` has no roles and records every column. Counts are reported as `leaks[]` (`count`, `checked`, `skipped` — plus `declared_role` on the column, plan only) and, on `plan`, a warning line on stderr and a `code: "leak"` element in `findings.warnings` when a count is 1 or more; `inspect` prints one candidates-format line instead. The numbers are possibilities, not proof, and warnings never change the exit code.

**Derived keep-vs-qi relations (v0.6.0, `plan` only).** For every (keep column X, qi column Q) pair, evaluated in both directions, `plan` reports when one column is a near-perfect proxy for the other: `reveals_qi` (X is kept verbatim in the output, so generalizing Q does not hide it — the attacker reads Q off X) and `implied_by_qi` (the qi value nearly determines the kept value). Every evaluated direction lands in exactly one of four classes: `unchecked` (fewer than 50 compared records), `trivial` (a constant column on either side, or every source value unique — the relation carries no information), `flagged` (the support s is at least 50 and the violations v — records the source value does not pin down to one target value — are at most 1% of s and at most 10% of the excess s−m, where m is the number of distinct source values), and `clear` (checked, but too many violations). Flagged directions appear as `  - derived: …` lines on stderr (after the hint-pack findings, without a heading of their own) and as `code: "derived"` elements in `findings.warnings` (`column`, `declared_role`, `qi_column`, `relation`, `support`, `violations`); the top-level `derived_summary` counts all four classes and satisfies `unchecked + trivial + flagged + clear = 2 × (pairs − skipped_pairs)`. Values are compared with the engine's own normalization (NFC + strip) and empty cells are excluded. At most 400 pairs are evaluated per plan (`skipped_pairs` counts the rest). `--no-derived` skips the whole report; thresholds are code constants, not settings. Column names and counts only — never a cell value.

**Invisible-character observation (v0.7.1, `plan` only).** `plan` also scans every cell of every column for invisible characters from the shared chartable — zero-width (U+200B/200C/200D/2060/FEFF), bidi controls, tag characters and variation selectors. Per column it counts `rows` (rows containing at least one), `chars` (total) and `kinds` (sorted names). One warning per `keep` / `qi` / `sensitive` column with `rows > 0`, in column-name sort order — e.g. `  - hidden_chars: "memo" (declared keep): 12 row(s) contain invisible characters (zero_width); they stay in the output` (kept columns) or `…; values that look identical form separate groups` (qi columns, in both languages). `id`/`drop` columns are counted in the summary only: their values never reach the output verbatim. This is an observation, not a change — no cell is rewritten, `run` never scans anything, and no cell value or code point ever appears in any output (kind names and counts only). The findings JSON gains `warnings` elements `{code: "hidden_chars", column, declared_role, rows, chars, kinds}` and a top-level `hidden_chars_summary` (`columns_checked`, `columns_flagged`); `--no-hidden-chars` skips the whole observation (on by default).

The built-in `jp-basic` pack (version 1.5.0 since v0.7.4) covers Japanese postal codes (`jp-zip`, `#{7}`, and since v0.7.3 `jp-zip-hyphen`, `#{3}-#{4}` — both suggest `prefix` length 4, so the four partial levels keep the same remaining digits 6·5·4·3 and the dash is never masked; full-width `１２３－４５６７` reaches the hyphen shape through the fold; since v0.7.4 the column names are 13 — `郵便番号`, `〒番号`, `郵便番号1`, `郵便番号2`, `zip_code`, `postal_code`, `post_code` join, and full-width `郵便番号２` matches as `郵便番号2` through the normalization), birth dates (`#{4}-#{2}-#{2}` → suggest `qi` with `type: date`; added in v0.6.0), kana name columns (`jp-name-kana`, name-only — `furigana`/`kana`/`name_kana`/`last_name_kana`/`first_name_kana` and the Japanese forms フリガナ・ふりがな・カナ・氏名カナ・氏名フリガナ・姓カナ・名カナ・姓フリガナ・名フリガナ suggest `role: id`, the direct-identifier treatment; added in v0.7.1), person-name columns (`jp-person-name`, name-only — `name`/`full_name`/`fullname`/`first_name`/`last_name`/`family_name`/`given_name`/`customer_name` and the Japanese forms 氏名・名前・お名前・姓名・姓・名・苗字・顧客名 suggest `role: id` — a person-name-looking column; kept in the output it identifies the person; added in v0.7.2), address columns (`jp-address`, name-only — `address`/`addr`/`address1`/`address2`/`street`/`street_address` and the Japanese forms 住所・住所1・住所2・現住所・所在地・番地 suggest `role: id` — an address-looking column; combined with the other columns it reaches a person; added in v0.7.2), and since v0.7.3 four value rules suggest `role: id` too: email columns (`jp-email` — `email`/`mail`/`e-mail`/`メール` plus `mail_address`/`メールアドレス`; the `email_shape` check), phone columns (`jp-phone` — `phone`/`tel`/`telephone`/`mobile`/`電話`/`携帯` plus `電話番号`/`携帯電話`; shape `#{10,11}`; since v0.7.4 the dash form is `jp-phone-hyphen`, `#{2,4}-#{2,4}-#{3,4}`, with the same names, suggestion and leak flag), My Number columns (`jp-mynumber` — `my_number`/`mynumber`/`マイナンバー`/`個人番号`; shape `#{12}` and the official residue-11 check digit) and card-number columns (`jp-card` — `card`/`card_number`/`credit_card`/`カード番号`/`クレジットカード`; shape `#{13,19}` and Luhn; since v0.7.4 the dash form is `jp-card-hyphen`, `#{4}-#{4}-#{4}-#{4}` — the value check never folds dashes away, so a hyphenated value counts as `cannot_check`), each of them still a leak check; the 47 prefectures as a `category` hierarchy mapped to the eight-block 地方ブロック grouping (三重 = 近畿, 新潟 = 中部 — one standard fixed inside the pack), plausible ages, and three observation warnings: `role_mismatch` (a column suggested `qi` with name+value/value evidence but declared `keep`/`sensitive`, or suggested `id` with name+value evidence but declared `keep`/`qi`/`sensitive` — the `id` warning fires when the column name matches and the value has the shape; a column whose name does not match is the leak scan's job, and id/drop declarations are never a mismatch), `mixed_form` (full/half-width forms mixed in a column — NFC keeps them as separate crowds), and `japanese_era` (values in a 和暦 form). Edit a pack to change a standard; hints never affect a run.

**The `packs/` directory (v0.6.0; municipality edition since v0.6.2).** Hint packs that ship separately from the wheel live here — nothing in `packs/` or `tools/` is packaged. The municipality edition of `jp-municipality-2026` (pack 1.1.0) ships with the repository: the ABR prefecture extract `packs/mt_pref_all.csv` (47 rows), the 総務省 municipality extract `packs/soumu_city_r611.csv` (1,747 rows, basis date R6.1.1 = 2024-01-01) and the generated pack `packs/jp-municipality-2026.json` (load with `--hint-pack packs/jp-municipality-2026.json`), which carries 1,794 codes, 1,794 five-digit prefixes, 47 prefecture names and 1,714 distinct municipality names in four rules. Both sources follow the 公共データ利用規約（第1.0版） — PDL 1.0 (the 総務省 applies the same terms to its site content) — and the required source citations and edited-data statements are in `packs/README.md`. The generator `tools/make_municipality_pack.py` (standard library only) auto-detects the input contract from the header — the prefecture master (`lg_code` / `pref`) or the 総務省 list (`団体コード` / `都道府県名` / `市区町村名`) — and merges one of each (either order) into the four-rule pack; two inputs of the same contract, or more than two, exit with code 2. It is deterministic (byte-identical output for the same input, independent of the input order), and contract violations exit with code 2 naming the columns. Regenerating from the two committed extracts with `--pack-version 1.1.0` reproduces the committed bytes (T29). The town-level master (156 MB) and the 総務省 政令指定都市 sheet are not redistributed.

---

## ⚙️ Settings and options

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `k` | 5 | Each record must have at least k−1 look-alikes. Larger is safer but increases generalization. |
| `l` | optional | Every crowd must hold at least l distinct sensitive values, preventing "everyone has the same diagnosis". |
| `max_suppression` | 0.05 (5%) | The maximum fraction of records that may be removed (suppressed) instead of lowering the resolution of the whole table. |
| `missing_value_policy` | `star` | `star`: an empty quasi-identifier generalizes to `*` like any value. `suppress`: such records are removed before the search, counted against `max_suppression`. |
| Role (`role`) | — | `id` (drop or pseudonymize) · `qi` (generalize) · `sensitive` (keep) · `keep` (keep) · `drop` (remove) |
| Generalizer (`type`) | — | For `qi` columns: `numeric` (`widths`, or custom non-uniform `bins`), `date`, `prefix`, `category` (hierarchy), `exact` |

Main command-line options:

- `--dry-run`: do not write data; only measure anonymization and assess risk
- `sieve-crowd plan people.csv -c config.json`: pre-flight estimate of the search space, budget and warnings, including the derived keep-vs-qi relations (`--no-derived` skips them) and the invisible-character observation (`--no-hidden-chars` skips it; no search, no output)
- `sieve-crowd audit people.csv -c config.json [--subject COLUMN]`: observe the current table — classes, per-QI columns, repeated subjects (integers only; no search, no output)
- `--lang ja`: issue a Japanese receipt (default is English; JSON output is also available)
- `--in-format` / `--out-format`: explicitly set the input/output format (csv, json, xml)
- `sieve-crowd keygen -o key.txt`: generate a cryptographic key for pseudonymization

Exit codes:

- `0`: success
- `1`: I/O error
- `2`: configuration error
- `3`: refused (the target anonymization level could not be reached; no output written)

---

## 🔬 Tests

```bash
python -m unittest discover -s tests -v
```

All test suites run with no external dependencies (standard library only).

The suite also carries a sha256-pinned replica of the Sieve Schema
Contract v1 conformance corpus (44 accept/reject cases, maintained in
the sieve-lens repository, which hosts the contract text
`docs/SCHEMA_CONTRACT_v1.md` and the canonical engine
`sieve_lens_ext/schema.py`). The replica exercises Crowd's JSON core
(`sieve_crowd.jsonio`): duplicate keys and `NaN`/`Infinity` are
refused. The UTF-8 BOM case is a declared divergence — Crowd decodes
with `utf-8-sig` on purpose (spreadsheet exports carry a BOM), so the
runner pins the acceptance instead of the refusal, as declared in the
contract's conformance matrix (§6).

---

## ⚠️ Known limitations and caveats

1. **Model assumption** — Sieve Crowd protects against an attacker who knows the attributes you declared as `qi` (quasi-identifiers). It is not a universal shield against re-identification through auxiliary information you did not anticipate.
2. **Not a substitute for legal or privacy review** — It does not guarantee legal or regulatory compliance under privacy laws or guidelines; it is a tool that supports such review technically.
3. **Excel is not supported** — Since the tool depends on no external library, the binary `.xlsx` format remains out of scope for now (use CSV / JSON / XML).
4. **Row shuffling** — To minimize re-identification risk, the output row order is deterministically shuffled.
5. **Column-name matching still depends on the Unicode database** — Since v0.7.1 the *value* matching folds through a fixed, sha256-pinned table, so it no longer depends on the runtime Unicode data. Column **names** are still matched with NFKC (the v0.5.0 decision), which remains the one place where the Python Unicode database version can influence the result (a future release may fix the column-name normalization too).
6. **Hyphenated card numbers stay outside the luhn check** — the value check folds without touching dashes, so a hyphenated value counts as `cannot_check` even in a `jp-card-hyphen` column (only the dashless form gets `match`/`mismatch`; the leak scan does match hyphenated tokens). Teaching the check to strip dashes is recorded as a candidate for the next version that touches `hintpack.py`.

---

## 📜 Version history

One line per release. The feature sections above always describe the current version; the precise contracts are specified in [SPEC](docs/SPEC.md) ([日本語版](docs/SPEC.ja.md)).

| Version | Highlights |
| :--- | :--- |
| 0.7.4 | jp-basic 1.5.0: `jp-phone-hyphen` (`#{2,4}-#{2,4}-#{3,4}`) and `jp-card-hyphen` (`#{4}-#{4}-#{4}-#{4}`) join — each shares its sibling's (`jp-phone`/`jp-card`) column names, `role: id` suggestion and leak flag. The card's luhn check carries over, but the value check never folds dashes away, so hyphenated values count as `cannot_check` (known limitation 6). The `jp-zip`/`jp-zip-hyphen` column names widen from 6 to 13 (`郵便番号`, `〒番号`, `郵便番号1`, `郵便番号2`, `zip_code`, `postal_code`, `post_code` added). `hintpack.py` joins the frozen cores (T62 pins its bytes). A hyphen-form phone/card column declared keep/qi/sensitive now prints two leak lines plus one role_mismatch. `run`/`config.py`/`engine.py`/`audit.py`/`derived.py`/`chartable.py`/`hidden_chars.py` byte-identical. |
| 0.7.3 | jp-basic 1.4.0: `jp-email`/`jp-phone`/`jp-mynumber`/`jp-card` now suggest `role: id` (their `when`/`check`/`leak` unchanged; the requested column names added — `mail_address`/`メールアドレス`, `電話番号`/`携帯電話`, `my_number`/`mynumber`/`マイナンバー`/`個人番号`, `card`/`card_number`/`credit_card`/`カード番号`/`クレジットカード`), and `jp-zip-hyphen` recognises the dash form `#{3}-#{4}` (suggest prefix 4 — the same partial levels as `#{7}`, remaining digits 6·5·4·3, the dash never masked). A suggestion now needs a name or a value signal (unrelated columns never carry one), and `role_mismatch` also fires for `id` suggestions: keep/qi/sensitive with name+value evidence — a column whose name does not match is the leak scan's job. `run`/`config.py`/`engine.py`/`audit.py`/`derived.py`/`chartable.py`/`hidden_chars.py` byte-identical. |
| 0.7.2 | jp-basic 1.3.0: the `jp-person-name` and `jp-address` column rules (name-only, both suggest `id` — the direct-identifier treatment; person-name and address columns, English and Japanese names). The `hintpack` docstrings now state the column-name match as implemented — exact match on the normalized name. `run`/`config.py`/`engine.py`/`audit.py`/`derived.py` byte-identical. |
| 0.7.1 | The shared chartable (a sha256-pinned Sieve Lens replica) and the fixed fold: hint-pack value matching and the leak scan fold through it — full-width digits/symbols, long-vowel dashes and invisible characters now match (the v0.5.2 full-width limitation is resolved; no Unicode-database lookups, pure-ASCII matching byte-identical). The invisible-character observation on `plan` (per-column rows/chars/kinds, warnings for keep/qi/sensitive, `hidden_chars_summary`, `--no-hidden-chars`). jp-basic 1.2.0: the `jp-name-kana` column rule (name-only, suggests `id`). `run`/`config.py`/`engine.py`/`audit.py`/`derived.py` byte-identical. |
| 0.7.0 | The `audit` subcommand: an integer-only observation of the table as it is — equivalence classes and size buckets, per-QI-column leverage (distinct, column-unique rows, rows below k without the column), and, with `--subject`, the people behind the rows (repeats, subjects per class, and `rows_overstated`: classes that look safe on rows but hold fewer than k distinct people). Nothing is generalized, judged or written; `run`/`plan`/`inspect` are byte-identical to 0.6.2. |
| 0.6.2 | Municipality edition of the `jp-municipality-2026` pack (pack 1.1.0): the 総務省 "地方公共団体コード一覧" extract (basis date R6.1.1 = 2024-01-01, 1,747 municipalities) committed alongside the ABR prefecture extract, and the generator merges one prefecture + one municipality source (either order, `--pack-version`) into a single four-rule pack — 1,794 codes, 1,794 five-digit prefixes, 47 prefecture names, 1,714 distinct municipality names. Both sources are PDL 1.0. |
| 0.6.1 | Prefecture edition committed in `packs/`: the ABR prefecture master extract (47 prefectures, PDL 1.0), the generated pack, a prefecture mode for the generator with a fail-closed prefecture-level guard, and the attribution and compliance notes in `packs/README.md`. |
| 0.6.0 | Derived keep-vs-qi relations on `plan` (both directions, four classes, `derived_summary`, `--no-derived`); the `jp-birthdate` rule (jp-basic 1.1.0); the pack generator `tools/make_municipality_pack.py` and the `packs/` directory (generator only — the data arrived with 0.6.1). |
| 0.5.2 | The candidate order becomes a contract: evidence strength, then role, then rule id — independent of the pack load order and of the order rules are written in a pack; `_suggest` follows the first sorted candidate. The full-width token constraint is documented. |
| 0.5.1 | Hint packs load by default (builtin `jp-basic`); the role-aware leak scan (prose tokens, stderr warnings, `findings.warnings`); `pack_info`; duplicate pack/rule ids refused. |
| 0.5.0 | The hint pack system for `inspect`/`plan` (opt-in; `run` untouched); a sha256-pinned replica of the Sieve Schema Contract v1 conformance corpus for the JSON core. |
| 0.4.0 | `missing_value_policy` (`star` / `suppress` with budget sharing and `missing_exceeds_budget`); phase-2 refinement as a pruned depth-first walk (no region materialisation). |
| 0.3.0 | The `plan` subcommand (pre-flight search-space profile with warnings); aggregate-only diagnostics in receipts for suppression and refusals; custom non-uniform numeric `bins`. |
| 0.2.0 | The initial tagged release. |

- Since 0.5.0, every release keeps the `run` path byte-for-byte identical to 0.4.0 — the engine core is frozen, and releases touch only the observation side (`inspect` / `plan`, hint packs, docs).
- PyPI carries 0.2.0, 0.3.0, 0.4.0, 0.5.2 and everything from 0.6.0 on; 0.5.0 and 0.5.1 exist as git tags only.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 👤 Author

* **Kai IWASAKI**
