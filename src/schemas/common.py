from enum import StrEnum
from typing import Generic, Optional, TypeVar, Union

from app.schemas.common import Region
from pydantic import BaseModel, Field
from pydantic.generics import GenericModel


_KT = TypeVar("_KT")
_KV = TypeVar("_KV")


class MappingBase(GenericModel, Generic[_KV]):
    JP: Optional[_KV] = None
    CN: Optional[_KV] = None
    TW: Optional[_KV] = None
    NA: Optional[_KV] = None
    KR: Optional[_KV] = None

    def update(self, region: Region, value: _KV | None, skip_exists=False):
        def _resolve_value(region_v):
            v = region_v or value if skip_exists else value or region_v
            if v:
                return v

        if region == Region.JP:
            self.JP = _resolve_value(self.JP)
        elif region == Region.CN:
            self.CN = _resolve_value(self.CN)
        elif region == Region.TW:
            self.TW = _resolve_value(self.TW)
        elif region == Region.NA:
            self.NA = _resolve_value(self.NA)
        elif region == Region.KR:
            self.KR = _resolve_value(self.KR)

    def update_from(self, other: "MappingBase[_KV]", skip_exist=True):
        if skip_exist:
            self.JP = self.JP or other.JP
            self.CN = self.CN or other.CN
            self.TW = self.TW or other.TW
            self.NA = self.NA or other.NA
            self.KR = self.KR or other.KR
        else:
            self.JP = other.JP or self.JP
            self.CN = other.CN or self.CN
            self.TW = other.TW or self.TW
            self.NA = other.NA or self.NA
            self.KR = other.KR or self.KR

    def of(self, region: Region) -> _KV | None:
        if region == Region.JP:
            return self.JP
        elif region == Region.CN:
            return self.CN
        elif region == Region.TW:
            return self.TW
        elif region == Region.NA:
            return self.NA
        elif region == Region.KR:
            return self.KR


MappingStr = MappingBase[str]
MappingInt = MappingBase[int]


class MappingExtend(MappingBase[str]):
    ES: Optional[str] = None  # Spanish


class SvtObtain(StrEnum):
    friendPoint = "friendPoint"
    story = "story"
    permanent = "permanent"
    heroine = "heroine"
    limited = "limited"
    unavailable = "unavailable"
    eventReward = "eventReward"
    clearReward = "clearReward"
    unknown = "unknown"

    @staticmethod
    def from_cn(s: str) -> "SvtObtain":
        s = s.strip()
        if not s or s in ("活动通关奖励", "事前登录赠送"):
            return SvtObtain.unknown
        return {
            "友情点召唤": SvtObtain.friendPoint,
            "剧情限定": SvtObtain.story,
            "圣晶石常驻": SvtObtain.permanent,
            "初始获得": SvtObtain.heroine,
            "期间限定": SvtObtain.limited,
            "无法获得": SvtObtain.unavailable,
            "活动赠送": SvtObtain.eventReward,
            "通关报酬": SvtObtain.clearReward,
        }[s]


class CEObtain(StrEnum):
    exp = "exp"
    shop = "shop"
    story = "story"
    permanent = "permanent"
    valentine = "valentine"
    limited = "limited"
    eventReward = "eventReward"
    campaign = "campaign"
    bond = "bond"
    drop = "drop"
    unknown = "unknown"  # should not be included in db

    @staticmethod
    def from_cn(s: str) -> "CEObtain":
        s = s.strip()
        if not s:
            return CEObtain.unknown
        return {
            "EXP卡": CEObtain.exp,
            "兑换": CEObtain.shop,
            "剧情限定": CEObtain.story,
            "卡池常驻": CEObtain.permanent,
            "情人节": CEObtain.valentine,
            "期间限定": CEObtain.limited,
            "活动奖励": CEObtain.eventReward,
            "纪念": CEObtain.campaign,
            "牵绊": CEObtain.bond,
            "掉落加成": CEObtain.drop,
            "未知": CEObtain.unknown,
        }[s]


