# packs/

Hint packs that ship separately from the wheel: this directory is **not** part
of the `sieve_crowd` package and nothing in it is packaged into the wheel or
the sdist.  A pack placed here is loaded with `--hint-pack` on `inspect` /
`plan` (compose it with the built-in pack, or use `--no-builtin-hints`).

## jp-municipality-2026 — municipality edition (v0.6.2, pack 1.1.0, distributed)

The Japanese local-government hint pack, **prefecture + municipality level**:
1,794 six-digit codes (47 prefectures + 1,747 municipalities), 1,794 distinct
five-digit prefixes (47 of them prefecture-level, ending in `000`), the 47
prefecture names and the 1,714 distinct municipality names.  The full
town-level master (156 MB) and the 総務省 sheet 「R6.1.1政令指定都市」 (the 20
designated cities and their wards) stay out of the repository.

| file | what it is |
|---|---|
| `mt_pref_all.csv` | the ABR prefecture master rows as obtained — 47 rows, UTF-8; line endings normalized CRLF → LF when committed (2,690 → 2,642 bytes; the obtained file's sha256 was `9f1f7a95e17b2e44e1f44f1d8964565d127f86a6b9c43c735c1c3da955136ba0`) |
| `soumu_city_r611.csv` | the 総務省 municipality rows (basis date R6.1.1 = 2024-01-01) — 1,747 rows, UTF-8, LF, source row order preserved (code-ascending).  Converted from the obtained xlsx (sheet 「R6.1.1現在の団体」; 97,186 bytes, sha256 `7d04c8a7f6a6e76a7823a0414a8422bf2b26bb6070766971df76eab58ea6ff78`, byte-identical to https://www.soumu.go.jp/main_content/000925835.xlsx): the headers were normalized (`都道府県名␊（漢字）` → `都道府県名` etc.; the （カナ） columns are kept as extra columns the tool ignores), and the 47 prefecture rows of the sheet were removed — they carry empty city names (the tool would reject them), and the prefecture data of the pack comes from the ABR extract instead; both sources agree on the 47 codes and the 47 kanji names (mechanically checked).  The check digits of all 1,794 codes were verified against the 総務省 spec (weights 6,5,4,3,2 → the last digit of 11 − remainder) at receipt time — the tool itself never checks them. |
| `jp-municipality-2026.json` | the generated pack (`--hint-pack packs/jp-municipality-2026.json`); never hand-edit |

## 出典・ライセンス表記 / Source and license

Both sources are governed by the 公共データ利用規約（第1.0版） — PDL 1.0: the
Digital Agency publishes the registry under it, and the 総務省 states that its
site content follows the same terms unless noted otherwise
(https://www.soumu.go.jp/menu_kyotsuu/policy/tyosaku.html 「当省ホームページ
について」).

English:

> The data in `packs/` (`mt_pref_all.csv`, `soumu_city_r611.csv` and the pack
> JSON generated from them) is created by the **sieve-crowd** project based on
> the アドレス・ベース・レジストリ (Address-base registry) by the Digital
> Agency of Japan
> (https://www.digital.go.jp/policies/base_registry_address) and on the
> 「地方公共団体コード一覧」 (全国地方公共団体コード) by the Ministry of
> Internal Affairs and Communications
> (https://www.soumu.go.jp/denshijiti/code.html).
> License: Public Data License (Version 1.0) — PDL 1.0
> (https://www.digital.go.jp/resources/open_data/public_data_license_v1.0).

日本語:

> 本ディレクトリのデータ（`mt_pref_all.csv`、`soumu_city_r611.csv`、および
> そこから生成した `jp-municipality-2026.json`）は、デジタル庁の
> 「アドレス・ベース・レジストリ」
> （https://www.digital.go.jp/policies/base_registry_address）及び総務省の
> 「地方公共団体コード一覧」（全国地方公共団体コード）
> （https://www.soumu.go.jp/denshijiti/code.html）をもとに
> **sieve-crowd** プロジェクトが加工・作成したものです。
> ライセンス: パブリック・データ・ライセンス 1.0（PDL 1.0）
> （https://www.digital.go.jp/resources/open_data/public_data_license_v1.0）。

Compliance notes (PDL 1.0 — 公共データ利用規約 第1.0版, established 2024-07-05):

- **加工の明示（項1.1）** — the pack is a filtered subset of two government
  sources converted to JSON, so it is published as *edited* data
  （「〜をもとに加工・作成」）, never presented as an unmodified registry; the
  総務省 site policy 1.1-イ states the same requirement (加工したことを記載し、
  国が作成したかのような態様で公表しない).
- **ロゴ不使用（項1.4）** — no Digital Agency or 総務省 logo or symbol mark is
  used in this repository; the sources are cited in text only.
- PDL 1.0 requires the source citation and the edited-data statement above
  and is stated to be compatible with CC BY 4.0.

| field | value |
|---|---|
| source 1 (出典) | デジタル庁「アドレス・ベース・レジストリ」 https://www.digital.go.jp/policies/base_registry_address |
| source 2 (出典) | 総務省「地方公共団体コード一覧」（全国地方公共団体コード） https://www.soumu.go.jp/denshijiti/code.html — obtained file https://www.soumu.go.jp/main_content/000925835.xlsx (R6.1.1現在, 97,186 bytes, sha256 `7d04c8a7f6a6e76a7823a0414a8422bf2b26bb6070766971df76eab58ea6ff78`; the received copy is byte-identical) |
| license (利用条件) | パブリック・データ・ライセンス 1.0（PDL 1.0） https://www.digital.go.jp/resources/open_data/public_data_license_v1.0 — the 総務省 applies the same 公共データ利用規約（第1.0版） to its site content (https://www.soumu.go.jp/menu_kyotsuu/policy/tyosaku.html) |
| obtained (取得日) | both sources 2026-11-02; the 総務省 list's own basis date is R6.1.1 = 2024-01-01 (carried in the sheet name, recorded here — the extracts themselves carry no basis date) |
| scope (範囲) | prefecture level: 47 rows (ABR, all currently effective, `efct_date` 1947-04-17 / `ablt_date` empty); municipality level: 1,747 rows (市 792 / 町 743 / 村 189 / 区 23 — the 区 are the 東京 23 special wards); the 総務省 sheet 「R6.1.1政令指定都市」 (192 rows) is not used |
| generator | `tools/make_municipality_pack.py` (standard library only) |

Regenerate (deterministic — the same inputs yield byte-identical output, in
either input order):

    python3 tools/make_municipality_pack.py packs/mt_pref_all.csv packs/soumu_city_r611.csv -o packs/jp-municipality-2026.json --pack-version 1.1.0

The xlsx itself is not committed (only the converted extract described above);
regenerating from the two committed extracts must reproduce the committed pack
bytes (T29).  Do not hand-edit the output.
