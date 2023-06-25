from functools import cached_property
from typing import Optional

from app.schemas.base import BaseModelORJson
from app.schemas.basic import BasicServant
from app.schemas.common import Region
from app.schemas.enums import Attribute, NiceSkillType, Trait
from app.schemas.gameenums import NiceBuffAction, NiceCardType
from app.schemas.nice import (
    ExtraPassive,
    NiceBaseFunction,
    NiceBgmEntity,
    NiceBuff,
    NiceClassBoard,
    NiceCommandCode,
    NiceCostume,
    NiceEnemyMaster,
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
    NiceSvtSkillRelease,
    NiceTd,
    NiceWar,
)
from app.schemas.raw import MstCv, MstIllustrator
from pydantic import BaseModel, Field

from ..utils import sort_dict
from .common import (
    NEVER_CLOSED_TIMESTAMP,
    MappingBase,
    MstClass,
    MstClassRelation,
    MstViewEnemy,
)
from .const_data import (
    BuffActionDetail,
    CardInfo,
    ConstGameData,
    GrailCostDetail,
    MasterUserLvDetail,
)
from .drop_data import DropData
from .mappings import MappingData


class ExchangeTicket(BaseModel):
    id: int
    year: int
    month: int
    items: list[int]
    replaced: MappingBase[list[int]] | None = None
    multiplier: int = 1


# TODO: use <phase, <item, num>>
class FixedDrop(BaseModel):
    id: int  # quest phase key
    items: dict[int, int]


class NiceBaseTd(NiceTd):
    svtId: int = Field(0, exclude=True)
    num: int = Field(0, exclude=True)
    npNum: int = Field(1, exclude=True)
    strengthStatus: int = Field(0, exclude=True)
    priority: int = Field(0, exclude=True)
    condQuestId: int = Field(0, exclude=True)
    condQuestPhase: int = Field(0, exclude=True)
    releaseConditions: list[NiceSvtSkillRelease] = Field([], exclude=True)
    # damage
    # card: NiceCardType
    # icon: Optional[HttpUrl]
    # npDistribution: list[int]


class NiceBaseSkill(NiceSkill):
    svtId: int = Field(0, exclude=True)
    num: int = Field(0, exclude=True)
    strengthStatus: int = Field(0, exclude=True)
    priority: int = Field(0, exclude=True)
    condQuestId: int = Field(0, exclude=True)
    condQuestPhase: int = Field(0, exclude=True)
    condLv: int = Field(0, exclude=True)
    condLimitCount: int = Field(0, exclude=True)
    extraPassive: list[ExtraPassive] = Field([], exclude=True)
    releaseConditions: list[NiceSvtSkillRelease] = Field([], exclude=True)


class NiceEquipSort(NiceEquip):
    sortId: float | None = None


class NewAddedData(BaseModelORJson):
    time: str
    svt: list[NiceServant] = []
    ce: list[NiceEquip] = []
    cc: list[NiceCommandCode] = []
    item: list[NiceItem] = []

    def is_empty(self):
        # skip item only changes
        return not self.svt and not self.ce and not self.cc and not self.cc


