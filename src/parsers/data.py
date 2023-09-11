import re

from app.schemas.common import Region


MIN_APP = "2.4.11"


# cn_ces: dict[int, tuple[str, float]] = {102022: ("STAR影法師", 1461.5)}
ADD_CES = {
    Region.TW: {
        # 6th anniversary, same id with CN 102022, put if before CN
        302023: ("リヨ", 1466.1),
    },
    Region.CN: {
        102019: ("STAR影法師", 1526.1),  # 3rd
        102020: ("STAR影法師", 1526.2),  # 4th
        102021: ("STAR影法師", 1526.3),  # 5th
        102022: ("STAR影法師", 1526.4),  # 6th anniversary
    },
}

# svt_no, questIds
STORY_UPGRADE_QUESTS = {
    1: [1000624, 3000124, 3000607, 3001301, 1000631],
    38: [3000915],  # Cú Chulainn
}


EXTRA_CAMPAIGN_CE_MC_DATA = {
    102022: {
        "id": "102022",
        "name": "简中版6周年纪念",
        "name_link": "简中版6周年纪念",
        "des": "支援中获得的友情点＋10(可以重复)",
        "type": "纪念",
    },
    102023: {
        "id": "102023",
        "name": "简中版3周年纪念",
        "name_link": "简中版3周年纪念",
        "type": "纪念",
    },
    102024: {
        "id": "102024",
        "name": "简中版4周年纪念",
        "name_link": "简中版4周年纪念",
        "type": "纪念",
    },
    102025: {
        "id": "102025",
        "name": "简中版5周年纪念",
        "name_link": "简中版5周年纪念",
        "type": "纪念",
    },
}

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
    # item
    "祸骨": "凶骨",
}


EXCLUDE_REWARD_QUESTS = [
    1000825,  # 终局特异点 section 12
    3000540,  # Atlantis section 18
    94040905,  # Battle In NewYork 2019
    94067707,  # Battle In NewYork 2022 > 2019 rerun story
]
