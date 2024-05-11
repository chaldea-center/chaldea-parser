from typing import Any

from app.schemas.common import NiceTrait
from app.schemas.gameenums import NiceCondType
from app.schemas.nice import (
    AscensionAdd,
    BasicServant,
    BuffScript,
    EnemyDrop,
    EnemyTd,
    ExtraAssets,
    NiceBaseFunction,
    NiceBgm,
    NiceBgmEntity,
    NiceBuff,
    NiceEquip,
    NiceEvent,
    NiceEventCooltimeReward,
    NiceEventDiggingBlock,
    NiceEventLotteryBox,
    NiceEventMission,
    NiceEventMissionCondition,
    NiceEventPointBuff,
    NiceEventReward,
    NiceEventTowerReward,
    NiceEventTreasureBox,
    NiceFunction,
    NiceGift,
    NiceHeelPortrait,
    NiceItem,
    NiceItemAmount,
    NiceItemSelect,
    NiceLore,
    NiceMap,
    NiceMapGimmick,
    NiceMasterMission,
    NiceMysticCode,
    NiceQuest,
    NiceQuestPhase,
    NiceServant,
    NiceShop,
    NiceShopRelease,
    NiceSkill,
    NiceTd,
    NiceTdSvt,
    NiceVoiceLine,
    NiceWar,
    QuestEnemy,
)
from pydantic import BaseModel
from pydantic.json import pydantic_encoder

from ...schemas.gamedata import MasterData, NiceBaseSkill, NiceBaseTd, NiceEquipSort


_excluded_fields: dict[type, list[str]] = {
    BuffScript: [
        "ProgressSelfTurn",
        "ReleaseText",
    ],
    NiceBaseSkill: [
        "svtId",
        "num",
        "strengthStatus",
        "priority",
        "condQuestId",
        "condQuestPhase",
        "condLv",
        "condLimitCount",
        "extraPassive",
        "releaseConditions",
        "detail",
        "groupOverwrites",
    ],
    NiceSkill: [
        "name",
        "originalName",
        "ruby",
        "detail",
        "unmodifiedDetail",
        "type",
        "icon",
        "coolDown",
        "actIndividuality",
        "script",
        "skillAdd",
        "aiIds",
        "groupOverwrites",
        "functions",
        "skillSvts",
    ],
    NiceBaseTd: [
        "svtId",
        "num",
        "npNum",
        "strengthStatus",
        "priority",
        "condQuestId",
        "condQuestPhase",
        "releaseConditions",
        "detail",
    ],
    NiceTd: [
        # "card",
        "name",
        "originalName",
        "ruby",
        # "icon",
        "rank",
        "type",
        "effectFlags",
        "detail",
        "unmodifiedDetail",
        "npGain",
        # "npDistribution",
        "individuality",
        "script",
        "functions",
        "npSvts",
    ],
    NiceTdSvt: ["motion"],
    NiceBgm: ["name", "fileName", "notReleased", "audioAsset"],
    NiceTrait: ["name"],
    NiceGift: ["priority"],
    NiceLore: ["comments", "voices"],
    NiceWar: ["originalLongName", "emptyMessage"],
    NiceMap: [],
    NiceMapGimmick: ["actionAnimTime", "actionEffectId", "startedAt", "endedAt"],
    NiceQuest: ["spotName", "warLongName"],
    NiceQuestPhase: ["spotName", "warLongName", "supportServants"],
    QuestEnemy: ["userSvtId", "uniqueId", "drops", "limit"],
    EnemyDrop: ["dropExpected", "dropVariance"],
    EnemyTd: ["noblePhantasmLv2", "noblePhantasmLv3"],  # noblePhantasmLv1
    NiceEvent: ["voicePlays", "materialOpenedAt"],
    NiceEventMissionCondition: ["missionTargetId", "detail"],
    NiceEventMission: [
        "flag",
        "missionTargetId",
        "detail",
        "startedAt",
        "endedAt",
        "closedAt",
        "rewardRarity",
        "notfyPriority",
        "presentMessageId",
    ],
    NiceEventTreasureBox: ["commonConsume"],
    NiceEventDiggingBlock: ["commonConsume"],
    NiceEventTowerReward: ["boardMessage", "rewardGet", "banner"],
    NiceEventLotteryBox: ["id", "priority", "detail", "icon", "banner"],
    NiceEventReward: ["bgImagePoint", "bgImageGet"],
    NiceEventPointBuff: ["detail"],
    NiceEventCooltimeReward: ["commonRelease"],
    NiceHeelPortrait: ["dispCondType", "dispCondId", "dispCondNum", "script"],
    NiceShop: [
        "baseShopId",
        # "eventId",
        "detail",
        # "openedAt",
        # "closedAt",
        "warningMessage",
        "materialOpenedAt",
    ],
    NiceShopRelease: [
        "isClosedDisp",
        "closedMessage",
        "closedItemName",
    ],
    NiceItemSelect: ["detail"],
    NiceServant: [
        "originalBattleName",
        "className",
        "atkGrowth",
        "hpGrowth",
        "expGrowth",
        "expFeed",
        "hitsDistribution",
    ],
    BasicServant: ["originalOverwriteName", "className"],
    NiceEquip: ["expFeed", "expGrowth", "atkGrowth", "hpGrowth"],
    NiceEquipSort: ["expFeed", "expGrowth", "atkGrowth", "hpGrowth"],
    AscensionAdd: [
        "originalOverWriteServantName",
        "originalOverWriteServantBattleName",
        "originalOverWriteTDName",
        "rarity",  # playable servants always the same except mash
    ],
    NiceMasterMission: ["quests"],
    # NiceMysticCode: ["shortName"],
}

