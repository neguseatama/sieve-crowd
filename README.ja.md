# Sieve Crowd v0.2.0

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

### 3. 匿名化の実行

```bash
sieve-crowd run people.csv -c config.json -o people_safe.csv --receipt receipt.json
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

## ⚙️ 設定パラメータとオプション

| 設定項目 | 既定値 | 意味・説明 |
| :--- | :--- | :--- |
| `k` | 5 | 誰もが少なくとも k−1 人の似た者を持つ基準。大きいほど安全で一般化の度合いも強くなる |
| `l` | 任意 | どの群れにも少なくとも l 種類の機微な値があることを保証し、「全員が同じ診断名」を防ぐ |
| `max_suppression` | 0.05 (5%) | データ全体の解像度をもっと下げる代わりに、目立つ少数のレコードを除外（抑制）してよい最大割合 |
| 役割 (`role`) | — | `id`（削除または仮名化）・`qi`（一般化）・`sensitive`（残す）・`keep`（残す）・`drop`（削除） |

主なコマンドラインオプション:

- `--dry-run`: データを書き出さず、匿名化の測定とリスク評価のみを実行
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
