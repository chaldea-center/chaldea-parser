from enum import StrEnum
from typing import Any, Type

from app.schemas.enums import (
    AI_ACT_NUM_NAME,
    AI_TIMING_NAME,
    Attribute,
    ServantPersonality,
    ServantPolicy,
)
from app.schemas.gameenums import (
    NiceAiActTarget,
    NiceAiActType,
    NiceBuffType,
    NiceCombineAdjustTarget,
    NiceEventType,
    NiceEventWorkType,
    NiceFuncTargetType,
    NiceFuncType,
    NiceGender,
    NiceMissionProgressType,
    NiceMissionType,
    NicePurchaseType,
    NiceRestrictionType,
    NiceShopType,
    NiceSvtType,
    NiceSvtVoiceType,
    NiceTdEffectFlag,
)
from pydantic import BaseModel

from .common import (
    CEObtain,
    CustomMissionType,
    ItemCategory,
    MappingBase,
    MappingInt,
    MappingStr,
    SummonType,
    SvtObtain,
)


class EventTrait(MappingStr):
    eventId: int = 0


class FieldTrait(MappingStr):
    warIds: list[int] = []


class SvtClassMapping(MappingStr):
    name: str | None = None


class EnumMapping(BaseModel):
    svt_class: dict[int, SvtClassMapping] = {}
    attribute: dict[Attribute, MappingStr] = {}
    svt_type: dict[NiceSvtType, MappingStr] = {}
    servant_policy: dict[ServantPolicy, MappingStr] = {}
    servant_personality: dict[ServantPersonality, MappingStr] = {}
    gender: dict[NiceGender, MappingStr] = {}
    func_target_type: dict[NiceFuncTargetType, MappingStr] = {}
    mission_progress_type: dict[NiceMissionProgressType, MappingStr] = {}
    mission_type: dict[NiceMissionType, MappingStr] = {}
    td_effect_flag: dict[NiceTdEffectFlag, MappingStr] = {}
    event_type: dict[NiceEventType, MappingStr] = {}
    combine_adjust_target: dict[NiceCombineAdjustTarget, MappingStr] = {}
    event_work_type: dict[NiceEventWorkType, MappingStr] = {}
    shop_type: dict[NiceShopType, MappingStr] = {}
    purchase_type: dict[NicePurchaseType, MappingStr] = {}
    restriction_type: dict[NiceRestrictionType, MappingStr] = {}
    # ai
    ai_act_num: dict[int, MappingStr] = {}
    ai_timing: dict[int, MappingStr] = {}
    ai_act_type: dict[NiceAiActType, MappingStr] = {}
    ai_act_target: dict[NiceAiActTarget, MappingStr] = {}

    # wiki
    svt_obtain: dict[SvtObtain, MappingStr] = {}
    ce_obtain: dict[CEObtain, MappingStr] = {}
    item_category: dict[ItemCategory, MappingStr] = {}
    custom_mission_type: dict[CustomMissionType, MappingStr] = {}
    summon_type: dict[SummonType, MappingStr] = {}
    effect_type: dict[str, MappingStr] = {}  # custom
    # long dict
    func_type: dict[NiceFuncType, MappingStr] = {}
    buff_type: dict[str, MappingStr] = {}  # NiceBuffType, similar with BuffAction
    svt_voice_type: dict[NiceSvtVoiceType, MappingStr] = {}

    def update_enums(self):
        enum_fields: dict[Type[StrEnum], dict[Any, MappingStr]] = {
            Attribute: self.attribute,
            NiceSvtType: self.svt_type,
            ServantPolicy: self.servant_policy,
            ServantPersonality: self.servant_personality,
            NiceGender: self.gender,
            NiceFuncTargetType: self.func_target_type,
            NiceMissionProgressType: self.mission_progress_type,
            NiceMissionType: self.mission_type,
            NiceTdEffectFlag: self.td_effect_flag,
            NiceEventType: self.event_type,
            NiceEventWorkType: self.event_work_type,
            NiceShopType: self.shop_type,
            NicePurchaseType: self.purchase_type,
            NiceRestrictionType: self.restriction_type,
            NiceCombineAdjustTarget: self.combine_adjust_target,
            NiceAiActType: self.ai_act_type,
            NiceAiActTarget: self.ai_act_target,
            SvtObtain: self.svt_obtain,
            CEObtain: self.ce_obtain,
            ItemCategory: self.item_category,
            CustomMissionType: self.custom_mission_type,
            SummonType: self.summon_type,
            # effect_type
            NiceFuncType: self.func_type,
            # NiceBuffType: self.buff_type,
            NiceSvtVoiceType: self.svt_voice_type,
        }
        for k, v in enum_fields.items():
            for kk in k.__members__.values():
                v.setdefault(kk, MappingBase())

        _deprecated_buff_types = {
            "commandattackFunction": "commandattackAfterFunction",
            "upDefencecommanDamage": "upDefenceCommanddamage",
            "downDefencecommanDamage": "downDefenceCommanddamage",
            "attackFunction": "attackAfterFunction",
            "commandcodeattackFunction": "commandcodeattackBeforeFunction",
        }
        for kk in NiceBuffType:
            key = kk.value
            vv = self.buff_type.setdefault(key, MappingBase())
            if key in _deprecated_buff_types:
                key2 = _deprecated_buff_types[key]
                vv2 = self.buff_type.setdefault(key2, MappingBase())
                vv2.update_from(vv)

        for act_num in AI_ACT_NUM_NAME.keys():
            act_num_enum = AI_ACT_NUM_NAME.get(act_num)
            self.ai_act_num.setdefault(
                act_num, MappingStr(NA=act_num_enum.value if act_num_enum else None)
            )
        for timing in AI_TIMING_NAME.keys():
            timing_enum = AI_TIMING_NAME.get(timing)
            self.ai_timing.setdefault(
                timing, MappingStr(NA=timing_enum.value if timing_enum else None)
            )


