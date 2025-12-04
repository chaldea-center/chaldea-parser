import hashlib
import re
import shutil
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import orjson
import pytz
import requests
from app.schemas.basic import BasicCommandCode, BasicEquip
from app.schemas.common import Region, RegionInfo, Trait
from app.schemas.enums import OLD_TRAIT_MAPPING, SvtClass, get_class_name
from app.schemas.gameenums import EventType, NiceItemType, SvtType
from app.schemas.nice import NiceBaseFunction, NiceBuff, NiceBuffType
from app.schemas.raw import (
    MstEvent,
    MstItem,
    MstQuestPhase,
    MstQuestPhaseIndividuality,
    MstSvt,
    MstWar,
)
from pydantic import BaseModel

from ..config import PayloadSetting, settings
from ..schemas.common import (
    DataVersion,
    FileVersion,
    MappingBase,
    MappingStr,
    MstClass,
    MstClassRelation,
    MstQuestGroup,
    MstViewEnemy,
)
from ..schemas.data import ADD_CES, MIN_APP
from ..schemas.drop_data import DomusAureaData
from ..schemas.gamedata import (
    BasicServant,
    MappingData,
    MasterData,
    NewAddedData,
    NiceBaseSkill,
    NiceBaseTd,
    NiceEquipSort,
)
from ..schemas.mappings import FieldTrait, SvtClassMapping
from ..schemas.wiki_data import AppNews, WikiData, WikiTranslation
from ..utils import (
    AtlasApi,
    DownUrl,
    McApi,
    Worker,
    count_time,
    discord,
    dump_json,
    load_json,
    logger,
    sort_dict,
)
from ..utils.helper import (
    beautify_file,
    describe_regions,
    iter_model,
    parse_json_file_as,
    parse_json_obj_as,
    pydantic_encoder,
)
from ..utils.stopwatch import Stopwatch
from ..wiki.wiki_tool import KnownTimeZone
from .core.aa_export import update_exported_files
from .core.const_data import get_const_data
from .core.dump import DataEncoder
from .core.mapping.autofill import autofill_mapping
from .core.mapping.common import _KT, _T
from .core.mapping.official import (
    fix_cn_transl_qab,
    fix_cn_transl_svt_class,
    merge_official_mappings,
)
from .core.mapping.wiki import merge_atlas_na_mapping, merge_wiki_translation
from .core.mm import load_mm_with_gifts
from .core.quest import get_quest_phase_basic, parse_quest_drops
from .core.ticket import parse_exchange_tickets
from .domus_aurea import run_drop_rate_update
from .helper import get_all_func_val
from .update_mapping import run_mapping_update


# print(f'{__name__} version: {datetime.datetime.now().isoformat()}')