_exclude_empty_fields: dict[type, list[str]] = {
    NiceBuff: ["script"],
    NiceSkill: ["script"],
    NiceBaseSkill: ["script"],
    NiceTd: ["script"],
    NiceBaseTd: ["script"],
    NiceServant: ["script"],
    NiceEquip: ["script"],
}


def common_pydantic_encoder(obj):
    try:
        return pydantic_encoder(obj)
    except TypeError:
        return obj


def _exclude_skill(skill: NiceSkill | NiceTd) -> set[str]:
    keys = [
        "svtId",
        "num",
        "priority",
        "strengthStatus",
        "condQuestId",
        "condQuestPhase",
        "condLv",
        "condLimitCount",
    ]
    excludes = set(key for key in keys if getattr(skill, key, None) in (0, -1))
    conds = getattr(skill, "releaseConditions", None)
    if conds is not None and not conds:
        excludes.add("releaseConditions")
    return excludes


def _trim_func_vals(data: dict[str, Any]):
    first: dict[str, Any] | None = data["svals"][0] if data.get("svals") else None
    if not first:
        return
    for key1 in ["svals", "svals2", "svals3", "svals4", "svals5"]:
        svals: list[dict] | None = data.get(key1)
        if not svals:
            continue
        for index in range(len(svals)):
            if key1 == "svals" and index == 0:
                continue
            val = svals[index]
            new_val = dict()
            for key2 in first.keys():
                v = val.get(key2)
                if first[key2] != v:
                    new_val[key2] = v
            for key2 in val.keys():
                if key2 not in first:
                    new_val[key2] = val[key2]
            svals[index] = new_val


def _clean_dict_empty(d: dict):
    for k in list(d.keys()):
        v = d[k]
        if isinstance(v, dict):
            _clean_dict_empty(v)
        if v is None or v == [] or v == {}:
            d.pop(k)


