from functools import cached_property
from typing import Optional

from app.schemas.base import BaseModelORJson
from app.schemas.basic import BasicServant
from app.schemas.common import Region
from app.schemas.enums import Attribute, SvtClass, Trait
from app.schemas.gameenums import NiceBuffAction, NiceCardType
from app.schemas.nice import (
    NiceBgm,
    NiceBuff,
    NiceCommandCode,
    NiceCostume,
    NiceEquip,
    NiceEvent,
    NiceFunction,
    NiceItem,
    NiceMasterMission,
    NiceMysticCode,
    NiceQuest,
    NiceQuestPhase,
    NiceServant,
    NiceSkill,
    NiceSpot,
    NiceTd,
    NiceWar,
)
from app.schemas.raw import MstCv, MstIllustrator
from pydantic import BaseModel

from ..utils import sort_dict
from .const_data import BuffActionDetail, CardInfo, GrailCostDetail, MasterUserLvDetail
from .mappings import MappingData


class ExchangeTicket(BaseModel):
    id: int
    year: int
    month: int
    items: list[int]


class FixedDrop(BaseModel):
    id: int  # quest phase key
    items: dict[int, int]


class MasterData(BaseModelORJson):
    region: Region
    # directly from atlas
    basic_svt: list[BasicServant] = []
    nice_command_code: list[NiceCommandCode] = []
    nice_cv: list[MstCv] = []
    nice_bgm: list[NiceBgm] = []
    nice_enums: dict[str, dict[int, str]] = {}
    # nice_equip: list[NiceEquip]=[]
    nice_equip_lore: list[NiceEquip] = []
    nice_illustrator: list[MstIllustrator] = []
    nice_item: list[NiceItem] = []
    nice_master_mission: list[NiceMasterMission] = []
    nice_mystic_code: list[NiceMysticCode] = []
    # nice_servant: list[NiceServant]
    nice_servant_lore: list[NiceServant] = []
    nice_war: list[NiceWar] = []
    nice_event: list[NiceEvent] = []
    nice_trait: dict[int, Trait] = {}
    NiceAttributeRelation: dict[Attribute, dict[Attribute, int]] = {}
    NiceBuffList_ActionList: dict[NiceBuffAction, BuffActionDetail] = {}
    NiceCard: dict[NiceCardType, dict[int, CardInfo]] = {}
    NiceClassAttackRate: dict[SvtClass, int] = {}
    NiceClassRelation: dict[SvtClass, dict[SvtClass, int]] = {}
    NiceConstant: dict[str, int] = {}
    NiceSvtGrailCost: dict[int, dict[int, GrailCostDetail]] = {}
    NiceUserLevel: dict[int, MasterUserLvDetail] = {}

    # extra
    cachedQuests: dict[int, NiceQuest] = {}
    cachedQuestsNA: dict[int, NiceQuest] = {}
    cachedQuestPhases: dict[int, Optional[NiceQuestPhase]] = {}
    fixedDrops: dict[int, FixedDrop] = {}
    mappingData: MappingData = MappingData()
    exchangeTickets: list[ExchangeTicket] = []

    class Config:
        keep_untouched = (cached_property,)

    def sort(self):
        self.nice_command_code.sort(key=lambda x: x.collectionNo)
        self.nice_equip_lore.sort(key=lambda x: x.collectionNo)
        self.nice_mystic_code.sort(key=lambda x: x.id)
        self.nice_servant_lore.sort(key=lambda x: x.collectionNo)
        self.nice_war.sort(key=lambda x: x.id)
        self.nice_event.sort(key=lambda x: x.startedAt)
        self.nice_item.sort(key=lambda x: x.priority)
        phases = [v for v in self.cachedQuestPhases.values() if v]
        phases.sort(key=lambda x: x.id * 100 + x.phase)
        self.cachedQuestPhases = {x.id * 100 + x.phase: x for x in phases}
        self.fixedDrops = sort_dict(self.fixedDrops)
        self.mappingData.costume_detail = sort_dict(self.mappingData.costume_detail)
        self.mappingData.trait = sort_dict(self.mappingData.trait)

    @cached_property
    def svt_dict(self) -> dict[int, NiceServant]:
        return {x.collectionNo: x for x in self.nice_servant_lore}

    @cached_property
    def svt_id_dict(self) -> dict[int, NiceServant]:
        return {x.id: x for x in self.nice_servant_lore}

    @cached_property
    def costume_dict(self) -> dict[int, NiceCostume]:
        d = {}
        for svt in self.nice_servant_lore:
            if svt.profile:
                d.update(svt.profile.costume)
        return d

    @cached_property
    def ce_dict(self) -> dict[int, NiceEquip]:
        return {x.collectionNo: x for x in self.nice_equip_lore}

    @cached_property
    def ce_id_dict(self) -> dict[int, NiceEquip]:
        return {x.id: x for x in self.nice_equip_lore}

    @cached_property
    def cc_dict(self) -> dict[int, NiceCommandCode]:
        return {x.collectionNo: x for x in self.nice_command_code}

    @cached_property
    def cc_id_dict(self) -> dict[int, NiceCommandCode]:
        return {x.id: x for x in self.nice_command_code}

    @cached_property
    def mc_dict(self) -> dict[int, NiceMysticCode]:
        return {x.id: x for x in self.nice_mystic_code}

    @cached_property
    def cv_dict(self) -> dict[int, MstCv]:
        return {x.id: x for x in self.nice_cv}

    @cached_property
    def illustrator_dict(self) -> dict[int, MstIllustrator]:
        return {x.id: x for x in self.nice_illustrator}

    @cached_property
    def bgm_dict(self) -> dict[int, NiceBgm]:
        return {x.id: x for x in self.nice_bgm}

    @cached_property
    def item_dict(self) -> dict[int, NiceItem]:
        return {x.id: x for x in self.nice_item}

    @cached_property
    def event_dict(self) -> dict[int, NiceEvent]:
        return {x.id: x for x in self.nice_event}

    @cached_property
    def war_dict(self) -> dict[int, NiceWar]:
        return {x.id: x for x in self.nice_war}

    @cached_property
    def skill_dict(self) -> dict[int, NiceSkill]:
        d: dict[int, NiceSkill] = {}
        skills: list[NiceSkill] = []
        for svt in self.nice_servant_lore:
            skills.extend(svt.skills)
            skills.extend(svt.classPassive)
            skills.extend(svt.extraPassive)
            for append_passive in svt.appendPassive:
                skills.append(append_passive.skill)
        for ce in self.nice_equip_lore:
            skills.extend(ce.skills)
        for cc in self.nice_command_code:
            skills.extend(cc.skills)
        for mc in self.nice_mystic_code:
            skills.extend(mc.skills)
        for skill in skills:
            d[skill.id] = skill
        return d

    @cached_property
    def td_dict(self) -> dict[int, NiceTd]:
        d: dict[int, NiceTd] = {}
        for svt in self.nice_servant_lore:
            for td in svt.noblePhantasms:
                d[td.id] = td
        return d

    @cached_property
    def func_dict(self) -> dict[int, NiceFunction]:
        d: dict[int, NiceFunction] = {}
        for skill in self.skill_dict.values():
            for func in skill.functions:
                d[func.funcId] = func
        for td in self.td_dict.values():
            for func in td.functions:
                d[func.funcId] = func
        return d

    @cached_property
    def buff_dict(self) -> dict[int, NiceBuff]:
        d: dict[int, NiceBuff] = {}
        for func in self.func_dict.values():
            for buff in func.buffs:
                d[buff.id] = buff
        return d

    @cached_property
    def spot_dict(self) -> dict[int, NiceSpot]:
        d: dict[int, NiceSpot] = {}
        for war in self.nice_war:
            for spot in war.spots:
                d[spot.id] = spot
        return d

    @cached_property
    def main_free_quest_dict(self) -> dict[int, NiceQuest]:
        """
        Main Story: main+free+svt_quests
        Event: free only
        """
        d: dict[int, NiceQuest] = {}
        for war in self.nice_war:
            for spot in war.spots:
                for quest in spot.quests:
                    if (
                        war.id < 999
                        or war.id in (1001, 1003)
                        or (war.id == 1002 and quest.closedAt > 1893420000)
                    ):
                        d[quest.id] = quest
        return d

    @cached_property
    def entity_dict(self) -> dict[int, BasicServant]:
        return {x.id: x for x in self.basic_svt}
