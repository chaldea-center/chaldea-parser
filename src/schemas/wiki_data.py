from typing import Any

from app.schemas.base import BaseModelORJson
from app.schemas.common import Region
from pydantic import BaseModel

from ..config import settings
from ..schemas.common import MstMasterMissionWithGift
from ..utils.helper import (
    dump_json,
    dump_json_beautify,
    iter_model,
    load_json,
    parse_json_obj_as,
    pydantic_encoder,
    sort_dict,
)
from .common import (
    NEVER_CLOSED_TIMESTAMP,
    BaseModelTrim,
    CEObtain,
    MappingBase,
    MappingInt,
    MappingStr,
    SummonType,
    SvtObtain,
)
from .data import jp_chars


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
    illustrator_names: dict[str, str] = {}
    item_names: dict[str, str] = {}
    event_names: dict[str, str] = {}
    quest_names: dict[str, str] = {}
    spot_names: dict[str, str] = {}

    ce_skill_des: dict[int, str] = {}
    ce_skill_des_max: dict[int, str] = {}
    cc_skill_des: dict[int, str] = {}
    costume_names: dict[str, str] = {}
    costume_details: dict[int, str] = {}
    mc_names: dict[str, str] = {}
    mc_details: dict[str, str] = {}  # <name_jp: detail>
    summon_names: dict[str, str] = {}

    def sort(self):
        self.svt_names = sort_dict(self.svt_names)
        self.skill_names = sort_dict(self.skill_names)
        self.td_names = sort_dict(self.td_names)
        self.td_ruby = sort_dict(self.td_ruby)
        self.ce_names = sort_dict(self.ce_names)
        self.cc_names = sort_dict(self.cc_names)
        self.illustrator_names = sort_dict(self.illustrator_names)
        self.item_names = sort_dict(self.item_names)
        self.event_names = sort_dict(self.event_names)
        self.quest_names = sort_dict(self.quest_names)
        self.spot_names = sort_dict(self.spot_names)
        self.ce_skill_des = sort_dict(self.ce_skill_des)
        self.ce_skill_des_max = sort_dict(self.ce_skill_des_max)
        self.cc_skill_des = sort_dict(self.cc_skill_des)
        self.costume_names = sort_dict(self.costume_names)
        self.costume_details = sort_dict(self.costume_details)
        self.mc_names = sort_dict(self.mc_names)
        self.mc_details = sort_dict(self.mc_details)
        self.summon_names = sort_dict(self.summon_names)

    def clean_untranslated(self):
        def _clean(data: dict[Any, str]):
            keys_to_remove = [k for k, v in data.items() if jp_chars.search(v)]
            for key in keys_to_remove:
                data.pop(key)

        str_transls = [
            self.svt_names,
            self.skill_names,
            self.td_names,
            self.td_ruby,
            self.ce_names,
            self.cc_names,
            self.illustrator_names,
            self.item_names,
            self.event_names,
            self.quest_names,
            self.spot_names,
            self.costume_names,
            self.mc_names,
            self.mc_details,
            self.summon_names,
        ]
        int_transls = [
            self.ce_skill_des,
            self.ce_skill_des_max,
            self.cc_skill_des,
            self.costume_details,
        ]
        for x in str_transls:
            _clean(x)
        for x in int_transls:
            _clean(x)


class BiliVideo(BaseModel):
    av: int
    # bv: str | None = None
    p: int


class ServantWBase(BaseModel):
    collectionNo: int
    mcLink: str | None = None
    fandomLink: str | None = None
    nicknames: MappingBase[list[str]] = MappingBase()


class ServantW(ServantWBase):
    releasedAt: int | None = None
    obtains: list[SvtObtain] = []
    aprilFoolAssets: list[str] = []  # url
    aprilFoolProfile: MappingStr = MappingStr()
    mcSprites: list[str] = []  # filename
    fandomSprites: list[str] = []  # filename
    mcProfiles: dict[int, list[str]] = {}
    fandomProfiles: dict[int, list[str]] = {}
    # tdAnimations: list[BiliVideo] = []


class CraftEssenceW(BaseModel):
    collectionNo: int
    obtain: CEObtain = CEObtain.unknown
    profile: MappingStr = MappingStr()
    characters: list[int] = []  # convert to collectionNo
    unknownCharacters: list[str] = []
    mcLink: str | None = None
    fandomLink: str | None = None