class DataEncoder:
    def __init__(self, jp_data: MasterData) -> None:
        self.item = False
        self.bgm = False
        self.basic_svt = False

        self.jp_data = jp_data

    def default(self, obj):
        if not isinstance(obj, BaseModel):
            return common_pydantic_encoder(obj)

        _type = type(obj)
        excludes = {"originalName"}
        type_excludes = _excluded_fields.get(_type, [])
        excludes.update(type_excludes)

        if _type in (NiceBgm, NiceBgmEntity) and self.bgm:
            excludes.update(NiceBgmEntity.__fields__.keys())
            excludes.discard("id")
        elif _type == NiceItem and self.item:
            excludes.update(NiceItem.__fields__.keys())
            excludes.discard("id")

        if isinstance(obj, (NiceSkill, NiceTd)):
            excludes.update(_exclude_skill(obj))
            if _type == NiceSkill and isinstance(obj, NiceSkill):
                self._save_basic_skill(excludes, obj)
            elif _type == NiceTd and isinstance(obj, NiceTd):
                self._save_basic_td(excludes, obj)
        if _type == NiceFunction and isinstance(obj, NiceFunction):
            self._save_basic_func(excludes, obj)
        elif isinstance(obj, NiceItemAmount):
            return {"itemId": obj.item.id, "amount": obj.amount}
        elif isinstance(obj, (ExtraAssets, AscensionAdd)):
            obj = obj.dict(exclude_none=True, exclude_defaults=True, exclude=excludes)
            _clean_dict_empty(obj)
        elif isinstance(obj, NiceVoiceLine):
            if not "".join(obj.text):
                excludes.add("text")
            if not [x for x in obj.form if x != 0]:
                excludes.add("form")
        elif isinstance(obj, NiceBuff):
            for key in type_excludes:
                setattr(obj.script, key, None)
            obj.originalScript.pop("relationOverwrite", None)
        elif isinstance(obj, NiceQuest):
            if isinstance(obj, NiceQuestPhase):
                if len(obj.availableEnemyHashes) > 100:
                    hashes = obj.availableEnemyHashes[-100:]
                    if obj.enemyHash and obj.enemyHash not in hashes:
                        hashes.append(obj.enemyHash)
                    obj.availableEnemyHashes = hashes
            else:
                if obj.warId == 1002:
                    obj.releaseOverwrites = [
                        release
                        for release in obj.releaseOverwrites
                        if not (
                            release.eventId == 0
                            and release.condType == NiceCondType.weekdays
                        )
                    ]
        elif isinstance(obj, BasicServant):
            self._save_basic_svt(excludes, obj)

        if isinstance(obj, BaseModel):
            if isinstance(obj, NiceFunction):
                data = dict(
                    obj._iter(
                        to_dict=True,
                        exclude_none=True,
                        exclude_defaults=True,
                        exclude=excludes,
                    )
                )
                _trim_func_vals(data)
            else:
                data = dict(
                    obj._iter(
                        to_dict=False,
                        exclude_none=True,
                        exclude_defaults=True,
                        exclude=excludes,
                    )
                )
            data = {k: self.default(v) for k, v in data.items()}
            for field in _exclude_empty_fields.get(_type, []):
                if field in data and (data[field] == {} or data[field] == []):
                    data.pop(field)
            return data
        elif isinstance(obj, (list, dict)):
            return obj
        return common_pydantic_encoder(obj)

    def _save_basic_skill(self, excludes: set[str], skill: NiceSkill):
        if skill.id not in self.jp_data.base_skills:
            skill = NiceBaseSkill.parse_obj(skill.dict(exclude_none=True))
            self.jp_data.base_skills[skill.id] = skill
        if skill.ruby in ("", "-"):
            excludes.add("ruby")

    def _save_basic_td(self, excludes: set[str], skill: NiceTd):
        if skill.id not in self.jp_data.base_tds:
            td = NiceBaseTd.parse_obj(skill.dict(exclude_none=True))
            self.jp_data.base_tds[skill.id] = td
        base_td = self.jp_data.base_tds[skill.id]
        for key in ["card", "icon", "npDistribution"]:
            if getattr(skill, key, None) == getattr(base_td, key, None):
                excludes.add(key)
        if skill.ruby in ("", "-"):
            excludes.add("ruby")

    def _save_basic_func(self, excludes: set[str], func: NiceFunction):
        if func.funcId not in self.jp_data.base_functions:
            self.jp_data.base_functions[func.funcId] = NiceBaseFunction.parse_obj(
                func.dict()
            )
        excludes.update(NiceBaseFunction.__fields__.keys())
        excludes.remove("funcId")

    def _save_basic_svt(self, excludes: set[str], svt: BasicServant):
        if not self.basic_svt:
            return
        db_svt = self.jp_data.basic_svt_dict.get(svt.id)
        if not db_svt:
            return
        excludes.update(BasicServant.__fields__.keys())
        excludes.remove("id")
        # atkMax, hpMax
        for key in ("classId", "attribute", "face", "rarity"):
            if getattr(db_svt, key) != getattr(svt, key):
                excludes.discard(key)
