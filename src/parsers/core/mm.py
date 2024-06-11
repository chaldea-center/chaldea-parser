import time

from app.schemas.gameenums import NiceGiftType, NiceMissionType

from ...schemas.common import MstMasterMissionWithGift
from ...utils import AtlasApi
from ...utils.helper import parse_json_obj_as
from ...utils.url import DownUrl


def guess_mission_type(mm_id: int) -> NiceMissionType:
    a = mm_id // 100_000
    if a == 1:
        return NiceMissionType.weekly
    elif a == 2:
        return NiceMissionType.limited
    elif a == 3:
        return NiceMissionType.daily
    b = mm_id // 10000
    if b == 8:
        return NiceMissionType.complete
    if mm_id == 10001:
        return NiceMissionType.extra
    return NiceMissionType.none


def load_mm_with_gifts(
    mms_cache: dict[int, MstMasterMissionWithGift]
) -> dict[int, MstMasterMissionWithGift]:
    mms: dict[int, MstMasterMissionWithGift] = dict(mms_cache)

    for mm in parse_json_obj_as(
        list[MstMasterMissionWithGift], DownUrl.gitaa("mstMasterMission")
    ):
        mms[mm.id] = mm
    now = int(time.time())
    for mm in mms.values():
        mm_type = guess_mission_type(mm.id)
        if mm_type in (
            NiceMissionType.daily,
            NiceMissionType.weekly,
            # NiceMissionType.extra,
        ):
            continue
        nice_mm = AtlasApi.master_mission(
            mm.id, expire_after=0 if mm.startedAt <= now <= mm.endedAt else None
        )
        if not nice_mm:
            continue
        gifts: dict[int, int] = {}
        for mission in nice_mm.missions:
            for gift in mission.gifts:
                if gift.type not in (
                    NiceGiftType.item,
                    NiceGiftType.servant,
                    NiceGiftType.commandCode,
                ):
                    continue
                gifts[gift.objectId] = gifts.get(gift.objectId, 0) + gift.num
        gifts = {k: gifts[k] for k in sorted(gifts)}
        mm.gifts = gifts
    return mms
