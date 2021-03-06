from app.schemas.base import BaseModelORJson
from pydantic import BaseModel, Field, NoneStr

from src.utils.helper import dump_json_beautify

from ..config import settings
from ..schemas.common import (
    CEObtain,
    MappingBase,
    MappingInt,
    MappingStr,
    SummonType,
    SvtObtain,
)
from ..utils import NEVER_CLOSED_TIMESTAMP, dump_json, load_json, sort_dict


class WikiTranslation(BaseModelORJson):
    """
    Mooncell/Fandom Translations

    <id/jp_name, cn_name>
    """

    svt_names: dict[str, str] = {}
    skill_names: dict[str, str] = {}
    td_names: dict[str, str] = {}
    td_ruby: dict[str, str] = {}
    ce_names: dict[str, str] = {}
    cc_names: dict[str, str] = {}
    event_names: dict[str, str] = {}
    quest_names: dict[str, str] = {}
    spot_names: dict[str, str] = {}
    ce_skill_des: dict[int, str] = {}
    ce_skill_des_max: dict[int, str] = {}
    cc_skill_des: dict[int, str] = {}

    def sort(self):
        self.svt_names = sort_dict(self.svt_names)
        self.skill_names = sort_dict(self.skill_names)
        self.td_names = sort_dict(self.td_names)
        self.td_ruby = sort_dict(self.td_ruby)
        self.ce_names = sort_dict(self.ce_names)
        self.cc_names = sort_dict(self.cc_names)
        self.event_names = sort_dict(self.event_names)
        self.quest_names = sort_dict(self.quest_names)
        self.spot_names = sort_dict(self.spot_names)
        self.ce_skill_des = sort_dict(self.ce_skill_des)
        self.ce_skill_des_max = sort_dict(self.ce_skill_des_max)
        self.cc_skill_des = sort_dict(self.cc_skill_des)


class ServantWBase(BaseModel):
    collectionNo: int
    nicknames: MappingBase[list[str]] = MappingBase()


class ServantW(ServantWBase):
    mcLink: NoneStr = None
    fandomLink: NoneStr = None
    obtains: list[SvtObtain] = []
    aprilFoolAssets: list[str] = []
    aprilFoolProfile: MappingStr = MappingStr()
    spriteModels: list[str] = []
    mcProfiles: dict[int, list[str]] = {}
    fandomProfiles: dict[int, list[str]] = {}


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
    detail: MappingStr | None = None
    fixedItems: dict[int, int] = {}  # <itemId, count>
    items: dict[int, MappingStr | None] = {}  # <itemId, ap or drop rate or hint>


class EventExtraFixedItems(BaseModel):
    id: int
    detail: MappingStr | None = None
    items: dict[int, int] = {}


class EventWBase(BaseModel):
    id: int
    name: str
    mcLink: NoneStr = None
    fandomLink: NoneStr = None
    forceShown: bool = False
    titleBanner: MappingBase[str] = MappingBase()
    officialBanner: MappingBase[str] = MappingBase()
    noticeLink: MappingStr = MappingStr()
    huntingId: int = 0
    huntingQuestIds: list[int] = []
    extraFixedItems: list[EventExtraFixedItems] = []
    extraItems: list[EventExtraItems] = []


class WarW(BaseModel):
    id: int
    mcLink: NoneStr = None
    fandomLink: NoneStr = None
    titleBanner: MappingBase[str] = MappingBase()
    officialBanner: MappingBase[str] = MappingBase()
    noticeLink: MappingStr = MappingStr()


class EventW(EventWBase):
    startTime: MappingInt = MappingInt()
    endTime: MappingInt = MappingInt()
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
    banner: MappingBase[str] = MappingBase()
    officialBanner: MappingBase[str] = MappingBase()
    noticeLink: MappingStr = MappingStr()  # cn&tw: number
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
    events: dict[int, EventW] = {}
    wars: dict[int, WarW] = {}
    summons: dict[str, LimitedSummon] = {}
    mcTransl: WikiTranslation = WikiTranslation()
    fandomTransl: WikiTranslation = WikiTranslation()

    @classmethod
    def parse_dir(cls, full_version: bool = False) -> "WikiData":
        folder = settings.output_wiki
        data = {
            "craftEssences": {
                ce["collectionNo"]: ce
                for ce in load_json(folder / "craftEssences.json") or []
            },
            "commandCodes": {
                cc["collectionNo"]: cc
                for cc in load_json(folder / "commandCodes.json") or []
            },
            "wars": {war["id"]: war for war in load_json(folder / "wars.json") or []},
            "mcTransl": load_json(folder / "mcTransl.json", {}),
            "fandomTransl": load_json(folder / "fandomTransl.json", {}),
        }
        if full_version:
            data |= {
                "servants": {
                    svt["collectionNo"]: svt
                    for svt in load_json(folder / "servants.json") or []
                },
                "events": {
                    event["id"]: event
                    for event in load_json(folder / "events.json") or []
                },
                "summons": {
                    summon["id"]: summon
                    for summon in load_json(folder / "summons.json") or []
                },
            }
        else:
            data |= {
                "servants": {
                    svt["collectionNo"]: ServantWBase.parse_obj(svt).dict()
                    for svt in load_json(folder / "servants.json") or []
                },
                "events": {
                    event["id"]: event
                    for event in load_json(folder / "eventsBase.json") or []
                },
                "summons": {
                    summon["id"]: summon
                    for summon in load_json(folder / "summonsBase.json") or []
                },
            }
        return WikiData.parse_obj(data)

    def sort(self):
        self.servants = sort_dict(self.servants)
        self.craftEssences = sort_dict(self.craftEssences)
        self.commandCodes = sort_dict(self.commandCodes)
        events = list(self.events.values())
        events.sort(key=lambda event: event.startTime.JP or NEVER_CLOSED_TIMESTAMP)
        self.events = {event.id: event for event in events}
        self.wars = sort_dict(self.wars)
        summons = list(self.summons.values())
        summons.sort(key=lambda summon: summon.startTime.JP or NEVER_CLOSED_TIMESTAMP)
        self.summons = {summon.id: summon for summon in summons}
        self.mcTransl.sort()

    def save(self, full_version: bool):
        folder = settings.output_wiki
        if full_version:
            dump_json_beautify(list(self.servants.values()), folder / "servants.json")
            dump_json_beautify(
                list(self.craftEssences.values()),
                folder / "craftEssences.json",
            )
            dump_json_beautify(
                list(self.commandCodes.values()),
                folder / "commandCodes.json",
            )
            dump_json_beautify(list(self.events.values()), folder / "events.json")
            dump_json_beautify(list(self.summons.values()), folder / "summons.json")
            dump_json(self.mcTransl, settings.output_wiki / "mcTransl.json")
            dump_json(self.fandomTransl, settings.output_wiki / "fandomTransl.json")

        dump_json_beautify(list(self.wars.values()), folder / "wars.json")
        events_base = [
            event.dict(include=set(EventWBase.__fields__.keys()))
            for event in self.events.values()
        ]
        dump_json_beautify(events_base, folder / "eventsBase.json")
        summons_base = [
            summon.dict(include=set(LimitedSummonBase.__fields__.keys()))
            for summon in self.summons.values()
        ]
        dump_json_beautify(summons_base, folder / "summonsBase.json")

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


class AppNews(BaseModel):
    type: int | None = None
    priority: int | None = None
    startTime: str | None = None
    endTime: str | None = None
    title: str | None = None
    content: str | None = None
    image: str | None = None
    link: str | None = None