class MappingData(BaseModel):
    item_names: dict[str, MappingStr] = {}  # jp_name
    # item_detail: dict[int, MappingStr] = {}  # item.id
    mc_names: dict[str, MappingStr] = {}
    costume_names: dict[str, MappingStr] = {}  # collection id, including shortname
    cv_names: dict[str, MappingStr] = {}
    illustrator_names: dict[str, MappingStr] = {}
    cc_names: dict[str, MappingStr] = {}
    svt_names: dict[str, MappingStr] = {}  # svt.id
    ce_names: dict[str, MappingStr] = {}
    event_names: dict[str, MappingStr] = {}  # including shortname
    war_names: dict[str, MappingStr] = {}  # including longname
    quest_names: dict[str, MappingStr] = {}
    spot_names: dict[str, MappingStr] = {}
    entity_names: dict[str, MappingStr] = {}  # only for QuestEnemy.svt.collectionNo==0
    td_types: dict[str, MappingStr] = {}  # jp->
    bgm_names: dict[str, MappingStr] = {}
    chara_names: dict[str, MappingStr] = {}

    buff_names: dict[str, MappingStr] = {}
    buff_detail: dict[str, MappingStr] = {}
    func_popuptext: dict[str, MappingStr] = {}
    skill_names: dict[str, MappingStr] = {}
    # skill_ruby: dict[int, MappingStr] = {}
    skill_detail: dict[str, MappingStr] = {}
    td_names: dict[str, MappingStr] = {}
    td_ruby: dict[str, MappingStr] = {}
    td_detail: dict[str, MappingStr] = {}
    voice_line_names: dict[str, MappingStr] = {}

    trait: dict[int, MappingStr] = {}  # trait.id
    # trait_redirect: dict[int, int] = {}  # event_trait -> normal trait
    event_trait: dict[int, EventTrait] = {}
    field_trait: dict[int, FieldTrait] = {}

    # additional strings
    # ce_comment: dict[int, MappingStr] = {}  # in w
    # cc_comment: dict[int, MappingStr] = {}  # in w
    mc_detail: dict[int, MappingStr] = {}
    costume_detail: dict[int, MappingStr] = {}  # collection no

    # ignored when copy to mapping folder
    # <svt_id, region:<skill_id, strengthenState>>
    skill_priority: dict[int, MappingBase[dict[int, int]]] = {}
    # <svt_id, region:<td_id, strengthenState>>
    td_priority: dict[int, MappingBase[dict[int, int]]] = {}

    entity_release: MappingBase[list[int]] = MappingBase()
    cc_release: MappingBase[list[int]] = MappingBase()
    mc_release: MappingBase[list[int]] = MappingBase()
    war_release: MappingBase[list[int]] = MappingBase()
    quest_release: dict[int, MappingInt] = {}

    enums: EnumMapping = EnumMapping()
    misc: dict[str, dict[str, MappingStr]] = {}
    cn_replace: dict[str, str] = {}
