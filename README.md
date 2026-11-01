# Sieve Crowd v0.4.0

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
- **Pre-flight plan**
  `sieve-crowd plan` reports, before any search, the exact search-space size (lattice nodes), the suppression budget, the level-0 risk profile and warnings (unreachable k/l, tight limits, many isolated records) — so tuning happens before the run, not after.
- **Diagnostics in the receipt**
  When records are suppressed, the receipt explains why — crowd sizes, "smaller than k" vs "short of diversity", and a per-column hint of which quasi-identifier one more generalization step would rescue. In aggregates only; never a cell value.
- **Custom bins for numeric columns**
  Non-uniform classifications such as `0-19, 20-39, 40-64, 65+` (legal age brackets, income bands) can be given directly as bin edges.
- **A policy for missing values**
  `missing_value_policy` decides what happens to records whose quasi-identifier is empty: `star` (default) generalizes the value to `*`; `suppress` removes the record up front, inside the same counted suppression budget (and refuses with `missing_exceeds_budget` when they exceed it). No placeholder option — filling values in would turn the missing pattern itself into an identifier.
- **Receipt for the record**
  A machine-readable receipt records what was done (rules applied, suppression count, measurements). The receipt contains no personal information.
- **Supported formats**
  CSV, JSON and XML (UTF-8). Excel is excluded to keep the tool dependency-free.

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
- `sieve-crowd plan people.csv -c config.json`: pre-flight estimate of the search space, budget and warnings (no search, no output)
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
3. **Excel is not supported** — To keep the dependency-free principle, the binary `.xlsx` format is out of scope (use CSV / JSON / XML).
4. **Row shuffling** — To minimize re-identification risk, the output row order is deterministically shuffled.

---

## 📄 License

MIT License. See [LICENSE](LICENSE) for details.

---

## 👤 Author

* **Kai IWASAKI**
