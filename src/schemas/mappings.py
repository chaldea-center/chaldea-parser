from pydantic import BaseModel

from .common import MappingBase, MappingStr


class EnumMapping(BaseModel):
    svt_class: dict[str, MappingStr] = {}
    attribute: dict[str, MappingStr] = {}
    servant_policy: dict[str, MappingStr] = {}
    servant_personality: dict[str, MappingStr] = {}
    gender: dict[str, MappingStr] = {}
    func_target_type: dict[str, MappingStr] = {}
    # wiki
    svt_obtain: dict[str, MappingStr] = {}
    ce_obtain: dict[str, MappingStr] = {}


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

    trait: dict[int, MappingStr] = {}  # trait.id
    svt_class: dict[int, MappingStr] = {}

    # additional strings
    # ce_comment: dict[int, MappingStr] = {}  # in w
    # cc_comment: dict[int, MappingStr] = {}  # in w
    mc_detail: dict[int, MappingStr] = {}
    costume_detail: dict[int, MappingStr] = {}  # collection no

    # ignored when copy to mapping folder
    # <svt_id, region:<skill_id, strengthenState>>
    skill_state: dict[int, MappingBase[dict[int, int]]] = {}
    # <svt_id, region:<td_id, strengthenState>>
    td_state: dict[int, MappingBase[dict[int, int]]] = {}

    svt_release: MappingBase[list[int]] = MappingBase()
    ce_release: MappingBase[list[int]] = MappingBase()
    cc_release: MappingBase[list[int]] = MappingBase()

    enums: EnumMapping = EnumMapping()