class CCObtain(StrEnum):
    @staticmethod
    def from_name(s: str):
        return


class SummonType(StrEnum):
    story = "story"
    limited = "limited"
    gssr = "gssr"
    gssrsr = "gssrsr"
    unknown = "unknown"


class ItemCategory(StrEnum):
    normal = "normal"
    ascension = "ascension"
    skill = "skill"
    special = "special"
    eventAscension = "eventAscension"
    event = "event"
    coin = "coin"
    other = "other"


class CustomMissionType(StrEnum):
    trait = "trait"
    questTrait = "questTrait"
    quest = "quest"
    enemy = "enemy"
    servantClass = "servantClass"
    enemyClass = "enemyClass"
    enemyNotServantClass = "enemyNotServantClass"


class OpenApiInfo(BaseModel):
    # title: str
    # description: str
    version: str
    x_server_commit_hash: str = Field(..., alias="x-server-commit-hash")
    x_server_commit_timestamp: int = Field(..., alias="x-server-commit-timestamp")

    class Config:
        allow_population_by_field_name = True


class AtlasExportFile(StrEnum):
    basic_svt = "basic_svt"
    # nice_servant = "nice_servant"
    nice_servant_lore = "nice_servant_lore"
    # nice_equip = "nice_equip"
    nice_equip_lore = "nice_equip_lore"
    nice_command_code = "nice_command_code"
    nice_mystic_code = "nice_mystic_code"
    nice_item = "nice_item"
    nice_master_mission = "nice_master_mission"
    nice_illustrator = "nice_illustrator"
    nice_cv = "nice_cv"
    nice_bgm = "nice_bgm"
    nice_war = "nice_war"
    nice_event = "nice_event"
    # shared constants
    nice_enums = "nice_enums"  # hard code
    nice_trait = "nice_trait"  # hard code, +unknown
    nice_attribute_relation = "NiceAttributeRelation"  # hard code
    nice_class = "NiceClass"
    nice_class_attack_rate = "NiceClassAttackRate"
    nice_class_relation = "NiceClassRelation"
    nice_card = "NiceCard"
    nice_constant = "NiceConstant"  # hard code
    nice_buff_list_action_list = "NiceBuffList_ActionList"
    nice_user_level = "NiceUserLevel"
    nice_svt_grail_cost = "NiceSvtGrailCost"

    def resolve_link(self, region: Union[str, Region]):
        fn = (
            "NiceBuffList.ActionList"
            if self == AtlasExportFile.nice_buff_list_action_list
            else f"{self.value}"
        )
        return f"https://api.atlasacademy.io/export/{region}/{fn}.json"

    def cache_path(self, region: Union[str, Region] = Region.JP):
        from ..config import settings

        return settings.atlas_export_dir / f"{region}" / f"{self.value}.json"


class FileVersion(BaseModel):
    key: str
    filename: str
    size: int
    hash: str
    minSize: int = 0
    minHash: str = ""
    timestamp: int


class DataVersion(BaseModel):
    timestamp: int
    utc: str
    minimalApp: str
    files: dict[str, FileVersion] = {}


# raw


class MstViewEnemy(BaseModel):
    questId: int
    enemyId: int
    name: str
    classId: int
    svtId: int
    limitCount: int
    iconId: int
    displayType: int
    # missionIds: list[int]
    npcSvtId: int | None


class MstClass(BaseModel):
    id: int
    attri: int
    name: str
    individuality: int
    attackRate: int
    imageId: int
    iconImageId: int
    frameId: int
    priority: int
    groupType: int
    relationId: int
    supportGroup: int
    autoSelSupportType: int


class MstClassRelation(BaseModel):
    atkClass: int
    defClass: int
    attackRate: int
    # advIconId: int
    # disadvIconId: int
