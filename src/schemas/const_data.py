from typing import Any

from app.schemas.common import NiceTrait
from app.schemas.enums import Attribute, SvtClass, Trait
from app.schemas.gameenums import (
    NiceBuffAction,
    NiceBuffLimit,
    NiceBuffType,
    NiceSvtFrameType,
)
from app.schemas.nice import NiceBuffTypeDetail, NiceFuncTypeDetail, NiceGift
from pydantic import BaseModel

from .common import MstClass


class ConstDataConfig(BaseModel):
    autoLoginMinVerJp: str = "2.5.19"
    autoLoginMinVerNa: str = "2.5.5"


class BuffActionInfo(BaseModel):
    limit: NiceBuffLimit
    plusTypes: list[NiceBuffType]
    minusTypes: list[NiceBuffType]
    baseParam: int
    baseValue: int
    isRec: bool
    plusAction: int | NiceBuffAction  # remove int type in 2.6.0
    maxRate: list[int]
    isChangeMaxHp: bool


class NiceClassInfo(BaseModel):
    id: int
    className: SvtClass | None = None
    name: str
    individuality: Trait
    attackRate: int
    imageId: int
    iconImageId: int
    frameId: int
    priority: int
    groupType: int
    relationId: int
    supportGroup: int
    autoSelSupportType: int


class CardInfo(BaseModel):
    individuality: list[NiceTrait]
    adjustAtk: int
    adjustTdGauge: int
    adjustCritical: int
    addAtk: int
    addTdGauge: int
    addCritical: int


class GrailCostDetail(BaseModel):
    qp: int
    addLvMax: int
    frameType: NiceSvtFrameType


class MasterUserLvDetail(BaseModel):
    requiredExp: int
    maxAp: int
    maxCost: int
    maxFriend: int
    gift: NiceGift | None = None


class SvtExpCurve(BaseModel):
    type: int
    lv: list[int]
    exp: list[int]
    curve: list[int]


class SvtLimitHide(BaseModel):
    limits: list[int]
    tds: list[int] = []
    activeSkills: dict[int, list[int]] = {}
    # classPassives: list[int] = []
    addPassives: list[int] = []


class SvtAllowedExtraPassive(BaseModel):
    eventId: int
    groupId: int
    skillId: int
    fromPassive: bool
    svtIds: list[int]


class ConstGameData(BaseModel):
    cnReplace: dict[str, str]
    attributeRelation: dict[Attribute, dict[Attribute, int]]
    buffActions: dict[NiceBuffAction, BuffActionInfo]
    classInfo: dict[int, MstClass]
    cardInfo: dict[int, dict[int, CardInfo]]
    classRelation: dict[int, dict[int, int]]
    constants: dict[str, int]
    constantStr: dict[str, Any]  # list[int] | int | str | list[str] ...
    svtGrailCost: dict[int, dict[int, GrailCostDetail]]
    userLevel: dict[int, MasterUserLvDetail]
    svtExp: dict[int, SvtExpCurve]
    funcTypeDetail: dict[int, NiceFuncTypeDetail]
    buffTypeDetail: dict[int, NiceBuffTypeDetail]
    svtLimitHides: dict[int, list[SvtLimitHide]]
    svtAllowedExtraPassives: list[SvtAllowedExtraPassive]
    eventPointBuffGroupSkillNumMap: dict[int, dict[int, int]]
    laplaceUploadAllowAiQuests: list[int]
    excludeRewardQuests: list[int]
    randomEnemyQuests: list[int]
    freeExchangeSvtEvents: list[int]
    destinyOrderSummons: list[str]
    destinyOrderClasses: dict[str, list[int]]
    svtFaceLimits: dict[int, list[int]]
    extraWarEventMapping: dict[int, int]
    sameQuestRemap: dict[int, int]
    routeSelects: dict[str, list[str]]
    config: ConstDataConfig
