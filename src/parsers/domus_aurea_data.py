FIX_SPOT_QUEST_MAPPING: dict[str, int] = {
    "殺極級": 94066106,
    "殺超級": 94006828,
    "殺上級": 94006827,
    "殺中級": 94006826,
    "殺初級": 94006825,
    "術極級": 94066105,
    "術超級": 94006824,
    "術上級": 94006823,
    "術中級": 94006822,
    "術初級": 94006821,
    "騎極級": 94066104,
    "騎超級": 94006820,
    "騎上級": 94006819,
    "騎中級": 94006818,
    "騎初級": 94006817,
    "狂極級": 94066103,
    "狂超級": 94006816,
    "狂上級": 94006815,
    "狂中級": 94006814,
    "狂初級": 94006813,
    "槍極級": 94066102,
    "槍超級": 94006812,
    "槍上級": 94006811,
    "槍中級": 94006810,
    "槍初級": 94006809,
    "弓極級": 94066101,
    "弓超級": 94006808,
    "弓上級": 94006807,
    "弓中級": 94006806,
    "弓初級": 94006805,
    "剣極級": 94066107,
    "剣超級": 94006804,
    "剣上級": 94006803,
    "剣中級": 94006802,
    "剣初級": 94006801,
    # huyuki
    "X-A（屋敷跡）": 93000001,
    "X-B（爆心地）": 93000002,
    "X-C（大橋）": 93000003,
    "X-D（港）": 93000004,
    "X-E（教会）": 93000005,
    "X-F（校舎）": 93000006,
    "X-G（燃え盛る森）": 93000007,
    "変動座標点0号（大空洞）": 93000008,
    # dup
    # "群島（静かな入り江）": 93000308,
    # "群島（隠された島）": 93000312,
    # "裏山（名もなき霊峰）": 93020307,
    # "裏山（戦戦恐恐）": 93020309,
    # "代々木ニ丁目" ニ 二
    "代々木二丁目": 93020101,
    # LB2.7 角のような岩山 => 賢者の隠れ家
    "賢者の隠れ家": 93031302,
    # Ordeal Call
    # "光糸導く迷宮": 94093201,
    # "久遠の微笑": 94093202,
}


