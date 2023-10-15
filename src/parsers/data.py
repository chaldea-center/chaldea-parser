import re

from app.schemas.common import Region


MIN_APP = "2.4.17"


ADD_CES: dict[Region, dict[int, tuple[str, float]]] = {
    # 2017.11
    Region.KR: {
        202022: ("ダンミル", 1269.1),  # 5th 90082001
    },
    # 2017.06
    Region.NA: {
        402023: ("Namie", 1466.2),  # 6th 90084001
    },
    # 2017.05
    Region.TW: {
        # 6th anniversary, same id with CN 102022, put if before CN
        302023: ("リヨ", 1466.1),  # 6th 90086001
    },
    # 2016.08 (2016.09)
    Region.CN: {
        102019: ("STAR影法師", 1458.1),  # 3rd 90086002
        102020: ("STAR影法師", 1458.2),  # 4th 90086003
        102021: ("STAR影法師", 1458.3),  # 5th 90086004
        102022: ("STAR影法師", 1458.4),  # 6th 90086001
        102023: ("STAR影法師", 1458.4),  # 7th 90086005
    },
}

EXTRA_CAMPAIGN_CE_MC_DATA = {
    102019: {
        "id": "102019",
        "name": "简中版3周年纪念",
        "name_link": "简中版3周年纪念",
        "type": "纪念",
    },
    102020: {
        "id": "102020",
        "name": "简中版4周年纪念",
        "name_link": "简中版4周年纪念",
        "type": "纪念",
    },
    102021: {
        "id": "102021",
        "name": "简中版5周年纪念",
        "name_link": "简中版5周年纪念",
        "type": "纪念",
    },
    102022: {
        "id": "102022",
        "name": "简中版6周年纪念",
        "name_link": "简中版6周年纪念",
        "des": "支援中获得的友情点＋10(可以重复)",
        "type": "纪念",
    },
    102023: {
        "id": "102023",
        "name": "简中版7周年纪念",
        "name_link": "简中版7周年纪念",
        "des": "支援中获得的友情点＋10(可以重复)",
        "type": "纪念",
    },
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


jp_chars = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")


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

# fmt: off
LAPLACE_UPLOAD_ALLOW_AI_QUESTS = [
    # Tunguska
    94065101, 94065102, 94065103, 94065104, 94065105, 94065106,
    94065112, 94065108, 94065113, 94065123, 94065115, 94065107,
    94065119, 94065110, 94065114, 94065118, 94065116, 94065122,
    94065117, 94065124, 94065125, 94065111, 94065121, 94065109,
    94065120, 94065126, 94065127, 94065128, 94065129,
]
# fmt: on


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
]

FREE_EXCHANGE_SVT_EVENTS = [
    80450,  # 109, 3000日突破記念
    80374,  # 68, 2500万DL突破纪念活动
    80288,  # 25, 2000万DL突破活动
    80265,  # 60, 1800万下载突破纪念活动
    80220,  # 54, 1500万DL突破纪念活动
    80068,  # 42, 1000万下载突破纪念活动
]
