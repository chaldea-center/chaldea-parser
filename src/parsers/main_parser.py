import hashlib
import itertools
import re
import shutil
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, AnyStr, Iterable, Match, TypeVar

import orjson
import pytz
import requests
from app.schemas.common import NiceTrait, Region
from app.schemas.enums import OLD_TRAIT_MAPPING, NiceSvtType
from app.schemas.gameenums import (
    NiceGiftType,
    NiceQuestAfterClearType,
    NiceSpotOverwriteType,
    NiceSvtFlag,
    NiceWarOverwriteType,
    SvtType,
)
from app.schemas.nice import (
    AscensionAdd,
    AscensionAddEntryStr,
    BasicServant,
    EnemyDrop,
    ExtraAssets,
    NiceBaseFunction,
    NiceBgm,
    NiceBuff,
    NiceBuffType,
    NiceCommandCode,
    NiceEquip,
    NiceEvent,
    NiceEventDiggingBlock,
    NiceEventLotteryBox,
    NiceEventMission,
    NiceEventMissionCondition,
    NiceEventPointBuff,
    NiceEventReward,
    NiceEventTowerReward,
    NiceEventTreasureBox,
    NiceFunction,
    NiceGift,
    NiceItem,
    NiceItemAmount,
    NiceLore,
    NiceLoreComment,
    NiceMap,
    NiceMapGimmick,
    NiceMasterMission,
    NiceQuest,
    NiceQuestPhase,
    NiceQuestType,
    NiceServant,
    NiceShop,
    NiceSkill,
    NiceTd,
    NiceWar,
    QuestEnemy,
)
from pydantic import BaseModel, parse_file_as, parse_obj_as
from pydantic.json import pydantic_encoder

from ..config import PayloadSetting, settings
from ..schemas.common import (
    AtlasExportFile,
    DataVersion,
    FileVersion,
    MappingBase,
    MappingStr,
    MstClass,
    MstClassRelation,
    MstViewEnemy,
    OpenApiInfo,
)
from ..schemas.const_data import ConstGameData
from ..schemas.gamedata import (
    FixedDrop,
    MappingData,
    MasterData,
    NewAddedData,
    NiceBaseSkill,
    NiceBaseTd,
    NiceEquipSort,
)
from ..schemas.mappings import CN_REPLACE
from ..schemas.wiki_data import AppNews, CommandCodeW, WikiData, WikiTranslation
from ..utils import (
    NEVER_CLOSED_TIMESTAMP,
    AtlasApi,
    DownUrl,
    McApi,
    NumDict,
    Worker,
    count_time,
    dump_json,
    load_json,
    logger,
    sort_dict,
)
from ..utils.helper import LocalProxy, beautify_file, describe_regions
from ..utils.stopwatch import Stopwatch
from ..wiki import FANDOM, MOONCELL
from ..wiki.wiki_tool import KnownTimeZone
from .core.ticket import parse_exchange_tickets
from .domus_aurea import run_drop_rate_update
from .update_mapping import run_mapping_update


_T = TypeVar("_T")
_KT = TypeVar("_KT", str, int)
_KV = TypeVar("_KV", str, int)

# print(f'{__name__} version: {datetime.datetime.now().isoformat()}')

MIN_APP = "2.2.3"

# TODO in 2.2.4
# remove classInfo=data.NiceClass,
# remove classAttackRate=data.NiceClassAttackRate,
# remove classRelation=data.NiceClassRelation,


# cn_ces: dict[int, tuple[str, float]] = {102022: ("STAR影法師", 1461.5)}
ADD_CES = {
    Region.CN: {
        102022: ("STAR影法師", 1526.4),  # 6th anniversary
        102023: ("STAR影法師", 1526.1),  # 3rd
        102024: ("STAR影法師", 1526.2),  # 4th
        102025: ("STAR影法師", 1526.3),  # 5th
    }
}

# svt_no, questIds
STORY_UPGRADE_QUESTS = {
    1: [1000624, 3000124, 3000607, 3001301, 1000631],
    38: [3000915],  # Cú Chulainn
}


