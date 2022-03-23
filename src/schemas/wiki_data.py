from typing import Optional

from app.schemas.base import BaseModelORJson
from pydantic import BaseModel, HttpUrl, NoneStr

from ..schemas.common import (
    CEObtain,
    MappingBase,
    MappingInt,
    MappingStr,
    SummonType,
    SvtObtain,
)
from ..utils import sort_dict


class MooncellTranslation(BaseModelORJson):
    """
    Mooncell Translations

    <id/jp_name, cn_name>
    """

    svt_names: dict[int, str] = {}
    skill_names: dict[str, str] = {}
    td_names: dict[str, str] = {}
    td_ruby: dict[str, str] = {}
    ce_names: dict[int, str] = {}
    cc_names: dict[int, str] = {}
    event_names: dict[str, str] = {}

    def sort(self):
        self.svt_names = sort_dict(self.svt_names)
        self.skill_names = sort_dict(self.skill_names)
        self.td_names = sort_dict(self.td_names)
        self.td_ruby = sort_dict(self.td_ruby)
        self.ce_names = sort_dict(self.ce_names)
        self.cc_names = sort_dict(self.cc_names)
        self.event_names = sort_dict(self.event_names)


class ServantW(BaseModel):
    collectionNo: int
    nameOther: list[str] = []
    obtains: list[SvtObtain] = []
    aprilFoolAssets: list[HttpUrl] = []
    aprilFoolProfile: MappingStr = MappingStr()
    # profileComment: MappingBase[list[NiceLoreComment]] = Field(default_factory=MappingBase)
    mcLink: NoneStr = None
    fandomLink: NoneStr = None


class CraftEssenceW(BaseModel):
    collectionNo: int
    obtain: CEObtain = CEObtain.unknown
    profile: MappingStr = MappingStr()
    characters: list[int] = []  # convert to collectionNo
    unknownCharacters: list[str] = []
    mcLink: NoneStr = None
    fandomLink: NoneStr = None


class CommandCodeW(BaseModel):
    collectionNo: int
    profile: MappingStr = MappingStr()
    characters: list[int] = []  # convert to collectionNo
    unknownCharacters: list[str] = []
    mcLink: NoneStr = None
    fandomLink: NoneStr = None


# class MysticCodeW(BaseModel):
#     id: int
#     detail: MappingStr = MappingStr()


class EventExtraItems(BaseModel):
    id: int
    detail: NoneStr = None
    items: dict[int, str] = {}


class EventWBase(BaseModel):
    id: int
    name: str
    mcLink: NoneStr = None
    fandomLink: NoneStr = None
    titleBanner: MappingBase[HttpUrl] = MappingBase()
    noticeLink: MappingStr = MappingStr()
    huntingQuestIds: list[int] = []
    # item_id: hint, ${var_name}
    extraItems: list[EventExtraItems] = []


class WarW(BaseModel):
    id: int
    mcLink: NoneStr = None
    fandomLink: NoneStr = None
    titleBanner: MappingBase[HttpUrl] = MappingBase()
    noticeLink: MappingStr = MappingStr()


class EventW(EventWBase):
    startTime: Optional[MappingInt] = None
    endTime: Optional[MappingInt] = None
    rarePrism: int = 0
    grail: int = 0  # pure grail
    crystal: int = 0  # pure crystal
    grail2crystal: int = 0  # total = grail+crystal+grail2crystal
    foukun4: int = 0
    relatedSummons: list[str] = []


class ProbGroup(BaseModel):
    isSvt: bool
    rarity: int
    weight: float
    display: bool
    ids: list[int] = []  # collectionNo


class SubSummon(BaseModel):
    title: str
    probs: list[ProbGroup] = []


class LimitedSummonBase(BaseModel):
    id: str
    mcLink: NoneStr = None
    fandomLink: NoneStr = None
    name: MappingStr = MappingStr()
    banner: MappingBase[HttpUrl] = MappingBase()
    noticeLink: MappingStr = MappingStr()  # cn: number, tw?
    startTime: MappingInt = MappingInt()
    endTime: MappingInt = MappingInt()


class LimitedSummon(LimitedSummonBase):
    type: SummonType = SummonType.unknown
    rollCount: int = 11  # 11 or 10
    subSummons: list[SubSummon] = []


class WikiData(BaseModelORJson):
    servants: dict[int, ServantW] = {}
    craftEssences: dict[int, CraftEssenceW] = {}
    commandCodes: dict[int, CommandCodeW] = {}
    # mysticCodes: dict[int, MysticCodeW] = {}

    # events and summons are stored as base
    events: dict[int, EventW] = {}
    wars: dict[int, WarW] = {}
    fsmSvtIdMapping: dict[int, int] = {}

    def get_svt(self, collection_no: int):
        return self.servants.setdefault(
            collection_no, ServantW(collectionNo=collection_no)
        )

    def get_ce(self, collection_no: int):
        return self.craftEssences.setdefault(
            collection_no, CraftEssenceW(collectionNo=collection_no)
        )

    def get_cc(self, collection_no: int):
        return self.commandCodes.setdefault(
            collection_no, CommandCodeW(collectionNo=collection_no)
        )
