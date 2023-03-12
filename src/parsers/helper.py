from app.schemas.gameenums import NiceQuestType
from app.schemas.nice import NiceQuest


def is_quest_in_expired_wars(quest: NiceQuest, wars: list[int]):
    if not wars:
        return False
    if quest.warId in wars:
        return True
    if quest.type == NiceQuestType.friendship and -1 in wars:
        return True
    return False
