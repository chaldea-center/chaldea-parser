from pydantic import BaseModel

from .common import MappingBase, MappingInt, MappingStr


CN_REPLACE = {
    "西行者": "玄奘三藏",
    "匕见": "荆轲",
    "虎狼": "吕布",
    "歌果": "美杜莎",
    "雾都弃子": "开膛手杰克",
    "莲偶": "哪吒",
    "周照": "武则天",
    "瞑生院祈荒": "杀生院祈荒",
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
    svt_class: dict[str, MappingStr] = {}
    attribute: dict[str, MappingStr] = {}
    svt_type: dict[str, MappingStr] = {}
    servant_policy: dict[str, MappingStr] = {}
    servant_personality: dict[str, MappingStr] = {}
    gender: dict[str, MappingStr] = {}
    func_target_type: dict[str, MappingStr] = {}
    # wiki
    svt_obtain: dict[str, MappingStr] = {}
    ce_obtain: dict[str, MappingStr] = {}
    mission_progress_type: dict[str, MappingStr] = {}
    mission_type: dict[str, MappingStr] = {}
    item_category: dict[str, MappingStr] = {}
    custom_mission_type: dict[str, MappingStr] = {}
    np_damage_type: dict[str, MappingStr] = {}
    td_effect_flag: dict[str, MappingStr] = {}
    summon_type: dict[str, MappingStr] = {}
    # long dict
    effect_type: dict[str, MappingStr] = {}
    func_type: dict[str, MappingStr] = {}
    buff_type: dict[str, MappingStr] = {}
    svt_voice_type: dict[str, MappingStr] = {}


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
    trait_redirect: dict[int, int] = {}  # event_trait -> normal trait

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
    quest_release: dict[int, MappingInt] = {}

    enums: EnumMapping = EnumMapping()
    misc: dict[str, MappingStr] = {}
    cn_replace: dict[str, str] = {}