_LEGACY_ITEM_MAPPING = (
    ("証", 6503, "英雄の証"),
    ("骨", 6516, "凶骨"),
    ("牙", 6512, "竜の牙"),
    ("塵", 6505, "虚影の塵"),
    ("鎖", 6522, "愚者の鎖"),
    ("毒針", 6527, "万死の毒針"),
    ("髄液", 6530, "魔術髄液"),
    ("鉄杭", 6533, "宵哭きの鉄杭"),
    ("火薬", 6534, "励振火薬"),
    ("小鐘", 6549, "赦免の小鐘"),
    ("種", 6502, "世界樹の種"),
    ("ﾗﾝﾀﾝ", 6508, "ゴーストランタン"),
    ("八連", 6515, "八連双晶"),
    ("蛇玉", 6509, "蛇の宝玉"),
    ("羽根", 6501, "鳳凰の羽根"),
    ("歯車", 6510, "無間の歯車"),
    ("頁", 6511, "禁断の頁"),
    ("ホム", 6514, "ホムンクルスベビー"),
    ("蹄鉄", 6513, "隕蹄鉄"),
    ("勲章", 6524, "大騎士勲章"),
    ("貝殻", 6526, "追憶の貝殻"),
    ("勾玉", 6532, "枯淡勾玉"),
    ("結氷", 6535, "永遠結氷"),
    ("指輪", 6537, "巨人の指輪"),
    ("ｵｰﾛﾗ", 6536, "オーロラ鋼"),
    ("鈴", 6538, "閑古鈴"),
    ("矢尻", 6541, "禍罪の矢尻"),
    ("冠", 6543, "光銀の冠"),
    ("霊子", 6545, "神脈霊子"),
    ("糸玉", 6547, "虹の糸玉"),
    ("鱗粉", 6550, "夢幻の鱗粉"),
    ("爪", 6507, "混沌の爪"),
    ("心臓", 6517, "蛮神の心臓"),
    ("逆鱗", 6506, "竜の逆鱗"),
    ("根", 6518, "精霊根"),
    ("幼角", 6519, "戦馬の幼角"),
    ("涙石", 6520, "血の涙石"),
    ("脂", 6521, "黒獣脂"),
    ("ﾗﾝﾌﾟ", 6523, "封魔のランプ"),
    ("ｽｶﾗﾍﾞ", 6525, "智慧のスカラベ"),
    ("産毛", 6528, "原初の産毛"),
    ("胆石", 6529, "呪獣胆石"),
    ("神酒", 6531, "奇奇神酒"),
    ("炉心", 6539, "暁光炉心"),
    ("鏡", 6540, "九十九鏡"),
    ("卵", 6542, "真理の卵"),
    ("ｶｹﾗ", 6544, "煌星のカケラ"),
    ("実", 6546, "悠久の実"),
    ("鬼灯", 6548, "鬼炎鬼灯"),
    ("剣", 6001, "剣の輝石"),
    ("弓", 6002, "弓の輝石"),
    ("槍", 6003, "槍の輝石"),
    ("騎", 6004, "騎の輝石"),
    ("術", 6005, "術の輝石"),
    ("殺", 6006, "殺の輝石"),
    ("狂", 6007, "狂の輝石"),
    ("剣", 6101, "剣の魔石"),
    ("弓", 6102, "弓の魔石"),
    ("槍", 6103, "槍の魔石"),
    ("騎", 6104, "騎の魔石"),
    ("術", 6105, "術の魔石"),
    ("殺", 6106, "殺の魔石"),
    ("狂", 6107, "狂の魔石"),
    ("剣", 6201, "剣の秘石"),
    ("弓", 6202, "弓の秘石"),
    ("槍", 6203, "槍の秘石"),
    ("騎", 6204, "騎の秘石"),
    ("術", 6205, "術の秘石"),
    ("殺", 6206, "殺の秘石"),
    ("狂", 6207, "狂の秘石"),
    ("剣", 7001, "セイバーピース"),
    ("弓", 7002, "アーチャーピース"),
    ("槍", 7003, "ランサーピース"),
    ("騎", 7004, "ライダーピース"),
    ("術", 7005, "キャスターピース"),
    ("殺", 7006, "アサシンピース"),
    ("狂", 7007, "バーサーカーピース"),
    ("剣", 7101, "セイバーモニュメント"),
    ("弓", 7102, "アーチャーモニュメント"),
    ("槍", 7103, "ランサーモニュメント"),
    ("騎", 7104, "ライダーモニュメント"),
    ("術", 7105, "キャスターモニュメント"),
    ("殺", 7106, "アサシンモニュメント"),
    ("狂", 7107, "バーサーカーモニュメント"),
)