class CommandCodeW(BaseModel):
    collectionNo: int
    profile: MappingStr = MappingStr()
    characters: list[int] = []  # convert to collectionNo
    unknownCharacters: list[str] = []
    mcLink: str | None = None
    fandomLink: str | None = None


# class MysticCodeW(BaseModel):
#     id: int
#     detail: MappingStr = MappingStr()


class EventExtraItems(BaseModel):
    id: int
    infinite: bool = False
    detail: MappingStr | None = None
    items: dict[int, MappingStr | None] = {}  # <itemId, ap or drop rate or hint>


class EventExtraFixedItems(BaseModel):
    id: int
    detail: MappingStr | None = None
    items: dict[int, int] = {}


class EventExtraScript(BaseModelTrim):
    huntingId: int | None = None
    raidLink: dict[Region, str] | None = None


class EventWBase(BaseModel):
    id: int
    name: str
    mcLink: str | None = None
    fandomLink: str | None = None
    shown: bool | None = None
    titleBanner: MappingBase[str] = MappingBase()
    officialBanner: MappingBase[str] = MappingBase()
    extraBanners: MappingBase[list[str]] = MappingBase()
    noticeLink: MappingStr = MappingStr()
    extraFixedItems: list[EventExtraFixedItems] = []
    extraItems: list[EventExtraItems] = []
    script: EventExtraScript = EventExtraScript()


class WarW(BaseModel):
    id: int
    mcLink: str | None = None
    fandomLink: str | None = None
    titleBanner: MappingBase[str] = MappingBase()
    officialBanner: MappingBase[str] = MappingBase()
    extraBanners: MappingBase[list[str]] = MappingBase()
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
    mcLink: str | None = None
    fandomLink: str | None = None
    banner: MappingBase[str] = MappingBase()
    officialBanner: MappingBase[str] = MappingBase()
    noticeLink: MappingStr = MappingStr()  # cn&tw: number
    startTime: MappingInt = MappingInt()
    endTime: MappingInt = MappingInt()


class LimitedSummon(LimitedSummonBase):
    name: str | None = None
    type: SummonType = SummonType.unknown
    rollCount: int = 11  # 11 or 10
    puSvt: list[int] = []
    puCE: list[int] = []
    subSummons: list[SubSummon] = []


class CampaignEvent(BaseModelORJson):
    key: str
    id: int
    # type: NiceEventType
    name: str
    startedAt: int
    endedAt: int


