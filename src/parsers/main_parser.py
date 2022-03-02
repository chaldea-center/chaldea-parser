import datetime
import hashlib
import re
import shutil
import time
from pathlib import Path
from typing import AnyStr, Match, TypeVar

import orjson
import requests
from app.schemas.common import NiceTrait, Region, RepoInfo
from app.schemas.gameenums import (
    NiceEventType,
    NiceGiftType,
    NiceItemType,
    NiceQuestAfterClearType,
)
from app.schemas.nice import (
    AscensionAdd,
    EnemyDrop,
    ExtraAssets,
    NiceBaseFunction,
    NiceBaseSkill,
    NiceBgm,
    NiceEquip,
    NiceEventLotteryBox,
    NiceEventMission,
    NiceEventMissionCondition,
    NiceEventPointBuff,
    NiceEventReward,
    NiceEventTowerReward,
    NiceFunction,
    NiceGift,
    NiceItemAmount,
    NiceLore,
    NiceQuest,
    NiceQuestPhase,
    NiceQuestType,
    NiceServant,
    NiceShop,
    NiceSkill,
    NiceTd,
    QuestEnemy,
    Vals,
)
from pydantic import BaseModel
from pydantic.json import pydantic_encoder
from requests_cache import CachedResponse

from ..config import settings
from ..schemas.common import AtlasExportFile, DataVersion, FileVersion, OpenApiInfo
from ..schemas.const_data import ConstGameData
from ..schemas.gamedata import (
    ExchangeTicket,
    ExtData,
    FixedDrop,
    MappingBase,
    MappingData,
    MappingStr,
    MasterData,
)
from ..schemas.wiki_data import (
    CommandCodeW,
    CraftEssenceW,
    EventWBase,
    MooncellTranslation,
)
from ..utils import (
    NOT_CLOSED_TIMESTAMP,
    AtlasApi,
    NumDict,
    Worker,
    count_time,
    dump_json,
    load_json,
    logger,
)
from ..utils.nullsafe import nullsafe, undefined


_ = nullsafe

_KT = TypeVar("_KT", str, int)
_KV = TypeVar("_KV", str, int)

# print(f'{__name__} version: {datetime.datetime.now().isoformat()}')

MIN_APP = "1.6.7"