class MainParser:
    def __init__(self):
        self.jp_data = MasterData(region=Region.JP)
        self.wiki_data = WikiData()
        self.payload: PayloadSetting = PayloadSetting()
        logger.info(f"Payload: {self.payload}")
        self.stopwatch = Stopwatch("MainParser")
        self.now = datetime.now()
        self.encoder = DataEncoder(self.jp_data)

    @count_time
    def start(self):
        self.stopwatch.start()

        if self.payload.event in ("gametop", "new_apk_downloaded"):
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
        parse_json_file_as(
            list[AppNews], Path(settings.output_dir) / "static" / "news.json"
        )

        if self.payload.clear_cache_http:
            logger.warning("clear all http_cache")
            AtlasApi.cache_storage.clear()
            McApi.cache_storage.clear()

        logger.info("update_exported_files")
        update_exported_files(self.payload.regions, self.payload.force_update_export)
        self.stopwatch.log("update_export")
        self.wiki_data = WikiData.parse_dir(full_version=True)
        self.stopwatch.log(f"load wiki data")
        self.encoder.jp_data = self.jp_data = self.load_master_data(Region.JP)

        self.merge_all_mappings()
        self.stopwatch.log(f"mappings finish")
        self.parse_quest_data()
        self.stopwatch.log(f"quests")

        self.jp_data.exchangeTickets = parse_exchange_tickets(self.jp_data.nice_item)
        self.jp_data.questGroups = parse_json_obj_as(
            list[MstQuestGroup], DownUrl.git_jp("mstQuestGroup")
        )
        self.wiki_data.mms = load_mm_with_gifts(self.wiki_data.mms)
        self.jp_data.questPhaseDetails = get_quest_phase_basic(
            self.jp_data.quest_dict,
            self.jp_data.mstQuestPhase,
            self.jp_data.mstQuestPhaseDetail,
        )
        self.jp_data.constData = get_const_data(self.jp_data)
        self.save_data()
        print(self.stopwatch.output())

    def add_changes_only(self):
        added = NewAddedData(
            time=datetime.now(pytz.timezone(KnownTimeZone.jst)).isoformat()
        )
        version = parse_json_file_as(DataVersion, settings.output_dist / "version.json")

        def load_data_dict(key: str, field_key: str) -> dict[int, dict]:
            out: dict[int, dict] = {}
            for file in version.files.values():
                if file.key == key:
                    for entry in load_json(settings.output_dist / file.filename) or []:
                        out[entry[field_key]] = entry
            return out

        remote_svts = parse_json_obj_as(list[MstSvt], DownUrl.git_jp("mstSvt"))
        local_svts = load_data_dict("servants", "collectionNo")
        for svt in remote_svts:
            collection = svt.collectionNo
            if collection == 0 or svt.type not in [
                SvtType.NORMAL,
                SvtType.ENEMY_COLLECTION_DETAIL,
            ]:
                continue
            if collection in local_svts:
                continue
            added.svts.append(svt.id)

        remote_ces = parse_json_obj_as(list[BasicEquip], DownUrl.export("basic_equip"))
        local_ces = load_data_dict("craftEssences", "collectionNo")
        for ce in remote_ces:
            collection = ce.collectionNo
            if collection == 0 or collection in local_ces:
                continue
            added.ces.append(ce.id)
        # valentine/anniversary CE
        if len(added.ces) > 15:
            added.ces = []

        remote_ccs = parse_json_obj_as(
            list[BasicCommandCode], DownUrl.export("basic_command_code")
        )
        local_ccs = load_data_dict("commandCodes", "collectionNo")
        for cc in remote_ccs:
            collection = cc.collectionNo
            if collection == 0 or collection in local_ccs:
                continue
            added.ccs.append(cc.id)

        remote_items = parse_json_obj_as(list[MstItem], DownUrl.git_jp("mstItem"))
        local_items = load_data_dict("items", "id")
        for item in remote_items:
            if item.id not in local_items:
                added.items.append(item.id)

        remote_events = parse_json_obj_as(list[MstEvent], DownUrl.git_jp("mstEvent"))
        local_events = load_data_dict("events", "id")
        for event in remote_events:
            if event.id in local_events or event.type != EventType.EVENT_QUEST:
                continue
            added.events.append(event.id)

        remote_wars = parse_json_obj_as(list[MstWar], DownUrl.git_jp("mstWar"))
        local_wars = load_data_dict("wars", "id")
        for war in remote_wars:
            if war.id in local_wars:
                continue
            added.wars.append(war.id)

        if added.is_empty():
            logger.info(f"No new notable resources added")
            return

        def _encoder(obj):
            if isinstance(obj, BaseModel):
                return obj.model_dump(exclude_none=True, exclude_defaults=True)
            return pydantic_encoder(obj)

        add_fv = self._normal_dump(added, "addData", encoder=_encoder)
        version.files[add_fv.filename] = add_fv
        version.timestamp = int(self.now.timestamp())
        version.utc = self.now.isoformat(timespec="seconds").split("+")[0]
        dump_json(version, settings.output_dist / "version.json")

        msg = f"[JP] {version.utc} " + ";".join(
            [
                (
                    k + " " + ",".join([str(x) for x in v])
                    if len(v) < 10
                    else f"{len(v)} {k}"
                )
                for k, v in added.model_dump(
                    exclude_defaults=True, exclude={"time"}
                ).items()
            ]
        )
        settings.commit_msg.write_text(msg)

    def load_master_data(self, region: Region, add_trigger: bool = True) -> MasterData:
        logger.info(f"loading {region} master data")
        data = {}
        for k in MasterData.model_fields:
            fp = settings.atlas_export_dir / region.value / f"{k}.json"
            v = load_json(fp)
            if v:
                data[k] = v
            # print(f'loading {k}: {fp}: {None if v is None else len(data[k])} items')
        data["region"] = f"{region}"
        master_data = parse_json_obj_as(MasterData, data)

        if region == Region.JP:
            entity_ids = {x.id for x in master_data.basic_svt}
            for add_region, ces in ADD_CES.items():
                for collection, (illustrator,) in ces.items():
                    ce = AtlasApi.api_model(
                        f"/nice/{add_region}/equip/{collection}?lore=true",
                        NiceEquipSort,
                        expire_after=(7 if region == Region.JP else 31) * 24 * 3600,
                    )
                    assert ce and ce.profile
                    if illustrator:
                        ce.profile.illustrator = illustrator
                    # ce.sortId = sort_id
                    ce.sortId = -ce.collectionNo
                    master_data.nice_equip_lore.append(ce)
                    if ce.id not in entity_ids:
                        entity = AtlasApi.api_model(
                            f"/basic/{add_region}/svt/{ce.id}",
                            BasicServant,
                            expire_after=7 * 24 * 3600,
                        )
                        assert entity
                        master_data.basic_svt.append(entity)
                        entity_ids.add(entity.id)
            # for svt_id in (600710, 2501500):
            #     extra_svt = AtlasApi.api_model(
            #         f"/nice/JP/svt/{svt_id}?lore=true", NiceServant, 0
            #     )
            #     assert extra_svt is not None and extra_svt.profile
            #     master_data.nice_servant_lore.append(extra_svt)

        if region == Region.NA:
            self.jp_data.all_quests_na = master_data.quest_dict
        for svt in master_data.nice_servant_lore:
            master_data.remainedQuestIds.update(svt.relateQuestIds)
            master_data.remainedQuestIds.update(svt.trialQuestIds)
            if svt.collectionNo == 405:  # 宮本伊織, remove TD "???"
                svt.noblePhantasms = [
                    td for td in svt.noblePhantasms if td.id != 106099
                ]
        master_data.extraMasterMission = [
            mm for mm in master_data.nice_master_mission if mm.id == 10001
        ]
        # raw
        master_data.viewEnemy = parse_json_obj_as(
            list[MstViewEnemy], DownUrl.gitaa("viewEnemy", region)
        )
        master_data.mstEnemyMaster = parse_json_obj_as(
            list[dict], DownUrl.gitaa("mstEnemyMaster", region)
        )
        if region == Region.JP:
            master_data.mstClass = parse_json_obj_as(
                list[MstClass], DownUrl.gitaa("mstClass", region)
            )
            master_data.mstClassRelation = parse_json_obj_as(
                list[MstClassRelation], DownUrl.gitaa("mstClassRelation", region)
            )
            master_data.mstQuestPhase = parse_json_obj_as(
                list[MstQuestPhase], DownUrl.gitaa("mstQuestPhase", region)
            )

        master_data.mstConstant = {
            e["name"]: e["value"] for e in DownUrl.gitaa("mstConstant", region)
        }

        master_data.sort()
        if not add_trigger:
            self.stopwatch.log(f"master data [{region}] no trigger")
            return master_data

        def _add_trigger_skill(
            buff: NiceBuff | None, skill_ids: Iterable[int], is_td=False
        ):
            if buff:
                master_data.mappingData.func_popuptext.setdefault(
                    buff.type.value, MappingStr()
                )
            for skill_id in set(skill_ids):
                self._add_trigger(master_data, skill_id, is_td)

        worker = Worker(f"base_skill_{region}", _add_trigger_skill)
        for skill in master_data.skill_list_no_cache():
            for branch in skill.script.condBranchSkillInfo or []:
                self._add_trigger(master_data, branch.skillId)

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
                worker.add_default(buff, get_all_func_val(func, "SkillID"))
            elif buff.type == NiceBuffType.counterFunction:
                # this is TD
                worker.add_default(buff, get_all_func_val(func, "CounterId"), True)
            elif buff.type == NiceBuffType.substituteInstantDeath:
                # this is TD
                worker.add_default(
                    buff, get_all_func_val(func, "SubstituteSkillId"), True
                )
                worker.add_default(buff, get_all_func_val(func, "ResistSkillId"), True)
            elif buff.type in {
                NiceBuffType.delayFunction,
                NiceBuffType.deadFunction,
                NiceBuffType.battlestartFunction,
                NiceBuffType.wavestartFunction,
                NiceBuffType.selfturnendFunction,
                NiceBuffType.damageFunction,
                NiceBuffType.commandattackAfterFunction,
                NiceBuffType.deadattackFunction,
                NiceBuffType.entryFunction,
                NiceBuffType.reflectionFunction,
                NiceBuffType.attackAfterFunction,
                NiceBuffType.commandcodeattackBeforeFunction,
                NiceBuffType.commandattackBeforeFunction,
                NiceBuffType.gutsFunction,
                NiceBuffType.commandcodeattackAfterFunction,
                NiceBuffType.attackBeforeFunction,
                NiceBuffType.counterFunction,
                NiceBuffType.selfturnstartFunction,
                NiceBuffType.commandcodeattackBeforeFunctionMainOnly,
                NiceBuffType.commandcodeattackAfterFunctionMainOnly,
                NiceBuffType.commandattackBeforeFunctionMainOnly,
                NiceBuffType.commandattackAfterFunctionMainOnly,
                NiceBuffType.attackBeforeFunctionMainOnly,
                NiceBuffType.attackAfterFunctionMainOnly,
                NiceBuffType.skillAfterFunction,
                NiceBuffType.treasureDeviceAfterFunction,
                NiceBuffType.skillAfterFunctionMainOnly,
                NiceBuffType.treasureDeviceAfterFunctionMainOnly,
                NiceBuffType.continueFunction,
                NiceBuffType.confirmCommandFunction,
                NiceBuffType.skillBeforeFunction,
                NiceBuffType.skillTargetedBeforeFunction,
                NiceBuffType.fieldIndividualityChangedFunction,
                NiceBuffType.treasureDeviceBeforeFunction,
                NiceBuffType.stepInAfterFunction,
                NiceBuffType.functionedFunction,
                NiceBuffType.comboStartFunction,
                NiceBuffType.comboEndFunction,
            } or buff.type.name.endswith("Function"):
                worker.add_default(buff, get_all_func_val(func, "Value"))
        skillIds = set()
        for svt in master_data.nice_servant_lore:
            for skills in (svt.script.SkillRankUp or {}).values():
                skillIds.update(skills)
            for skills in svt.ascensionAdd.overwriteClassPassive.ascension.values():
                skillIds.update(skills)
            for skills in svt.ascensionAdd.overwriteClassPassive.costume.values():
                skillIds.update(skills)
        worker.add_default(None, skillIds)
        # trigger in trigger or some weird trigger
        # 世界樹への生贄, マンドリカルド-間際の一撃, クロエx2
        worker.add_default(None, [966447, 970405, 970412, 970413])
        # grand board
        worker.add_default(None, [994725, 5009002])
        worker.add_default(
            None,
            [
                item.value
                for item in master_data.nice_item
                if item.type == NiceItemType.eventPassiveSkillGiven and item.value > 0
            ],
        )

        worker.wait()
        logger.info(
            f"{region}: loaded {len(master_data.base_skills)} trigger skills, {len(master_data.base_tds)} trigger TD"
        )

        if region != Region.JP:
            jp_item_ids = set(item.id for item in self.jp_data.nice_item)
            for item in master_data.nice_item:
                if (
                    item.type in (NiceItemType.friendshipUpItem,)
                    and item.id not in jp_item_ids
                ):
                    self.jp_data.nice_item.append(item)

        self.stopwatch.log(f"master data [{region}]")
        return master_data

    @classmethod
    def _add_trigger(
        cls, master_data: MasterData, skill_id: int | None, is_td: bool = False
    ):
        region = master_data.region
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

    def event_field_trait(self):
        # field_indiv: warId[]
        fields: dict[int, set[int]] = defaultdict(set)
        quest_list = parse_json_obj_as(
            list[MstQuestPhase], DownUrl.git_jp("mstQuestPhase")
        )
        phase_indiv_list = parse_json_obj_as(
            list[MstQuestPhaseIndividuality],
            DownUrl.git_jp("mstQuestPhaseIndividuality"),
        )
        for phase in quest_list:
            quest = self.jp_data.quest_dict.get(phase.questId)
            if not quest or quest.warId == 9999:
                continue
            for indiv in phase.individuality:
                if indiv >= 94000000:
                    fields[indiv].add(quest.warId)
        for phase in phase_indiv_list:
            quest = self.jp_data.quest_dict.get(phase.questId)
            if not quest or quest.warId == 9999:
                continue
            for indiv in phase.individuality or []:
                if indiv >= 94000000:
                    fields[indiv].add(quest.warId)
        ids = sorted(fields.keys())
        self.jp_data.mappingData.field_trait = {
            k: FieldTrait(warIds=sorted(fields[k])) for k in ids
        }

    def parse_quest_data(self):
        """Need NA data, run after mappings merged"""
        if not settings.output_wiki.joinpath("domusAurea.json").exists():
            logger.info("domusAurea.json not exist, run domus_aurea parser")
            run_drop_rate_update()
        domus_data = parse_json_file_as(
            DomusAureaData, settings.output_wiki / "domusAurea.json"
        )
        self.jp_data.dropData.domusVer = domus_data.updatedAt
        self.jp_data.dropData.domusAurea = domus_data.newData
        parse_quest_drops(self.jp_data, self.payload)

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
                obj,
                default=encoder or self.encoder.default,
                indent2=False,
                new_line=False,
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
            _last_version = parse_json_file_as(
                DataVersion, settings.output_dist / "version.json"
            )
        except:  # noqa
            _last_version = cur_version.model_copy(deep=True)

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
            n = (len(obj) / count).__ceil__()
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
                if f.name in ("addData.json", "gametop.json"):
                    continue
                elif f.is_file():
                    f.unlink()
                elif f.is_dir():
                    shutil.rmtree(f)

        servants = list(data.nice_servant_lore)

        _normal_dump(data.nice_item, "items")
        self.encoder.item = True
        _normal_dump(data.basic_svt, "entities")
        self.encoder.basic_svt = True
        _normal_dump(data.nice_bgm, "bgms")
        self.encoder.bgm = True
        _dump_by_count(servants, 100, "servants")
        _dump_by_count(data.nice_equip_lore, 500, "craftEssences")
        _normal_dump(data.nice_command_code, "commandCodes")
        _normal_dump(data.nice_mystic_code, "mysticCodes")
        _normal_dump(data.exchangeTickets, "exchangeTickets")
        _normal_dump(data.nice_enemy_master, "enemyMasters")
        _normal_dump(data.nice_class_board, "classBoards")
        _normal_dump(data.nice_grand_graph, "grandGraphs")
        _normal_dump(list(wiki_data.mms.values()), "masterMissions")

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

        event_dict = dict(data.event_dict)
        # event_dict.pop(71543, None)  # 期間限定で攻撃威力アップ！
        _dump_by_ranges(
            event_dict,
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
                list(range(0, 2000))
                + list(range(40000, 41000))
                + list(range(9999, 19000)),
                range(8000, 9000),
                range(9000, 9050),
                range(9050, 9100),
                range(9100, 9999),
            ],
            save_remained=False,
            key="wars",
        )
        # sometimes disabled quest parser when debugging
        _normal_dump(self.jp_data.dropData, "dropData")
        if data.cachedQuestPhases:
            _dump_by_count(list(data.cachedQuestPhases.values()), 100, "questPhases")
        _normal_dump(data.extraMasterMission, "extraMasterMission")
        _normal_dump(data.questGroups, "questGroups")
        for index, phases in enumerate(data.questPhaseDetails):
            _normal_dump(
                phases, "questPhaseDetails", f"questPhaseDetails.{index+1}.json"
            )

        _dump_by_count(data.nice_gacha, 2000, "mstGacha")
        _normal_dump(list(wiki_data.campaigns.values()), "campaigns")

        assert data.constData
        _normal_dump(data.constData, "constData")
        _dump_by_count(list(wiki_data.servants.values()), 100, "wiki.servants")
        _dump_by_count(
            list(wiki_data.craftEssences.values()), 500, "wiki.craftEssences"
        )
        _normal_dump(list(wiki_data.commandCodes.values()), "wiki.commandCodes")
        wiki_events = list(wiki_data.events.values())
        wiki_events_normal = [e for e in wiki_events if e.id > 0]
        wiki_events_campaign = [e for e in wiki_events if e.id < 0]
        _normal_dump(list(wiki_events_normal), "wiki.events", "wiki.events.1.json")
        _normal_dump(list(wiki_events_campaign), "wiki.events", "wiki.events.2.json")
        _normal_dump(list(wiki_data.wars.values()), "wiki.wars")
        _dump_by_count(list(wiki_data.summons.values()), 100, "wiki.summons")
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
        msg = f"{cur_version.minimalApp}, {cur_version.utc}"
        if len(self.payload.regions) not in (0, len(Region.__members__)):
            msg = describe_regions(self.payload.regions) + msg
        settings.commit_msg.write_text(msg)
        try:
            self.gametop()
        except Exception as e:
            logger.exception(f"update gametop failed")
            discord.text(f"Update gametop failed: {e}")

    @staticmethod
    def _replace_dw_chars(content: _T) -> _T:
        # '魔{jin}剑', 鯖江
        chars = {"\ue000": "{jin}", "\ue001": "鯖", "\ue00b": "槌"}
        if isinstance(content, str):
            for k, v in chars.items():
                content = content.replace(k, v)  # type: ignore
        elif isinstance(content, bytes):
            for k, v in chars.items():
                content = content.replace(k.encode(), v.encode())  # type: ignore
        return content

    def _patch_mappings(
        self, mappings: MappingData, last_ver: DataVersion
    ) -> tuple[dict[str, dict], dict[str, dict]]:
        encoded = dump_json(
            self._encode_mapping_data(mappings),
            default=self.encoder.default,
            indent2=False,
            new_line=False,
        )
        assert encoded
        encoded = self._replace_dw_chars(encoded)

        data1: dict = orjson.loads(encoded)
        releases = {k: v for k, v in data1.items() if str(k).endswith("_release")}
        if not self.payload.patch_mappings:
            return data1, releases
        data0 = {}
        for file in last_ver.files.values():
            if file.key == "mappingData":
                data0.update(
                    orjson.loads((settings.output_dist / file.filename).read_text())
                )
        if not data0:
            return data1, releases

        def _create_patch(new_: dict, old_: dict) -> dict:
            # only addition and changes, no deletion
            patch = {}
            for k, v in new_.items():
                if k not in old_ or str(k).endswith("_release"):
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

        _dict = data.model_dump(exclude_none=True)
        _dict = _clean_map(_dict)
        data = parse_json_obj_as(MappingData, _dict)

        for k, v in iter_model(data, exclude_none=True):
            if isinstance(v, MappingBase):
                r[k] = v.model_dump(exclude_none=True)
            elif isinstance(v, dict):
                r[k] = sort_dict(v)
            else:
                r[k] = v
        return r

    def merge_all_mappings(self):
        logger.info("merge all mappings")
        if not self.payload.skip_mapping:
            # CN
            merge_official_mappings(
                self.jp_data, self.load_master_data(Region.CN), self.wiki_data
            )
            merge_wiki_translation(
                self.jp_data,
                Region.CN,
                parse_json_file_as(
                    WikiTranslation, settings.output_wiki / "mcTransl.json"
                ),
            )
            self._fix_cn_translation()
            # NA
            merge_official_mappings(
                self.jp_data, self.load_master_data(Region.NA), self.wiki_data
            )
            self.jp_data.mappingData = merge_atlas_na_mapping(self.jp_data.mappingData)
            merge_wiki_translation(
                self.jp_data,
                Region.NA,
                parse_json_file_as(
                    WikiTranslation, settings.output_wiki / "fandomTransl.json"
                ),
            )
            # TW
            merge_official_mappings(
                self.jp_data, self.load_master_data(Region.TW), self.wiki_data
            )
            # KR
            merge_official_mappings(
                self.jp_data, self.load_master_data(Region.KR), self.wiki_data
            )
        self.event_field_trait()
        self._add_enum_mappings()
        self._merge_repo_mapping()
        self.jp_data.mappingData = parse_json_obj_as(
            MappingData,
            autofill_mapping(
                orjson.loads(self.jp_data.mappingData.model_dump_json()),
                self.wiki_data.mcTransl,
            ),
        )
        self._post_mappings()

    def _post_mappings(self):
        mappings = self.jp_data.mappingData
        for key in mappings.war_names.keys():
            name = mappings.event_names.pop(key, None)
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
        for key in mappings.event_trait.keys():
            mappings.trait.pop(key, None)
        for key in mappings.field_trait.keys():
            mappings.trait.pop(key, None)

    def _add_enum_mappings(self):
        mappings = self.jp_data.mappingData
        for k, v in self.jp_data.nice_trait.items():
            if v in OLD_TRAIT_MAPPING:
                continue
            m_trait = mappings.trait.setdefault(k, MappingStr())
            if v != Trait.unknown:
                m_trait.update(Region.NA, v.value, skip_exists=True)

        enums = self.jp_data.mappingData.enums
        enums.update_enums()
        for cls_info in self.jp_data.mstClass:
            v = enums.svt_class.setdefault(cls_info.id, SvtClassMapping())
            name = get_class_name(cls_info.id)
            if isinstance(name, SvtClass):
                name = name.value
            v.name = name
        svt_class = sort_dict(enums.svt_class)
        enums.svt_class = {}
        enums.svt_class = svt_class

    def _fix_cn_translation(self):
        logger.info("fix Chinese translations")
        mappings = self.jp_data.mappingData
        mappings_dict: dict[str, dict] = mappings.model_dump()

        for key in (
            "buff_detail",
            "buff_names",
            "func_popuptext",
            "skill_detail",
            "td_detail",
            "skill_names",
        ):
            fix_cn_transl_qab(mappings_dict[key])
        fix_cn_transl_svt_class(
            mappings_dict, ["对{0}", "({0})", "（{0}）", "〔{0}〕", "{0}职阶"]
        )
        for key in ["svt_names", "entity_names"]:
            fix_cn_transl_svt_class(mappings_dict[key], ["的{0}"])
        self.jp_data.mappingData = parse_json_obj_as(MappingData, mappings_dict)

    def _merge_repo_mapping(self):
        logger.info("merging repo translations")

        folder = settings.output_mapping
        mappings = self.jp_data.mappingData
        mapping_dict = orjson.loads(mappings.model_dump_json())
        mappings_repo = {
            k: load_json(folder / f"{k}.json", {}) for k in MappingData.model_fields
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
        self.jp_data.mappingData = parse_json_obj_as(MappingData, mappings_repo)

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
    def gametop():
        fp = settings.output_dist / "gametop.json"
        data = {
            "JP": {
                "region": "JP",
                "gameServer": "game.fate-go.jp",
                "bundle": "com.aniplex.fategrandorder",
                "unityVer": "2022.3.28f1",
            },
            "NA": {
                "region": "NA",
                "gameServer": "game.fate-go.us",
                "bundle": "com.aniplex.fategrandorder.en",
                "unityVer": None,
            },
            "CN": {
                "region": "CN",
                "gameServer": "",
                "bundle": "com.bilibili.fatego",
                "unityVer": "2022.3.18f1",
            },
        }

        for region in data.keys():
            region_info = AtlasApi.api_model(
                f"/raw/{region}/info", RegionInfo, expire_after=0
            )
            assert region_info
            data[region] |= {
                "hash": region_info.hash,
                "timestamp": region_info.timestamp,
                "serverHash": region_info.serverHash,
                "serverTimestamp": region_info.serverTimestamp,
                "dataVer": region_info.dataVer or 0,
                "dateVer": region_info.dateVer or 0,
                "assetbundle": region_info.assetbundle,
            }

        for region in ["JP", "NA"]:
            top = DownUrl.gitaa("gamedatatop", Region(region), "")
            top = top["response"][0]["success"]
            assetbundle = DownUrl.gitaa("assetbundle", Region(region), "metadata/")
            ver_codes = requests.get(
                f"https://fgo.square.ovh/{region}/verCode.txt?t={int(time.time())}"
            ).text
            ver_code_match = re.match(
                r"^appVer=(\d+\.\d+\.\d+)&verCode=([0-9a-f]{64})$", ver_codes
            )
            assert ver_code_match, ver_codes
            data[region] |= {
                "appVer": ver_code_match.group(1),
                "verCode": ver_code_match.group(2),
                "dataVer": max(data[region]["dataVer"], top["dataVer"]),
                "dateVer": max(data[region]["dateVer"], top["dateVer"]),
                "assetbundleFolder": assetbundle["folderName"],
            }

        # CN
        cn_top = DownUrl.gitaa("gamedatatop", Region.CN, "")
        cn_top = cn_top["response"][0]["success"]
        cn_config = requests.get("https://static.biligame.com/config/fgo.config.js")
        data["CN"] |= {
            "appVer": re.findall(r"_([1-3]\.\d+\.\d+)_[^\"]+\.apk", cn_config.text)[0],
            "verCode": "",
            "dataVer": cn_top["version"],
            "dateVer": 0,
            "assetbundleFolder": "",
        }
        dump_json(data, fp)