class WikiData(BaseModelORJson):
    servants: dict[int, ServantW] = {}
    craftEssences: dict[int, CraftEssenceW] = {}
    commandCodes: dict[int, CommandCodeW] = {}
    # mysticCodes: dict[int, MysticCodeW] = {}
    events: dict[int, EventW] = {}
    campaigns: dict[int, CampaignEvent] = {}
    wars: dict[int, WarW] = {}
    summons: dict[str, LimitedSummon] = {}
    mcTransl: WikiTranslation = WikiTranslation()
    fandomTransl: WikiTranslation = WikiTranslation()
    mms: dict[int, MstMasterMissionWithGift] = {}

    @classmethod
    def parse_dir(cls, full_version: bool = False) -> "WikiData":
        folder = settings.output_wiki
        data = {
            "craftEssences": {
                ce["collectionNo"]: ce
                for ce in load_json(folder / "craftEssences.json", [])
            },
            "commandCodes": {
                cc["collectionNo"]: cc
                for cc in load_json(folder / "commandCodes.json", [])
            },
            "wars": {war["id"]: war for war in load_json(folder / "wars.json", [])},
            "mms": {mm["id"]: mm for mm in load_json(folder / "mms.json", [])},
            "campaigns": {
                campaign["id"]: campaign
                for campaign in load_json(folder / "campaigns.json", [])
            },
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
                "mcTransl": load_json(folder / "mcTransl.json", {}),
                "fandomTransl": load_json(folder / "fandomTransl.json", {}),
            }
        else:
            data |= {
                "servants": {
                    svt["collectionNo"]: parse_json_obj_as(
                        ServantWBase, svt
                    ).model_dump()
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
        return parse_json_obj_as(WikiData, data)

    def sort(self):
        self.servants = sort_dict(self.servants)
        self.craftEssences = sort_dict(self.craftEssences)
        self.commandCodes = sort_dict(self.commandCodes)
        for ce in self.craftEssences.values():
            ce.characters.sort()
            ce.unknownCharacters.sort()
        for cc in self.commandCodes.values():
            cc.characters.sort()
            cc.unknownCharacters.sort()
        events = list(self.events.values())
        events.sort(key=lambda event: event.id)
        self.events = {event.id: event for event in events}
        campaigns = list(self.campaigns.values())
        campaigns.sort(key=lambda campaign: abs(campaign.startedAt))
        self.campaigns = {campaign.id: campaign for campaign in campaigns}
        self.wars = sort_dict(self.wars)
        summons = list(self.summons.values())
        summons.sort(key=lambda summon: summon.startTime.JP or NEVER_CLOSED_TIMESTAMP)
        self.summons = {summon.id: summon for summon in summons}
        self.mcTransl.clean_untranslated()
        self.mcTransl.sort()
        self.fandomTransl.clean_untranslated()
        self.fandomTransl.sort()
        mms = list(self.mms.values())
        mms.sort(key=lambda x: x.id)
        self.mms = {mm.id: mm for mm in mms}

    # read: main=True, wiki=False
    # save: main=False, wiki=True
    def save(self, full_version: bool):
        folder = settings.output_wiki
        encoder = _get_encoder(exclude_default=True)
        encoder_full = _get_encoder(exclude_default=False)
        if full_version:
            dump_json(self.mcTransl, settings.output_wiki / "mcTransl.json")
            dump_json(self.fandomTransl, settings.output_wiki / "fandomTransl.json")
            dump_json_beautify(
                list(self.servants.values()), folder / "servants.json", default=encoder
            )
            dump_json_beautify(
                list(self.craftEssences.values()),
                folder / "craftEssences.json",
                default=encoder,
            )
            dump_json_beautify(
                list(self.commandCodes.values()),
                folder / "commandCodes.json",
                default=encoder,
            )
            dump_json_beautify(
                list(self.events.values()),
                folder / "events.json",
                default=encoder,
            )
            dump_json_beautify(
                list(self.summons.values()),
                folder / "summons.json",
                default=encoder,
            )
        dump_json_beautify(
            list(self.wars.values()), folder / "wars.json", default=encoder_full
        )
        dump_json_beautify(
            list(self.campaigns.values()),
            folder / "campaigns.json",
            default=encoder_full,
        )
        dump_json(
            [mm.model_dump(exclude_defaults=True) for mm in self.mms.values()],
            settings.output_wiki / "mms.json",
        )

        include_event_keys = set(EventWBase.model_fields.keys())
        events_base = [
            dict(iter_model(event, include=include_event_keys))
            for event in self.events.values()
            if (event.id // 10000)
            not in [2, 3, 7]  # combineCampaign, svtequipCombineCampaign, questCampaign
            and event.name
            not in [
                "[FFFF00]開放条件緩和中！[-]",
            ]
        ]
        dump_json_beautify(
            events_base, folder / "eventsBase.json", default=encoder_full
        )

        include_summon_keys = set(LimitedSummonBase.model_fields.keys())
        summons_base = [
            dict(iter_model(summon, include=include_summon_keys))
            for summon in self.summons.values()
        ]
        dump_json_beautify(
            summons_base, folder / "summonsBase.json", default=encoder_full
        )

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

    def get_event(self, event_id: int, name: str):
        return self.events.setdefault(event_id, EventW(id=event_id, name=name))

    def get_war(self, war_id: int):
        return self.wars.setdefault(war_id, WarW(id=war_id))


def _get_encoder(exclude_default: bool):
    def _encoder(obj):
        if isinstance(obj, BaseModelTrim):
            return obj.model_dump(exclude_none=True, exclude_defaults=True)
        elif isinstance(obj, MappingBase):
            return obj.model_dump(exclude_none=True)
        elif isinstance(obj, BaseModel):
            return dict(iter_model(obj, exclude_defaults=exclude_default))
        return pydantic_encoder(obj)

    return _encoder


class AppNews(BaseModel):
    type: int | None = None
    priority: int | None = None
    startTime: str | None = None
    endTime: str | None = None
    title: str | None = None
    content: str | None = None
    image: str | None = None
    link: str | None = None
