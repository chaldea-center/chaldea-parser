from typing import Optional

from app.schemas.common import NiceTrait
from app.schemas.enums import Attribute, SvtClass, Trait
from app.schemas.gameenums import (
    NiceBuffAction,
    NiceBuffLimit,
    NiceBuffType,
    NiceCardType,
    NiceSvtFrameType,
)
from app.schemas.nice import NiceBuffTypeDetail, NiceFuncTypeDetail, NiceGift
from app.schemas.raw import MstSvtExp
from pydantic import BaseModel

from .common import MstClass


class BuffActionDetail(BaseModel):
    limit: NiceBuffLimit
    plusTypes: list[NiceBuffType]
    minusTypes: list[NiceBuffType]
    baseParam: int
    baseValue: int
    isRec: bool
    plusAction: int
    maxRate: list[int]


class NiceClassInfo(BaseModel):
    id: int
    className: SvtClass | None
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
    gift: Optional[NiceGift]


class SvtExpCurve(BaseModel):
    type: int
    lv: list[int]
    exp: list[int]
    curve: list[int]


class ConstGameData(BaseModel):
    attributeRelation: dict[Attribute, dict[Attribute, int]]
    buffActions: dict[NiceBuffAction, BuffActionDetail]
    classInfo: dict[int, MstClass]
    cardInfo: dict[NiceCardType, dict[int, CardInfo]]
    classRelation: dict[int, dict[int, int]]
    constants: dict[str, int]
    svtGrailCost: dict[int, dict[int, GrailCostDetail]]
    userLevel: dict[int, MasterUserLvDetail]
    svtExp: dict[int, SvtExpCurve]
    funcTypeDetail: dict[int, NiceFuncTypeDetail]
    buffTypeDetail: dict[int, NiceBuffTypeDetail]
