import re
from collections import defaultdict
from pathlib import Path

from app.core.utils import get_traits_list
from app.schemas.gameenums import (
    BUFF_TYPE_NAME,
    FUNC_TYPE_NAME,
)
from app.schemas.nice import NiceBuffTypeDetail, NiceFuncTypeDetail
from app.schemas.raw import MstBuffTypeDetail, MstFuncTypeDetail, MstSvtExp

from ...schemas.common import MstConstantStr
from ...schemas.const_data import ConstDataConfig, ConstGameData, SvtExpCurve
from ...schemas.data import (
    CN_REPLACE,
    DESTINY_ORDER_CLASSES,
    DESTINY_ORDER_SUMMONS,
    EVENT_POINT_BUFF_GROUP_SKILL_NUM_MAP,
    EXCLUDE_REWARD_QUESTS,
    EXTRA_WAR_EVENT_MAPPING,
    FREE_EXCHANGE_SVT_EVENTS,
    LAPLACE_UPLOAD_ALLOW_AI_QUESTS,
    RANDOM_ENEMY_QUESTS,
    SAME_QUEST_REMAP,
    SVT_ALLOWED_EXTRA_PASSIVES,
    SVT_FACE_LIMITS,
    SVT_LIMIT_HIDES,
)
from ...schemas.gamedata import MasterData
from ...utils.helper import parse_json_obj_as, sort_dict
from ...utils.url import DownUrl


def get_const_data(data: MasterData):
    class_relations: dict[int, dict[int, int]] = defaultdict(dict)
    for relation in data.mstClassRelation:
        class_relations[relation.atkClass][relation.defClass] = relation.attackRate
    for cls_info in data.mstClass:
        if not isinstance(cls_info.individuality, int):
            cls_info.individuality = 0

    mst_exps = parse_json_obj_as(list[MstSvtExp], DownUrl.git_jp("mstSvtExp"))
    exp_dict: dict[int, list[MstSvtExp]] = defaultdict(list)
    for exp in mst_exps:
        exp_dict[exp.type].append(exp)
    for exp_list in exp_dict.values():
        exp_list.sort(key=lambda x: x.lv)
    exp_dict = sort_dict(exp_dict)
    svt_exps: dict[int, SvtExpCurve] = {}
    for key, exps in exp_dict.items():
        svt_exps[key] = SvtExpCurve(
            type=key,
            lv=[x.lv for x in exps],
            exp=[x.exp for x in exps],
            curve=[x.curve for x in exps],
        )

    mst_func_type_details = parse_json_obj_as(
        list[MstFuncTypeDetail], DownUrl.git_jp("mstFuncTypeDetail")
    )
    mst_buff_type_details = parse_json_obj_as(
        list[MstBuffTypeDetail], DownUrl.git_jp("mstBuffTypeDetail")
    )

    return ConstGameData(
        cnReplace=dict(CN_REPLACE),
        attributeRelation=data.NiceAttributeRelation,
        buffActions=data.NiceBuffList_ActionList,
        cardInfo=data.NiceCard,
        classInfo={x.id: x for x in data.mstClass},
        classRelation=class_relations,
        constants=data.NiceConstant,
        constantStr=get_constant_str(),
        svtGrailCost=data.NiceSvtGrailCost,
        userLevel=data.NiceUserLevel,
        svtExp=svt_exps,
        funcTypeDetail={
            detail.funcType: get_nice_func_type_detail(detail)
            for detail in mst_func_type_details
        },
        buffTypeDetail={
            detail.buffType: get_nice_buff_type_detail(detail)
            for detail in mst_buff_type_details
        },
        svtLimitHides=SVT_LIMIT_HIDES,
        svtAllowedExtraPassives=SVT_ALLOWED_EXTRA_PASSIVES,
        eventPointBuffGroupSkillNumMap=EVENT_POINT_BUFF_GROUP_SKILL_NUM_MAP,
        laplaceUploadAllowAiQuests=LAPLACE_UPLOAD_ALLOW_AI_QUESTS,
        excludeRewardQuests=EXCLUDE_REWARD_QUESTS,
        randomEnemyQuests=RANDOM_ENEMY_QUESTS,
        freeExchangeSvtEvents=FREE_EXCHANGE_SVT_EVENTS,
        svtFaceLimits=SVT_FACE_LIMITS,
        destinyOrderSummons=DESTINY_ORDER_SUMMONS,
        destinyOrderClasses=DESTINY_ORDER_CLASSES,
        extraWarEventMapping=EXTRA_WAR_EVENT_MAPPING,
        sameQuestRemap=SAME_QUEST_REMAP,
        routeSelects=get_route_selects(),
        config=ConstDataConfig(),
        deprecatedEnums={"BuffType": {}, "BuffAction": {}, "FuncType": {}},
    )


