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