class MasterData(BaseModelORJson):
    region: Region
    # directly from atlas
    basic_svt: list[BasicServant] = []
    nice_command_code: list[NiceCommandCode] = []
    nice_cv: list[MstCv] = []
    nice_bgm: list[NiceBgmEntity] = []
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
    nice_enemy_master: list[NiceEnemyMaster] = []
    nice_class_board: list[NiceClassBoard] = []
    nice_trait: dict[int, Trait] = {}
    NiceAttributeRelation: dict[Attribute, dict[Attribute, int]] = {}
    NiceBuffList_ActionList: dict[NiceBuffAction, BuffActionDetail] = {}
    NiceCard: dict[NiceCardType, dict[int, CardInfo]] = {}

    # NiceClass: list[NiceClassInfo] = []
    # NiceClassAttackRate: dict[SvtClass, int] = {}
    # NiceClassRelation: dict[SvtClass, dict[SvtClass, int]] = {}
    NiceConstant: dict[str, int] = {}
    NiceSvtGrailCost: dict[int, dict[int, GrailCostDetail]] = {}
    NiceUserLevel: dict[int, MasterUserLvDetail] = {}

    # raw mst data
    mstClass: list[MstClass] = []
    mstClassRelation: list[MstClassRelation] = []
    viewEnemy: list[MstViewEnemy] = []
    mstConstant: dict[str, int] = {}
    mstEnemyMaster: list[dict] = []

    # extra
    # all_quests: dict[int, NiceQuest] = {}
    all_quests_na: dict[int, NiceQuest] = {}  # only saved in jp_data
    cachedQuestPhases: dict[int, Optional[NiceQuestPhase]] = {}
    fixedDrops: dict[int, FixedDrop] = {}
    dropData: DropData = DropData()
    mappingData: MappingData = MappingData()
    exchangeTickets: list[ExchangeTicket] = []
    remainedQuestIds: set[int] = set()
    extraMasterMission: list[NiceMasterMission] = []
    constData: ConstGameData | None = None

    # base
    base_tds: dict[int, NiceBaseTd] = {}
    base_skills: dict[int, NiceBaseSkill] = {}
    base_functions: dict[int, NiceBaseFunction] = {}

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
        self.dropData.fixedDrops = sort_dict(self.dropData.fixedDrops)
        self.dropData.freeDrops = sort_dict(self.dropData.freeDrops)
        self.mappingData.costume_detail = sort_dict(self.mappingData.costume_detail)
        self.mappingData.trait = sort_dict(self.mappingData.trait)
        # self.mappingData.event_trait = sort_dict(self.mappingData.event_trait)
        self.base_tds = sort_dict(self.base_tds)
        self.base_skills = sort_dict(self.base_skills)
        self.base_functions = sort_dict(self.base_functions)

    @cached_property
    def svt_dict(self) -> dict[int, NiceServant]:
        return {x.collectionNo: x for x in self.nice_servant_lore}

    @cached_property
    def svt_id_dict(self) -> dict[int, NiceServant]:
        return {x.id: x for x in self.nice_servant_lore}

    @cached_property
    def basic_svt_dict(self) -> dict[int, BasicServant]:
        return {x.id: x for x in self.basic_svt}

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
    def bgm_dict(self) -> dict[int, NiceBgmEntity]:
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

    def skill_list_no_cache(self):
        # don't include trigger skill, enemy skills
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
        for event in self.nice_event:
            for assist in event.commandAssists:
                skills.append(assist.skill)
        for board in self.nice_class_board:
            for square in board.squares:
                if square.targetSkill:
                    skills.append(square.targetSkill)
                if square.targetCommandSpell:
                    skills.append(
                        NiceSkill(
                            id=-10000 - square.targetCommandSpell.id,
                            name=square.targetCommandSpell.name,
                            originalName=square.targetCommandSpell.name,
                            unmodifiedDetail=square.targetCommandSpell.detail,
                            type=NiceSkillType.active,
                            functions=square.targetCommandSpell.functions,
                        )
                    )
        skills.extend(self.base_skills.values())
        return skills

    @cached_property
    def skill_dict(self) -> dict[int, NiceSkill]:
        assert self.base_skills
        return {skill.id: skill for skill in self.skill_list_no_cache()}

    def td_list_no_cache(self):
        tds: list[NiceTd] = []
        for svt in self.nice_servant_lore:
            for td in svt.noblePhantasms:
                tds.append(td)
        tds.extend(self.base_tds.values())
        return tds

    @cached_property
    def td_dict(self) -> dict[int, NiceTd]:
        return {td.id: td for td in self.td_list_no_cache()}

    def func_list_no_cache(self):
        funcs: list[NiceFunction] = []
        for skill in self.skill_list_no_cache():
            funcs.extend(skill.functions)
        for td in self.td_list_no_cache():
            funcs.extend(td.functions)
        return funcs

    @cached_property
    def func_dict(self) -> dict[int, NiceFunction]:
        return {func.funcId: func for func in self.func_list_no_cache()}

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
    def quest_dict(self) -> dict[int, NiceQuest]:
        """
        Main Story+Event: main+free+svt_quests
        Daily quests: only not closed
        """
        d: dict[int, NiceQuest] = {}
        for war in self.nice_war:
            for spot in war.spots:
                for quest in spot.quests:
                    # if war.id == 9999 and quest.id not in self.remainedQuestIds:
                    #     continue
                    if war.id == 1002 and quest.closedAt < NEVER_CLOSED_TIMESTAMP:
                        continue
                    d[quest.id] = quest
        return d

    @cached_property
    def entity_dict(self) -> dict[int, BasicServant]:
        return {x.id: x for x in self.basic_svt}

    @cached_property
    def view_enemy_names(self):
        d: dict[int, dict[int, str]] = {}
        for enemy in self.viewEnemy:
            d.setdefault(enemy.questId, {}).setdefault(enemy.svtId, enemy.name)
        return d

    @cached_property
    def enemy_master_names(self) -> dict[int, str]:
        return {master["id"]: master["name"] for master in self.mstEnemyMaster}
