import re

from app.schemas.common import Region
from pydantic import BaseModel

from .common import SvtLimitHide


MIN_APP = "2.5.9"


class ConstDataConfig(BaseModel):
    autoLoginMinVerJp: str = "999.999.999"
    autoLoginMinVerNa: str = "2.5.5"


ADD_CES: dict[Region, dict[int, tuple[str | None,]]] = {
    # 2017.11
    Region.KR: {
        202022: ("ダンミル",),  # 5th 90082001
        202023: ("リヨ",),  # 6th 90082002
    },
    # 2017.06
    Region.NA: {
        402020: (None,),  # 3th 90084002
        402021: (None,),  # 4th 90084003
        402022: (None,),  # 5th 90084004
        402023: (None,),  # 6th 90084001
        402024: (None,),  # 7th 90084005
    },
    # 2017.05
    Region.TW: {
        # 6th anniversary, same id with CN 102022, put if before CN
        302023: ("リヨ",),  # 6th 90086001
        302024: ("VOFAN",),  # 7th 90087002
    },
    # 2016.08 (2016.09)
    Region.CN: {
        102019: ("STAR影法師",),  # 3rd 90086002
        102020: ("STAR影法師",),  # 4th 90086003
        102021: ("STAR影法師",),  # 5th 90086004
        102022: ("STAR影法師",),  # 6th 90086001
        102023: ("STAR影法師",),  # 7th 90086005
        102024: ("白浜鴎",),  # 2024 FES 90086006
        102025: ("STAR影法師",),  # 8th 90086007
    },
}

# Laplace - skip skills/tds
SVT_LIMIT_HIDES: dict[int, list[SvtLimitHide]] = {
    -1: [
        SvtLimitHide(
            limits=[-1],
            addPassives=[
                # fmt:off
                # Valentine 2023 NP300, Fate 20th
                940274, 940321,
                # 巡霊の祝祭
                940284, 940285, 940289, 940298, 940302, 940308,
                #  終局特異点
                960502, 960503, 960504, 960505, 960506, 960507,
                # fmt:on
            ],
        )
    ],
    800100: [
        SvtLimitHide(
            limits=[0, 1, 2, 3, 4, 11, 800130, 14, 800160, 15, 800170],
            tds=[800105, 800106],
            activeSkills={1: [459550, 744450], 2: [460250], 3: [457000, 2162350]},
        ),
        SvtLimitHide(
            limits=[12, 800140, 13, 800150],
            # 02 not in nice data, 03 not exist
            tds=[800100, 800101, 800104, 800102],
            activeSkills={1: [1000, 236000], 2: [2000], 3: [133000]},
        ),
    ],
    304800: [
        SvtLimitHide(
            limits=[0, 1, 2, 11, 304830, 12, 304840],
            tds=[304802],
            activeSkills={3: [888575]},
        ),
        SvtLimitHide(
            limits=[3, 4, 13, 304850],
            tds=[304801],
            activeSkills={3: [888550]},
        ),
    ],
    205000: [
        SvtLimitHide(
            limits=[0, 1, 2],
            tds=[205002],
            activeSkills={3: [2281675]},
        ),
        SvtLimitHide(
            limits=[3, 4],
            tds=[205001],
            activeSkills={3: [2281650]},
        ),
    ],
    106000: [
        SvtLimitHide(
            limits=[-1],
            tds=[106099],
        )
    ],
}


# svt_no, questIds
STORY_UPGRADE_QUESTS = {
    1: [1000624, 3000124, 3000607, 3001301, 1000631],
    38: [3000915],  # Cú Chulainn
}

# Ordeal Call quests, radom enemy
# Need to update it if enemy trait changed, such as "Seven-Knight Servant"
MAIN_FREE_ENEMY_HASH = {
    93040105: "1_0649_51e792f",
    94089602: "1_0607_ca2dbef",
}


RANDOM_ENEMY_QUESTS = [
    # Ordeal Call
    93040105,  # オセアニア北部エリア
    94089602,  # アメリカ南部エリア
]


# u30fb: "・"
jp_chars = re.compile(r"[\u3040-\u309f\u30a0-\u30fa\u30fc-\u30ff]")


# <eventId, <buffGroupId, skillNum>>
EVENT_POINT_BUFF_GROUP_SKILL_NUM_MAP = {
    # summer 2023
    80442: {
        8044203: 2,
        8044202: 3,
        8044204: 4,
        8044205: 5,
        8044201: 6,
        8044206: 7,
    },
}

# Update api worker too
LAPLACE_UPLOAD_ALLOW_AI_QUESTS: list[int] = [
    *range(94065101, 94065129 + 1),  # Tunguska
    *range(94090301, 94090330 + 1),  # Gudaguda2023
]


DESTINY_ORDER_SUMMONS = ["2023_8th_destiny", "50021851", "2024_9th_destiny"]

CN_REPLACE = {
    "西行者": "玄奘三藏",
    "匕见": "荆轲",
    "虎狼": "吕布",
    "歌果": "美杜莎",
    "雾都弃子": "开膛手杰克",
    "莲偶": "哪吒",
    "周照": "武则天",
    "瞑生院": "杀生院",
    "重瞳": "项羽",
    "忠贞": "秦良玉",
    "祖政": "始皇帝",
    "雏罂": "虞美人",
    "丹驹": "赤兔马",
    "琰女": "杨贵妃",
    "爱迪·萨奇": "爱德华·蒂奇",
    "萨奇": "蒂奇",
    "方巿": "徐福",
    "吾绰": "呼延灼",
    "晋帝": "司马懿",
    # item
    "祸骨": "凶骨",
}