ITEM_NAME_MAPPING: dict[str, tuple[int, str]] = {
    "証": (6503, "英雄の証"),
    "骨": (6516, "凶骨"),
    "牙": (6512, "竜の牙"),
    "塵": (6505, "虚影の塵"),
    "鎖": (6522, "愚者の鎖"),
    "毒針": (6527, "万死の毒針"),
    "髄液": (6530, "魔術髄液"),
    "鉄杭": (6533, "宵哭きの鉄杭"),
    "火薬": (6534, "励振火薬"),
    "小鐘": (6549, "赦免の小鐘"),
    "剣": (6551, "黄昏の儀式剣"),
    "灰": (6552, "忘れじの灰"),
    "刃": (6554, "黒曜鋭刃"),
    "残滓": (6555, "狂気の残滓"),
    #
    "種": (6502, "世界樹の種"),
    "ﾗﾝﾀﾝ": (6508, "ゴーストランタン"),
    "八連": (6515, "八連双晶"),
    "蛇玉": (6509, "蛇の宝玉"),
    "羽根": (6501, "鳳凰の羽根"),
    "歯車": (6510, "無間の歯車"),
    "頁": (6511, "禁断の頁"),
    "ホム": (6514, "ホムンクルスベビー"),
    "蹄鉄": (6513, "隕蹄鉄"),
    "勲章": (6524, "大騎士勲章"),
    "貝殻": (6526, "追憶の貝殻"),
    "勾玉": (6532, "枯淡勾玉"),
    "結氷": (6535, "永遠結氷"),
    "指輪": (6537, "巨人の指輪"),
    "ｵｰﾛﾗ": (6536, "オーロラ鋼"),
    "鈴": (6538, "閑古鈴"),
    "矢尻": (6541, "禍罪の矢尻"),
    "冠": (6543, "光銀の冠"),
    "霊子": (6545, "神脈霊子"),
    "糸玉": (6547, "虹の糸玉"),
    "鱗粉": (6550, "夢幻の鱗粉"),
    "皮": (6553, "太陽皮"),
    "ｴｰﾃﾙ": (6556, "エーテル収光体"),
    "花": (6557, "終の花"),
    "ｷｭｰﾌﾞ": (6559, "ユニバーサルキューブ"),
    #
    "爪": (6507, "混沌の爪"),
    "心臓": (6517, "蛮神の心臓"),
    "逆鱗": (6506, "竜の逆鱗"),
    "根": (6518, "精霊根"),
    "幼角": (6519, "戦馬の幼角"),
    "涙石": (6520, "血の涙石"),
    "脂": (6521, "黒獣脂"),
    "ﾗﾝﾌﾟ": (6523, "封魔のランプ"),
    "ｽｶﾗﾍﾞ": (6525, "智慧のスカラベ"),
    "産毛": (6528, "原初の産毛"),
    "胆石": (6529, "呪獣胆石"),
    "神酒": (6531, "奇奇神酒"),
    "炉心": (6539, "暁光炉心"),
    "鏡": (6540, "九十九鏡"),
    "卵": (6542, "真理の卵"),
    "ｶｹﾗ": (6544, "煌星のカケラ"),
    "実": (6546, "悠久の実"),
    "鬼灯": (6548, "鬼炎鬼灯"),
    "釜": (6558, "黄金釜"),
    "月光": (6560, "月光核"),
    #
    "剣輝": (6001, "剣の輝石"),
    "弓輝": (6002, "弓の輝石"),
    "槍輝": (6003, "槍の輝石"),
    "騎輝": (6004, "騎の輝石"),
    "術輝": (6005, "術の輝石"),
    "殺輝": (6006, "殺の輝石"),
    "狂輝": (6007, "狂の輝石"),
    "剣魔": (6101, "剣の魔石"),
    "弓魔": (6102, "弓の魔石"),
    "槍魔": (6103, "槍の魔石"),
    "騎魔": (6104, "騎の魔石"),
    "術魔": (6105, "術の魔石"),
    "殺魔": (6106, "殺の魔石"),
    "狂魔": (6107, "狂の魔石"),
    "剣秘": (6201, "剣の秘石"),
    "弓秘": (6202, "弓の秘石"),
    "槍秘": (6203, "槍の秘石"),
    "騎秘": (6204, "騎の秘石"),
    "術秘": (6205, "術の秘石"),
    "殺秘": (6206, "殺の秘石"),
    "狂秘": (6207, "狂の秘石"),
    "剣ピ": (7001, "セイバーピース"),
    "弓ピ": (7002, "アーチャーピース"),
    "槍ピ": (7003, "ランサーピース"),
    "騎ピ": (7004, "ライダーピース"),
    "術ピ": (7005, "キャスターピース"),
    "殺ピ": (7006, "アサシンピース"),
    "狂ピ": (7007, "バーサーカーピース"),
    "剣モ": (7101, "セイバーモニュメント"),
    "弓モ": (7102, "アーチャーモニュメント"),
    "槍モ": (7103, "ランサーモニュメント"),
    "騎モ": (7104, "ライダーモニュメント"),
    "術モ": (7105, "キャスターモニュメント"),
    "殺モ": (7106, "アサシンモニュメント"),
    "狂モ": (7107, "バーサーカーモニュメント"),
}
