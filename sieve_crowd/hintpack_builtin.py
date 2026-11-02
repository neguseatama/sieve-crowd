"""The built-in ``jp-basic`` hint pack.

A string constant, not a separate file: it ships with the wheel and is loaded
by ``hintpack.load_packs`` unless ``--no-builtin-hints`` is given.  A user pack
that reuses the id ``jp-basic`` overrides the built-in (the user copy wins).

Region classification (案 A — one standard fixed inside the pack, as decided):
the 47 prefectures are mapped to the eight-block grouping used by government
statistics (総務省/e-Stat 地方ブロック).  Prefectures whose regional placement
varies by source — 三重 (近畿 here), 新潟 (中部), 長野 and 岐阜 (中部) — are
called out in the pack's ``_comment``.  Because hints never touch the output,
a different choice would change only the wording of a suggestion, never a run.
"""
from __future__ import annotations

import json

# 47 都道府県 -> [地方] (one level of hierarchy).  The set check uses the same
# 47 names; both are generated from this mapping so they cannot drift apart.
_PREF_TO_REGION = {
    "北海道": "北海道",
    "青森県": "東北", "岩手県": "東北", "宮城県": "東北", "秋田県": "東北",
    "山形県": "東北", "福島県": "東北",
    "茨城県": "関東", "栃木県": "関東", "群馬県": "関東", "埼玉県": "関東",
    "千葉県": "関東", "東京都": "関東", "神奈川県": "関東",
    "新潟県": "中部", "富山県": "中部", "石川県": "中部", "福井県": "中部",
    "山梨県": "中部", "長野県": "中部", "岐阜県": "中部", "静岡県": "中部", "愛知県": "中部",
    "三重県": "近畿", "滋賀県": "近畿", "京都府": "近畿", "大阪府": "近畿",
    "兵庫県": "近畿", "奈良県": "近畿", "和歌山県": "近畿",
    "鳥取県": "中国", "島根県": "中国", "岡山県": "中国", "広島県": "中国", "山口県": "中国",
    "徳島県": "四国", "香川県": "四国", "愛媛県": "四国", "高知県": "四国",
    "福岡県": "九州・沖縄", "佐賀県": "九州・沖縄", "長崎県": "九州・沖縄", "熊本県": "九州・沖縄",
    "大分県": "九州・沖縄", "宮崎県": "九州・沖縄", "鹿児島県": "九州・沖縄", "沖縄県": "九州・沖縄",
}
assert len(_PREF_TO_REGION) == 47

_PACK = {
    "schema": 1,
    "id": "jp-basic",
    "version": "1.2.0",
    "_comment": (
        "Built-in hints for common Japanese columns. Region classification "
        "follows the 総務省/e-Stat eight-block 地方ブロック grouping: 三重=近畿, "
        "新潟=中部, 長野/岐阜=中部. 1.1.0 adds jp-birthdate (ISO YYYY-MM-DD). "
        "1.2.0 adds jp-name-kana (kana name columns suggest id). "
        "Hints never affect the run output; edit this pack to change a standard."
    ),
    "rules": [
        {
            "id": "jp-zip",
            "when": {"column_names": ["zip", "zipcode", "postal", "postcode", "郵便", "〒"],
                     "value_shape": "#{7}"},
            "suggest": {"role": "qi", "type": "prefix", "length": 4},
        },
        {
            "id": "jp-phone",
            "when": {"column_names": ["phone", "tel", "telephone", "mobile", "電話", "携帯"],
                     "value_shape": "#{10,11}"},
            "leak": True,
        },
        {
            "id": "jp-mynumber",
            "when": {"value_shape": "#{12}"},
            "check": {"kind": "my_number"},
            "leak": True,
        },
        {
            "id": "jp-card",
            "when": {"value_shape": "#{13,19}"},
            "check": {"kind": "luhn"},
            "leak": True,
        },
        {
            "id": "jp-email",
            "when": {"column_names": ["email", "mail", "e-mail", "メール"]},
            "check": {"kind": "email_shape"},
            "leak": True,
        },
        {
            "id": "jp-name-kana",
            "when": {"column_names": ["furigana", "kana", "name_kana", "last_name_kana",
                                      "first_name_kana", "フリガナ", "ふりがな", "カナ",
                                      "氏名カナ", "氏名フリガナ", "姓カナ", "名カナ",
                                      "姓フリガナ", "名フリガナ"]},
            "suggest": {"role": "id"},
        },
        {
            "id": "jp-prefecture",
            "when": {"column_names": ["pref", "prefecture", "都道府県", "prefecture_name"]},
            "check": {"kind": "set", "values": list(_PREF_TO_REGION)},
            "suggest": {"role": "qi", "type": "category",
                        "hierarchy": {p: [r] for p, r in _PREF_TO_REGION.items()}},
        },
        {
            "id": "jp-birthdate",
            "when": {"column_names": ["birth_date", "birthdate", "date_of_birth",
                                      "dob", "birthday", "birth",
                                      "生年月日", "誕生年月日", "誕生日"],
                     "value_shape": "#{4}-#{2}-#{2}"},
            "suggest": {"role": "qi", "type": "date"},
        },
        {
            "id": "jp-age",
            "when": {"column_names": ["age", "年齢"]},
            "check": {"kind": "range", "min": 0, "max": 120},
            "suggest": {"role": "qi", "type": "numeric", "widths": [5, 10, 20]},
        },
    ],
}

BUILTIN_PACK_BYTES = (json.dumps(_PACK, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
BUILTIN_PACK_ID = _PACK["id"]
