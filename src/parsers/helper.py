from app.schemas.gameenums import NiceQuestType
from app.schemas.nice import NiceFunction, NiceQuest


def is_quest_in_expired_wars(quest: NiceQuest, wars: list[int]):
    if not wars:
        return False
    if quest.warId in wars:
        return True
    if quest.type == NiceQuestType.friendship and -1 in wars:
        return True
    return False


def get_all_func_val(func: NiceFunction, val_key: str):
    vals = (
        func.svals
        + (func.svals2 or [])
        + (func.svals3 or [])
        + (func.svals4 or [])
        + (func.svals5 or [])
    )
    return set(getattr(val, val_key) for val in vals)
