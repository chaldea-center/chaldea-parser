from collections import defaultdict

from app.core.utils import get_traits_list
from app.schemas.gameenums import (
    BUFF_ACTION_NAME,
    BUFF_TYPE_NAME,
    FUNC_TYPE_NAME,
    NiceBuffAction,
    NiceCardType,
)
from app.schemas.nice import NiceBuffTypeDetail, NiceFuncTypeDetail
from app.schemas.raw import MstBuffTypeDetail, MstFuncTypeDetail, MstSvtExp

from ...schemas.common import MstConstantStr
from ...schemas.const_data import ConstDataConfig, ConstGameData, SvtExpCurve
from ...schemas.data import (
    CN_REPLACE,
    DESTINY_ORDER_SUMMONS,
    EVENT_POINT_BUFF_GROUP_SKILL_NUM_MAP,
    EXCLUDE_REWARD_QUESTS,
    FREE_EXCHANGE_SVT_EVENTS,
    LAPLACE_UPLOAD_ALLOW_AI_QUESTS,
    RANDOM_ENEMY_QUESTS,
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

    mst_exps = parse_json_obj_as(list[MstSvtExp], DownUrl.gitaa("mstSvtExp"))
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
        list[MstFuncTypeDetail], DownUrl.gitaa("mstFuncTypeDetail")
    )
    mst_buff_type_details = parse_json_obj_as(
        list[MstBuffTypeDetail], DownUrl.gitaa("mstBuffTypeDetail")
    )

    BUFF_ACTION_NAME_REVERSE = {v: k for k, v in BUFF_ACTION_NAME.items()}
    for act_info in data.NiceBuffList_ActionList.values():
        if isinstance(act_info.plusAction, NiceBuffAction):
            act_info.plusAction = BUFF_ACTION_NAME_REVERSE[act_info.plusAction]

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
        config=ConstDataConfig(),
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
        list[MstConstantStr], DownUrl.gitaa("mstConstantStr")
    )
    int_list_keys = [
        "EXTEND_TURN_BUFF_TYPE",
        "INVALID_SACRIFICE_INDIV",
        "NOT_REDUCE_COUNT_WITH_NO_DAMAGE_BUFF",
        "STAR_REFRESH_BUFF_TYPE",
        "SUB_PT_BUFF_INDIVI",
        "SVT_EXIT_PT_BUFF_INDIVI",
        "PLAYABLE_BEAST_CLASS_IDS",
        "ENABLE_OVERWRITE_CLASS_IDS",
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
