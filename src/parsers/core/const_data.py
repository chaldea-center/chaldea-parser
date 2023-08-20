from collections import defaultdict

from app.schemas.gameenums import BUFF_TYPE_NAME, FUNC_TYPE_NAME
from app.schemas.nice import NiceBuffTypeDetail, NiceFuncTypeDetail
from app.schemas.raw import MstBuffTypeDetail, MstFuncTypeDetail, MstSvtExp
from pydantic import parse_obj_as

from ...schemas.const_data import ConstGameData, SvtExpCurve
from ...schemas.gamedata import MasterData
from ...utils.helper import sort_dict
from ...utils.url import DownUrl
from ..data import EVENT_POINT_BUFF_GROUP_SKILL_NUM_MAP, LAPLACE_UPLOAD_ALLOW_AI_QUESTS


def get_const_data(data: MasterData):
    class_relations: dict[int, dict[int, int]] = defaultdict(dict)
    for relation in data.mstClassRelation:
        class_relations[relation.atkClass][relation.defClass] = relation.attackRate
    for cls_info in data.mstClass:
        if not isinstance(cls_info.individuality, int):
            cls_info.individuality = 0

    mst_exps = parse_obj_as(list[MstSvtExp], DownUrl.gitaa("mstSvtExp"))
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

    mst_func_type_details = parse_obj_as(
        list[MstFuncTypeDetail], DownUrl.gitaa("mstFuncTypeDetail")
    )
    mst_buff_type_details = parse_obj_as(
        list[MstBuffTypeDetail], DownUrl.gitaa("mstBuffTypeDetail")
    )

    return ConstGameData(
        attributeRelation=data.NiceAttributeRelation,
        buffActions=data.NiceBuffList_ActionList,
        cardInfo=data.NiceCard,
        classInfo={x.id: x for x in data.mstClass},
        classRelation=class_relations,
        constants=data.NiceConstant,
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
        eventPointBuffGroupSkillNumMap=EVENT_POINT_BUFF_GROUP_SKILL_NUM_MAP,
        laplaceUploadAllowAiQuests=LAPLACE_UPLOAD_ALLOW_AI_QUESTS,
    )


def get_nice_func_type_detail(detail: MstFuncTypeDetail) -> NiceFuncTypeDetail:
    return NiceFuncTypeDetail(
        funcType=FUNC_TYPE_NAME[detail.funcType],
        ignoreValueUp=detail.ignoreValueUp,
    )


def get_nice_buff_type_detail(detail: MstBuffTypeDetail) -> NiceBuffTypeDetail:
    return NiceBuffTypeDetail(
        buffType=BUFF_TYPE_NAME[detail.buffType],
        ignoreValueUp=detail.ignoreValueUp,
        script=detail.script,
    )
