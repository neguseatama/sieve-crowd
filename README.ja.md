# Sieve Crowd v0.5.0

[English](README.md) | 日本語

**テーブルデータ匿名化・プライバシー保護エンジン**

[![PyPI Version](https://img.shields.io/pypi/v/sieve-crowd.svg)](https://pypi.org/project/sieve-crowd/)
[![Python Version](https://img.shields.io/pypi/pyversions/sieve-crowd.svg)](https://pypi.org/project/sieve-crowd/)
[![CI](https://github.com/neguseatama/sieve-crowd/actions/workflows/test.yml/badge.svg)](https://github.com/neguseatama/sieve-crowd/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

> Sieve Crowd は、表形式データにおける個人の特定リスクを抑え、安全に共有するためのテーブルデータ加工エンジンです。k-匿名性および l-多様性の原理に基づき、属性の丸め加工（一般化）と一部レコードの除外（抑制）を決定論的に行います。

完全ローカル実行・外部依存ゼロ・決定論的（100%再現可能）な、テーブルデータの匿名化・再識別を無効化する数理的変換エンジンです。[Sieve-Core](https://github.com/neguseatama/sieve-core) の設計思想をテーブルデータドメインへ拡張したプロジェクトです。

---

## 💡 コンセプトと開発思想

個人データを手元で安全に管理していても、それらの情報を含む表データを外部へ提供・公開しなければならないことがあります。あるいは漏洩のリスクを抱えます。一方で、統計的に見れば、年齢・郵便番号・性別といった複数の属性が組み合わさることで、個人の特定につながるリスクは常に存在します。

例えば、あるデータセット（600人規模）を例に取ると、そのリスク構造が明確になります。

- **処理前**: 600人のうち574人（96%）が、年齢・郵便番号・性別の組み合わせにおいて「自分と同じ条件の人が他にいない（＝孤立した1人）」状態となっており、外部から容易に特定されてしまいます。
- **変換の仕組み**: 本エンジンは、この孤立したデータを放置せず、類似するレコード同士をグループ化（丸めや一般化）することで、全員が安全な集団に紛れ込むよう構造を変換します。
- **処理後**: その結果、全員が「自分を含めて5人以上のグループ（4人の似た者）」に属するようになり、特定を試みても正解を当てる確率は最大でも20%（1/5）に抑えられます。

Sieve Crowd は、確率的な推測やブラックボックスなAIに頼らず、厳密な数学的モデル（k-anonymity / l-diversity）に基づいて、表データを「誰も目立たない安全な状態」へと決定論的に変換します。

- **決定論的アプローチ**: 同一の入力と設定からは、常に全く同じ出力が得られます。実行環境や時刻、乱数に依存しません。
- **結果は約束ではなく測定**: 処理後のデータが目標とする安全基準を満たしているかを事後的に数え直します。基準に届かなければ、理由はレシートに示され、表は出力されません。
- **説明可能性**: 匿名化のためのデータ処理を記したレシートを出力し、何が行われたかを完全に追跡できます。

---

## 🧩 Sieve シリーズ

Sieve は、決定的・ゼロ依存・完全ローカルという共通の設計原則を共有するエンジン群です。各エンジンが 1 つのリスクの観測または排除を担い、相互に接続します:

| パッケージ | 役割 | 接続 |
| :--- | :--- | :--- |
| [sieve-core-engine](https://github.com/neguseatama/sieve-core) | エコシステムの基盤ロジック / プラグインホスト | — |
| [sieve-lens](https://github.com/neguseatama/sieve-lens) | 文書内の不可視コンテンツ・隠しプロンプトを観測 | — |
| [sieve-scope](https://github.com/neguseatama/sieve-scope) | 構造的に類似したコードペアを検出 | — |
| [sieve-referee](https://github.com/neguseatama/sieve-referee) | 言い換え・流用されたテキストペアを検出 | — |
| [sieve-redact](https://github.com/neguseatama/sieve-redact) | 機密領域をレシートつきでマスキング (テキスト & PNG) | ← lens、→ tray |
| [sieve-crowd](https://github.com/neguseatama/sieve-crowd) | 表形式データにおける再識別リスクの観測と匿名化（k-匿名性） | — |
| [sieve-tray](https://github.com/neguseatama/sieve-tray) | ファイルを適切なエンジンへ振り分けるデスクトップフロントエンド | ← 全エンジン |

---

## 🔥 主な特徴

- **k-anonymity と l-diversity の適用**
  各レコードに少なくとも k−1 人の「似た者」が存在するように属性を一般化し、さらに機微情報の多様性を保証します。
- **ゼロ依存・完全ローカル**
  Python標準ライブラリのみで実装。データがパソコンの外に出ることは一切ありません（アカウント不要、オフライン、アップロードなし）。
- **最小限の一般化と抑制（Suppression）**
  データを必要以上に丸めず、解像度をできるだけ保ったままグループ化を行います。それでも他のデータとグループを作れない孤立したレコードは、無理に歪めず安全に除外（抑制）します。
- **事前プラン（plan）**
  `sieve-crowd plan` が、探索の前に正確な探索空間の大きさ（格子ノード数）、除外の上限、段階0のリスク・プロファイル、警告（届かない k / l、上限不足、孤立レコードの多さ）、そして v0.6.0 からは keep 列と準識別子の導出関係（keep 列が準識別子をほぼ決めていないか、その逆も含め双方向）を報告します。チューニングを「実行後」ではなく「実行前」に。
- **レシート内の診断（diagnostics）**
  レコードが除外されたとき、レシートが理由を説明します。群れの大きさ、「k 未満」か「多様性不足」かの別、さらにどの準識別子を1段階粗くすれば救われるかの列ごとのヒント。すべて集計値のみで、セルの値は一切出ません。
- **数値列のカスタム区間（bins）**
  「0-19, 20-39, 40-64, 65以上」のような不均一な区分（法定年齢階級、所得階層など）を、境界値のリストとして直接指定できます。
- **欠損値の方針（missing_value_policy）**
  準識別子が空のレコードの扱いを設定できます。`star`（既定）は他の値と同じく `*` に一般化し、`suppress` は検索の前にそのレコードを除きます（同じ除外予算に算入。予算を超えると `missing_exceeds_budget` で拒否）。埋め値（placeholder）は意図的に提供しません。埋めた値は、欠損パターンそのものを識別子に変えてしまいます。
- **レシートによる記録**
  処理の事実（適用ルール、抑制件数、測定値）を記した機械可読なレシートを出力します（レシートに個人情報は含まれません）。
- **対応フォーマット**
  CSV・JSON・XML（UTF-8）をサポート。Excelは依存ライブラリを排除するため対象外としています。

---

## 🎯 主な活用シーン

- 内部利用や社内シェア用に、手元のデータを安全に保管・管理・共有したいとき
- アンケートや顧客データを大学、代理店、分析委託先へ提供するとき
- 病院、学校、自治体などの統計やオープンデータを公開するとき
- 開発環境へ本物らしいテスト用データを安全に投入するとき
- データの匿名化処理と加工の記録を法務・監査用に残したいとき

---

## 📦 インストール

```bash
pip install git+https://github.com/neguseatama/sieve-crowd.git
```

またはローカルのクローンから:

```bash
git clone https://github.com/neguseatama/sieve-crowd.git
cd sieve-crowd
pip install .
```

---

## 💻 クイックスタート

### 1. 構造の検査

ファイルを読み込み、各列の役割（氏名、準識別子、機微情報など）の目安を提案する設定ファイルを出力します。

```bash
sieve-crowd inspect people.csv --config-out config.json
```

### 2. 設定の確認・編集

生成された `config.json` を編集し、各列の役割を定義します。

### 3. 事前プランの確認（任意）

実行の前に、探索の規模・除外の上限・段階0のリスク構造を確認できます。探索は行われず、何も書き込まれません:

```bash
sieve-crowd plan people.csv -c config.json
```

### 4. 匿名化の実行

```bash
sieve-crowd run people.csv -c config.json -o people_safe.csv --report-json receipt.json
```

入力・出力の例:

```
people.csv                                       people_safe.csv   （行はシャッフル済み）
name,birth_date,age,zip,sex,diagnosis            age,zip,sex,diagnosis
Takahashi Hina,1986-11-02,40,1500052,M,none     20-24,15100**,F,cold
Kobayashi Haruto,2003-01-03,23,1000042,F,flu    20-24,16000**,M,none
Yamamoto Aoi,1971-10-04,55,1510061,M,flu        55-59,15100**,M,asthma
```

---

## 🧪 ヒントパック（組み込みは既定オン）

`inspect` と `plan` は**ヒントパック**（JSON ファイル）を読み込みます。列への役割・一般化器の提案と値の形の検査を行い、匿名化には一切触れません。v0.5.1 から組み込みの `jp-basic` パックは**既定で読み込まれ**ます。`--no-builtin-hints` で除外します。`run` はパックを読みません（run のパスは v0.4.0 とバイト単位で同一です。`--no-builtin-hints` を付けてパックを指定しなければ、inspect のテンプレートまで v0.4.0 とバイト一致のままです）。

```bash
sieve-crowd inspect people.csv --config-out config.json              # 組み込み jp-basic を含めて提案
sieve-crowd plan   people.csv -c config.json    --findings-json f.json
sieve-crowd inspect people.csv --hint-pack my.json                   # 組み込み + my.json
sieve-crowd inspect people.csv --config-out t.json --no-builtin-hints  # v0.4.0 バイト一致の経路
```

- `--hint-pack FILE` — 組み込みに加えてパックを読み込む（複数指定可）。読み込み順は組み込みが先、次にコマンドラインの指定順。`findings` の `packs` / `pack_info` はこの順序に従います。候補の並びは独立の契約です（v0.5.2）: 根拠の強さ（name+value → value → name → stat）→ 役割（id → sensitive → qi・一覧にない役割は最後）→ ルール id の昇順 — 読み込み順にもパック内のルールの記述順にも従いません。`_suggest` は並べ替え後の先頭の候補に従います。
- `--no-builtin-hints` — `jp-basic` を除外し、指定したパックのみを使います（指定がなければ何も読み込まず、v0.4.0 バイト一致の出力のままです）。
- `--findings-json FILE` — 所見を JSON で書き出します。集計値と列名のみで、**セルの値は一切出ません**。`packs` は従来どおりパック id の配列。`pack_info` が読み込み順に `{id, version, source, sha256}` を加えます。`plan` ではパックが無くても導出分析の結果（`derived_summary`、v0.6.0）が入ります。

**パック id とルール id は組み込みを含め全パックで一意です。** 組み込みと同じ `jp-basic`（または `jp-phone` などのルール id）を使うユーザーパックは終了コード 2 で拒否されます。組み込みを差し替えるには、`--no-builtin-hints` を付けてからその id を使ってください。

パック（`schema: 1`・`utf-8-sig` で読み込み・省略可能な `version` 文字列）はルールのリストです。各ルールは `when`（`column_names` と/または `value_shape` で列を照合）、省略可能な `suggest`（役割＋一般化器の設定・その列だけ `_suggest` に書き込まれる）、省略可能な `check`（`set`/`range`/`luhn`/`my_number`/`email_shape`・各 3 値: 一致/不一致/無法検査）、省略可能な `leak` フラグを持ちます。`value_shape` 言語は暴走を防ぐため意図的に閉じています: `#` は数字 1 桁、`@` は英字 1 桁、`\X` は X の字面エスケープ、量化子は `{m}`/`{m,n}` のみ（選択・入れ子なし・バックトラック暴走の余地なし）。

**漏洩検査（v0.5.1）。** `leak: true` のルールは、検査対象の列を *トークン* 単位で走査します。セルを空白と句読点で区切り（`-`・`+`・`@`・`.`・`_`・`%` は区切らない）、文章の途中に混ざった番号も見つけます（`03-1234-5678` はハイフンを除いた形でも照合します）。空白で区切られた断片は決して結合しません — `03 1234 5678` は**検出されません**（文書化した制約）。トークンは ASCII 英数字と区切らない記号の連続なので、全角の数字やハイフン（`０９０－１２３４－５６７８` など）はトークンにならず、このままでは検出されません（同種の文書化した制約）。4096 文字を超えるセルは検査せず `skipped` として数えます。`plan` では宣言された役割が `keep`・`sensitive`・`qi` の列だけを検査し（id/drop は決して検査しません）、`inspect` は役割がないので全列を記録します。件数は `leaks[]`（`count`・`checked`・`skipped`、列には plan のみ `declared_role`）で報告され、`plan` では件数 1 以上のとき stderr の警告行と `findings.warnings` の `code: "leak"` 要素が出ます。`inspect` は代わりに候補と同じ書式の 1 行を出します。数字は「可能性」であって証明ではなく、警告は終了コードを変えません。

**keep 列 × 準識別子の導出関係（v0.6.0、`plan` のみ）。** keep 列 X と準識別子 Q の全ての組（X ≠ Q）を双方向で評価し、一方がもう一方をほぼ決めていないかを報告します: `reveals_qi`（X は出力にそのまま残るため、Q を一般化しても X から元の値が読めてしまう）と `implied_by_qi`（準識別子の値から keep 列の値がほぼ決まる）。評価された各方向は必ず次の 4 分類の 1 つになります: `unchecked`（比較レコードが 50 未満）、`trivial`（どちらかの列が一定、またはソースの値が全て一意 — 関係が情報を持たない）、`flagged`（支持 s が 50 以上で、違反 v — ソースの値では 1 つの値に定まらないレコード — が s の 1% 以下かつ超過分 s−m の 10% 以下。m はソースの異なる値の数）、`clear`（検査したが違反が多い）。flagged は stderr に `  - derived: …` 行として（ヒントパックの所見の直後に、自分の見出しは付けずに）出力され、`findings.warnings` には `code: "derived"` 要素（`column`・`declared_role`・`qi_column`・`relation`・`support`・`violations`）として入ります。トップレベルの `derived_summary` は 4 分類を数え、`unchecked + trivial + flagged + clear = 2 × (pairs − skipped_pairs)` が常に成り立ちます。値の比較はエンジンと同じ正規化（NFC＋前後の空白除去）で行い、空のセルは除外します。1 回の plan で評価する組は最大 400（残りは `skipped_pairs`）。`--no-derived` でこの報告全体を省きます。閾値はコード内定数で設定化しません。列名と件数のみで、セルの値は一切出ません。

組み込みの `jp-basic` パック（version 1.1.0）は、日本の郵便番号（`prefix` length 4）、生年月日（`#{4}-#{2}-#{2}` → `qi` と `type: date` を提案。v0.6.0 で追加）、電話/マイナンバー/メール/カード番号の漏洩検査（Luhn と公式のマイナンバー検査数字）、47 都道府県を 8 地方ブロック区分の `category` 階層として（三重 = 近畿・新潟 = 中部・パック内に基準を 1 つ固定）、年齢、そして 3 つの観測警告をカバーします: `role_mismatch`（`qi` を提案した列が `keep`/`sensitive` として宣言されている）、`mixed_form`（全角・半角が混在 — NFC では別の群れになる）、`japanese_era`（和暦形式の値）。基準を変えるにはパックを編集してください。ヒントは run に影響しません。

**`packs/` ディレクトリ（v0.6.0）。** wheel とは別に配布するヒントパックを置く場所です — `packs/` も `tools/` もパッケージには含まれません。最初の候補 `jp-municipality-2026` は、総務省の全国地方公共団体コードから `tools/make_municipality_pack.py` でローカル生成します（標準ライブラリのみ・決定論的でバイト同一の出力・列名の契約違反は列名だけ示して終了コード 2）。配布は出典の利用条件の確認後まで保留 — 詳細は `packs/README.md`。

---

## ⚙️ 設定パラメータとオプション

| 設定項目 | 既定値 | 意味・説明 |
| :--- | :--- | :--- |
| `k` | 5 | 誰もが少なくとも k−1 人の似た者を持つ基準。大きいほど安全で一般化の度合いも強くなる |
| `l` | 任意 | どの群れにも少なくとも l 種類の機微な値があることを保証し、「全員が同じ診断名」を防ぐ |
| `max_suppression` | 0.05 (5%) | データ全体の解像度をもっと下げる代わりに、目立つ少数のレコードを除外（抑制）してよい最大割合 |
| `missing_value_policy` | `star` | `star`：空の準識別子は他の値と同じく `*` に一般化される。`suppress`：そのようなレコードは探索の前に除外され、`max_suppression` に算入される。 |
| 役割 (`role`) | — | `id`（削除または仮名化）・`qi`（一般化）・`sensitive`（残す）・`keep`（残す）・`drop`（削除） |
| 一般化器 (`type`) | — | `qi` 列に対して: `numeric`（`widths`、または不均一なカスタム `bins`）・`date`・`prefix`・`category`（階層）・`exact` |

主なコマンドラインオプション:

- `--dry-run`: データを書き出さず、匿名化の測定とリスク評価のみを実行
- `sieve-crowd plan people.csv -c config.json`: 探索空間・除外の上限・警告、そして keep 列 × 準識別子の導出関係の事前見積り（`--no-derived` で導出関係を省略。探索なし、出力なし）
- `--lang ja`: 日本語のレシートを出力（既定は英語、JSON出力も可）
- `--in-format` / `--out-format`: 入出力形式の明示指定（csv, json, xml）
- `sieve-crowd keygen -o key.txt`: 仮名化（pseudonymize）用の暗号鍵を生成

終了コード:

- `0`: 成功
- `1`: 入出力エラー
- `2`: 設定エラー
- `3`: 拒否（目標とする匿名化レベルに到達せず出力を停止）

---

## 🔬 テスト

```bash
python -m unittest discover -s tests -v
```

外部依存なし（標準ライブラリのみ）で全てのテストスイートが実行されます。

テストスイートには、Sieve Schema Contract v1 適合コーパス (受理/拒否
44 ケース) の sha256 pin 付き複製が同梱されています。コーパスの正本と
契約書 (`docs/SCHEMA_CONTRACT_v1.md`)・正本エンジン
(`sieve_lens_ext/schema.py`) は sieve-lens リポジトリで管理されています。
複製が実測するのは Crowd の JSON コア (`sieve_crowd.jsonio`) で、重複キーと
`NaN`/`Infinity` を拒否します。UTF-8 BOM のケースは宣言済みの差異
(declared divergence) です — Crowd は表計算ソフトの書き出し (BOM 付き) を
意図して `utf-8-sig` でデコードするため、契約の適合マトリクス (§6) の
宣言どおり、ランナーは拒否ではなく受理を pin します。

---

## ⚠️ 既知の限界と注意点

1. **モデルの前提** — Sieve Crowdが守るのは、`qi`（準識別子）に指定した属性を把握している攻撃者に対してです。想定外の補助情報による再識別を完全に防ぐ万能の盾ではありません。
2. **法務・プライバシー確認の代替ではない** — 個人情報保護法や各種ガイドラインに基づく法的・制度的な適合性を保証するものではなく、それを技術的に支援するツールです。
3. **Excel非対応** — 依存ライブラリゼロの原則を貫くため、バイナリ形式の `.xlsx` は非対応です（CSV / JSON / XML をご利用ください）。
4. **レコードのシャッフル** — 再識別リスクを最小化するため、出力される行順序は決定論的にシャッフルされます。

---

## 📄 ライセンス

MIT License。詳細は [LICENSE](LICENSE) を参照してください。

---

## 👤 Author

* **Kai IWASAKI**