EXCLUDE_REWARD_QUESTS = [
    1000825,  # 终局特异点 section 12
    3000540,  # Atlantis section 18
    94040905,  # Battle In NewYork 2019
    94067707,  # Battle In NewYork 2022 > 2019 rerun story
    94077706,  # カルデア妖精騎士杯
    94087053,
    94087054,
    94087055,
    94087056,
    94087057,
    94087058,
    94087059,  # 【聖杯戦線 ～白天の城、黒夜の城～】night war bard
]

FREE_EXCHANGE_SVT_EVENTS = [
    80450,  # 109, 3000日突破記念
    80374,  # 68, 2500万DL突破纪念活动
    80288,  # 25, 2000万DL突破活动
    80265,  # 60, 1800万下载突破纪念活动
    80220,  # 54, 1500万DL突破纪念活动
    80068,  # 42, 1000万下载突破纪念活动
]

# skip some old events without battle data
GUARANTEED_RARE_COPY_ENEMY_WARS = [
    # copy
    9033,  # ぐだぐだ帝都聖杯奇譚
    9057,  # 復刻:ぐだぐだ帝都聖杯奇譚
    9109,  # 鎌倉
    9125,  # ハロウィン・ライジング ～砂塵の女王と暗黒の使徒～
    # rare
    9058,  # レディ・ライネスの事件簿
    9130,  # 復刻版:レディ・ライネスの事件簿
    9071,  # ラスベガス
    9087,  # 復刻:ラスベガス
    9091,  # サーヴァント・サマーキャンプ！ ～カルデア・スリラーナイト～
    9113,  # 復刻:サーヴァント・サマーキャンプ！
    9166,  # 魔法使いの夜
]


SVT_FACE_LIMITS: dict[int, list[int]] = {
    9935510: [1],  # ゲーティア
    9936700: [1],  # アルトリア・ペンドラゴン
    9936701: [1],  # アルトリア・ペンドラゴン
    9936870: [1],  # イリヤスフィール
    9936880: [1],  # クロエ・フォン・アインツベルン
    9936960: [1],  # 佐々木小次郎
    9936980: [3],  # エミヤ
    9936990: [2],  # 天草四郎
    9937000: [1],  # アルトリア・ペンドラゴン〔オルタ〕
    9937120: [1],  # エルキドゥ
    9937200: [1],  # 牛若丸
    9938960: [1],  # 真田エミ村
    9938980: [1],  # スーパー土方
    9939010: [1],  # 新宿のアーチャー
    9939020: [1],  # 新宿のアーチャー
    9939150: [2],  # 殺生院キアラ
    9939160: [1],  # パッションリップ
    9939360: [1],  # ダユー
    9939370: [1],  # メガロス
    9939570: [1],  # メイヴ監獄長
    9939580: [1],  # ネロ・クラウディウス
    9939690: [4],  # 宝蔵院胤舜
    9939700: [2],  # 酒呑童子
    9939710: [2],  # 源頼光
    9940370: [1],  # 黒聖杯
    9940380: [1],  # 火のアイリ
    9940390: [1],  # 水のアイリ
    9940400: [1],  # 風のアイリ
    9940410: [1],  # 土のアイリ
    9940530: [1],  # 茨木童子
    9940600: [1],  # 丑御前
    9941050: [4],  # アビゲイル・ウィリアムズ
    9941170: [3],  # アナスタシア
    9941180: [4],  # シグルド
    9941400: [1],  # ＢＢ
    9941540: [1],  # 始皇帝
    9941670: [1],  # ブラック・ケツァルマスク
    9941700: [1],  # おんせん魔猿
    9941710: [1],  # がんたん魔猿
    9941720: [1],  # ふろしき魔猿
    9941750: [1],  # 衛士長
    9941880: [1],  # カーマ
    9941900: [1],  # 哪吒
    9942010: [1],  # ウィリアム・シェイクスピア
    9942080: [1],  # アルジュナ〔オルタ〕
    9942150: [1],  # 宮本武蔵
    9942250: [1],  # キリシュタリア
    9942410: [1],  # タマモキャット
    9942510: [1],  # カリギュラ
    9943090: [1],  # アルトリア・キャスター
    9943220: [1],  # パーシヴァル
    9943280: [1],  # パーシヴァル
    9943320: [0],  # 妖精騎士ランスロット
    9943330: [2],  # メリュジーヌ
    9943410: [1],  # カーマ
    9943850: [1],  # ドン・キホーテ
    9943860: [1],  # 張角
    9943880: [1],  # ジェームズ・モリアーティ
    9944220: [2],  # 千利休
    9944690: [2],  # ソドムズビースト／ドラコー
    9944970: [1],  # ドライノッブ
    9944820: [1],  # メドゥーサ
    9945349: [2],  # 上杉謙信
    9945430: [1],  # アレッサンドロ・ディ・カリオストロ
    9945710: [1],  # カルナ
    9945740: [1],  # テノチティトラン
    9945760: [1],  # 謎のヒロインXX〔オルタ〕
    9945340: [2],  # 上杉謙信
    9945700: [1],  # ＢＢドバイ
}
