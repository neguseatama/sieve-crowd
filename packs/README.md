# packs/

Hint packs that ship separately from the wheel: this directory is **not** part
of the `sieve_crowd` package and nothing in it is packaged into the wheel or
the sdist.  A pack placed here is loaded with `--hint-pack` on `inspect` /
`plan` (compose it with the built-in pack, or use `--no-builtin-hints`).

## jp-municipality-2026 — prefecture edition (v0.6.1, distributed)

The Japanese local-government hint pack, **prefecture level**: the 6-digit and
5-digit codes of the 47 prefectures and the 47 prefecture names.  The full
town-level master (156 MB) is too large to redistribute here and stays out of
the repository; only the prefecture-level extract is committed.

| file | what it is |
|---|---|
| `mt_pref_all.csv` | the prefecture master rows as obtained — 47 rows, UTF-8; line endings normalized CRLF → LF when committed (2,690 → 2,642 bytes; the obtained file's sha256 was `9f1f7a95e17b2e44e1f44f1d8964565d127f86a6b9c43c735c1c3da955136ba0`) |
| `jp-municipality-2026.json` | the generated pack (`--hint-pack packs/jp-municipality-2026.json`); never hand-edit |

## 出典・ライセンス表記 / Source and license

English:

> The data in `packs/` (`mt_pref_all.csv` and the pack JSON generated from it)
> is created by the **sieve-crowd** project based on the アドレス・ベース・
> レジストリ (Address-base registry) by the Digital Agency of Japan
> (https://www.digital.go.jp/policies/base_registry_address).
> License: Public Data License (Version 1.0) — PDL 1.0
> (https://www.digital.go.jp/resources/open_data/public_data_license_v1.0).

日本語:

> 本ディレクトリのデータ（`mt_pref_all.csv`、およびそこから生成した
> `jp-municipality-2026.json`）は、デジタル庁の「アドレス・ベース・レジストリ」
> （https://www.digital.go.jp/policies/base_registry_address）をもとに
> **sieve-crowd** プロジェクトが加工・作成したものです。
> ライセンス: パブリック・データ・ライセンス 1.0（PDL 1.0）
> （https://www.digital.go.jp/resources/open_data/public_data_license_v1.0）。

Compliance notes (PDL 1.0 — 公共データ利用規約 第1.0版, established 2024-07-05):

- **加工の明示（項1.1）** — the pack is a filtered subset (prefecture rows
  only) converted to JSON, so it is published as *edited* data
  （「〜をもとに加工・作成」）, never presented as the unmodified registry.
- **ロゴ不使用（項1.4）** — no Digital Agency logo or symbol mark is used in
  this repository; the source is cited in text only.
- PDL 1.0 requires the source citation and the edited-data statement above
  and is stated to be compatible with CC BY 4.0.

| field | value |
|---|---|
| source (出典) | デジタル庁「アドレス・ベース・レジストリ」 https://www.digital.go.jp/policies/base_registry_address |
| license (利用条件) | パブリック・データ・ライセンス 1.0（PDL 1.0） https://www.digital.go.jp/resources/open_data/public_data_license_v1.0 |
| obtained (取得日) | 2026-11-02 |
| scope (範囲) | prefecture level only — 47 rows, all currently effective (`efct_date` 1947-04-17, `ablt_date` empty); the download's 基準日 is not carried inside the extract itself |
| generator | `tools/make_municipality_pack.py` (standard library only) |

Regenerate (deterministic — the same input yields byte-identical output):

    python3 tools/make_municipality_pack.py packs/mt_pref_all.csv -o packs/jp-municipality-2026.json

The generator also accepts the 総務省 local-government code list
(`団体コード` / `都道府県名` / `市区町村名` — municipality level).  A pack
generated that way stays local: the terms of use for that source are not
confirmed, and it would carry municipality names the committed prefecture
edition does not have.  Regenerate the committed pack only from the committed
extract; do not hand-edit the output.
