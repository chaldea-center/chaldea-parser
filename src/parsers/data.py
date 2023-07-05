from app.schemas.common import Region


MIN_APP = "2.4.4"


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
