from enum import StrEnum
from typing import Any, Type

from app.schemas.enums import Attribute, ServantPersonality, ServantPolicy, SvtClass
from app.schemas.gameenums import (
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
}


class EnumMapping(BaseModel):
    svt_class: dict[SvtClass, MappingStr] = {}
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
    # wiki
    svt_obtain: dict[SvtObtain, MappingStr] = {}
    ce_obtain: dict[CEObtain, MappingStr] = {}
    item_category: dict[ItemCategory, MappingStr] = {}
    custom_mission_type: dict[CustomMissionType, MappingStr] = {}
    summon_type: dict[SummonType, MappingStr] = {}
    effect_type: dict[str, MappingStr] = {}  # custom
    # long dict
    func_type: dict[NiceFuncType, MappingStr] = {}
    buff_type: dict[NiceBuffType, MappingStr] = {}
    svt_voice_type: dict[NiceSvtVoiceType, MappingStr] = {}

    def update_enums(self):
        enum_fields: dict[Type[StrEnum], dict[Any, MappingStr]] = {
            SvtClass: self.svt_class,
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
            SvtObtain: self.svt_obtain,
            CEObtain: self.ce_obtain,
            ItemCategory: self.item_category,
            CustomMissionType: self.custom_mission_type,
            SummonType: self.summon_type,
            # effect_type
            NiceFuncType: self.func_type,
            NiceBuffType: self.buff_type,
            NiceSvtVoiceType: self.svt_voice_type,
        }
        for k, v in enum_fields.items():
            for kk in k.__members__.values():
                v.setdefault(kk, MappingBase())


class EventTrait(MappingStr):
    eventId: int
    JP: str | None = None
    CN: str | None = None
    TW: str | None = None
    NA: str | None = None
    KR: str | None = None


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

    svt_release: MappingBase[list[int]] = MappingBase()
    ce_release: MappingBase[list[int]] = MappingBase()
    cc_release: MappingBase[list[int]] = MappingBase()
    mc_release: MappingBase[list[int]] = MappingBase()
    war_release: MappingBase[list[int]] = MappingBase()
    quest_release: dict[int, MappingInt] = {}

    enums: EnumMapping = EnumMapping()
    misc: dict[str, MappingStr] = {}
    cn_replace: dict[str, str] = {}
