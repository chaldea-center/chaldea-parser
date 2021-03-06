import datetime
import hashlib
import itertools
import re
import shutil
import time
from pathlib import Path
from typing import Any, AnyStr, Iterable, Match, TypeVar

import orjson
import requests
from app.schemas.common import NiceTrait, Region
from app.schemas.enums import (
    OLD_TRAIT_MAPPING,
    Attribute,
    ServantPersonality,
    ServantPolicy,
    SvtClass,
)
from app.schemas.gameenums import (
    NiceEventType,
    NiceFuncTargetType,
    NiceGender,
    NiceGiftType,
    NiceMissionProgressType,
    NiceMissionType,
    NiceQuestAfterClearType,
    NiceSvtFlag,
    NiceSvtType,
    NiceSvtVoiceType,
    NiceTdEffectFlag,
    NiceWarOverwriteType,
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
    NiceEquip,
    NiceEventLotteryBox,
    NiceEventMission,
    NiceEventMissionCondition,
    NiceEventPointBuff,
    NiceEventReward,
    NiceEventTowerReward,
    NiceFunction,
    NiceFuncType,
    NiceGift,
    NiceItemAmount,
    NiceLore,
    NiceMap,
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
from pydantic import BaseModel
from pydantic.json import pydantic_encoder

from ..config import PayloadSetting, settings
from ..schemas.common import (
    AtlasExportFile,
    CEObtain,
    CustomMissionType,
    DataVersion,
    FileVersion,
    ItemCategory,
    MappingBase,
    MappingStr,
    NpDamageType,
    OpenApiInfo,
    SummonType,
    SvtObtain,
)
from ..schemas.const_data import ConstGameData
from ..schemas.gamedata import (
    FixedDrop,
    MappingData,
    MasterData,
    MstViewEnemy,
    NiceBaseSkill,
    NiceBaseTd,
)
from ..schemas.wiki_data import (
    AppNews,
    CommandCodeW,
    CraftEssenceW,
    EventW,
    WarW,
    WikiData,
    WikiTranslation,
)
from ..utils import (
    NEVER_CLOSED_TIMESTAMP,
    AtlasApi,
    McApi,
    NumDict,
    Worker,
    count_time,
    dump_json,
    load_json,
    logger,
    sort_dict,
)
from ..utils.helper import beautify_file
from ..utils.stopwatch import Stopwatch
from ..wiki import FANDOM, MOONCELL
from .core.ticket import parse_exchange_tickets


_KT = TypeVar("_KT", str, int)
_KV = TypeVar("_KV", str, int)

# print(f'{__name__} version: {datetime.datetime.now().isoformat()}')

MIN_APP = "2.0.7"


class MainParser:
    def __init__(self):
        self.jp_data = MasterData(region=Region.JP)
        self.wiki_data = WikiData()
        self.huntingQuests: list[int] = []
        self.payload: PayloadSetting = PayloadSetting()
        logger.info(f"Payload: {self.payload}")
        self.stopwatch = Stopwatch("MainParser")

    @count_time
    def start(self):
        # check news.json
        fp_news = settings.output_dist / "news.json"
        for obj in load_json(fp_news) or []:
            AppNews.parse_obj(obj)

        self.stopwatch.start()
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
        if settings.is_debug and self.payload.skip_quests:
            logger.warning("skip checking quests data")
        else:
            self.filter_quests()
            self.stopwatch.log(f"quests")
        self._post_mappings()
        self.jp_data.exchangeTickets = parse_exchange_tickets(self.jp_data.nice_item)
        if not settings.output_wiki.joinpath("dropRate.json").exists():
            logger.info("dropRate.json not exist, run domus_aurea parser")
            from .domus_aurea import run_drop_rate_update

            run_drop_rate_update()
        self.save_data()
        print(self.stopwatch.output())

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
            info_remote = requests.get(
                AtlasApi.full_url(f"export/{region}/info.json")
            ).json()
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
            logger.debug(f"Exported files updated:\n{dump_json(info_remote)}")
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
        if region == Region.JP:
            cn_ce = AtlasApi.api_model(
                "/nice/CN/equip/102022?lore=true", NiceEquip, expire_after=0
            )
            assert cn_ce and cn_ce.profile
            cn_ce.profile.illustrator = "STAR?????????"
            master_data.nice_equip_lore.append(cn_ce)
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
        master_data.viewEnemy = [
            MstViewEnemy.parse_obj(o)
            for o in requests.get(
                raw_fmt.format(region=region, name="viewEnemy")
            ).json()
        ]
        master_data.mstConstant = {
            e["name"]: e["value"]
            for e in requests.get(
                raw_fmt.format(region=region, name="mstConstant")
            ).json()
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
        logger.info("processing quest data")
        previous_fixed_drops: dict[int, FixedDrop] = {}
        used_previous_count = 0
        close_at_limit = int(time.time() - 3 * 24 * 3600)
        expire_time = int(time.time() - self.payload.recent_quest_expire * 24 * 3600)
        try:
            if not self.payload.skip_prev_quest_drops:
                previous_fixed_drops = {
                    v["id"]: FixedDrop.parse_obj(v)
                    for v in load_json(settings.output_dist / "fixedDrops.json") or []
                }
        except Exception as e:
            logger.error(f"fail to reading fixed drop data of previous build: {e}")

        def _check_one_quest(quest: NiceQuest):
            # main story's free
            last_phase = quest.phases[-1]
            last_phase_key = quest.id * 100 + last_phase
            # war 9033 ?????????????????????????????? also use FREE ???
            if (
                quest.type == NiceQuestType.free
                and quest.warId < 1000
                and quest.afterClear == NiceQuestAfterClearType.repeatLast
            ):
                phase_data = AtlasApi.quest_phase(
                    quest.id,
                    last_phase,
                    # filter_fn=_check_quest_phase_in_recent,
                    expire_after=self.payload.main_story_quest_expire * 24 * 3600,
                )
                self.jp_data.cachedQuestPhases[last_phase_key] = phase_data
                return
            if quest.warId == 1002:  # ??????????????????
                self.jp_data.cachedQuestPhases[last_phase_key] = AtlasApi.quest_phase(
                    quest.id,
                    last_phase,
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
                phase_key = quest.id * 100 + phase
                previous_data = previous_fixed_drops.get(phase_key)
                quest_na = self.jp_data.all_quests_na.get(quest.id)
                jp_ended = (
                    quest.closedAt < close_at_limit or quest.openedAt < expire_time
                )
                na_ended = (
                    not quest_na
                    or quest_na.closedAt < close_at_limit
                    or quest_na.openedAt < expire_time
                )
                if previous_data is not None and (
                    self.payload.regions or (jp_ended and na_ended)
                ):
                    self.jp_data.fixedDrops[phase_key] = previous_data.copy(deep=True)
                    nonlocal used_previous_count
                    used_previous_count += 1
                    continue
                phase_data = None
                if phase in quest.phasesWithEnemies:
                    phase_data = AtlasApi.quest_phase(
                        quest.id,
                        phase,
                        filter_fn=quest.closedAt > close_at_limit
                        and quest.openedAt > expire_time,
                    )
                else:
                    quest_na = self.jp_data.all_quests_na.get(quest.id)
                    if quest_na and phase in quest_na.phasesWithEnemies:
                        phase_data = AtlasApi.quest_phase(
                            quest_na.id,
                            phase,
                            Region.NA,
                            filter_fn=quest_na.closedAt > close_at_limit
                            and quest_na.openedAt > expire_time,
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

        worker = Worker("quest", func=_check_one_quest)
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
                continue
            if war.id == 1002:  # ??????????????????
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
                if _quest.type == NiceQuestType.free:
                    worker.add_default(_quest)
                    continue
                if _quest.warId == 1002:
                    if _quest.id == 94061636:  # ???????????????????????? ??????
                        worker.add_default(_quest)
                        continue
                    # if (
                    #     _quest.closedAt > NEVER_CLOSED_TIMESTAMP
                    #     and _quest.afterClear == NiceQuestAfterClearType.repeatLast
                    # ):
                    #     worker.add_default(_quest)
                    #     continue
                if _quest.afterClear not in (
                    NiceQuestAfterClearType.close,
                    NiceQuestAfterClearType.resetInterval,
                ):
                    continue
                if not _quest.phasesWithEnemies:
                    _quest_na = self.jp_data.all_quests_na.get(_quest.id)
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
                _quest_na = self.jp_data.all_quests_na.get(_quest.id)
                if not _quest_na or not _quest_na.phasesWithEnemies:
                    continue
                worker.add_default(_quest)
        worker.wait()
        logger.debug(
            f"used {used_previous_count} quest phases' fixed drop from previous build"
        )
        logger.info("finished checking quests")

    def save_data(self):
        settings.output_wiki.mkdir(parents=True, exist_ok=True)

        dist_folder = settings.output_dist
        dist_folder.mkdir(parents=True, exist_ok=True)
        data = self.jp_data
        wiki_data = self.wiki_data
        data.sort()
        wiki_data.sort()
        wiki_data.save(full_version=False)

        _now = datetime.datetime.now(datetime.timezone.utc)

        logger.debug("Saving data")
        self.stopwatch.log(f"Save start")
        cur_version = DataVersion(
            timestamp=int(_now.timestamp()),
            utc=_now.isoformat(timespec="seconds").split("+")[0],
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
                if f.name in ("news.json"):
                    continue
                elif f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)

        def _normal_dump(
            obj,
            key: str,
            _fn: str | None = None,
            encoder=None,
            _bytes: bytes | None = None,
        ):
            if _fn is None:
                _fn = f"{key}.json"
            if _bytes is None:
                _text = dump_json(
                    obj, default=encoder or self._encoder, indent2=False, new_line=False
                )
                assert _text
                _bytes = _text.encode()
            _hash = hashlib.md5(_bytes).hexdigest()[:6]
            fv = FileVersion(
                key=key,
                filename=_fn,
                timestamp=int(_now.timestamp()),
                size=len(_bytes),
                hash=_hash,
                minSize=len(_bytes),
                minHash=_hash,
            )
            if _fn in _last_version.files:
                last_fv = _last_version.files[_fn]
                if (fv.key, fv.filename, fv.minSize, fv.minHash) == (
                    last_fv.key,
                    last_fv.filename,
                    last_fv.minSize,
                    last_fv.minHash,
                ):
                    fv.timestamp = last_fv.timestamp
            cur_version.files[_fn] = fv
            _fp = settings.output_dist.joinpath(_fn)
            _fp.write_bytes(_bytes)
            beautify_file(_fp)
            _bytes = _fp.read_bytes()
            fv.hash = hashlib.md5(_bytes).hexdigest()[:6]
            fv.size = len(_bytes)
            logger.info(f"[version] dump {key}: {_fn}")

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

        _dump_by_count(data.nice_servant_lore, 100, "servants")
        _dump_by_count(data.nice_equip_lore, 500, "craftEssences")
        _normal_dump(data.nice_command_code, "commandCodes")
        _normal_dump(data.nice_mystic_code, "mysticCodes")
        _normal_dump(data.nice_item, "items")
        _normal_dump(data.basic_svt, "entities")
        _normal_dump(data.exchangeTickets, "exchangeTickets")
        _normal_dump(data.nice_bgm, "bgms", encoder=pydantic_encoder)
        _dump_by_ranges(
            self._encode_mapping_data(data.mappingData),
            ranges=[
                ["skill_detail", "td_detail"],
                ["quest_names", "entity_names"],
            ],
            save_remained=True,
            key="mappingData",
            use_dict=True,
        )
        _dump_by_ranges(
            data.event_dict,
            ranges=[
                range(80000, 80100),
                range(80100, 80300),
                range(80300, 80400),
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
        _normal_dump(
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
            "constData",
        )
        _normal_dump(list(wiki_data.servants.values()), "wiki.servants")
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
            msg = "[" + ",".join([r.value for r in self.payload.regions]) + "] " + msg
        Path(settings.output_dir).joinpath("commit-msg.txt").write_text(msg)
        logger.info("Updating mappings")
        from .update_mapping import run_mapping_update

        run_mapping_update()

    @staticmethod
    def _encode_mapping_data(data: MappingData) -> dict[str, Any]:
        r = {}
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
            "card",
            "name",
            "originalName",
            "ruby",
            "icon",
            "rank",
            "type",
            "effectFlags",
            "detail",
            "unmodifiedDetail",
            "npGain",
            "npDistribution",
            "individuality",
            "script",
            "functions",
        ],
        NiceBgm: ["name", "fileName", "notReleased", "audioAsset"],
        NiceTrait: ["name"],
        NiceGift: ["id", "priority"],
        NiceLore: ["comments", "voices"],
        NiceWar: ["emptyMessage"],
        NiceMap: ["mapGimmicks"],
        NiceQuestPhase: ["supportServants"],
        NiceQuest: [],
        QuestEnemy: ["drops", "ai", "limit"],
        EnemyDrop: ["dropExpected", "dropVariance"],
        NiceEventMissionCondition: ["missionTargetId"],
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
        NiceServant: ["originalBattleName", "expFeed"],
        BasicServant: ["originalOverwriteName"],
        NiceEquip: ["expFeed", "expGrowth", "atkGrowth", "hpGrowth"],
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
        elif isinstance(obj, (AscensionAdd, ExtraAssets)):
            obj = obj.dict(exclude_none=True, exclude_defaults=True, exclude=exclude)
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

    def merge_all_mappings(self):
        logger.info("merge all mappings")
        self._add_enum_mappings()

        self._merge_official_mappings(Region.CN)
        self._merge_wiki_translation(
            Region.CN,
            WikiTranslation.parse_obj(
                load_json(settings.output_wiki / "mcTransl.json", {})
            ),
        )

        self._merge_official_mappings(Region.NA)
        self._add_na_mapping()
        self._merge_wiki_translation(
            Region.NA,
            WikiTranslation.parse_obj(
                load_json(settings.output_wiki / "fandomTransl.json", {})
            ),
        )

        self._merge_official_mappings(Region.TW)
        self._merge_official_mappings(Region.KR)
        self._merge_repo_mapping()
        self._fix_cn_translation()

    def _post_mappings(self):
        mappings = self.jp_data.mappingData
        for key in self.jp_data.mappingData.event_names.keys():
            mappings.war_names.pop(key, None)
        for key in self.jp_data.mappingData.svt_names.keys():
            mappings.entity_names.pop(key, None)
        for key in self.jp_data.mappingData.ce_names.keys():
            mappings.entity_names.pop(key, None)
            mappings.skill_names.pop(key, None)
        for key in self.jp_data.mappingData.cc_names.keys():
            mappings.skill_names.pop(key, None)

    def _add_enum_mappings(self):
        mappings = self.jp_data.mappingData
        for k, v in self.jp_data.nice_trait.items():
            if v in OLD_TRAIT_MAPPING:
                continue
            m_trait = mappings.trait.setdefault(k, MappingStr())
            m_trait.update(Region.NA, v.value, skip_exists=True)

        enums = self.jp_data.mappingData.enums
        for v in SvtClass.__members__.values():
            enums.svt_class.setdefault(v.value, MappingStr())
        for v in Attribute.__members__.values():
            enums.attribute.setdefault(v.value, MappingStr())
        for v in NiceSvtType.__members__.values():
            enums.svt_type.setdefault(v.value, MappingStr())
        for v in ServantPolicy.__members__.values():
            enums.servant_policy.setdefault(v.value, MappingStr())
        for v in ServantPersonality.__members__.values():
            enums.servant_personality.setdefault(v.value, MappingStr())
        for v in NiceGender.__members__.values():
            enums.gender.setdefault(v.value, MappingStr())
        for v in NiceFuncTargetType.__members__.values():
            enums.func_target_type.setdefault(v.value, MappingStr())
        for v in SvtObtain.__members__.values():
            enums.svt_obtain.setdefault(v.value, MappingStr())
        for v in CEObtain.__members__.values():
            enums.ce_obtain.setdefault(v.value, MappingStr())
            enums.svt_obtain.setdefault(v.value, MappingStr())
        for v in NiceMissionProgressType.__members__.values():
            enums.mission_progress_type.setdefault(v.value, MappingStr())
            enums.svt_obtain.setdefault(v.value, MappingStr())
        for v in NiceMissionType.__members__.values():
            enums.mission_type.setdefault(v.value, MappingStr())
        # custom enums
        for v in ItemCategory.__members__.values():
            enums.item_category.setdefault(v.value, MappingStr())
        for v in CustomMissionType.__members__.values():
            enums.custom_mission_type.setdefault(v.value, MappingStr())
        for v in NpDamageType.__members__.values():
            enums.np_damage_type.setdefault(v.value, MappingStr())
        for v in NiceTdEffectFlag.__members__.values():
            enums.td_effect_flag.setdefault(v.value, MappingStr())
        for v in SummonType.__members__.values():
            enums.summon_type.setdefault(v.value, MappingStr())
        # long dict
        for v in NiceFuncType.__members__.values():
            enums.func_type.setdefault(v.value, MappingStr())
        for v in NiceBuffType.__members__.values():
            enums.buff_type.setdefault(v.value, MappingStr())
        for v in NiceSvtVoiceType.__members__.values():
            enums.svt_voice_type.setdefault(v.value, MappingStr())

    def _merge_official_mappings(self, region: Region):
        logger.info(f"merging official translations from {region}")
        mappings = self.jp_data.mappingData
        jp_data = self.jp_data
        data = self.load_master_data(region)
        jp_chars = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")

        if region != Region.JP:
            mappings.svt_release.update(region, sorted(data.svt_dict.keys()))
            mappings.ce_release.update(region, sorted(data.ce_dict.keys()))
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
            cv_names = [str(s).strip() for s in re.split(r"[&???]+", cv_jp.name) if s]
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
                str(s).strip() for s in re.split(r"[&???]+", illustrator_jp.name) if s
            ]
            if len(illustrator_names) > 1:
                for one_name in illustrator_names:
                    mappings.illustrator_names.setdefault(one_name, MappingBase())
        for bgm_jp in jp_data.nice_bgm:
            bgm = data.bgm_dict.get(bgm_jp.id)
            _update_mapping(mappings.bgm_names, bgm_jp.name, bgm.name if bgm else None)

        for event_jp in jp_data.nice_event:
            event_extra = self.wiki_data.events.setdefault(
                event_jp.id, EventW(id=event_jp.id, name=event_jp.name)  # type: ignore
            )
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
        for war_jp in jp_data.nice_war:
            if war_jp.id < 1000:
                self.wiki_data.wars.setdefault(war_jp.id, WarW(id=war_jp.id))
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
            if data.mstConstant["LAST_WAR_ID"] < war.id < 1000:
                continue
            # if war.id < 11000 and war.lastQuestId == 0:  # not released wars
            #     continue
            _update_mapping(mappings.war_names, war_jp.name, war.name)
            _update_mapping(mappings.war_names, war_jp.longName, war.longName)
        for spot_jp in jp_data.spot_dict.values():
            spot = data.spot_dict.get(spot_jp.id)
            _update_mapping(
                mappings.spot_names, spot_jp.name, spot.name if spot else None
            )

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
                    name = line.name.replace("\u3000????????????????????????????????????????????????", "")
                    name = name.replace("???57????????????", "")
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
        for ce_jp in jp_data.nice_equip_lore:
            ce = data.ce_id_dict.get(ce_jp.id)
            _update_mapping(mappings.ce_names, ce_jp.name, ce.name if ce else None)
            ce_w = self.wiki_data.craftEssences.setdefault(
                ce_jp.collectionNo, CraftEssenceW(collectionNo=ce_jp.collectionNo)
            )
            if ce_jp.profile and ce_jp.profile.comments:
                ce_w.profile.update(Region.JP, ce_jp.profile.comments[0].comment)
            if not ce:
                continue
            if region != Region.JP and ce.profile and ce.profile.comments:
                comment = ce.profile.comments[0].comment
                if comment != ce_w.profile.JP:
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
            if func_jp.funcPopupText in ["", "-", "??????"]:
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
            for quest_id in svt.relateQuestIds:
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
            if quest.warId != 1002 and not (
                quest.warId < 1000
                and quest.type == NiceQuestType.free
                and quest.afterClear == NiceQuestAfterClearType.repeatLast
            ):
                continue
            for svt_id, name_jp in enemies.items():
                name = data.view_enemy_names.get(quest_id, {}).get(svt_id)
                _update_mapping(mappings.entity_names, name_jp, name)

        self.jp_data.mappingData = mappings
        del data

    @staticmethod
    def _process_effect_detail(detail: str | None):
        if not detail:
            return detail
        return detail.replace("[g][o]???[/o][/g]", "???")

    def _merge_wiki_translation(self, region: Region, transl: WikiTranslation):
        logger.info(f"merging Wiki translations for {region}")

        def _update_mapping(
            m: dict[_KT, MappingBase[_KV]],
            _key: _KT,
            value: _KV | None,
        ):
            if value is None:
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
            name_jp = name_jp.replace("???", "???")
            _update_mapping(mappings.event_names, name_jp, name_cn)
        for name_jp, name_cn in transl.quest_names.items():
            _update_mapping(mappings.quest_names, name_jp, name_cn)
        for name_jp, name_cn in transl.spot_names.items():
            _update_mapping(mappings.spot_names, name_jp, name_cn)

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
            re.compile(r"(?<![?????????])([?????????])(?=??????|??????|?????????|??????|??????|??????|??????)"),
            re.compile(r"(?<=[:???])([?????????])$"),
            re.compile(r"(?<=[??????(])[?????????](?=[)??????])"),
        ]
        extra_regexes = [re.compile(r"??????(?=??????|??????)")]
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
                return {"???": "Buster", "???": "Arts", "???": "Quick", "??????": "Extra"}[
                    str(match.group(0))
                ]

            for jp_name, regions in mappings_dict[key].items():
                cn_name2 = cn_name = regions["CN"]
                if not cn_name:
                    continue
                if re.findall(r"Buster|Art|Quick|?????????|????????????|????????????", jp_name):
                    for regex in color_regexes:
                        cn_name2 = regex.sub(_repl, cn_name2)
                if re.findall(r"Extra|???????????????", jp_name):
                    for regex in extra_regexes:
                        cn_name2 = regex.sub(_repl, cn_name2)
                cn_name2 = cn_name2.replace("<???????????????", "<Over Charge???")
                cn_name2 = cn_name2.replace("?????????", "NP")
                if cn_name2 != cn_name:
                    # print(f"Convert CN: {cn_name} -> {cn_name2}")
                    regions["CN"] = cn_name2
        # self.test_mapping_dict = mappings_dict
        self.jp_data.mappingData = MappingData.parse_obj(mappings_dict)

    def _add_na_mapping(self):
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
                if value and value == key:
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