# noinspection DuplicatedCode
class MainParser:
    def __init__(self):
        self.jp_data = MasterData(region=Region.JP)
        # self.wiki_data = WikiData()
        self.ext_data = ExtData()
        self.base_skills: dict[int, NiceBaseSkill] = {}
        self.base_functions: dict[int, NiceBaseFunction] = {}

    @count_time
    def start(self):
        self.update_exported_files()
        self.ext_data = ExtData.parse_obj(
            {
                "wiki_data": load_json(settings.output_wiki / "wiki_data.json", {}),
                "summons": load_json(settings.output_wiki / "summons.json", []),
            }
        )
        self.jp_data = self.load_master_data(Region.JP)
        self.gen_base_data()
        self.merge_all_mappings()
        if settings.skip_quests:
            logger.warning("skip checking quests data")
        else:
            self.filter_quests()
        self.exchange_tickets()
        if not settings.output_dist.joinpath("drop_rate.json").exists():
            logger.info("drop_rate.json not exist, run domus_aurea parser")
            from .domus_aurea import run_drop_rate_update

            run_drop_rate_update()
        self.save_data()

    @staticmethod
    def update_exported_files():
        worker = Worker("exported_file")

        def _add_download_task(_url, _fp):
            Path(_fp).write_bytes(requests.get(_url).content)
            logger.info(f"{_fp}: update exported file from {_url}")

        fp_openapi = settings.atlas_export_dir / "openapi.json"
        fp_info = settings.atlas_export_dir / "info.json"

        openapi_remote = requests.get(AtlasApi.full_url("openapi.json")).json()
        openapi_local = load_json(fp_openapi)

        api_changed = not openapi_local or OpenApiInfo.parse_obj(
            openapi_remote["info"]
        ) != OpenApiInfo.parse_obj(openapi_local["info"])
        if api_changed:
            logger.info(f'API changed:\n{dict(openapi_remote["info"], description="")}')

        info_remote = requests.get(AtlasApi.full_url("info")).json()
        info_local = load_json(fp_info, {})

        for region, info in info_remote.items():
            region_changed = not info_local.get(region) or RepoInfo.parse_obj(
                info_local[region]
            ) != RepoInfo.parse_obj(info)

            for f in AtlasExportFile.__members__.values():  # type:AtlasExportFile
                fp_export = f.cache_path(region)
                fp_export.parent.mkdir(parents=True, exist_ok=True)
                if api_changed or region_changed or not fp_export.exists():
                    url = f.resolve_link(region)
                    worker.add(_add_download_task, url, fp_export)
                else:
                    # logger.info(f'{fp_export}: already updated')
                    pass
        worker.wait()
        dump_json(info_remote, fp_info)
        dump_json(openapi_remote, fp_openapi)
        print(f"Exported files updated:\n{dump_json(info_remote)}")

    @staticmethod
    def load_master_data(region: Region) -> MasterData:
        print(f"loading {region} master data")
        data = {}
        for k in MasterData.__fields__:
            fp = settings.atlas_export_dir / region.value / f"{k}.json"
            v = load_json(fp)
            if v:
                data[k] = v
            # print(f'loading {k}: {fp}: {None if v is None else len(data[k])} items')
        data["region"] = f"{region}"
        master_data = MasterData.parse_obj(data)
        master_data.nice_event = [
            event
            for event in master_data.nice_event
            if event.type
            not in (
                NiceEventType.combineCampaign,
                NiceEventType.svtequipCombineCampaign,
                NiceEventType.questCampaign,
            )
        ]
        return master_data

    def filter_quests(self):
        """
        1. add main story's free quests + daily quests' phase data to game_data.questPhases
        2. count each war's one-off questPhase's fixed drop
        """
        print("processing quest data")

        def _get_phase_key(quest_phase: NiceQuestPhase) -> int:
            return quest_phase.id * 100 + quest_phase.phase

        def _check_quest_phase_in_recent(response: CachedResponse):
            try:
                phase_data = orjson.loads(response.content)
                return (
                    phase_data["openedAt"]
                    > time.time() - settings.quest_phase_expire * 24 * 3600
                )
            except Exception as e:
                print(e)
                return True

        def _check_one_quest(quest: NiceQuest):
            # main story's free
            last_phase = quest.phases[-1]
            last_phase_key = quest.id * 100 + last_phase
            if quest.type == NiceQuestType.free:
                self.jp_data.cachedQuestPhases[last_phase_key] = AtlasApi.api_model(
                    f"/nice/JP/quest/{quest.id}/{last_phase}",
                    model=NiceQuestPhase,
                    filter_fn=_check_quest_phase_in_recent,
                )
                return
            if quest.warId == 1002:  # 曜日クエスト
                self.jp_data.cachedQuestPhases[last_phase_key] = AtlasApi.api_model(
                    f"/nice/JP/quest/{quest.id}/{last_phase}",
                    model=NiceQuestPhase,
                )
                return

            if quest.afterClear not in (
                NiceQuestAfterClearType.close,
                NiceQuestAfterClearType.resetInterval,
            ):
                return

            # fixed drops
            for phase in quest.phases:
                if phase in quest.phasesNoBattle:
                    continue
                phase_data = None
                if phase in quest.phasesWithEnemies:
                    phase_data = AtlasApi.api_model(
                        f"/nice/JP/quest/{quest.id}/{phase}",
                        NiceQuestPhase,
                        filter_fn=_check_quest_phase_in_recent,
                    )
                else:
                    quest_na = self.jp_data.cachedQuestsNA.get(quest.id)
                    if quest_na and phase in quest_na.phasesWithEnemies:
                        phase_data = AtlasApi.api_model(
                            f"/nice/NA/quest/{quest.id}/{phase}",
                            NiceQuestPhase,
                            filter_fn=_check_quest_phase_in_recent,
                        )
                if phase_data is None:
                    continue
                phase_drops: NumDict[int, int] = NumDict()
                for drop in [
                    _drop
                    for stage in phase_data.stages
                    for enemy in stage.enemies
                    for _drop in enemy.drops
                ]:
                    if (
                        drop.type == NiceGiftType.item
                        and drop.dropCount >= drop.runs * 0.95 > 0
                    ):
                        phase_drops.add_one(
                            drop.objectId, round(drop.dropCount / drop.runs) * drop.num
                        )
                phase_drops.drop_negative()
                if phase_drops:
                    phase_key = _get_phase_key(phase_data)
                    self.jp_data.questPhaseFixedDrops[phase_key] = FixedDrop(
                        key=phase_key, items=phase_drops
                    )

        worker = Worker("quest", func=_check_one_quest)
        _now = int(time.time()) + 60 * 24 * 3600
        for war in self.jp_data.nice_war:
            if war.id == 9999:  # Chaldea Gate
                for spot in war.spots:
                    spot.quests.clear()
                continue
            if war.id == 1002:  # 曜日クエスト
                # remove closed quests
                for spot in war.spots:
                    spot.quests = [
                        q
                        for q in spot.quests
                        if (
                            q.closedAt > NOT_CLOSED_TIMESTAMP
                            and q.afterClear == NiceQuestAfterClearType.repeatLast
                        )
                    ]
            for _quest in [q for spot in war.spots for q in spot.quests]:
                if not _quest.phases:
                    continue
                if _quest.type == NiceQuestType.free:
                    worker.add_default(_quest)
                    continue
                if _quest.warId == 1002:
                    if (
                        _quest.closedAt > NOT_CLOSED_TIMESTAMP
                        and _quest.afterClear == NiceQuestAfterClearType.repeatLast
                    ):
                        worker.add_default(_quest)
                        continue
                if _quest.afterClear not in (
                    NiceQuestAfterClearType.close,
                    NiceQuestAfterClearType.resetInterval,
                ):
                    continue
                if not _quest.phasesWithEnemies:
                    _quest_na = self.jp_data.cachedQuestsNA.get(_quest.id)
                    if not _quest_na or not _quest_na.phasesWithEnemies:
                        continue
                worker.add_default(_quest)

                if (
                    _quest.type != NiceQuestType.free
                    and _quest.warId != 1002
                    and _quest.afterClear
                    not in (
                        NiceQuestAfterClearType.close,
                        NiceQuestAfterClearType.resetInterval,
                    )
                    and not _quest.phasesWithEnemies
                ):
                    continue
                _quest_na = self.jp_data.cachedQuestsNA.get(_quest.id)
                if not _quest_na or not _quest_na.phasesWithEnemies:
                    continue
                worker.add_default(_quest)
        worker.wait()

    def save_data(self):
        settings.output_wiki.mkdir(parents=True, exist_ok=True)

        dist_folder = settings.output_dist
        dist_folder.mkdir(parents=True, exist_ok=True)
        data = self.jp_data
        data.sort()
        _now = datetime.datetime.now(datetime.timezone.utc)

        print("updating wiki/events_base.json")
        wiki_event_base = {
            e["id"]: EventWBase.parse_obj(e)
            for e in load_json(settings.output_wiki / "events_base.json", [])
        }
        wiki_event_base_new = []
        for event in self.jp_data.nice_event:
            event_base = wiki_event_base.get(event.id) or EventWBase(
                id=event.id, name=event.name
            )
            event_base.name = event.name
            wiki_event_base_new.append(event_base)
        dump_json(
            wiki_event_base_new,
            settings.output_wiki / "events_base.json",
            default=pydantic_encoder,
        )

        print("Saving data")
        cur_version = DataVersion(
            timestamp=int(_now.timestamp()),
            utc=_now.isoformat(timespec="seconds"),
            minimalApp=MIN_APP,
            files={},
        )
        try:
            _last_version = DataVersion.parse_file(
                settings.output_dist / "version.json"
            )
        except:  # noqa
            _last_version = cur_version.copy(deep=True)
        if not settings.is_debug:
            for f in settings.output_dist.glob("**/*"):
                if f.name == "drop_rate.json":
                    continue
                if f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)

        def _get_file_version(_fn: str, key: str, _bytes: bytes) -> FileVersion:
            md5 = hashlib.md5()
            md5.update(_bytes)
            _hash = md5.hexdigest()[:6]
            if _fn in _last_version.files:
                _fv = _last_version.files[_fn]
                if _hash == _fv.hash and key == _fv.key:
                    return _last_version.files[_fn].copy()
            return FileVersion(
                key=key,
                filename=_fn,
                timestamp=int(_now.timestamp()),
                hash=_hash,
                size=len(_bytes),
            )

        def _dump(_fn: str, obj=None, per_file: int = None, encoder=None):
            if encoder is None:
                encoder = self._encoder
            assert not _fn.lower().endswith(".json"), _fn
            fn_splits = _fn.split("_")
            key = "".join([fn_splits[0]] + [x.title() for x in fn_splits[1:]])
            if per_file is not None:
                assert per_file > 0 and isinstance(obj, list), (per_file, type(obj))
                n = len(obj) // per_file + 1
                for i in range(n):
                    _fn_i = f"{_fn}.{i + 1}.json"
                    _bytes = orjson.dumps(
                        obj[i * per_file : (i + 1) * per_file],
                        default=encoder,
                        option=orjson.OPT_NON_STR_KEYS,
                    )
                    cur_version.files[_fn_i] = _get_file_version(_fn_i, key, _bytes)
                    dist_folder.joinpath(_fn_i).write_bytes(_bytes)
                    print(f"dump {_fn_i}")
            else:
                _fp_0 = dist_folder / f"{_fn}.json"
                if obj is None:
                    if not _fp_0.exists():
                        logger.warning(f"skip non-exist file: {_fp_0}")
                        return
                    _bytes = _fp_0.read_bytes()
                    print(f"read file: {_fp_0.name}")
                else:
                    _bytes = orjson.dumps(
                        obj, default=encoder, option=orjson.OPT_NON_STR_KEYS
                    )
                cur_version.files[_fp_0.name] = _get_file_version(
                    _fp_0.name, key, _bytes
                )
                if obj is not None:
                    dist_folder.joinpath(_fp_0.name).write_bytes(_bytes)
                    print(f"dump {_fp_0.name}")

        # save by priority
        _dump("wiki_data", self.ext_data.wiki_data)
        _dump("mapping_data", data.mappingData.dict(exclude_none=True))

        _dump("servants", data.nice_servant_lore, 100)
        _dump("items", data.nice_item)
        old_events = set()
        # _3year = int(time.time()) - 3 * 365 * 24 * 3600
        # for event in data.nice_event:
        #     if event.endedAt < _3year:
        #         old_events.add(event.id)
        _dump("events", [e for e in data.nice_event if e.id not in old_events], 50)
        _dump(
            "wars", [war for war in data.nice_war if war.eventId not in old_events], 40
        )
        _dump("entities", data.basic_svt)
        _dump("exchange_tickets", data.exchangeTickets)
        _dump("craft_essences", data.nice_equip_lore, 500)
        _dump("command_codes", data.nice_command_code)
        _dump("mystic_codes", data.nice_mystic_code)
        if data.questPhaseFixedDrops:
            _dump("fixed_drops", list(data.questPhaseFixedDrops.values()))
        _dump("drop_rate")
        _dump("bgms", data.nice_bgm, encoder=pydantic_encoder)
        # sometimes disabled quest parser when debugging
        if data.cachedQuestPhases:
            _dump("quest_phases", list(data.cachedQuestPhases.values()), 150)
        base_skills = list(self.base_skills.values())
        base_skills.sort(key=lambda x: x.id)
        _dump("base_skills", base_skills)
        base_functions = list(self.base_functions.values())
        base_functions.sort(key=lambda x: x.funcId)
        _dump("base_functions", base_functions)
        _dump(
            "const_data",
            ConstGameData(
                attributeRelation=data.NiceAttributeRelation,
                buffActions=data.NiceBuffList_ActionList,
                cardInfo=data.NiceCard,
                classAttackRate=data.NiceClassAttackRate,
                classRelation=data.NiceClassRelation,
                constants=data.NiceConstant,
                svtGrailCost=data.NiceSvtGrailCost,
                userLevel=data.NiceUserLevel,
            ),
        )
        _dump("summons", self.ext_data.summons)

        changed = False
        for k, f in cur_version.files.items():
            f_old = _last_version.files.get(k)
            if not f_old:
                changed = True
                print(f"[Publish] create new file {f.filename}")
            elif f != f_old:
                changed = True
                print(f"[Publish] file updated {f.filename}")

        if _last_version.minimalApp == cur_version.minimalApp and not changed:
            cur_version.timestamp = _last_version.timestamp
            cur_version.utc = _last_version.utc

        dump_json(cur_version, dist_folder / "version.json")
        print(dump_json(cur_version))
        self.copy_static()
        Path(settings.output_dir).joinpath("commit-msg.txt").write_text(
            f"Version({cur_version.minimalApp}, {cur_version.utc})"
        )
        print("Updating mappings")
        from .update_mapping import run_mapping_update

        run_mapping_update()

    def _encoder(self, obj):
        exclude = set()
        if obj is undefined:
            return None
        if isinstance(obj, NiceBgm):
            exclude.update({"name", "fileName", "notReleased", "audioAsset"})
        if isinstance(obj, NiceTrait):
            exclude.add("name")
        if isinstance(obj, NiceItemAmount):
            return {"itemId": obj.item.id, "amount": obj.amount}
        if isinstance(obj, NiceGift):
            exclude.update({"id", "priority"})
        if isinstance(obj, NiceLore):
            # print("ignore lore comments&voices")
            exclude.update({"comments", "voices"})
        if isinstance(obj, NiceSkill):
            if obj.id not in self.base_skills:
                self.base_skills[obj.id] = NiceBaseSkill.parse_obj(obj.dict())
            exclude.update(NiceBaseSkill.__fields__.keys())
            exclude.remove("id")
            if obj.ruby in ("", "-"):
                exclude.add("ruby")
        elif isinstance(obj, NiceBaseSkill):
            exclude.add("detail")
        if isinstance(obj, NiceFunction):
            if obj.funcId not in self.base_functions:
                self.base_functions[obj.funcId] = NiceBaseFunction.parse_obj(obj.dict())
            exclude.update(NiceBaseFunction.__fields__.keys())
            exclude.remove("funcId")

            def _trim_dup(svals: list[Vals] | None):
                if not svals:
                    return
                v0 = svals[0]
                if len(set([v == v0 for v in svals])) == 1:
                    svals.clear()
                    svals.append(v0)

            _trim_dup(obj.svals)
            _trim_dup(obj.svals2)
            _trim_dup(obj.svals3)
            _trim_dup(obj.svals4)
            _trim_dup(obj.svals5)
        elif isinstance(obj, NiceBaseFunction):
            ...
        if isinstance(obj, NiceTd):
            exclude.add("detail")
        if isinstance(obj, NiceQuest):
            # exclude.update({"warLongName"})
            pass
        if isinstance(obj, QuestEnemy):
            exclude.update({"drops", "skills", "noblePhantasm", "ai", "limit"})
        if isinstance(obj, EnemyDrop):
            exclude.update({"dropExpected", "dropVariance"})
        if isinstance(obj, NiceEventMissionCondition):
            exclude.update({"missionTargetId", "conditionMessage"})
        if isinstance(obj, NiceEventMission):
            exclude.update(
                {
                    "flag",
                    "missionTargetId",
                    "detail",
                    "startedAt",
                    "endedAt",
                    "closedAt",
                    "rewardRarity",
                    "notfyPriority",
                    "presentMessageId",
                }
            )
        if isinstance(obj, NiceEventTowerReward):
            exclude.update({"boardMessage", "rewardGet", "banner"})
        if isinstance(obj, NiceEventLotteryBox):
            exclude.update({"id", "priority", "detail", "icon", "banner"})
        if isinstance(obj, NiceEventReward):
            exclude.update({"bgImagePoint", "bgImageGet"})
        if isinstance(obj, NiceEventPointBuff):
            exclude.update({"detail"})
        if isinstance(obj, NiceShop):
            exclude.update(
                {
                    "id",
                    "name",
                    "baseShopId",
                    "eventId",
                    "detail",
                    "openedAt",
                    "closedAt",
                    "warningMessage",
                }
            )
        if isinstance(obj, (NiceServant, NiceEquip)):
            exclude.update({"expFeed", "expGrowth"})
        if isinstance(obj, (AscensionAdd, ExtraAssets)):
            obj = obj.dict(exclude_none=True, exclude_defaults=True)
            # print('start encoding ', type(obj))
            for k in list(obj.keys()):
                if isinstance(obj[k], dict):
                    for kk in list(obj[k].keys()):
                        if not obj[k][kk]:
                            obj[k].pop(kk)
                if not obj[k]:
                    obj.pop(k)
            # print('ended encoding ', type(obj))
            return obj
        if isinstance(obj, BaseModel):
            # noinspection PyProtectedMember
            return dict(
                obj._iter(
                    to_dict=False,
                    exclude_none=True,
                    exclude_defaults=True,
                    exclude=exclude,
                )
            )
        return pydantic_encoder(obj)

    def exchange_tickets(self):
        name_id_map = {item.name: item.id for item in self.jp_data.nice_item}
        tickets: list[ExchangeTicket] = []
        for item in self.jp_data.nice_item:
            if item.type != NiceItemType.itemSelect:
                continue
            match = re.search(r"^(\d+)月交換券\((\d+)\)$", item.name)
            if not match:
                continue
            year, month = match.group(2), match.group(1)
            m2 = re.search(r"^(.+)、(.+)、(.+)の中から一つと交換ができます。$", item.detail)
            item_ids = [name_id_map.get(m2.group(i)) for i in (1, 2, 3)]
            if None in item_ids:
                print(
                    f"exchange ticket: unknown items: {item_ids}: {item.id}-{item.name}:{item.detail}"
                )
            tickets.append(
                ExchangeTicket(
                    id=int(year) * 100 + int(month),
                    year=int(year),
                    month=int(month),
                    items=item_ids,
                )
            )
        self.jp_data.exchangeTickets = tickets

    def merge_all_mappings(self):
        self._merge_official_mappings(Region.CN)
        self._fix_cn_translation()
        self._merge_mc_translation()
        self._merge_official_mappings(Region.NA)
        self._add_na_mapping()
        self._merge_official_mappings(Region.TW)
        self._merge_official_mappings(Region.KR)
        self._merge_repo_mapping()

    def _merge_official_mappings(self, region: Region):
        print(f"merging official translations from {region}")
        mappings = self.jp_data.mappingData
        jp_data = self.jp_data
        data = self.load_master_data(region)

        # trait
        for k, v in self.jp_data.nice_trait.items():
            m_trait = mappings.trait.setdefault(k, MappingBase())
            m_trait.update(Region.JP, v.value, skip_exists=True)

        def _update_mapping(
            m: dict[_KT, MappingBase[_KV]],
            _key: _KT,
            value: _KV,
            skip_exists=False,
            skip_unknown_key=False,
        ):
            if _key is None or _key is undefined:
                return
            m.setdefault(_key, MappingBase())
            return self._update_key_mapping(
                region,
                key_mapping=m,
                _key=_key,
                value=value,
                skip_exists=skip_exists,
                skip_unknown_key=skip_unknown_key,
            )

        # str key
        for item_jp in jp_data.nice_item:
            _update_mapping(
                mappings.item_names, item_jp.name, _(data.item_dict)[item_jp.id].name
            )
        for cv_jp in jp_data.nice_cv:
            _update_mapping(
                mappings.cv_names, cv_jp.name, _(data.cv_dict)[cv_jp.id].name
            )
            cv_names = [str(s).strip() for s in re.split(r"[&＆]", cv_jp.name)]
            if len(cv_names) > 1:
                for one_name in cv_names:
                    mappings.cv_names.setdefault(one_name, MappingBase())
        for illustrator_jp in jp_data.nice_illustrator:
            _update_mapping(
                mappings.illustrator_names,
                illustrator_jp.name,
                _(data.illustrator_dict)[illustrator_jp.id].name,
            )
            illustrator_names = [
                str(s).strip() for s in re.split(r"[&＆]", illustrator_jp.name)
            ]
            if len(illustrator_names) > 1:
                for one_name in illustrator_names:
                    mappings.illustrator_names.setdefault(one_name, MappingBase())
        for bgm_jp in jp_data.nice_bgm:
            _update_mapping(
                mappings.bgm_names, bgm_jp.name, _(data.bgm_dict)[bgm_jp.id].name
            )

        for event_jp in jp_data.nice_event:
            mappings.event_names.setdefault(event_jp.name, MappingBase())
            mappings.event_names.setdefault(event_jp.shortName, MappingBase())
            event = data.event_dict.get(event_jp.id)
            if event is None:
                continue
            if event.startedAt > time.time():
                continue
            _update_mapping(mappings.event_names, event_jp.name, event.name)
            _update_mapping(mappings.event_names, event_jp.shortName, event.shortName)
        for war_jp in jp_data.nice_war:
            mappings.war_names.setdefault(war_jp.name, MappingBase())
            mappings.war_names.setdefault(war_jp.longName, MappingBase())
            war = data.war_dict.get(war_jp.id)
            if war is None:
                continue
            if war.id < 11000 and war.lastQuestId == 0:  # not released wars
                continue
            _update_mapping(mappings.war_names, war_jp.name, war.name)
            _update_mapping(mappings.war_names, war_jp.longName, war.longName)
        for spot_jp in jp_data.spot_dict.values():
            _update_mapping(
                mappings.spot_names, spot_jp.name, _(data.spot_dict)[spot_jp.id].name
            )

        for svt_jp in jp_data.nice_servant_lore:
            svt = _(data.svt_id_dict)[svt_jp.id]
            _update_mapping(mappings.svt_names, svt_jp.name, svt.name)
            if not svt:
                continue
            mappings.svt_release.setdefault(svt_jp.id, MappingBase()).update(region, 1)
            skill_prog = mappings.skill_state.setdefault(svt_jp.id, MappingBase())
            skill_prog.update(
                region, {skill.id: skill.strengthStatus for skill in svt.skills}
            )
            td_prog = mappings.td_state.setdefault(svt_jp.id, MappingBase())
            td_prog.update(
                region, {td.id: td.strengthStatus for td in svt.noblePhantasms}
            )
            # if region != Region.JP and svt.profile.comments:
            #     svt_w = self.wiki_data.servants.setdefault(svt_jp.collectionNo,
            #       ServantW(collectionNo=svt.collectionNo))
            #     svt_w.profileComment.update(region, svt.profile.comments)
        for costume_id, costume_jp in jp_data.costume_dict.items():
            costume = _(data.costume_dict)[costume_id]
            _update_mapping(mappings.costume_names, costume_jp.name, costume.name)
            _update_mapping(
                mappings.costume_names, costume_jp.shortName, costume.shortName
            )
            mappings.costume_detail.setdefault(
                costume_jp.costumeCollectionNo, MappingStr()
            ).update(region, costume.detail)
        for ce_jp in jp_data.nice_equip_lore:
            ce = _(data.ce_id_dict)[ce_jp.id]
            _update_mapping(mappings.ce_names, ce_jp.name, ce.name)
            if not ce:
                continue
            mappings.ce_release.setdefault(ce_jp.id, MappingBase()).update(region, 1)
            if region != Region.JP and ce.profile.comments:
                ce_w = self.ext_data.wiki_data.craftEssences.setdefault(
                    ce_jp.collectionNo, CraftEssenceW(collectionNo=ce.collectionNo)
                )
                ce_w.profile.update(region, ce.profile.comments[0].comment)

        for cc_jp in jp_data.nice_command_code:
            cc = _(data.cc_id_dict)[cc_jp.id]
            _update_mapping(mappings.cc_names, cc_jp.name, cc.name)
            if not cc:
                continue
            mappings.cc_release.setdefault(cc_jp.id, MappingBase()).update(region, 1)
            if region != Region.JP and cc.comment:
                cc_w = self.ext_data.wiki_data.commandCodes.setdefault(
                    cc_jp.collectionNo, CommandCodeW(collectionNo=cc.collectionNo)
                )
                cc_w.profile.update(region, cc.comment)
        for mc_jp in jp_data.nice_mystic_code:
            mc = _(data.mc_dict)[mc_jp.id]
            _update_mapping(mappings.mc_names, mc_jp.name, mc.name)
            if mc and region != Region.JP and mc.detail:
                # mc_w = self.wiki_data.mysticCodes.setdefault(mc_jp.id, MysticCodeW(id=mc_jp.id))
                # mc_w.detail.update(region, mc.detail)
                mappings.mc_detail.setdefault(mc_jp.id, MappingStr()).update(
                    region, mc.detail
                )
        for skill_jp in jp_data.skill_dict.values():
            if skill_jp.name in mappings.ce_names or skill_jp.name in mappings.cc_names:
                continue
            skill = _(data.skill_dict)[skill_jp.id]
            _update_mapping(mappings.skill_names, skill_jp.name, skill.name)
            _update_mapping(
                mappings.skill_detail, skill_jp.unmodifiedDetail, skill.unmodifiedDetail
            )
        for td_jp in jp_data.td_dict.values():
            td = _(data.td_dict)[td_jp.id]
            _update_mapping(mappings.td_names, td_jp.name, td.name)
            if region != Region.NA:  # always empty for NA
                _update_mapping(mappings.td_ruby, td_jp.ruby, td.ruby)
            _update_mapping(mappings.td_types, td_jp.type, td.type)
            _update_mapping(
                mappings.td_detail, td_jp.unmodifiedDetail, td.unmodifiedDetail
            )
        for func_jp in jp_data.func_dict.values():
            func = _(data.func_dict)[func_jp.funcId]
            _update_mapping(
                mappings.func_popuptext, func_jp.funcPopupText, func.funcPopupText
            )
        for buff_jp in jp_data.buff_dict.values():
            buff = _(data.buff_dict)[buff_jp.id]
            _update_mapping(mappings.buff_names, buff_jp.name, buff.name)
            _update_mapping(mappings.buff_detail, buff_jp.detail, buff.detail)
        for quest_jp in jp_data.main_free_quest_dict.values():
            quest = _(data.main_free_quest_dict)[quest_jp.id]
            _update_mapping(mappings.quest_names, quest_jp.name, quest.name)
        for entity_jp in jp_data.basic_svt:
            entity = _(data.entity_dict)[entity_jp.id]
            _update_mapping(mappings.entity_names, entity_jp.name, entity.name)

        self.jp_data.mappingData = mappings
        del data

    def _merge_mc_translation(self):
        print("merging Mooncell translations for CN")

        def _update_mapping(
            m: dict[_KT, MappingBase[_KV]],
            _key: _KT,
            value: _KV,
            skip_exists=False,
            skip_unknown_key=False,
        ):
            return self._update_key_mapping(
                Region.CN,
                key_mapping=m,
                _key=_key,
                value=value,
                skip_exists=skip_exists,
                skip_unknown_key=skip_unknown_key,
            )

        mappings = self.jp_data.mappingData
        mc_trans = MooncellTranslation.parse_obj(
            load_json(settings.output_wiki / "mc_translation.json", {})
        )
        for svt_no, name in mc_trans.svt_names.items():
            svt = self.jp_data.svt_dict.get(svt_no)
            if svt:
                _update_mapping(mappings.svt_names, svt.name, name, True, True)
        for skill_jp, skill_cn in mc_trans.skill_names.items():
            _update_mapping(mappings.skill_names, skill_jp, skill_cn, True, True)
        for td_name_jp, td_name_cn in mc_trans.td_names.items():
            _update_mapping(mappings.td_names, td_name_jp, td_name_cn, True, True)
        for td_ruby_jp, td_runy_cn in mc_trans.td_ruby.items():
            _update_mapping(mappings.td_ruby, td_ruby_jp, td_runy_cn, True, True)
        for ce_no, name in mc_trans.ce_names.items():
            ce = self.jp_data.ce_dict.get(ce_no)
            if ce:
                _update_mapping(mappings.ce_names, ce.name, name, True, True)
        for cc_no, name in mc_trans.cc_names.items():
            cc = self.jp_data.cc_dict.get(cc_no)
            if cc:
                _update_mapping(mappings.cc_names, cc.name, name, True, True)
        # for event in self.ext_data

    def _fix_cn_translation(self):
        print("fix Chinese translations")
        mappings = self.jp_data.mappingData
        mappings_dict: dict[str, dict] = mappings.dict()
        color_regexes = [
            re.compile(r"(?<![击御威])([力技迅])(?=提升|攻击|指令卡|下降|性能|耐性|威力)"),
            re.compile(r"(?<=[:：])([力技迅])$"),
            re.compile(r"(?<=[〔（(])[力技迅](?=[)）〕])"),
        ]
        extra_regexes = [re.compile(r"额外(?=攻击|职阶)")]
        for key in (
            "buff_detail",
            "buff_names",
            "func_popuptext",
            "skill_detail",
            "td_detail",
            "skill_names",
        ):
            assert (
                key in mappings.__fields__
            ), f"{key} not in {list(mappings.__fields__.keys())}"

            def _repl(match: Match[AnyStr]) -> AnyStr:
                return {"力": "Buster", "技": "Arts", "迅": "Quick", "额外": "Extra"}[
                    match.group(0)
                ]

            for jp_name, regions in mappings_dict[key].items():
                cn_name2 = cn_name = regions["CN"]
                if not cn_name:
                    continue
                if re.findall(r"Buster|Art|Quick|アーツ|クイック|バスター", jp_name):
                    for regex in color_regexes:
                        cn_name2 = regex.sub(_repl, cn_name2)
                if re.findall(r"Extra|エクストラ", jp_name):
                    for regex in extra_regexes:
                        cn_name2 = regex.sub(_repl, cn_name2)
                if cn_name2 != cn_name:
                    # print(f"Convert CN: {cn_name} -> {cn_name2}")
                    regions["CN"] = cn_name2
        self.test_mapping_dict = mappings_dict
        self.jp_data.mappingData = MappingData.parse_obj(mappings_dict)

    def _add_na_mapping(self):
        print("merging Atlas translations for NA")

        mappings = self.jp_data.mappingData
        import app as app_lib

        na_folder = Path(app_lib.__file__).resolve().parent.joinpath("data/mappings/")
        print("AA mappings path:", na_folder)
        src_mapping: dict[str, dict[str, MappingStr]] = {
            "bgm_names.json": mappings.bgm_names,
            "cc_names.json": mappings.cc_names,
            "cv_names.json": mappings.cv_names,
            "entity_names.json": mappings.entity_names,
            "equip_names.json": mappings.ce_names,
            "event_names.json": mappings.event_names,
            "illustrator_names.json": mappings.illustrator_names,
            "item_names.json": mappings.item_names,
            "mc_names.json": mappings.mc_names,
            "np_names.json": mappings.td_names,
            "quest_names.json": mappings.quest_names,
            "servant_names.json": mappings.svt_names,
            "skill_names.json": mappings.skill_names,
            "spot_names.json": mappings.spot_names,
            "war_names.json": mappings.war_names,
        }
        for src_fn, dest in src_mapping.items():
            source = load_json(na_folder / src_fn, {})
            if not source:
                continue
            for key, trans in dest.items():
                value = source.get(key)
                if value and value == key:
                    continue
                trans.update(Region.NA, value, skip_exists=True)
        self.jp_data.mappingData = mappings

    def _merge_repo_mapping(self):
        print("merging repo translations")

        folder = settings.output_mapping
        mappings = self.jp_data.mappingData
        mapping_dict = orjson.loads(mappings.json())
        mappings_repo = {
            k: load_json(folder / f"{k}.json", {}) for k in MappingData.__fields__
        }
        self._merge_json(mappings_repo, mapping_dict)

        fp_override = folder / "override_mappings.json"
        if not fp_override.exists():
            fp_override.write_text("{}")
        override_data: dict[str, dict[str, dict[str, str]]] = load_json(fp_override, {})
        self._merge_json(mappings_repo, override_data)
        self.jp_data.mappingData = MappingData.parse_obj(mappings_repo)

    @staticmethod
    def _update_key_mapping(
        region: Region,
        key_mapping: dict[_KT, MappingBase[_KV]],
        _key: _KT,
        value: _KV,
        skip_exists=False,
        skip_unknown_key=False,
    ):
        if _key is None or (isinstance(_key, str) and _key.strip("-") == ""):
            return
        if value is None or (isinstance(value, str) and value.strip("-") == ""):
            return
        if skip_unknown_key and _key not in key_mapping:
            return
        one = key_mapping.setdefault(_key, MappingBase())
        if region == Region.JP and _key == value:
            value = None
        one.update(region, value, skip_exists)

    @staticmethod
    def _merge_json(dest: dict, src: dict):
        for key, value in src.items():
            if key not in dest:
                dest[key] = value
                continue
            assert not isinstance(value, list) and not isinstance(dest[key], list)
            if isinstance(value, dict):
                if dest[key] is None:
                    dest[key] = value
                else:
                    MainParser._merge_json(dest[key], value)
            else:
                dest[key] = value

    @staticmethod
    def copy_static():
        shutil.copytree(
            Path(__file__).resolve().parent.parent / "static",
            settings.output_dist,
            dirs_exist_ok=True,
        )

    def gen_base_data(self):
        # self.jp_data
        ...