class MainParser:
    def __init__(self):
        self.jp_data = MasterData(region=Region.JP)
        self.wiki_data = WikiData()
        self.huntingQuests: list[int] = []
        self.payload: PayloadSetting = PayloadSetting()
        logger.info(f"Payload: {self.payload}")
        self.stopwatch = Stopwatch("MainParser")
        self.now = datetime.now()

    @count_time
    def start(self):
        self.stopwatch.start()

        if self.payload.event == "gametop":
            time.sleep(300)
            self.gametop()
            settings.commit_msg.write_text(
                f"{describe_regions(self.payload.regions)}Update Gametop"
            )
            return
        elif self.payload.event == "load":
            if self.payload.regions == [Region.JP]:
                self.add_changes_only()
                self.stopwatch.log("dump changes only")
            else:
                logger.info(
                    f"ignore {self.payload.regions} changes for new-only addition"
                )
            print(self.stopwatch.output())
            return

        # check news.json
        parse_file_as(list[AppNews], settings.output_dist / "news.json")

        if self.payload.clear_cache_http:
            logger.warning("clear all http_cache")
            AtlasApi.cache_storage.clear()
            McApi.cache_storage.clear()
        if self.payload.clear_cache_wiki:
            logger.warning("clear all wiki cache")
            MOONCELL.clear()
            FANDOM.clear()

        logger.info("update_exported_files")
        self.update_exported_files()
        self.stopwatch.log("update_export")
        self.wiki_data = WikiData.parse_dir(full_version=True)
        self.huntingQuests = [
            q for event in self.wiki_data.events.values() for q in event.huntingQuestIds
        ]
        self.stopwatch.log(f"load wiki data")
        self.jp_data = self.load_master_data(Region.JP)
        self.merge_all_mappings()
        self.stopwatch.log(f"mappings finish")

        self.filter_quests()
        self.stopwatch.log(f"quests")

        self._post_mappings()

        self.jp_data.exchangeTickets = parse_exchange_tickets(self.jp_data.nice_item)
        if not settings.output_wiki.joinpath("dropRate.json").exists():
            logger.info("dropRate.json not exist, run domus_aurea parser")
            run_drop_rate_update()
        self.save_data()
        print(self.stopwatch.output())

    def add_changes_only(self):
        added = NewAddedData(
            time=datetime.now(pytz.timezone(KnownTimeZone.jst)).isoformat()
        )
        version = DataVersion.parse_file(settings.output_dist / "version.json")

        def load_data_dict(key: str, field_key: str) -> dict[int, dict]:
            out: dict[int, dict] = {}
            for file in version.files.values():
                if file.key == key:
                    for entry in load_json(settings.output_dist / file.filename) or []:
                        out[entry[field_key]] = entry
            return out

        remote_svts: list[dict] = DownUrl.gitaa("mstSvt")
        local_svts = load_data_dict("servants", "collectionNo")
        for svt in remote_svts:
            collection = svt["collectionNo"]
            if (
                collection == 0
                or svt["type"] not in [SvtType.NORMAL, SvtType.ENEMY_COLLECTION_DETAIL]
                or (
                    collection in local_svts
                    and sorted(svt["relateQuestIds"])
                    == sorted(local_svts[collection].get("relateQuestIds", []))
                )
            ):
                continue
            svt = AtlasApi.api_model(
                f"/nice/JP/servant/{collection}?lore=true", NiceServant, 0
            )
            if (
                not svt
                or svt.collectionNo == 0
                or svt.type
                not in [NiceSvtType.normal, NiceSvtType.enemyCollectionDetail]
            ):
                continue
            added.svt.append(svt)

        remote_ces = DownUrl.export("basic_equip")
        local_ces = load_data_dict("craftEssences", "collectionNo")
        for ce in remote_ces:
            collection = ce["collectionNo"]
            if collection == 0 or collection in local_ces:
                continue
            ce = AtlasApi.api_model(
                f"/nice/JP/equip/{collection}?lore=true", NiceEquip, 0
            )
            if not ce or ce.collectionNo == 0:
                continue
            added.ce.append(ce)

        remote_ccs = DownUrl.export("basic_command_code")
        local_ccs = load_data_dict("commandCodes", "collectionNo")
        for cc in remote_ccs:
            collection = cc["collectionNo"]
            if collection == 0 or collection in local_ccs:
                continue
            cc = AtlasApi.api_model(f"/nice/JP/CC/{collection}", NiceCommandCode, 0)
            if not cc or cc.collectionNo == 0:
                continue
            added.cc.append(cc)

        remote_items = DownUrl.export("nice_item")
        local_items = load_data_dict("items", "id")
        for item in remote_items:
            if item["id"] not in local_items:
                added.item.append(NiceItem.parse_obj(item))

        if added.is_empty():
            logger.info(f"No new user playable card added")
            return

        def _encoder(obj):
            if isinstance(obj, BaseModel):
                return obj.dict(exclude_none=True, exclude_defaults=True)
            return pydantic_encoder(obj)

        add_fv = self._normal_dump(added, "addData", encoder=_encoder)
        version.files[add_fv.filename] = add_fv
        version.timestamp = int(self.now.timestamp())
        version.utc = self.now.isoformat(timespec="seconds").split("+")[0]
        dump_json(version, settings.output_dist / "version.json")

        msg = f"[JP] {version.utc} " + ";".join(
            [
                k + " " + ",".join([str(x.get("collectionNo") or x["id"]) for x in v])
                for k, v in added.dict(exclude_defaults=True, exclude={"time"}).items()
            ]
        )
        settings.commit_msg.write_text(msg)

    def update_exported_files(self):
        def _add_download_task(_url, _fp):
            Path(_fp).write_bytes(
                requests.get(_url, headers={"cache-control": "no-cache"}).content
            )
            logger.info(f"{_fp}: update exported file from {_url}")

        fp_openapi = settings.atlas_export_dir / "openapi.json"

        openapi_remote = requests.get(AtlasApi.full_url("openapi.json")).json()
        openapi_local = load_json(fp_openapi)

        api_changed = not openapi_local or OpenApiInfo.parse_obj(
            openapi_remote["info"]
        ) != OpenApiInfo.parse_obj(openapi_local["info"])
        if api_changed:
            logger.info(f'API changed:\n{dict(openapi_remote["info"], description="")}')

        for region in Region.__members__.values():
            worker = Worker(f"exported_file_{region}")
            fp_info = settings.atlas_export_dir / region.value / "info.json"
            info_local = load_json(fp_info) or {}
            info_remote = DownUrl.export("info.json", region)
            region_changed = (
                region in self.payload.regions and self.payload.force_update_export
            ) or info_local != info_remote

            for f in AtlasExportFile.__members__.values():
                fp_export = f.cache_path(region)
                fp_export.parent.mkdir(parents=True, exist_ok=True)
                if api_changed or region_changed or not fp_export.exists():
                    if region not in self.payload.regions:
                        self.payload.regions.append(region)
                    url = f.resolve_link(region)
                    worker.add(_add_download_task, url, fp_export)
                else:
                    # logger.info(f'{fp_export}: already updated')
                    pass
            worker.wait()
            dump_json(info_remote, fp_info)
            logger.debug(f"Exported files updated:\n{info_remote}")
        dump_json(openapi_remote, fp_openapi)

    def load_master_data(self, region: Region, add_trigger: bool = True) -> MasterData:
        logger.info(f"loading {region} master data")
        data = {}
        for k in MasterData.__fields__:
            fp = settings.atlas_export_dir / region.value / f"{k}.json"
            v = load_json(fp)
            if v:
                data[k] = v
            # print(f'loading {k}: {fp}: {None if v is None else len(data[k])} items')
        data["region"] = f"{region}"
        master_data = MasterData.parse_obj(data)

        master_data.nice_event = [event for event in master_data.nice_event]
        if region == Region.JP:
            for add_region, ces in ADD_CES.items():
                for collection, (illustrator, sort_id) in ces.items():
                    ce = AtlasApi.api_model(
                        f"/nice/{add_region}/equip/{collection}?lore=true",
                        NiceEquipSort,
                        expire_after=7 * 24 * 3600,
                    )
                    assert ce and ce.profile
                    ce.profile.illustrator = illustrator
                    ce.sortId = sort_id
                    master_data.nice_equip_lore.append(ce)
        if region == Region.NA:
            self.jp_data.all_quests_na = master_data.quest_dict
        for svt in master_data.nice_servant_lore:
            master_data.remainedQuestIds.update(svt.relateQuestIds)
            master_data.remainedQuestIds.update(svt.trialQuestIds)
        master_data.remainedQuestIds.update(self.huntingQuests)
        master_data.extraMasterMission = [
            mm for mm in master_data.nice_master_mission if mm.id == 10001
        ]
        # raw
        raw_fmt = "https://git.atlasacademy.io/atlasacademy/fgo-game-data/raw/branch/{region}/master/{name}.json"
        master_data.viewEnemy = parse_obj_as(
            list[MstViewEnemy], DownUrl.gitaa("viewEnemy", region)
        )
        master_data.mstClass = parse_obj_as(
            list[MstClass], DownUrl.gitaa("mstClass", region)
        )
        master_data.mstClassRelation = parse_obj_as(
            list[MstClassRelation], DownUrl.gitaa("mstClassRelation", region)
        )

        master_data.mstConstant = {
            e["name"]: e["value"] for e in DownUrl.gitaa("mstConstant", region)
        }

        master_data.sort()
        if not add_trigger:
            self.stopwatch.log(f"master data [{region}] no trigger")
            return master_data

        def _add_trigger_skill(
            buff: NiceBuff | None, skill_id: int | None, is_td=False
        ):
            if buff:
                master_data.mappingData.func_popuptext.setdefault(
                    buff.type.value, MappingStr()
                )
            if not skill_id:
                return
            if is_td:
                if skill_id in master_data.base_tds:
                    return
                td = AtlasApi.api_model(
                    f"/nice/{region}/NP/{skill_id}",
                    NiceBaseTd,
                    expire_after=3600 * 24 * 7,
                )
                if td:
                    master_data.base_tds[skill_id] = td

            else:
                if skill_id in master_data.base_skills:
                    return
                skill = AtlasApi.api_model(
                    f"/nice/{region}/skill/{skill_id}",
                    NiceBaseSkill,
                    expire_after=3600 * 24 * 7,
                )
                if skill:
                    master_data.base_skills[skill_id] = skill

        worker = Worker(f"base_skill_{region}", _add_trigger_skill)
        for func in master_data.func_list_no_cache():
            if func.svals and func.svals[0].DependFuncId:
                func_id = func.svals[0].DependFuncId
                if func_id not in master_data.base_functions:
                    dep_func = AtlasApi.api_model(
                        f"/nice/JP/function/{func_id}",
                        NiceBaseFunction,
                        expire_after=3600 * 24 * 7,
                    )
                    if dep_func:
                        master_data.base_functions[func_id] = dep_func

            if not func.buffs or not func.svals:
                continue
            buff = func.buffs[0]
            if buff.type == NiceBuffType.npattackPrevBuff:
                worker.add_default(buff, func.svals[0].SkillID)
            elif buff.type == NiceBuffType.counterFunction:
                # this is TD
                worker.add_default(buff, func.svals[0].CounterId, True)
            elif buff.type in [
                NiceBuffType.reflectionFunction,
                NiceBuffType.attackFunction,
                NiceBuffType.commandattackFunction,
                NiceBuffType.commandattackBeforeFunction,
                NiceBuffType.damageFunction,
                NiceBuffType.deadFunction,
                NiceBuffType.deadattackFunction,
                NiceBuffType.delayFunction,
                NiceBuffType.selfturnendFunction,
                NiceBuffType.wavestartFunction,
                NiceBuffType.commandcodeattackFunction,
                NiceBuffType.commandcodeattackAfterFunction,
                NiceBuffType.gutsFunction,
                NiceBuffType.attackBeforeFunction,
                NiceBuffType.entryFunction,
            ]:
                worker.add_default(buff, func.svals[0].Value)
        for svt in master_data.nice_servant_lore:
            for skills in (svt.script.SkillRankUp or {}).values():
                for skill in skills:
                    worker.add_default(None, skill)
        worker.wait()
        logger.info(
            f"{region}: loaded {len(master_data.base_skills)} trigger skills, {len(master_data.base_tds)} trigger TD"
        )
        self.stopwatch.log(f"master data [{region}]")
        return master_data

    def filter_quests(self):
        """
        1. add main story's free quests + QP quest(10AP)' phase data to game_data.questPhases
        2. count each war's one-off questPhase's fixed drop
        """
        if self.payload.skip_quests and settings.is_debug:
            logger.warning("[debug] skip checking quests data")
            return

        logger.info("processing quest data")
        previous_fixed_drops: dict[int, FixedDrop] = {}
        used_previous_count = 0
        close_at_limit = int(time.time() - 3 * 24 * 3600)
        open_at_limit = int(time.time() - self.payload.recent_quest_expire * 24 * 3600)
        try:
            if not self.payload.skip_prev_quest_drops:
                previous_fixed_drops = {
                    v["id"]: FixedDrop.parse_obj(v)
                    for v in load_json(settings.output_dist / "fixedDrops.json") or []
                }
        except Exception as e:
            logger.error(f"fail to reading fixed drop data of previous build: {e}")

        def _get_expire(quest: NiceQuest, default_days: int | None) -> int | None:
            if quest.warId in self.payload.expired_wars:
                return 0
            if default_days is not None:
                return default_days * 24 * 3600
            return None

        def _save_free_phase(quest: NiceQuest, phase=3):
            assert (
                phase in quest.phases
                and quest.afterClear == NiceQuestAfterClearType.repeatLast
            ), quest.id
            assert quest.id in (94061636, 94061640) or (
                quest.warId < 1000 and quest.type == NiceQuestType.free
            ), quest.id

            phase_data = AtlasApi.quest_phase(
                quest.id,
                phase,
                # filter_fn=_check_quest_phase_in_recent,
                expire_after=_get_expire(quest, self.payload.main_story_quest_expire),
            )
            assert phase_data
            self.jp_data.cachedQuestPhases[quest.id * 100 + phase] = phase_data

        def _check_fixed_drop(quest: NiceQuest):
            assert quest.afterClear in (
                NiceQuestAfterClearType.close,
                NiceQuestAfterClearType.resetInterval,
            ), quest.id

            quest_na = self.jp_data.all_quests_na.get(quest.id)

            for phase in quest.phases:
                phase_key = quest.id * 100 + phase
                previous_data = previous_fixed_drops.get(phase_key)
                if previous_data and quest.warId not in self.payload.expired_wars:
                    # 关闭未过3天且20天内开放
                    retry_jp = (
                        quest.closedAt > close_at_limit
                        and quest.openedAt > open_at_limit
                    )
                    retry_na = (
                        quest_na
                        and quest_na.closedAt > close_at_limit
                        and quest_na.openedAt > open_at_limit
                    )
                    retry = not self.payload.regions and (retry_jp or retry_na)
                    if not retry:
                        self.jp_data.fixedDrops[phase_key] = previous_data.copy(
                            deep=True
                        )
                        nonlocal used_previous_count
                        used_previous_count += 1
                        continue
                phase_data = None
                if phase in quest.phasesWithEnemies:
                    phase_data = AtlasApi.quest_phase(
                        quest.id,
                        phase,
                        Region.JP,
                        filter_fn=quest.closedAt > close_at_limit
                        and quest.openedAt > open_at_limit,
                        expire_after=_get_expire(quest, None),
                    )
                elif quest_na and phase in quest_na.phasesWithEnemies:
                    phase_data = AtlasApi.quest_phase(
                        quest_na.id,
                        phase,
                        Region.NA,
                        filter_fn=quest_na.closedAt > close_at_limit
                        and quest_na.openedAt > open_at_limit,
                    )
                if not phase_data:
                    continue
                phase_drops: NumDict[int, int] = NumDict()
                for drop in [
                    _drop
                    for stage in phase_data.stages
                    for enemy in stage.enemies
                    for _drop in enemy.drops
                ]:
                    if drop.runs < 5:
                        continue
                    drop_prob = drop.dropCount / drop.runs
                    if 0.95 < drop_prob < 1:
                        drop_prob = 1
                    if drop.type == NiceGiftType.item and drop_prob >= 1:
                        phase_drops.add_one(drop.objectId, int(drop_prob) * drop.num)
                phase_drops.drop_negative()
                # always add even if there is nothing dropped
                # if phase_drops:
                self.jp_data.fixedDrops[phase_key] = FixedDrop(
                    id=phase_key, items=phase_drops
                )

        worker = Worker("quest")
        # _now = int(time.time()) + 60 * 24 * 3600

        for war in self.jp_data.nice_war:
            if war.id == 9999:  # Chaldea Gate
                _now = time.time()
                for spot in war.spots:
                    spot.quests = [
                        q
                        for q in spot.quests
                        if q.id in self.jp_data.remainedQuestIds or q.closedAt > _now
                    ]
                # continue
            if war.id == 1002:  # 曜日クエスト
                # remove closed quests
                for spot in war.spots:
                    spot.quests = [
                        q
                        for q in spot.quests
                        if (
                            q.closedAt > NEVER_CLOSED_TIMESTAMP
                            and q.afterClear == NiceQuestAfterClearType.repeatLast
                        )
                    ]
            for _quest in [q for spot in war.spots for q in spot.quests]:
                if not _quest.phases:
                    continue
                # main story free quests
                if (
                    _quest.type == NiceQuestType.free
                    and _quest.warId < 1000
                    and _quest.afterClear == NiceQuestAfterClearType.repeatLast
                ):
                    worker.add(_save_free_phase, _quest, 3)
                    continue
                if _quest.warId == 1002:
                    if _quest.id in (94061636, 94061640):  # 宝物庫の扉を開け 初級&極級
                        worker.add(_save_free_phase, _quest, 1)
                    continue
                # one-off quests: event/main story
                if _quest.afterClear not in (
                    NiceQuestAfterClearType.close,
                    NiceQuestAfterClearType.resetInterval,
                ):
                    continue
                if _quest.phasesWithEnemies:
                    worker.add(_check_fixed_drop, _quest)
                else:
                    _quest_na = self.jp_data.all_quests_na.get(_quest.id)
                    if _quest_na and _quest_na.phasesWithEnemies:
                        worker.add(_check_fixed_drop, _quest)
        worker.wait()
        logger.debug(
            f"used {used_previous_count} quest phases' fixed drop from previous build"
        )
        logger.info("finished checking quests")

    def _normal_dump(
        self,
        obj,
        key: str,
        _fn: str | None = None,
        encoder=None,
        _bytes: bytes | None = None,
        last_version: DataVersion | None = None,
    ) -> FileVersion:
        if _fn is None:
            _fn = f"{key}.json"
        if _bytes is None:
            _text = dump_json(
                obj, default=encoder or self._encoder, indent2=False, new_line=False
            )
            assert _text
            _bytes = _text.encode()
        _bytes = self._replace_dw_chars(_bytes)
        _hash = hashlib.md5(_bytes).hexdigest()[:6]
        fv = FileVersion(
            key=key,
            filename=_fn,
            timestamp=int(self.now.timestamp()),
            size=len(_bytes),
            hash=_hash,
            minSize=len(_bytes),
            minHash=_hash,
        )
        if last_version and _fn in last_version.files:
            last_fv = last_version.files[_fn]
            if (fv.key, fv.filename, fv.minSize, fv.minHash) == (
                last_fv.key,
                last_fv.filename,
                last_fv.minSize,
                last_fv.minHash,
            ):
                fv.timestamp = last_fv.timestamp
        _fp = settings.output_dist.joinpath(_fn)
        _fp.write_bytes(_bytes)
        beautify_file(_fp)
        _bytes = _fp.read_bytes()
        fv.hash = hashlib.md5(_bytes).hexdigest()[:6]
        fv.size = len(_bytes)
        logger.info(f"[version] dump {key}: {_fn}")
        return fv

    def save_data(self):
        settings.output_wiki.mkdir(parents=True, exist_ok=True)

        dist_folder = settings.output_dist
        dist_folder.mkdir(parents=True, exist_ok=True)
        data = self.jp_data
        wiki_data = self.wiki_data
        data.sort()
        wiki_data.sort()
        wiki_data.save(full_version=False)

        logger.debug("Saving data")
        self.stopwatch.log(f"Save start")
        cur_version = DataVersion(
            timestamp=int(self.now.timestamp()),
            utc=self.now.isoformat(timespec="seconds").split("+")[0],
            minimalApp=MIN_APP,
            files={},
        )
        try:
            _last_version = DataVersion.parse_file(
                settings.output_dist / "version.json"
            )
        except:  # noqa
            _last_version = cur_version.copy(deep=True)

        def _normal_dump(
            obj,
            key: str,
            _fn: str | None = None,
            encoder=None,
            _bytes: bytes | None = None,
        ):
            fv = self._normal_dump(obj, key, _fn, encoder, _bytes, _last_version)
            cur_version.files[fv.filename] = fv

        def _dump_by_count(
            obj: list, count: int, key: str, base_fn: str | None = None, encoder=None
        ):
            if base_fn is None:
                base_fn = key
            n = len(obj) // count + 1
            for i in range(n):
                _fn_i = f"{base_fn}.{i + 1}.json"
                _normal_dump(obj[i * count : (i + 1) * count], key, _fn_i, encoder)

        def _dump_by_ranges(
            obj: dict[_KT, Any],
            ranges: list[Iterable[_KT]],
            save_remained: bool,
            key: str,
            base_fn: str | None = None,
            encoder=None,
            use_dict=False,
        ):
            if base_fn is None:
                base_fn = key
            obj = dict(obj)
            i = -1
            for i, id_range in enumerate(ranges):
                _fn_i = f"{base_fn}.{i + 1}.json"
                if use_dict:
                    values = {_k: obj.pop(_k) for _k in id_range if _k in obj}
                else:
                    values = [obj.pop(_k) for _k in id_range if _k in obj]
                assert values, f"No value found at range {i}"
                _normal_dump(values, key, _fn_i, encoder)
            if save_remained:
                if use_dict:
                    values = obj
                else:
                    values = list(obj.values())
                _normal_dump(values, key, f"{base_fn}.{i + 2}.json", encoder)
            else:
                assert (
                    not obj
                ), f"There are still {len(obj)} values not saved: {list(obj.keys())}"

        def _dump_file(fp: Path, key: str, fn: str | None = None):
            if fn is None:
                fn = f"{key}.json"
            _normal_dump(None, key, fn, _bytes=fp.read_bytes())

        # start writing files
        mappings_new, mapping_patch = self._patch_mappings(
            data.mappingData, _last_version
        )
        # delete files after old mappings read
        if not settings.is_debug:
            for f in settings.output_dist.glob("**/*"):
                if f.name in (
                    "news.json",
                    "config.json",
                    "addData.json",
                    "mappingPatch.json",
                ):
                    continue
                elif f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)

        _dump_by_count(data.nice_servant_lore, 100, "servants")
        _dump_by_count(data.nice_equip_lore, 500, "craftEssences")
        _normal_dump(data.nice_command_code, "commandCodes")
        _normal_dump(data.nice_mystic_code, "mysticCodes")
        _normal_dump(data.nice_item, "items")
        _normal_dump(data.basic_svt, "entities")
        _normal_dump(data.exchangeTickets, "exchangeTickets")
        _normal_dump(data.nice_bgm, "bgms")

        logger.info("Updating mappings")
        run_mapping_update(data.mappingData)  # before dump
        _dump_by_ranges(
            mappings_new,
            ranges=[
                ["skill_detail", "td_detail"],
                ["quest_names", "entity_names"],
            ],
            save_remained=True,
            key="mappingData",
            use_dict=True,
        )
        if mapping_patch:
            _normal_dump(mapping_patch, "mappingPatch")
        else:
            logger.info("no mapping patch generated")

        _dump_by_ranges(
            data.event_dict,
            ranges=[
                range(80000, 80100),
                range(80100, 80300),
                range(80300, 80400),
                range(80400, 90000),
                # others, irregular 71256: White Day Spectacles
            ],
            save_remained=True,
            key="events",
        )
        _dump_by_ranges(
            data.war_dict,
            ranges=[
                list(range(0, 2000)) + list(range(9999, 14000)),
                range(8000, 9000),
                range(9000, 9050),
                range(9050, 9100),
                range(9100, 9999),
            ],
            save_remained=False,
            key="wars",
        )
        # sometimes disabled quest parser when debugging
        if data.fixedDrops:
            _normal_dump(list(data.fixedDrops.values()), "fixedDrops")
        if data.cachedQuestPhases:
            _dump_by_count(list(data.cachedQuestPhases.values()), 100, "questPhases")
        _normal_dump(data.extraMasterMission, "extraMasterMission")
        class_relations: dict[int, dict[int, int]] = defaultdict(dict)
        for relation in data.mstClassRelation:
            class_relations[relation.atkClass][relation.defClass] = relation.attackRate
        for cls_info in data.mstClass:
            if not isinstance(cls_info.individuality, int):
                cls_info.individuality = 0
        _normal_dump(
            ConstGameData(
                attributeRelation=data.NiceAttributeRelation,
                buffActions=data.NiceBuffList_ActionList,
                cardInfo=data.NiceCard,
                classInfo={x.id: x for x in data.NiceClass},
                classInfo2={x.id: x for x in data.mstClass},
                classAttackRate=data.NiceClassAttackRate,
                classRelation=data.NiceClassRelation,
                classRelation2=class_relations,
                constants=data.NiceConstant,
                svtGrailCost=data.NiceSvtGrailCost,
                userLevel=data.NiceUserLevel,
            ),
            "constData",
        )
        _dump_by_count(list(wiki_data.servants.values()), 100, "wiki.servants")
        _dump_by_count(
            list(wiki_data.craftEssences.values()), 500, "wiki.craftEssences"
        )
        _normal_dump(list(wiki_data.commandCodes.values()), "wiki.commandCodes")
        _normal_dump(list(wiki_data.events.values()), "wiki.events")
        _normal_dump(list(wiki_data.wars.values()), "wiki.wars")
        _dump_by_count(list(wiki_data.summons.values()), 100, "wiki.summons")
        _dump_file(settings.output_wiki / "webcrowMapping.json", "wiki.webcrowMapping")
        _dump_file(settings.output_wiki / "dropRate.json", "dropRate")
        base_tds = list(self.jp_data.base_tds.values())
        base_tds.sort(key=lambda x: x.id)
        _normal_dump(base_tds, "baseTds")
        base_skills = list(self.jp_data.base_skills.values())
        base_skills.sort(key=lambda x: x.id)
        _normal_dump(base_skills, "baseSkills")
        base_functions = list(self.jp_data.base_functions.values())
        base_functions.sort(key=lambda x: x.funcId)
        _normal_dump(base_functions, "baseFunctions")
        self.stopwatch.log(f"save end")

        changed = False
        for k, f in cur_version.files.items():
            f_old = _last_version.files.get(k)
            if not f_old:
                changed = True
                logger.info(f"[Publish] create new file {f.filename}")
            elif f != f_old:
                changed = True
                logger.info(f"[Publish] file updated {f.filename}")

        if _last_version.minimalApp == cur_version.minimalApp and not changed:
            cur_version.timestamp = _last_version.timestamp
            cur_version.utc = _last_version.utc

        dump_json(cur_version, dist_folder / "version.json")
        # logger.info(dump_json(cur_version))
        self.copy_static()
        msg = f"{cur_version.minimalApp}, {cur_version.utc}"
        if len(self.payload.regions) not in (0, len(Region.__members__)):
            msg = describe_regions(self.payload.regions) + msg
        settings.commit_msg.write_text(msg)
        self.gametop()

    @staticmethod
    def _replace_dw_chars(content: _T) -> _T:
        # '魔{jin}剑', 鯖江
        chars = {"\ue000": "{jin}", "\ue001": "鯖"}
        if isinstance(content, str):
            for k, v in chars.items():
                content = content.replace(k, v)
        elif isinstance(content, bytes):
            for k, v in chars.items():
                content = content.replace(k.encode(), v.encode())
        return content

    def _patch_mappings(
        self, mappings: MappingData, last_ver: DataVersion
    ) -> tuple[dict, dict]:
        encoded = dump_json(
            self._encode_mapping_data(mappings),
            default=self._encoder,
            indent2=False,
            new_line=False,
        )
        assert encoded
        encoded = self._replace_dw_chars(encoded)

        data1: dict = orjson.loads(encoded)
        if not self.payload.patch_mappings:
            return data1, {}
        data0 = {}
        for file in last_ver.files.values():
            if file.key == "mappingData":
                data0.update(
                    orjson.loads((settings.output_dist / file.filename).read_text())
                )
        if not data0:
            return data1, {}

        def _create_patch(new_: dict, old_: dict) -> dict:
            # only addition and changes, no deletion
            patch = {}
            for k, v in new_.items():
                if k not in old_:
                    patch[k] = v
                else:
                    v_old = old_[k]
                    if isinstance(v, dict) and isinstance(v_old, dict):
                        sub_patch = _create_patch(v, v_old)
                        if sub_patch:
                            patch[k] = sub_patch
                    elif v != v_old:
                        patch[k] = v
            return patch

        return data0, _create_patch(data1, data0)

    @staticmethod
    def _encode_mapping_data(data: MappingData) -> dict[str, Any]:
        r = {}

        def _clean_map(map):
            if not isinstance(map, dict):
                return map
            return {
                k: v if k in ("enums", "misc", "misc2") else _clean_map(v)
                for k, v in map.items()
                if v
            }

        _dict = data.dict(exclude_none=True)
        _dict = _clean_map(_dict)
        data = MappingData.parse_obj(_dict)

        for k, v in data._iter(exclude_none=True):
            if isinstance(v, MappingBase):
                r[k] = v.dict(exclude_none=True)
            elif isinstance(v, dict):
                r[k] = sort_dict(v)
            else:
                r[k] = v
        return r

    _excludes: dict[type, list[str]] = {
        NiceBaseSkill: ["detail"],
        NiceSkill: [
            "name",
            "originalName",
            "ruby",
            "detail",
            "unmodifiedDetail",
            "type",
            "icon",
            "coolDown",
            "actIndividuality",
            "script",
            "skillAdd",
            "aiIds",
            "functions",
        ],
        NiceBaseTd: ["detail"],
        NiceTd: [
            # "card",
            "name",
            "originalName",
            "ruby",
            # "icon",
            "rank",
            "type",
            "effectFlags",
            "detail",
            "unmodifiedDetail",
            "npGain",
            # "npDistribution",
            "individuality",
            "script",
            "functions",
        ],
        NiceBgm: ["name", "fileName", "notReleased", "audioAsset"],
        NiceTrait: ["name"],
        NiceGift: ["id", "priority"],
        NiceLore: ["comments", "voices"],
        NiceWar: ["emptyMessage"],
        NiceMap: [],
        NiceMapGimmick: ["actionAnimTime", "actionEffectId", "startedAt", "endedAt"],
        NiceQuestPhase: ["supportServants"],
        NiceQuest: [],
        QuestEnemy: ["drops", "limit"],
        EnemyDrop: ["dropExpected", "dropVariance"],
        NiceEvent: ["voicePlays"],
        NiceEventMissionCondition: ["missionTargetId", "detail"],
        NiceEventMission: [
            "flag",
            "missionTargetId",
            "detail",
            "startedAt",
            "endedAt",
            "closedAt",
            "rewardRarity",
            "notfyPriority",
            "presentMessageId",
        ],
        NiceEventTreasureBox: ["commonConsume"],
        NiceEventDiggingBlock: ["commonConsume"],
        NiceEventTowerReward: ["boardMessage", "rewardGet", "banner"],
        NiceEventLotteryBox: ["id", "priority", "detail", "icon", "banner"],
        NiceEventReward: ["bgImagePoint", "bgImageGet"],
        NiceEventPointBuff: ["detail"],
        NiceShop: [
            "baseShopId",
            "eventId",
            "detail",
            "openedAt",
            "closedAt",
            "warningMessage",
        ],
        NiceServant: [
            "originalBattleName",
            "expFeed",
            "hitsDistribution",
        ],
        BasicServant: ["originalOverwriteName"],
        NiceEquip: ["expFeed", "expGrowth", "atkGrowth", "hpGrowth"],
        NiceEquipSort: ["expFeed", "expGrowth", "atkGrowth", "hpGrowth"],
        AscensionAdd: [
            "originalOverWriteServantName",
            "originalOverWriteServantBattleName",
            "originalOverWriteTDName",
        ],
        NiceMasterMission: ["quests"],
    }

    def _encoder(self, obj):
        exclude = {"originalName"}
        _type = type(obj)
        exclude.update(self._excludes.get(_type, []))

        if _type == NiceSkill and isinstance(obj, NiceSkill):
            if obj.id not in self.jp_data.base_skills:
                self.jp_data.base_skills[obj.id] = NiceBaseSkill.parse_obj(obj.dict())
            if obj.ruby in ("", "-"):
                exclude.add("ruby")
        elif _type == NiceTd and isinstance(obj, NiceTd):
            if obj.id not in self.jp_data.base_tds:
                self.jp_data.base_tds[obj.id] = NiceBaseTd.parse_obj(obj.dict())
            base_td = self.jp_data.base_tds[obj.id]
            for key in ["card", "icon", "npDistribution"]:
                if getattr(obj, key, None) == getattr(base_td, key, None):
                    exclude.add(key)
            if obj.ruby in ("", "-"):
                exclude.add("ruby")
        elif _type == NiceFunction and isinstance(obj, NiceFunction):
            if obj.funcId not in self.jp_data.base_functions:
                self.jp_data.base_functions[obj.funcId] = NiceBaseFunction.parse_obj(
                    obj.dict()
                )
            exclude.update(NiceBaseFunction.__fields__.keys())
            exclude.remove("funcId")
        elif isinstance(obj, NiceItemAmount):
            return {"itemId": obj.item.id, "amount": obj.amount}
        elif isinstance(obj, (ExtraAssets, AscensionAdd)):
            # NiceTrait.name
            obj = obj.dict(
                exclude_none=True, exclude_defaults=True, exclude=exclude | {"name"}
            )
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
            if isinstance(obj, NiceFunction):
                map = dict(
                    obj._iter(
                        to_dict=True,
                        exclude_none=True,
                        exclude_defaults=True,
                        exclude=exclude,
                    )
                )
                # enable in 2.1.0
                self._trim_func_vals(map)
            else:
                map = dict(
                    obj._iter(
                        to_dict=False,
                        exclude_none=True,
                        exclude_defaults=True,
                        exclude=exclude,
                    )
                )
            return map
        return pydantic_encoder(obj)

    @staticmethod
    def _trim_func_vals(map: dict[str, Any]):
        first: dict[str, Any] | None = map["svals"][0] if map.get("svals") else None
        if not first:
            return
        for key1 in ["svals", "svals2", "svals3", "svals4", "svals5"]:
            svals: list[dict] | None = map.get(key1)
            if not svals:
                continue
            for index in range(len(svals)):
                if key1 == "svals" and index == 0:
                    continue
                val = svals[index]
                new_val = dict()
                for key2 in first.keys():
                    v = val.get(key2)
                    if first[key2] != v:
                        new_val[key2] = v
                for key2 in val.keys():
                    if key2 not in first:
                        new_val[key2] = val[key2]
                svals[index] = new_val

        return map

    def merge_all_mappings(self):
        logger.info("merge all mappings")
        if not self.payload.skip_mapping:
            self._merge_official_mappings(Region.CN)
            self._merge_wiki_translation(
                Region.CN,
                parse_file_as(WikiTranslation, settings.output_wiki / "mcTransl.json"),
            )

            self._merge_official_mappings(Region.NA)
            self._add_atlas_na_mapping()
            self._merge_wiki_translation(
                Region.NA,
                parse_file_as(
                    WikiTranslation, settings.output_wiki / "fandomTransl.json"
                ),
            )

            self._merge_official_mappings(Region.TW)
            self._merge_official_mappings(Region.KR)
        self._add_enum_mappings()
        self._merge_repo_mapping()
        self._fix_cn_translation()

    def _post_mappings(self):
        mappings = self.jp_data.mappingData
        for key in mappings.war_names.keys():
            name = mappings.event_names.get(key, None)
            if name:
                name.update_from(mappings.war_names[key])
                mappings.war_names[key].update_from(name)
            mappings.spot_names.pop(key, None)
        for key in mappings.svt_names.keys():
            entity = mappings.entity_names.pop(key, None)
            if entity:
                mappings.svt_names[key].update_from(entity)
        for key in mappings.ce_names.keys():
            mappings.entity_names.pop(key, None)
            mappings.skill_names.pop(key, None)
        for key in mappings.cc_names.keys():
            mappings.skill_names.pop(key, None)
        mappings.cn_replace = dict(CN_REPLACE)

    def _add_enum_mappings(self):
        mappings = self.jp_data.mappingData
        for k, v in self.jp_data.nice_trait.items():
            if v in OLD_TRAIT_MAPPING:
                continue
            m_trait = mappings.trait.setdefault(k, MappingStr())
            m_trait.update(Region.NA, v.value, skip_exists=True)

        enums = self.jp_data.mappingData.enums
        enums.update_enums()
        for cls_info in self.jp_data.mstClass:
            enums.svt_class2.setdefault(cls_info.id, MappingBase())

    def _merge_official_mappings(self, region: Region):
        logger.info(f"merging official translations from {region}")
        mappings = self.jp_data.mappingData
        jp_data = self.jp_data
        data = self.load_master_data(region)
        jp_chars = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")

        if region != Region.JP:
            mappings.ce_release.update(
                region,
                sorted(set(data.ce_dict.keys()) | set(ADD_CES.get(region, {}).keys())),
            )
            mappings.svt_release.update(region, sorted(data.svt_dict.keys()))
            mappings.entity_release.update(
                region, sorted([svt.id for svt in data.basic_svt])
            )
            mappings.cc_release.update(region, sorted(data.cc_dict.keys()))
            mappings.mc_release.update(region, sorted(data.mc_dict.keys()))

        def _update_mapping(
            m: dict[_KT, MappingBase[_KV]],
            _key: _KT,
            value: _KV | None,
            skip_exists=True,
            skip_unknown_key=False,
        ):
            if _key is None:
                return
            m.setdefault(_key, MappingBase())
            if value == _key:
                return
            if region in (Region.CN, Region.TW) and isinstance(value, str):
                if jp_chars.search(value):
                    return
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
            item = data.item_dict.get(item_jp.id)
            _update_mapping(
                mappings.item_names, item_jp.name, item.name if item else None
            )
        for cv_jp in jp_data.nice_cv:
            cv = data.cv_dict.get(cv_jp.id)
            _update_mapping(mappings.cv_names, cv_jp.name, cv.name if cv else None)
            cv_names = [str(s).strip() for s in re.split(r"[&＆]+", cv_jp.name) if s]
            if len(cv_names) > 1:
                for one_name in cv_names:
                    mappings.cv_names.setdefault(one_name, MappingBase())
        for illustrator_jp in jp_data.nice_illustrator:
            illustrator = data.illustrator_dict.get(illustrator_jp.id)
            _update_mapping(
                mappings.illustrator_names,
                illustrator_jp.name,
                illustrator.name if illustrator else None,
            )
            illustrator_names = [
                str(s).strip() for s in re.split(r"[&＆]+", illustrator_jp.name) if s
            ]
            if len(illustrator_names) > 1:
                for one_name in illustrator_names:
                    mappings.illustrator_names.setdefault(one_name, MappingBase())
        for bgm_jp in jp_data.nice_bgm:
            bgm = data.bgm_dict.get(bgm_jp.id)
            _update_mapping(mappings.bgm_names, bgm_jp.name, bgm.name if bgm else None)

        for event_jp in jp_data.nice_event:
            event_extra = self.wiki_data.get_event(event_jp.id, event_jp.name)
            event_extra.startTime.JP = event_jp.startedAt
            event_extra.endTime.JP = event_jp.endedAt
            mappings.event_names.setdefault(event_jp.name, MappingBase())
            mappings.event_names.setdefault(event_jp.shortName, MappingBase())
            event = data.event_dict.get(event_jp.id)
            if event is None:
                continue
            if event.startedAt < NEVER_CLOSED_TIMESTAMP:
                event_extra.startTime.update(region, event.startedAt)
                event_extra.endTime.update(region, event.endedAt)
            if event.startedAt > time.time():
                continue
            _update_mapping(mappings.event_names, event_jp.name, event.name)
            _update_mapping(mappings.event_names, event_jp.shortName, event.shortName)
        war_release = mappings.war_release.of(region) or []
        for war_jp in jp_data.nice_war:
            if war_jp.id < 1000:
                self.wiki_data.get_war(war_jp.id)
            mappings.war_names.setdefault(war_jp.name, MappingBase())
            mappings.war_names.setdefault(war_jp.longName, MappingBase())
            for war_add in war_jp.warAdds:
                if war_add.type in [
                    NiceWarOverwriteType.longName,
                    NiceWarOverwriteType.name_,
                ]:
                    mappings.war_names.setdefault(war_add.overwriteStr, MappingBase())
            war = data.war_dict.get(war_jp.id)
            if war is None:
                continue
            if war.id == 8098 and region == Region.NA:
                # for NA: 8098 is Da Vinci and the 7 Counterfeit Heroic Spirits
                continue
            if data.mstConstant["LAST_WAR_ID"] < war.id < 1000:
                continue
            event = data.event_dict.get(war.eventId)
            if event and event.startedAt > time.time():
                continue
            war_release.append(war.id)
            # if war.id < 11000 and war.lastQuestId == 0:  # not released wars
            #     continue
            _update_mapping(mappings.war_names, war_jp.longName, war.longName)
            _update_mapping(mappings.war_names, war_jp.name, war.name)
        mappings.war_release.update(region, sorted(war_release))
        for spot_jp in jp_data.spot_dict.values():
            spot = data.spot_dict.get(spot_jp.id)
            _update_mapping(
                mappings.spot_names, spot_jp.name, spot.name if spot else None
            )
            for spotAdd in spot_jp.spotAdds:
                if spotAdd.overrideType == NiceSpotOverwriteType.name_:
                    _update_mapping(mappings.spot_names, spotAdd.targetText, None)

        def __update_ascension_add(
            m: dict[str, MappingStr],
            jp_entry: AscensionAddEntryStr,
            entry: AscensionAddEntryStr | None,
        ):
            for ascension, name in jp_entry.ascension.items():
                _update_mapping(
                    m,
                    name,
                    entry.ascension.get(ascension) if entry else None,
                    skip_exists=True,
                )
            for ascension, name in jp_entry.costume.items():
                _update_mapping(
                    m,
                    name,
                    entry.costume.get(ascension) if entry else None,
                    skip_exists=True,
                )

        for svt_jp in jp_data.nice_servant_lore:
            svt = data.svt_id_dict.get(svt_jp.id)
            self.wiki_data.get_svt(svt_jp.collectionNo)
            _update_mapping(
                mappings.svt_names,
                svt_jp.name,
                svt.name if svt else None,
                skip_exists=True,
            )
            _update_mapping(
                mappings.svt_names,
                svt_jp.battleName,
                svt.battleName if svt else None,
                skip_exists=True,
            )
            __update_ascension_add(
                mappings.svt_names,
                svt_jp.ascensionAdd.overWriteServantName,
                svt.ascensionAdd.overWriteServantName if svt else None,
            )
            __update_ascension_add(
                mappings.svt_names,
                svt_jp.ascensionAdd.overWriteServantBattleName,
                svt.ascensionAdd.overWriteServantBattleName if svt else None,
            )
            __update_ascension_add(
                mappings.td_names,
                svt_jp.ascensionAdd.overWriteTDName,
                svt.ascensionAdd.overWriteTDName if svt else None,
            )
            if region != Region.NA:
                __update_ascension_add(
                    mappings.td_ruby,
                    svt_jp.ascensionAdd.overWriteTDRuby,
                    svt.ascensionAdd.overWriteTDRuby if svt else None,
                )
            __update_ascension_add(
                mappings.td_types,
                svt_jp.ascensionAdd.overWriteTDTypeText,
                svt.ascensionAdd.overWriteTDTypeText if svt else None,
            )

            def _svt_change_dict(_svt: NiceServant | None):
                return {
                    str(
                        (
                            change.priority,
                            change.condType,
                            change.condTargetId,
                            change.condValue,
                            change.limitCount,
                        )
                    ): change.name
                    for change in (_svt.svtChange if _svt else [])
                }

            changes_jp, changes = _svt_change_dict(svt_jp), _svt_change_dict(svt)
            for k, v in changes_jp.items():
                _update_mapping(mappings.svt_names, v, changes.get(k, None))
            assert svt_jp.profile is not None
            for group in svt_jp.profile.voices:
                for line in group.voiceLines:
                    if not line.name:
                        continue
                    name = line.name.replace("\u3000（ひとつの施策でふたつあるとき）", "")
                    name = name.replace("（57は欠番）", "")
                    name = re.sub(r"\d+$", "", name).strip()
                    mappings.voice_line_names.setdefault(name, MappingStr())

            if not svt:
                continue
            skill_priority = mappings.skill_priority.setdefault(
                svt_jp.id, MappingBase()
            )
            skill_priority.update(
                region, {skill.id: skill.priority for skill in svt.skills}
            )
            td_priority = mappings.td_priority.setdefault(svt_jp.id, MappingBase())
            td_priority.update(
                region, {td.id: td.priority for td in svt.noblePhantasms}
            )
            # if region != Region.JP and svt.profile.comments:
            #     svt_w = self.wiki_data.servants.setdefault(svt_jp.collectionNo,
            #       ServantW(collectionNo=svt.collectionNo))
            #     svt_w.profileComment.update(region, svt.profile.comments)
        for costume_id, costume_jp in jp_data.costume_dict.items():
            costume = data.costume_dict.get(costume_id)
            _update_mapping(
                mappings.costume_names,
                costume_jp.name,
                costume.name if costume else None,
            )
            _update_mapping(
                mappings.costume_names,
                costume_jp.shortName,
                costume.shortName if costume else None,
            )
            cos_w = mappings.costume_detail.setdefault(
                costume_jp.costumeCollectionNo, MappingStr()
            )
            cos_w.JP = costume_jp.detail
            if costume and costume.detail and costume.detail != costume_jp.detail:
                cos_w.update(region, costume.detail)

        def _get_comment(comments: list[NiceLoreComment]) -> NiceLoreComment:
            comment = comments[0]
            for c in comments:
                if c.priority > comment.priority:
                    comment = c
            return comment

        for ce_jp in jp_data.nice_equip_lore:
            ce = data.ce_id_dict.get(ce_jp.id)
            _update_mapping(mappings.ce_names, ce_jp.name, ce.name if ce else None)
            ce_w = self.wiki_data.get_ce(ce_jp.collectionNo)
            if ce_jp.profile and ce_jp.profile.comments:
                if len(ce_jp.profile.comments) > 1:
                    logger.debug(
                        f"{ce_jp.collectionNo}-{ce_jp.name} has {len(ce_jp.profile.comments)} lores"
                    )
                ce_w.profile.JP = _get_comment(ce_jp.profile.comments).comment
            if not ce:
                continue
            if region != Region.JP and ce.profile and ce.profile.comments:
                comment = _get_comment(ce.profile.comments).comment
                if comment and comment != ce_w.profile.JP:
                    ce_w.profile.update(region, comment)

        for cc_jp in jp_data.nice_command_code:
            cc = data.cc_id_dict.get(cc_jp.id)
            _update_mapping(mappings.cc_names, cc_jp.name, cc.name if cc else None)
            cc_w = self.wiki_data.commandCodes.setdefault(
                cc_jp.collectionNo, CommandCodeW(collectionNo=cc_jp.collectionNo)
            )
            cc_w.profile.update(Region.JP, cc_jp.comment)
            if not cc:
                continue
            if cc.comment and cc.comment != cc_jp.comment:
                cc_w.profile.update(region, cc.comment)
        for mc_jp in jp_data.nice_mystic_code:
            mc = data.mc_dict.get(mc_jp.id)
            _update_mapping(mappings.mc_names, mc_jp.name, mc.name if mc else None)
            mc_w = mappings.mc_detail.setdefault(mc_jp.id, MappingStr())
            mc_w.JP = mc_jp.detail
            if mc and mc.detail and mc.detail != mc_jp.detail:
                mc_w.update(region, mc.detail)

        for skill_jp in itertools.chain(
            jp_data.skill_dict.values(), jp_data.base_skills.values()
        ):
            for skill_add in skill_jp.skillAdd:
                # manually add
                _update_mapping(mappings.skill_names, skill_add.name, None)
            skill = data.skill_dict.get(skill_jp.id) or data.base_skills.get(
                skill_jp.id
            )
            if (
                skill_jp.name not in mappings.ce_names
                and skill_jp.name not in mappings.cc_names
            ):
                _update_mapping(
                    mappings.skill_names, skill_jp.name, skill.name if skill else None
                )
            detail_jp = self._process_effect_detail(skill_jp.unmodifiedDetail)
            if not detail_jp:
                continue
            _update_mapping(
                mappings.skill_detail,
                detail_jp,
                self._process_effect_detail(skill.unmodifiedDetail if skill else None),
            )
        for td_jp in itertools.chain(
            jp_data.td_dict.values(), jp_data.base_tds.values()
        ):
            td = data.td_dict.get(td_jp.id) or data.base_tds.get(td_jp.id)
            _update_mapping(mappings.td_names, td_jp.name, td.name if td else None)
            if region != Region.NA:  # always empty for NA
                _update_mapping(mappings.td_ruby, td_jp.ruby, td.ruby if td else None)
            _update_mapping(mappings.td_types, td_jp.type, td.type if td else None)
            detail_jp = self._process_effect_detail(td_jp.unmodifiedDetail)
            if not detail_jp:
                continue
            _update_mapping(
                mappings.td_detail,
                detail_jp,
                self._process_effect_detail(td.unmodifiedDetail if td else None),
            )
        for buff_jp in jp_data.buff_dict.values():
            buff = data.buff_dict.get(buff_jp.id)
            _update_mapping(
                mappings.buff_names, buff_jp.name, buff.name if buff else None
            )
            _update_mapping(
                mappings.buff_detail, buff_jp.detail, buff.detail if buff else None
            )
        for func_jp in jp_data.func_dict.values():
            if func_jp.funcPopupText in ["", "-", "なし"]:
                _update_mapping(mappings.func_popuptext, func_jp.funcType.value, None)
            if func_jp.funcPopupText in mappings.buff_names:
                continue
            func = data.func_dict.get(func_jp.funcId)
            _update_mapping(
                mappings.func_popuptext,
                func_jp.funcPopupText,
                func.funcPopupText if func else None,
            )
        for quest_jp in jp_data.quest_dict.values():
            quest = data.quest_dict.get(quest_jp.id)
            _update_mapping(
                mappings.quest_names, quest_jp.name, quest.name if quest else None
            )
        for entity_jp in jp_data.basic_svt:
            entity = data.entity_dict.get(entity_jp.id)
            if entity_jp.name in mappings.svt_names:
                _update_mapping(
                    mappings.svt_names,
                    entity_jp.name,
                    entity.name if entity else None,
                )
            else:
                _update_mapping(
                    mappings.entity_names,
                    entity_jp.name,
                    entity.name if entity else None,
                )
        # svt related quest release
        for svt in jp_data.nice_servant_lore:
            quest_ids = list(svt.relateQuestIds)
            if svt.collectionNo in STORY_UPGRADE_QUESTS:
                quest_ids += STORY_UPGRADE_QUESTS[svt.collectionNo]
            for quest_id in quest_ids:
                quest_jp = jp_data.quest_dict[quest_id]
                release = mappings.quest_release.setdefault(quest_id, MappingBase())
                release.update(Region.JP, quest_jp.openedAt)
                quest = data.quest_dict.get(quest_id)
                if not quest:
                    continue
                release.update(region, quest.openedAt)

        # view enemy name
        for quest_id, enemies in jp_data.view_enemy_names.items():
            quest = jp_data.quest_dict.get(quest_id)
            if not quest:
                continue
            for svt_id, name_jp in enemies.items():
                if name_jp not in mappings.entity_names:
                    continue
                name = data.view_enemy_names.get(quest_id, {}).get(svt_id)
                _update_mapping(mappings.entity_names, name_jp, name)

        self.jp_data.mappingData = mappings
        del data

    @staticmethod
    def _process_effect_detail(detail: str | None):
        if not detail:
            return detail
        return detail.replace("[g][o]▲[/o][/g]", "▲")

    def _merge_wiki_translation(self, region: Region, transl: WikiTranslation):
        logger.info(f"merging Wiki translations for {region}")

        def _update_mapping(
            m: dict[_KT, MappingBase[_KV]],
            _key: _KT,
            value: _KV | None,
        ):
            if value is None:
                return
            if _key == value:
                return
            if (
                re.findall(r"20[1-2][0-9]", str(value))
                and m.get(_key, MappingBase()).CN
            ):
                return
            return self._update_key_mapping(
                region,
                key_mapping=m,
                _key=_key,
                value=value,
                skip_exists=True,
                skip_unknown_key=True,
            )

        mappings = self.jp_data.mappingData

        for name_jp, name_cn in transl.svt_names.items():
            _update_mapping(mappings.svt_names, name_jp, name_cn)
        for skill_jp, skill_cn in transl.skill_names.items():
            _update_mapping(mappings.skill_names, skill_jp, skill_cn)
        for td_name_jp, td_name_cn in transl.td_names.items():
            _update_mapping(mappings.td_names, td_name_jp, td_name_cn)
        for td_ruby_jp, td_ruby_cn in transl.td_ruby.items():
            _update_mapping(mappings.td_ruby, td_ruby_jp, td_ruby_cn)
        for name_jp, name_cn in transl.ce_names.items():
            _update_mapping(mappings.ce_names, name_jp, name_cn)
        for name_jp, name_cn in transl.cc_names.items():
            _update_mapping(mappings.cc_names, name_jp, name_cn)
        for name_jp, name_cn in transl.event_names.items():
            _update_mapping(mappings.event_names, name_jp, name_cn)
            name_jp = name_jp.replace("･", "・")
            _update_mapping(mappings.event_names, name_jp, name_cn)
        for name_jp, name_cn in transl.quest_names.items():
            _update_mapping(mappings.quest_names, name_jp, name_cn)
        for name_jp, name_cn in transl.spot_names.items():
            _update_mapping(mappings.spot_names, name_jp, name_cn)
        for name_jp, name_cn in transl.costume_names.items():
            _update_mapping(mappings.costume_names, name_jp, name_cn)
        for collection, name_cn in transl.costume_details.items():
            _update_mapping(mappings.costume_detail, collection, name_cn)

        # ce/cc skill des
        for ce in self.jp_data.nice_equip_lore:
            if (
                ce.collectionNo <= 0
                or ce.valentineEquipOwner is not None
                or ce.flag == NiceSvtFlag.svtEquipExp
            ):
                continue
            skills = [s for s in ce.skills if s.num == 1]
            assert len(skills) in (1, 2)
            for skill in skills:
                assert skill.condLimitCount in (0, 4)
                is_max = skill.condLimitCount != 0
                detail = self._process_effect_detail(skill.unmodifiedDetail)
                des = (transl.ce_skill_des_max if is_max else transl.ce_skill_des).get(
                    ce.collectionNo
                )
                if not detail or des == detail:
                    continue
                _update_mapping(
                    mappings.skill_detail,
                    detail,
                    des,
                )
        for cc in self.jp_data.nice_command_code:
            if cc.collectionNo <= 0:
                continue
            assert len(cc.skills) == 1
            detail = self._process_effect_detail(cc.skills[0].unmodifiedDetail)
            des = transl.cc_skill_des.get(cc.collectionNo)
            if not detail or des == detail:
                continue
            _update_mapping(
                mappings.skill_detail,
                detail,
                des,
            )

    def _fix_cn_translation(self):
        logger.info("fix Chinese translations")
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

            def _repl(match: Match[AnyStr]) -> str:
                return {"力": "Buster", "技": "Arts", "迅": "Quick", "额外": "Extra"}[
                    str(match.group(0))
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
                cn_name2 = cn_name2.replace("<过量充能时", "<Over Charge时")
                cn_name2 = cn_name2.replace("宝具值", "NP")
                if cn_name2 != cn_name:
                    # print(f"Convert CN: {cn_name} -> {cn_name2}")
                    regions["CN"] = cn_name2
        # self.test_mapping_dict = mappings_dict
        def _iter(obj):
            if not isinstance(obj, dict):
                return
            v = obj.get("CN")
            if isinstance(v, str):
                for a, b in CN_REPLACE.items():
                    v = v.replace(a, b)
                obj["CN"] = v
            for k, v in obj.items():
                if k != "cn_replace":
                    _iter(v)

        _iter(mappings_dict)
        self.jp_data.mappingData = MappingData.parse_obj(mappings_dict)

    def _add_atlas_na_mapping(self):
        logger.info("merging Atlas translations for NA")

        mappings = self.jp_data.mappingData
        for _m in mappings.func_popuptext.values():
            if _m.NA:
                _m.NA = _m.NA.replace("\n", " ")

        import app as app_lib

        na_folder = Path(app_lib.__file__).resolve().parent.joinpath("data/mappings/")
        logger.debug(f"AA mappings path: {na_folder}")
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

        def _read_json(fn: str) -> dict:
            if settings.is_debug:
                return load_json(na_folder / fn) or {}
            else:
                url = (
                    "https://raw.githubusercontent.com/atlasacademy/fgo-game-data-api/master/app/data/mappings/"
                    + fn
                )
                return requests.get(url).json()

        for src_fn, dest in src_mapping.items():
            source: dict[str, str] = _read_json(src_fn)
            if not source:
                continue
            for key, trans in dest.items():
                value = source.get(key)
                if value and value.strip() == key.strip():
                    continue
                if value and "\n" in value and "\n" not in key:
                    continue
                if re.findall(r"20[1-2][0-9]", str(value)) and trans.NA:
                    continue
                trans.update(Region.NA, value, skip_exists=True)
        self.jp_data.mappingData = mappings

    def _merge_repo_mapping(self):
        logger.info("merging repo translations")

        folder = settings.output_mapping
        mappings = self.jp_data.mappingData
        mapping_dict = orjson.loads(mappings.json())
        mappings_repo = {
            k: load_json(folder / f"{k}.json", {}) for k in MappingData.__fields__
        }
        # mapping files which should override dist one
        self._merge_json(
            mapping_dict,
            {
                key: mappings_repo.pop(key)
                for key in [
                    "trait",
                ]
            },
        )
        self._merge_json(mappings_repo, mapping_dict)

        fp_override = folder / "override_mappings.json"
        if not fp_override.exists():
            fp_override.write_text("{}")
        override_data: dict[str, dict[str, dict[str, str]]] = (
            load_json(fp_override) or {}
        )
        self._merge_json(mappings_repo, override_data)
        self.jp_data.mappingData = MappingData.parse_obj(mappings_repo)

    @staticmethod
    def _update_key_mapping(
        region: Region,
        key_mapping: dict[_KT, MappingBase[_KV]],
        _key: _KT,
        value: _KV | None,
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
            if value is None:
                continue
            if key not in dest:
                dest[key] = value
                continue
            if isinstance(value, list):
                # only list of basic types
                dest[key] = list(value)
            elif isinstance(value, dict):
                if dest[key] is None:
                    dest[key] = value
                else:
                    MainParser._merge_json(dest[key], value)
            else:
                dest[key] = value

    @staticmethod
    def copy_static():
        logger.info("coping static files to dist folder")
        shutil.copytree(
            Path(__file__).resolve().parent.parent / "static",
            settings.output_dist,
            dirs_exist_ok=True,
        )

    @staticmethod
    def gametop():
        fp = settings.output_dist / "gametop.json"
        data = {
            "JP": {
                "region": "JP",
                "gameServer": "game.fate-go.jp",
                "bundle": "com.aniplex.fategrandorder",
            },
            "NA": {
                "region": "NA",
                "gameServer": "game.fate-go.us",
                "bundle": "com.aniplex.fategrandorder.en",
            },
        }
        for region in ["JP", "NA"]:
            top = DownUrl.gitaa("gamedatatop", Region(region), "")
            top = top["response"][0]["success"]
            assetbundle = DownUrl.gitaa("assetbundle", Region(region), "metadata/")
            with LocalProxy():
                ver_codes = requests.get(
                    f"https://raw.githubusercontent.com/O-Isaac/FGO-VerCode-extractor/{region}/VerCode.json"
                ).json()
            app_ver = requests.get(
                f'https://worker-cn.chaldea.center/proxy/gplay-ver?id={data[region]["bundle"]}'
            ).text
            if not re.match(r"\d+\.\d+\.\d+", app_ver):
                app_ver = ver_codes["appVer"]
            data[region] |= {
                "appVer": app_ver,
                "verCode": ver_codes["verCode"],
                "dataVer": top["dataVer"],
                "dateVer": top["dateVer"],
                "assetbundle": top["assetbundle"],
                "assetbundleFolder": assetbundle["folderName"],
            }
        dump_json(data, fp)
