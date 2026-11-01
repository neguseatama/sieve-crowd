# packs/

Hint packs that ship separately from the wheel: this directory is **not** part
of the `sieve_crowd` package and nothing in it is packaged into the wheel or
the sdist.  A pack placed here is loaded with `--hint-pack` on `inspect` /
`plan` (compose it with the built-in pack, or use `--no-builtin-hints`).

## jp-municipality-2026 — planned, not distributed yet

The Japanese municipality hint pack (6-digit and 5-digit local-government
codes, municipality names) is generated locally; distribution is on hold
until the terms of use for the source list are confirmed.

| field | value |
|---|---|
| source (出典) | 総務省「全国地方公共団体コード」— *URL to be recorded here* |
| basis date (基準日) | *to be recorded when the list version is fixed* |
| terms of use (利用条件) | *to be confirmed and recorded before any distribution* |
| generator | `tools/make_municipality_pack.py` (standard library only) |

Generate it locally:

    python3 tools/make_municipality_pack.py local_government_code.csv -o jp-municipality-2026.json

The tool is deterministic (the same input yields byte-identical output), so
the generated pack can be re-created and re-verified at any time.  Regenerate
it when the source list changes; do not hand-edit the output.