def get_nice_func_type_detail(detail: MstFuncTypeDetail) -> NiceFuncTypeDetail:
    return NiceFuncTypeDetail(
        funcType=FUNC_TYPE_NAME[detail.funcType],
        ignoreValueUp=detail.ignoreValueUp,
        individuality=get_traits_list(detail.individuality or []),
    )


def get_nice_buff_type_detail(detail: MstBuffTypeDetail) -> NiceBuffTypeDetail:
    return NiceBuffTypeDetail(
        buffType=BUFF_TYPE_NAME[detail.buffType],
        ignoreValueUp=detail.ignoreValueUp,
        script=detail.script,
    )


def get_constant_str():
    mst_const_str = parse_json_obj_as(
        list[MstConstantStr], DownUrl.git_jp("mstConstantStr")
    )
    int_list_keys = [
        # INDIV
        "IGNORE_RESIST_FUNC_INDIVIDUALITY",
        "INVALID_SACRIFICE_INDIV",
        "NP_INDIVIDUALITY_DAMAGE_ALL",
        "NP_INDIVIDUALITY_DAMAGE_ONE",
        "NP_INDIVIDUALITY_NOT_DAMAGE",
        "SUB_PT_BUFF_INDIVI",
        "SVT_EXIT_PT_BUFF_INDIVI",
        # BUFF
        "EXTEND_TURN_BUFF_TYPE",
        "NOT_REDUCE_COUNT_WITH_NO_DAMAGE_BUFF",
        "STAR_REFRESH_BUFF_TYPE",
        # FUNC
        "FUNCTION_TYPE_NOT_NP_DAMAGE",
        # OTHERS
        "PLAYABLE_BEAST_CLASS_IDS",
        "ENABLE_OVERWRITE_CLASS_IDS",
        "OVERWRITE_TO_NP_INDIVIDUALITY_DAMAGE_ALL_BY_TREASURE_DEVICE_IDS",
        "OVERWRITE_TO_NP_INDIVIDUALITY_DAMAGE_ONE_BY_TREASURE_DEVICE_IDS",
    ]
    int_keys = [
        # "MATERIAL_MAIN_INTERLUDE_WAR_ID",
    ]
    str_keys = []

    out: dict[str, list[int] | int | str] = {}
    for item in mst_const_str:
        key, value = item.name, item.value
        if key in int_list_keys:
            values = [int(v) for v in value.split(",") if v]
            assert values, item
            out[key] = values
        elif key in int_keys:
            out[key] = int(value)
        elif key in str_keys:
            out[key] = value
    return out


def get_route_selects() -> dict[str, list[str]]:
    from ...config import settings
    from ...utils import logger

    folder = Path(settings.game_data_jp_dir) / "ScriptActionEncrypt"
    result: dict[str, list[str]] = {}
    for fp in folder.glob("**/*.txt"):
        context = fp.read_text()
        matches = re.findall(
            r"[？?]\s*(\d+|[\?？])?\s*(?:[,，]\s*(\d+)\s*)[：:](.*)", context
        )
        route_ids = [route_id for (index, route_id, text) in matches if route_id]
        if not route_ids:
            continue
        script_id = fp.name[:-4]
        if not script_id.isdigit():
            logger.warning(f"not digit script id: {fp}")
        else:
            result[script_id] = route_ids
    result = sort_dict(result)
    if not result:
        raise Exception("no route select found")

    route_count = sum(len(v) for v in result.values())
    logger.info(f"Found {route_count} routes in {len(result)} script files")
    return result
