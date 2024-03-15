"""
SVT,CE,CC: 基本信息+个人资料+愚人节
Event: wiki_data/events.json + MC data
  - 狩猎关卡: quests
Summon: wiki_data/summons.json + MC data
"""

import binascii
import re
from collections import Counter, defaultdict
from datetime import datetime
from typing import Optional, Type
from urllib.parse import urlparse

import requests
import wikitextparser
from app.schemas.gameenums import NiceEventType
from app.schemas.nice import NiceEvent, NiceLoreComment, NiceServant
from pydantic import parse_file_as

from ..config import PayloadSetting, settings
from ..schemas.common import (
    CEObtain,
    DataVersion,
    MappingStr,
    Region,
    SummonType,
    SvtObtain,
)
from ..schemas.data import ADD_CES, jp_chars
from ..schemas.wiki_data import (
    CampaignEvent,
    CommandCodeW,
    CraftEssenceW,
    EventW,
    LimitedSummon,
    ProbGroup,
    ServantW,
    SubSummon,
    WarW,
    WikiData,
    WikiTranslation,
)
from ..utils import Worker, count_time, discord, dump_json, load_json, logger
from ..utils.helper import _KT, mean, parse_html_xpath, sort_dict
from ..wiki import FANDOM, MOONCELL
from ..wiki.template import (
    find_tabber,
    mwparse,
    parse_template,
    parse_template_list,
    remove_tag,
)
from ..wiki.wiki_tool import KnownTimeZone
from .core.aa_export import update_exported_files
from .wiki import replace_banner_url


class _WikiTemp:
    def __init__(self, region: Region) -> None:
        self.region = region
        self.invalid_links: list[str] = []
        self.released_svts: dict[int, NiceServant] = {}
        self.events: dict[int, NiceEvent] = {}

    def init(self):
        self._load_svts()
        if self.region == Region.JP:
            self._load_events()

    def _load_svts(self):
        servants = parse_file_as(
            list[NiceServant],
            f"{settings.atlas_export_dir}/{self.region}/nice_servant_lore.json",
        )
        self.released_svts = {e.collectionNo: e for e in servants}

    def _load_events(self):
        events = parse_file_as(
            list[NiceEvent],
            f"{settings.atlas_export_dir}/{self.region}/nice_event.json",
        )
        self.events = {e.id: e for e in events}


class WikiParser:
    def __init__(self):
        self.wiki_data: WikiData = WikiData()
        self.unknown_chara_mapping: dict[str, MappingStr] = {}
        self._svt_id_cache: dict[str, int] = {}
        self._ce_id_cache: dict[str, int] = {}
        self._mc = _WikiTemp(Region.CN)
        self._fandom = _WikiTemp(Region.NA)
        self._jp = _WikiTemp(Region.JP)
        self.payload = PayloadSetting()

    @property
    def mc_transl(self) -> WikiTranslation:
        return self.wiki_data.mcTransl

    @property
    def fandom_transl(self) -> WikiTranslation:
        return self.wiki_data.fandomTransl

    @count_time
    def start(self):
        if self.payload.run_wiki_parser is False:
            logger.info("run_wiki_parser=False, skip")
            return
        Worker.fake_mode = not self.payload.enable_wiki_threading
        update_exported_files(self.payload.regions, self.payload.force_update_export)

        self._jp.init()
        self._mc.init()
        self._fandom.init()
        MOONCELL.load(self.payload.clear_wiki_empty)
        FANDOM.load(self.payload.clear_wiki_empty)
        MOONCELL.remove_all_changes(
            self.payload.clear_wiki_changed, self.payload.clear_wiki_moved
        )
        FANDOM.remove_all_changes(
            self.payload.clear_wiki_changed, self.payload.clear_wiki_moved
        )

        self.init_wiki_data()
        logger.info("[MC] parsing servant data")
        self.mc_svt()
        logger.info("[MC] parsing craft essence data")
        self.mc_ce()
        logger.info("[MC] parsing command code data")
        self.mc_cc()
        logger.info("[MC] parsing mystic code data")
        self.mc_mystic()
        logger.info("[MC] parsing campaign")
        self.mc_campaigns()
        logger.info("[MC] parsing event/war/quest data")
        self.mc_events()
        self.mc_wars()
        self.mc_quests()
        logger.info("[MC] parsing summon data")
        self.mc_summon()
        logger.info("[MC] parsing extra data")
        self.mc_extra()
        logger.info("[Fandom] parsing servant data")
        self.fandom_svt()
        logger.info("[Fandom] parsing craft essence data")
        self.fandom_ce()
        logger.info("[Fandom] parsing command code data")
        self.fandom_cc()
        logger.info("[Fandom] parsing quest from main story")
        self.fandom_quests()
        logger.info("[Fandom] parsing extra data")
        self.fandom_extra()

        self.check_invalid_wikilinks()
        logger.info("[wiki] official banner")
        replace_banner_url.main(
            list(self.wiki_data.wars.values()),
            list(self.wiki_data.events.values()),
            list(self.wiki_data.summons.values()),
            False,
        )
        # self.check_webcrow()

        logger.info("Saving data...")
        MOONCELL.save_cache()
        FANDOM.save_cache()
        self.save_data()

    def init_wiki_data(self):
        self.wiki_data = WikiData.parse_dir(full_version=False)

        chara_names: dict = (
            load_json(settings.output_mapping / "chara_names.json") or {}
        )
        self.unknown_chara_mapping = {
            k: MappingStr.parse_obj(v) for k, v in chara_names.items()
        }

    def _need_wiki_profile(self, region: Region, collectionNo: int) -> bool:
        servants = (self._mc if region == Region.CN else self._fandom).released_svts
        if collectionNo not in servants:
            return True
        if collectionNo not in self._jp.released_svts:
            return False
        svt = servants[collectionNo]
        svt_jp = self._jp.released_svts[collectionNo]
        assert svt.profile and svt_jp.profile

        def _get_dict(_comments: list[NiceLoreComment]):
            tmp = defaultdict(dict)
            for c in _comments:
                tmp[c.id][c.priority] = c
            return {k * 10 + min(v.keys()): v[min(v.keys())] for k, v in tmp.items()}

        comments = _get_dict(svt.profile.comments)
        comments_jp = _get_dict(svt_jp.profile.comments)
        if len(comments) != len(comments_jp):
            return True
        for key, comment in comments.items():
            if comment.id != 7:
                continue
            comment_jp = comments_jp.get(key)
            if comment_jp and not comment_jp.comment:
                continue
            if region == Region.CN and len(comment.comment) < 20:
                return True
            if region == Region.NA and len(comment.comment) < 50:
                return True
        return False

    def get_svt_obtains(self, methods: str, detail_method: str) -> list[SvtObtain]: ...

    @staticmethod
    def _load_list_from_dist(key: str, _type: Type[_KT]) -> list[_KT]:
        out: list[_KT] = []
        versions = parse_file_as(DataVersion, settings.output_dist / "version.json")
        for file in versions.files.values():
            if file.key == key:
                out.extend(
                    parse_file_as(list[_type], settings.output_dist / file.filename)
                )
        return out

    def mc_svt(self):
        index_data = _mc_index_data("英灵图鉴/数据")

        prev_data = self._load_list_from_dist("wiki.servants", ServantW)
        extra_pages: dict[int, str] = {}
        extra_pages |= {k: v["name_link"] for k, v in index_data.items()}
        extra_pages |= {v.collectionNo: v.mcLink for v in prev_data if v.mcLink}
        extra_pages = {
            k: MOONCELL.moved_pages.get(v, v) for k, v in extra_pages.items()
        }
        extra_pages |= self.payload.mc_extra_svt
        extra_pages = extra_pages | _mc_smw_card_list("英灵图鉴", "序号")
        no_index_ids = [
            svt.collectionNo
            for svt in prev_data
            if not svt.mcLink and svt.collectionNo not in extra_pages
        ]
        if no_index_ids:
            logger.info(f"svt not in index: {no_index_ids}")

        def _parse_one(svt_id: int):
            svt_add = self.wiki_data.get_svt(svt_id)
            col_no = svt_add.collectionNo
            record = index_data.get(svt_id)
            nicknames: set[str] = set()
            svt_add.mcLink = extra_pages.get(svt_id) or svt_add.mcLink
            if record:
                nicknames.update([s.strip() for s in record["name_other"].split("&")])
                obtains: list[SvtObtain] = []
                for m in re.split(r"<br>|&", record["method"]):
                    if m not in ("活动通关奖励", "事前登录赠送"):
                        obtain = SvtObtain.from_cn(m)
                        if obtain != SvtObtain.unknown:
                            obtains.append(obtain)
                obtains = list(set(obtains))
                svt_add.obtains = sorted(obtains)

            if not svt_add.mcLink:
                return
            svt_add.mcLink = MOONCELL.moved_pages.get(svt_add.mcLink) or svt_add.mcLink

            # profile
            wikitext = mwparse(MOONCELL.get_page_text(svt_add.mcLink))
            params = parse_template(wikitext, r"^{{基础数值")
            name_cn, name_cn2 = params.get2("直译名") or params.get2(
                "中文名"
            ), params.get2("中文名2")
            name_jp, name_jp2 = params.get2("日文名"), params.get2("日文名2")
            if name_cn and name_jp:
                self.mc_transl.svt_names[name_jp] = name_cn
            if name_cn2 and name_jp2:
                self.mc_transl.svt_names[name_jp2] = name_cn2
            nicknames.update(re.split(r"[,，&]", params.get2("昵称") or ""))
            if svt_add.nicknames.CN:
                nicknames.update(svt_add.nicknames.CN)
            nicknames = set([s for s in nicknames if s])
            if nicknames:
                svt_add.nicknames.CN = sorted(nicknames)
            else:
                svt_add.nicknames.CN = None

            if not svt_add.obtains:
                detail_obtain = params.get2("获取途径")
                if detail_obtain:
                    obtain = SvtObtain.from_cn2(detail_obtain)
                    svt_add.obtains.append(obtain)

            # FGL - aa
            if 1 <= col_no <= 375 and col_no not in (83, 149, 151, 152, 168, 240, 333):
                svt_add.aprilFoolAssets.extend(
                    [
                        f"https://static.atlasacademy.io/JP/FGL/SaintGraph/card_sg_{col_no:03}.png",
                        f"https://static.atlasacademy.io/JP/FGL/Figure/figure_{col_no:03}.png",
                    ]
                )
            # riyo - aa
            if 1 <= col_no <= 336 and col_no not in (83, 149, 151, 152, 168, 240, 333):
                svt_id = self._jp.released_svts[col_no].id
                svt_add.aprilFoolAssets.append(
                    f"https://static.atlasacademy.io/CN/af_2023/{svt_id}c@1.png"
                )
            # riyo - mc
            if svt_add.collectionNo == 1:
                svt_add.aprilFoolAssets.append(
                    MOONCELL.get_image_url("玛修·基列莱特-卡面-y.png")
                )
            if svt_add.collectionNo == 83:
                svt_add.aprilFoolAssets.append(
                    MOONCELL.get_image_url("083所罗门愚人节.png")
                )
            if svt_add.collectionNo == 150:
                svt_add.aprilFoolAssets.append(
                    MOONCELL.get_image_url("梅林-愚人节2021.png")
                )
            # FGL - mc
            for index in range(1, 15):
                if "Grail League" in (params.get(f"立绘{index}") or ""):
                    illustration = params.get(f"文件{index}")
                    if illustration:
                        svt_add.aprilFoolAssets.append(
                            MOONCELL.get_image_url(f"{illustration}.png")
                        )
            # riyo-old mc
            for index in range(1, 15):
                if "愚人节（背景变更前）" in (params.get(f"立绘{index}") or ""):
                    illustration = params.get(f"文件{index}")
                    if illustration:
                        svt_add.aprilFoolAssets.append(
                            MOONCELL.get_image_url(f"{illustration}.png")
                        )

            april_profile_jp, april_profile_cn = [], []
            for params in parse_template_list(wikitext, r"^{{愚人节资料"):
                text_jp, text_cn = params.get2("日文"), params.get2("中文")
                if text_jp:
                    april_profile_jp.append(text_jp)
                if text_cn:
                    april_profile_cn.append(text_cn)
            if april_profile_jp:
                svt_add.aprilFoolProfile.JP = "\n\n".join(april_profile_jp)
            if april_profile_cn:
                svt_add.aprilFoolProfile.CN = "\n\n".join(april_profile_cn)

            need_profile = self._need_wiki_profile(Region.CN, svt_add.collectionNo)
            if need_profile:
                for params in parse_template_list(wikitext, r"^{{个人资料"):
                    for index in range(8):
                        prefix = "详情" if index == 0 else f"资料{index}"
                        comment = params.get2(prefix) or ""
                        if comment:
                            profiles = svt_add.mcProfiles.setdefault(index, [])
                            profiles.append(comment)

            for params in parse_template_list(wikitext, r"^{{持有技能"):
                text_cn, text_jp = params.get2(2), params.get2(3)
                if text_cn and text_jp:
                    self.mc_transl.skill_names[text_jp] = text_cn

            for params in parse_template_list(wikitext, r"^{{宝具"):
                td_name_cn, td_ruby_cn = params.get2("中文名"), params.get2("国服上标")
                td_name_jp, td_ruby_jp = params.get2("日文名"), params.get2("日服上标")
                if td_name_cn and td_name_jp:
                    self.mc_transl.td_names[td_name_jp] = td_name_cn
                if td_ruby_cn and td_ruby_jp:
                    self.mc_transl.td_ruby[td_ruby_jp] = td_ruby_cn
            for params in parse_template_list(wikitext, r"^{{战斗形象"):
                for key, value in params.items():
                    if ("模型" in key or "灵衣" in key) and str(value).endswith(".png"):
                        svt_add.mcSprites.append(MOONCELL.get_image_name(value))

            # td_av_text = MOONCELL.get_page_text(f"{svt_add.mcLink}/宝具动画")
            # for params in parse_template_list(td_av_text, r"^{{宝具动画"):
            #     av = params.get_cast("av", int) or 74352743
            #     p = params.get_cast("p", int) or 1
            #     svt_add.tdAnimations.append(BiliVideo(av=av, p=p))

        worker = Worker.from_map(
            _parse_one,
            set(self.wiki_data.servants.keys())
            | set(index_data.keys())
            | set(extra_pages.keys()),
            name="mc_svt",
        )
        worker.wait()

        release_wikitext = MOONCELL.expand_template(
            """{{#ask:
[[分类:英灵图鉴]][[基础ATK::+]]
|?序号|?获取途径|?创建日期#ISO
|format=template|template=沙盒/清玄/0/0
|userparam=实装时间
|sort=序号|order=desc
|link=none|limit=1000
}}"""
        )

        def parse_date(s: str):
            s = s.strip()
            if not s or s == "∅":
                return None
            return int(datetime.fromisoformat(s).timestamp())

        release_matches = re.findall(
            r";No\.(\d+) .*\n:日服：(.*)\n:国服：(.*)\n:创建：(.*)<br", release_wikitext
        )
        release_times: dict[int, int] = {}
        for svt_id, t_jp, t_cn, t_page in release_matches:
            svt_id = int(svt_id)
            if svt_id < 198:
                # 葛飾北斎, JP 2018/1/1
                continue
            t_jp, t_cn, t_page = parse_date(t_jp), parse_date(t_cn), parse_date(t_page)
            released_at = t_jp or t_page
            if released_at:
                release_times[svt_id] = released_at
        # in case some pages are created before released
        release_list = [
            release_times.get(x, 0) for x in range(max(release_times.keys()) + 1)
        ]
        for index in range(198, len(release_list)):
            prev_ts = [x for x in release_list[index - 5 : index] if x]
            if not prev_ts:
                continue
            if release_list[index] < mean(prev_ts):
                release_list[index] = 0
        for svt_id, released_at in enumerate(release_list):
            if released_at > 0:
                self.wiki_data.get_svt(svt_id).releasedAt = released_at

    def mc_ce(self):
        index_data = _mc_index_data("礼装图鉴/数据")

        prev_data = self._load_list_from_dist("wiki.craftEssences", CraftEssenceW)

        extra_pages: dict[int, str] = {}
        extra_pages |= {k: v["name_link"] for k, v in index_data.items()}
        extra_pages |= {v.collectionNo: v.mcLink for v in prev_data if v.mcLink}
        extra_pages = {
            k: MOONCELL.moved_pages.get(v, v) for k, v in extra_pages.items()
        }
        extra_pages |= self.payload.mc_extra_ce
        extra_pages = extra_pages | _mc_smw_card_list("礼装图鉴", "礼装序号")
        no_index_ids = [
            ce.collectionNo
            for ce in prev_data
            if not ce.mcLink
            and ce.collectionNo not in extra_pages
            and ce.collectionNo < 200000
        ]
        if no_index_ids:
            logger.info(f"ce not in index: {no_index_ids}")
        region_campaign_ces = set(k for v in ADD_CES.values() for k in v.keys())

        def _parse_one(ce_id: int):
            ce_add = self.wiki_data.get_ce(ce_id)
            if ce_id in region_campaign_ces:
                ce_add.obtain = CEObtain.campaign
            ce_add.mcLink = extra_pages.get(ce_id) or ce_add.mcLink

            record = index_data.get(ce_id)
            if record:
                ce_add.obtain = CEObtain.from_cn(record["type"])

                des = record.get("des")
                if des and des != "无效果" and not jp_chars.search(des):
                    des = remove_tag(des).replace("\n", "").strip()
                    self.mc_transl.ce_skill_des[ce_add.collectionNo] = des
                des_max = record.get("des_max")
                if des_max and des_max != "无效果" and not jp_chars.search(des_max):
                    des_max = remove_tag(des_max).replace("\n", "").strip()
                    self.mc_transl.ce_skill_des_max[ce_add.collectionNo] = des_max

            if not ce_add.mcLink:
                return
            ce_add.mcLink = MOONCELL.moved_pages.get(ce_add.mcLink) or ce_add.mcLink

            wikitext = mwparse(MOONCELL.get_page_text(ce_add.mcLink))
            params = parse_template(wikitext, r"^{{概念礼装")
            name_cn = params.get2("名称")
            name_jp = params.get2("日文名称")
            if name_cn and name_jp:
                self.mc_transl.ce_names[name_jp] = name_cn
            profile_cn = params.get2("解说")
            if profile_cn:
                ce_add.profile.CN = profile_cn
            ce_add.characters = []
            ce_add.unknownCharacters = []
            for index in range(20):
                key = "出场角色" if index == 0 else index
                chara = params.get2(key)
                if not chara:
                    continue
                known_, unknown_ = self._parse_chara(chara)
                ce_add.characters.extend(known_)
                ce_add.unknownCharacters.extend(unknown_)
            ce_add.characters = sorted(set(ce_add.characters))
            ce_add.unknownCharacters = sorted(set(ce_add.unknownCharacters))
            detail_obtain = params.get2("礼装分类")
            if ce_add.obtain == CEObtain.unknown and detail_obtain:
                ce_add.obtain = CEObtain.from_cn2(detail_obtain)

            skill_des = params.get2("持有技能")
            if skill_des and skill_des != "无效果" and not jp_chars.search(skill_des):
                lines = skill_des.splitlines()
                if len(lines) == 2 and "最大解放" in skill_des:
                    self.mc_transl.ce_skill_des.setdefault(
                        ce_add.collectionNo, lines[0].strip()
                    )
                    self.mc_transl.ce_skill_des_max.setdefault(
                        ce_add.collectionNo, lines[1].strip()
                    )
                elif len(lines) == 1:
                    self.mc_transl.ce_skill_des.setdefault(
                        ce_add.collectionNo, lines[0].strip()
                    )

        worker = Worker.from_map(
            _parse_one,
            set(self.wiki_data.craftEssences.keys())
            | set(index_data.keys())
            | set(extra_pages.keys())
            | region_campaign_ces,
            name="mc_ce",
        )
        worker.wait()

    def mc_cc(self):
        index_data = _mc_index_data("指令纹章图鉴/数据")

        prev_data = self._load_list_from_dist("wiki.commandCodes", CommandCodeW)
        extra_pages: dict[int, str] = {}
        extra_pages |= {k: v["name_link"] for k, v in index_data.items()}
        extra_pages |= {v.collectionNo: v.mcLink for v in prev_data if v.mcLink}
        extra_pages = {
            k: MOONCELL.moved_pages.get(v, v) for k, v in extra_pages.items()
        }
        extra_pages = extra_pages | _mc_smw_card_list("指令纹章图鉴", "纹章序号")
        no_index_ids = [
            cc.collectionNo
            for cc in prev_data
            if not cc.mcLink and cc.collectionNo not in extra_pages
        ]
        if no_index_ids:
            logger.info(f"cc not in index: {no_index_ids}")

        def _parse_one(cc_id: int):
            cc_add = self.wiki_data.get_cc(cc_id)
            cc_add.mcLink = extra_pages.get(cc_id) or cc_add.mcLink
            record = index_data.get(cc_id)
            if record:
                pass

            if not cc_add.mcLink:
                return
            cc_add.mcLink = MOONCELL.moved_pages.get(cc_add.mcLink) or cc_add.mcLink

            wikitext = mwparse(MOONCELL.get_page_text(cc_add.mcLink))
            params = parse_template(wikitext, r"^{{指令纹章")
            name_cn = params.get2("名称")
            name_jp = params.get2("日文名称")
            if name_cn and name_jp and cc_add.collectionNo != 113:
                # 113-小犭贪
                self.mc_transl.cc_names[name_jp] = name_cn
            skill_des = params.get2("持有技能", strip=True)
            if skill_des and not jp_chars.search(skill_des):
                self.mc_transl.cc_skill_des[cc_add.collectionNo] = skill_des
            profile_cn = params.get2("解说")
            if profile_cn:
                cc_add.profile.CN = profile_cn
            cc_add.characters = []
            cc_add.unknownCharacters = []
            for index in range(20):
                key = "出场角色" if index == 0 else index
                chara = params.get2(key)
                if not chara:
                    continue
                known_, unknown_ = self._parse_chara(chara)
                cc_add.characters.extend(known_)
                cc_add.unknownCharacters.extend(unknown_)
            cc_add.characters = sorted(set(cc_add.characters))
            cc_add.unknownCharacters = sorted(set(cc_add.unknownCharacters))

        worker = Worker.from_map(
            _parse_one,
            set(self.wiki_data.commandCodes.keys())
            | set(index_data.keys())
            | set(extra_pages.keys()),
            name="mc_cc",
        )
        worker.wait()

    def mc_mystic(self):
        wikitext = MOONCELL.get_page_text("御主装备")
        wikitext = mwparse(wikitext).get_sections([2], "魔术礼装")[0]
        transl = self.wiki_data.mcTransl
        for params in parse_template_list(wikitext, "^{{魔术礼装"):
            name_jp, name_cn = params.get2("日文名称"), params.get2("中文名称")
            detail_jp, detail_cn = params.get2("日文简介"), params.get2("中文简介")
            if name_jp and name_cn:
                transl.mc_names[name_jp] = name_cn
            if name_jp and detail_cn:
                transl.mc_details[name_jp] = detail_cn
        for params in parse_template_list(wikitext, "^{{赋予技能"):
            skill_cn, skill_jp = params.get2(2), params.get2(3)
            if skill_cn and skill_jp:
                transl.skill_names.setdefault(skill_jp, skill_cn)

    def _parse_chara(self, charas: str) -> tuple[list[int], list[str]]:
        known: list[int] = []
        unknown: list[str] = []
        for chara in charas.split(";;"):
            if "{{{" in chara:
                match = re.search(r"\{\{\{([^|{}]+)(?:\|([^|{}]*))?\}\}\}", chara)
                if match:
                    chara = match.group(2) or match.group(1)
                else:
                    raise Exception(f"chara not match template format: '{chara}'")
            chara = chara.strip()
            if not chara:
                continue
            if chara in self._svt_id_cache:
                known.append(self._svt_id_cache[chara])
            else:
                svt_text = MOONCELL.get_page_text(chara)
                param_svt = parse_template(svt_text, r"^{{基础数值")
                svt_no = param_svt.get_cast("序号", cast=int)
                if svt_no:
                    self._svt_id_cache[chara] = svt_no
                    known.append(svt_no)
                else:
                    unknown.append(chara)
                    self.unknown_chara_mapping.setdefault(chara, MappingStr())
        return known, unknown

    def _parse_cards(self, charas: str | None, is_svt: bool):
        known: list[int] = []
        unknown: list[str] = []
        if not charas:
            return known, unknown
        cache = self._svt_id_cache if is_svt else self._ce_id_cache
        for chara in charas.split(","):
            if "{{{" in chara:
                match = re.search(r"\{\{\{([^|{}]+)(?:\|([^|{}]*))?\}\}\}", chara)
                if match:
                    chara = match.group(2) or match.group(1)
                else:
                    raise Exception(f"chara not match template format: '{chara}'")
            chara = chara.strip()
            if not chara:
                continue
            if chara in cache:
                known.append(cache[chara])
            else:
                page_text = MOONCELL.get_page_text(chara)
                if is_svt:
                    match = re.match(r"^从者(\d+)$", chara)
                    if match:
                        card_id = int(str(match.group(1)).lstrip("0"))
                    else:
                        param_svt = parse_template(page_text, r"^{{基础数值")
                        card_id = param_svt.get_cast("序号", cast=int)
                else:
                    match = re.match(r"^礼装(\d+)$", chara)
                    if match:
                        card_id = int(str(match.group(1)).lstrip("0"))
                    else:
                        param_svt = parse_template(page_text, r"^{{概念礼装")
                        card_id = param_svt.get_cast("礼装id", cast=int)
                if card_id:
                    cache[chara] = card_id
                    known.append(card_id)
                else:
                    unknown.append(chara)
        return known, unknown

    def fandom_svt(self):
        def _parse_one(link: str):
            text = mwparse(FANDOM.get_page_text(link))
            info_param = parse_template(text, r"^{{CharactersNew")
            collection_no = info_param.get_cast("id", int)
            if not collection_no:
                return
            svt_add: ServantW = self.wiki_data.get_svt(collection_no)
            svt_add.fandomLink = link
            text = mwparse(FANDOM.get_page_text(link))

            need_profile = self._need_wiki_profile(Region.NA, svt_add.collectionNo)
            for params in parse_template_list(text, r"^{{Biography"):
                if need_profile:
                    for index in range(8):
                        if index == 0:
                            suffix = "def"
                        elif index == 6:
                            suffix = "ex"
                        else:
                            suffix = f"b{index}"
                        comment = params.get2("n" + suffix) or params.get2(suffix) or ""
                        if comment:
                            profiles = svt_add.fandomProfiles.setdefault(index, [])
                            profiles.append(comment)
                apex = params.get2("apex")
                if apex:
                    if svt_add.aprilFoolProfile.NA:
                        svt_add.aprilFoolProfile.NA += f"\n\n{apex}"
                    else:
                        svt_add.aprilFoolProfile.NA = apex

            sprites = []
            sprites_text = ""

            images_section = FANDOM.get_page_text(f"Sub:{link}/Gallery")
            sprites_text = str(
                mwparse(
                    mwparse(images_section).get_sections(levels=[2], matches="Sprites")
                )
            )
            sprites_text = sprites_text.strip()
            if not sprites_text:
                images_section = text.get_sections(levels=[2], matches="Images")
                sprites_text = find_tabber(images_section, "Sprites")

            if sprites_text:
                for line in sprites_text.split("\n"):
                    cells = [c.strip() for c in line.strip().split("|")]
                    if len(cells) != 2:
                        continue
                    fn, name = cells
                    if "Command Card" in name or "NP Logo" in name:
                        continue
                    if fn:
                        sprites.append(FANDOM.get_image_name(fn))
            svt_add.fandomSprites = sprites

        worker = Worker("fandom_svt")
        subpages = self._get_fandom_list_page_sub(
            "Sub:Servant_List_by_ID/1-100", r"Sub\:Servant_List_by_ID/(\d+\-\d+)"
        )
        subpages.insert(0, "1-100")
        for page in subpages:
            html_text = FANDOM.request(
                f"https://fategrandorder.fandom.com/wiki/Sub:Servant_List_by_ID/{page}?action=render"
            )
            links: list[str] = parse_html_xpath(
                html_text,
                '//div[@class="mw-parser-output"]/table[2]/tbody/tr/td[2]/a/@href',
            )
            prefix = "https://fategrandorder.fandom.com/wiki/"
            for link in links:
                assert link.startswith(prefix), link
                worker.add(_parse_one, FANDOM.norm_key(link[len(prefix) :]))
        worker.wait()

    def fandom_ce(self):
        def _parse_one(link: str):
            wikitext = mwparse(FANDOM.get_page_text(link))
            info_params = parse_template(wikitext, r"^{{Infoboxce2")
            collection_no = info_params.get_cast("id", int)
            if not collection_no:
                return

            ce_add = self.wiki_data.get_ce(collection_no)
            ce_add.fandomLink = link
            params = parse_template(wikitext, r"^{{Craftlore")
            profile = params.get2("na") or params.get2("en")
            if profile:
                ce_add.profile.NA = profile

            effect1 = info_params.get2("effect1", strip=True)
            effect2 = info_params.get2("effect2", strip=True)
            if effect1 and effect1.upper() != "N/A":
                self.fandom_transl.ce_skill_des[ce_add.collectionNo] = effect1
            if effect2 and effect2.upper() != "N/A":
                self.fandom_transl.ce_skill_des_max[ce_add.collectionNo] = effect2

        worker = Worker("fandom_ce")

        subpages = self._get_fandom_list_page_sub(
            "Craft_Essence_List/By_ID/1-100", r"Craft_Essence_List/By_ID/(\d+\-\d+)"
        )
        subpages.insert(0, "1-100")
        for page in subpages:
            html_text = FANDOM.render(f"Craft_Essence_List/By_ID/{page}")
            links: list[str] = parse_html_xpath(
                html_text,
                '//div[@class="mw-parser-output"]/table/tbody/tr/td[2]/a/@href',
            )
            prefix = "https://fategrandorder.fandom.com/wiki/"
            for link in links:
                assert link.startswith(prefix), link
                worker.add(_parse_one, FANDOM.norm_key(link[len(prefix) :]))
        worker.wait()

    def fandom_cc(self):
        # Category:Command Code Display Order
        subpages = self._get_fandom_list_page_sub(
            "Command_Code_List/By_ID/1-100", r"Command_Code_List/By_ID/(\d+\-\d+)"
        )
        subpages.insert(0, "1-100")

        for page in subpages:
            list_page_html = FANDOM.render(f"Command_Code_List/By_ID/{page}")
            pages = parse_html_xpath(
                list_page_html,
                '//div[@class="mw-parser-output"]/table/tbody/tr/td[3]/a/@href',
            )
            logger.debug(f"Fandom: ({page}) {len(pages)} command codes")
            prefix = "https://fategrandorder.fandom.com/wiki/"
            for page_link in pages:
                page_link = str(page_link)
                assert page_link.startswith(prefix), page_link
                fa_link = FANDOM.norm_key(page_link[len(prefix) :])
                wikitext = mwparse(FANDOM.get_page_text(fa_link))
                assert fa_link and wikitext, fa_link
                if not fa_link or not wikitext:
                    continue
                infoboxcc = parse_template(wikitext, r"^{{Infoboxcc")
                collection_no = infoboxcc.get_cast("id", cast=int)
                if not collection_no or not infoboxcc:
                    continue
                cc_add = self.wiki_data.get_cc(collection_no)
                cc_add.fandomLink = fa_link
                params = parse_template(wikitext, r"^{{Craftlore")
                cc_add.profile.NA = params.get2("na") or params.get2("en")

                effect1 = infoboxcc.get2("effect1", strip=True)
                if effect1 and effect1 != "N/A":
                    self.fandom_transl.cc_skill_des[cc_add.collectionNo] = effect1

    @staticmethod
    def _get_fandom_list_page_sub(page: str, pattern: str) -> list[str]:
        html_text = FANDOM.render(page)
        links: list[str] = parse_html_xpath(
            html_text,
            '//div[@class="mw-parser-output"]/table[1]/tbody//td/a/@href',
        )
        subpages: list[str] = []
        for link in links:
            matches = re.findall(pattern, link)
            if matches:
                subpages.append(matches[0])
        return subpages

    def mc_campaigns(self):
        titles = [x["fulltext"] for x in MOONCELL.ask_query("[[EventType::Campaign]]")]
        campaigns: list[CampaignEvent] = []
        for title in titles:
            text = MOONCELL.get_page_text(title)
            params = parse_template(text, r"^{{活动信息")
            name_jp = params.get2("名称jp")
            start_jp, end_jp = params.get("开始时间jp"), params.get("结束时间jp")
            if not name_jp or not start_jp or not end_jp:
                logger.info(
                    f"[{title}] Campaign name or time unknown: {name_jp, start_jp, end_jp}"
                )
                continue
            start_time = MOONCELL.get_timestamp(start_jp, KnownTimeZone.jst)
            end_time = MOONCELL.get_timestamp(end_jp, KnownTimeZone.jst)
            if not start_time or not end_time:
                logger.warning(
                    f"[{title}] Invalid timestamp: {start_jp,start_time,end_jp,end_time}",
                )
                continue
            notice_link = params.get2("官网链接jp")
            notice_key = _gen_jp_notice_key(notice_link)
            if not notice_key:
                logger.warning(f"[{title}] No jp notice link: {notice_link}")
                continue
            campaign_id = abs(start_time - 1420070400) // 3600
            campaign_id = campaign_id * 100 + binascii.crc32(notice_key.encode()) % 100
            campaign_id = -campaign_id
            campaigns.append(
                CampaignEvent(
                    id=campaign_id,
                    key=notice_key,
                    name=name_jp,
                    startedAt=start_time,
                    endedAt=end_time,
                )
            )
            event_add = self.wiki_data.get_event(event_id=campaign_id, name=name_jp)
            event_add.mcLink = MOONCELL.norm_key(title)
        self.wiki_data.campaigns = {x.id: x for x in campaigns}

    def mc_events(self):
        def _parse_one(event: EventW):
            if event.mcLink:
                move_target = MOONCELL.moved_pages.get(MOONCELL.norm_key(event.mcLink))
                if move_target:
                    discord.mc(
                        "Event page moved",
                        discord.mc_link(event.mcLink)
                        + " -> "
                        + discord.mc_link(move_target),
                    )
                    event.mcLink = move_target
            if event.fandomLink:
                move_target = FANDOM.moved_pages.get(FANDOM.norm_key(event.fandomLink))
                if move_target:
                    discord.fandom(
                        "Event page moved",
                        discord.fandom_link(event.fandomLink)
                        + " -> "
                        + discord.mc_link(move_target),
                    )
                    event.fandomLink = move_target

            if event.fandomLink and not FANDOM.get_page_text(event.fandomLink):
                logger.warning(
                    f'Fandom event page not found, may be moved: "{event.fandomLink}"'
                )
            if not event.mcLink:
                return
            text = MOONCELL.get_page_text(event.mcLink)
            if not text:
                self._mc.invalid_links.append(event.mcLink)
                logger.warning(
                    f'Mooncell event page not found, may be moved: "{event.mcLink}"'
                )
                return
            params = parse_template(text, r"^{{活动信息")
            name_jp = params.get2("名称jp")
            name_cn = params.get2("名称ha") or params.get2("名称cn")
            if name_jp and name_cn:
                self.mc_transl.event_names[name_jp] = name_cn
                self.mc_transl.event_names[name_jp.replace("･", "・")] = name_cn

            event.titleBanner.CN = MOONCELL.get_image_url_null(
                params.get("标题图文件名cn")
            )
            event.titleBanner.JP = MOONCELL.get_image_url_null(
                params.get("标题图文件名jp")
            )
            event.noticeLink.CN = params.get("官网链接cn")
            event.noticeLink.JP = params.get("官网链接jp")
            # campaign only
            if event.id < 0:
                event.startTime.CN = MOONCELL.get_timestamp(
                    params.get2("开始时间cn"), KnownTimeZone.cst
                )
                event.endTime.CN = MOONCELL.get_timestamp(
                    params.get2("结束时间cn"), KnownTimeZone.cst
                )
            # summons
            summon_pages = []
            for i in range(1, 6):
                if params.get(f"推荐召唤{i}"):
                    summon_pages.append(f'{event.mcLink}/卡池{"" if i == 1 else i}详情')
            for i in range(1, 6):
                page_link = params.get(f"关联卡池{i}")
                if page_link:
                    link = MOONCELL.resolve_wikilink(page_link)
                    if link:
                        summon_pages.append(link)
            for summon_page in summon_pages:
                summon_params = parse_template(
                    MOONCELL.get_page_text(summon_page), r"^{{卡池信息"
                )
                key = _gen_jp_notice_key(summon_params.get("卡池官网链接jp"))
                if key:
                    event.relatedSummons.append(key)
            self.wiki_data.events[event.id] = event

        worker = Worker.from_map(
            _parse_one, self.wiki_data.events.values(), name="mc_events"
        )
        worker.wait()

    def mc_wars(self):
        def _parse_one(war: WarW):
            if war.fandomLink and not FANDOM.get_page_text(war.fandomLink):
                logger.warning(
                    f'Fandom main story page not found, may be moved: "{war.mcLink}"'
                )
            if not war.mcLink:
                return
            text = MOONCELL.get_page_text(war.mcLink)
            if not text:
                self._mc.invalid_links.append(war.mcLink)
                logger.warning(
                    f'Mooncell main story page not found, may be moved: "{war.mcLink}"'
                )
                return
            params = parse_template(text, r"^{{活动信息")

            war.titleBanner.CN = MOONCELL.get_image_url_null(
                params.get("标题图文件名cn")
            )
            war.titleBanner.JP = MOONCELL.get_image_url_null(
                params.get("标题图文件名jp")
            )
            war.noticeLink.CN = params.get("官网链接cn")
            war.noticeLink.JP = params.get("官网链接jp")
            self.wiki_data.wars[war.id] = war

        worker = Worker.from_map(
            _parse_one, self.wiki_data.wars.values(), name="mc_war"
        )
        worker.wait()

    def mc_quests(self):
        def _parse_one(title: str):
            wikitext = mwparse(MOONCELL.get_page_text(title))
            for params in parse_template_list(wikitext, r"^{{关卡配置"):
                quest_jp = params.get2("名称jp")
                quest_cn = params.get2("名称cn")
                if quest_jp and quest_cn:
                    self.mc_transl.quest_names[quest_jp] = quest_cn
                for phase in "一二三四五六七八":
                    spot_jp = params.get2(phase + "地点jp")
                    spot_cn = params.get2(phase + "地点cn")
                    if spot_jp and spot_cn:
                        self.mc_transl.spot_names[spot_jp] = spot_cn

        worker = Worker("mc_quests")
        titles: set[str] = {"迦勒底之门/进阶关卡"}
        for event in self.wiki_data.events.values():
            if not event.mcLink:
                continue
            if (event.script.huntingId or 0) > 0:
                titles.add(event.mcLink)
                continue
            db_event = self._jp.events.get(event.id)
            if not db_event:
                continue
            if db_event.type == NiceEventType.eventQuest and db_event.warIds:
                titles.add(f"{event.mcLink}/关卡配置")
        for war in self.wiki_data.wars.values():
            if war.id < 1000 and war.mcLink:
                titles.add(f"{war.mcLink}/关卡配置")
        titles = {x.replace("/关卡配置/关卡配置", "/关卡配置") for x in titles}
        for answer in MOONCELL.ask_query("[[分类:主线关卡 || 活动关卡]]"):
            titles.add(answer["fulltext"])
        for svt in self._jp.released_svts.values():
            if not svt.relateQuestIds:
                continue
            svt_add = self.wiki_data.servants.get(svt.collectionNo)
            if svt_add and svt_add.mcLink:
                titles.add(f"{svt_add.mcLink}/从者任务")
        for title in sorted(titles):
            worker.add(_parse_one, title)
        worker.wait()

    def mc_summon(self):
        def t_summon_data_table(src_str: str, instance: SubSummon):
            table = []
            for row_str in src_str.strip().split("\n"):
                row = row_str.split("\t")
                row = [x.strip() for x in row]
                table.append(row)
            assert tuple(table[0]) == (
                "type",
                "star",
                "weight",
                "display",
                "ids",
            ), table[0]
            for row in table[1:]:
                if row[0] != "svt" and row[0] != "ce":
                    raise Exception(f"invalid type: {row[0]}")
                instance.probs.append(
                    ProbGroup(
                        isSvt=row[0] == "svt",
                        rarity=int(row[1]),
                        weight=float(row[2]),
                        display=row[3] != "0",
                        ids=[int(x) for x in re.findall(r"\d+", row[4])],
                    )
                )
            return instance

        added_summons: dict[str, str] = {}
        unknown_cards: set[str] = set()

        def _parse_one(title: str):
            wikitext = mwparse(MOONCELL.get_page_text(title))
            params = parse_template(wikitext, r"^{{卡池信息")
            key = _gen_jp_notice_key(params.get("卡池官网链接jp"))
            if not key:
                return
            if key in added_summons:
                discord.mc(
                    "Duplicated Summon Key",
                    f"{key}: " + discord.mc_links([title, added_summons[key]]),
                )
                raise KeyError(
                    f"Duplicated Summon Key: '{key}': {title}, {added_summons[key]}"
                )
            added_summons[key] = title

            name_jp = params.get2("卡池名jp")
            name_cn = params.get2("卡池名ha") or params.get2("卡池名cn") or title
            summon = self.wiki_data.summons.setdefault(key, LimitedSummon(id=key))
            summon.mcLink = title
            summon.name = name_jp
            if name_cn and name_jp:
                self.mc_transl.summon_names[name_jp] = name_cn
            summon.startTime.JP = MOONCELL.get_timestamp(
                params.get("卡池开始时间jp"), KnownTimeZone.jst
            )
            if not summon.startTime.JP:
                logger.warning(f"[Summon] unknown startTimeJP: {summon.mcLink}")
            summon.startTime.CN = MOONCELL.get_timestamp(
                params.get("卡池开始时间cn"), KnownTimeZone.cst
            )
            summon.endTime.JP = MOONCELL.get_timestamp(
                params.get("卡池结束时间jp"), KnownTimeZone.jst
            )
            summon.endTime.CN = MOONCELL.get_timestamp(
                params.get("卡池结束时间cn"), KnownTimeZone.cst
            )
            summon.banner.JP = MOONCELL.get_image_url_null(params.get("卡池图文件名jp"))
            summon.banner.CN = MOONCELL.get_image_url_null(params.get("卡池图文件名cn"))
            summon.noticeLink.JP = params.get("卡池官网链接jp")
            summon.noticeLink.CN = params.get("卡池官网链接cn")

            known_svt, unknown_svt = self._parse_cards(
                params.get2("推荐召唤从者"), True
            )
            known_ce, unknown_ce = self._parse_cards(params.get2("推荐召唤礼装"), False)
            if unknown_svt or unknown_ce:
                unknown_cards.add(f"{title}: " + ", ".join(unknown_svt + unknown_ce))
            summon.puSvt = known_svt
            summon.puCE = known_ce

            simulator_page = MOONCELL.get_page_text(f"{title}/模拟器")
            sim_params = parse_template(simulator_page, r"^{{抽卡模拟器")
            ssr_str = sim_params.get2("福袋")
            if ssr_str and ssr_str.lower() == "ssrsr":
                summon.type = SummonType.gssrsr
            elif ssr_str:
                summon.type = SummonType.gssr
            else:
                summon.type = SummonType.limited

            for i in range(1, 31):
                sub_title = sim_params.get(f"子名称{i}")
                sub_data = sim_params.get(f"数据{i}")
                if sub_title and sub_data:
                    sub_summon = SubSummon(title=sub_title)
                    data_page_name = sub_data.replace("{{PAGENAME}}", f"{title}/模拟器")
                    data_page_name = remove_tag(data_page_name)
                    table_str = MOONCELL.get_page_text(data_page_name)
                    if table_str:
                        t_summon_data_table(table_str, sub_summon)
                        summon.subSummons.append(sub_summon)

        worker = Worker("mc_summon")
        titles = [
            answer["fulltext"] for answer in MOONCELL.ask_query("[[分类:限时召唤]]")
        ]
        for title in sorted(titles):
            worker.add(_parse_one, title)
        worker.wait()
        name_jp_counts: dict[str, set[str]] = defaultdict(set)
        for summon in self.wiki_data.summons.values():
            if not summon.mcLink or not summon.name:
                continue
            if summon.name not in (
                "クラス別ピックアップ召喚",
                "ホワイトデーメモリアルピックアップ召喚",
            ):
                name_jp_counts[summon.name].add(summon.mcLink)
        dup_names = [
            f"`- {name}`: " + ",".join([discord.mc_link(link) for link in links])
            for name, links in name_jp_counts.items()
            if len(links) > 1
        ]
        if dup_names:
            discord.mc("Duplicated Summon JP name", "\n".join(dup_names))
        if unknown_cards:
            discord.mc("Unknown PickUp Card", "\n".join(sorted(unknown_cards)))

    def mc_extra(self):
        costume_page = MOONCELL.get_page_text("灵衣一览")
        for params in parse_template_list(costume_page, r"^{{灵衣一览"):
            name_cn, name_jp = params.get2("中文名"), params.get2("日文名")
            if name_cn and name_jp:
                self.mc_transl.costume_names[name_jp] = name_cn
            collection = params.get_cast("序号", int)
            detail_cn = params.get2("中文简介")
            if collection and detail_cn:
                self.mc_transl.costume_details[collection] = detail_cn

        # event item names
        item_pages = ["道具一览"] + [f"道具一览/活动道具/{i}" for i in range(1, 11)]
        for title in item_pages:
            text = MOONCELL.get_page_text(title)
            for params in parse_template_list(text, r"^{{活动道具表格"):
                name_cn, name_jp = params.get2("中文名称"), params.get2("日文名称")
                if name_cn and name_jp:
                    self.mc_transl.item_names[name_jp] = name_cn

        # illustrator
        illust_text = MOONCELL.get_page_text(
            "模块:GetIllustKey/data", allow_cache=False
        )
        illustrators: list[tuple[str, str]] = re.findall(
            r"\['(.+)'\]\s*=\s*'(.+)'", illust_text
        )
        assert illustrators, f"Illust data empty: {illust_text}"
        for name_cn, name_jp in illustrators:
            name_cn, name_jp = name_cn.strip(), name_jp.strip()
            if name_cn == name_jp:
                continue
            self.mc_transl.illustrator_names[name_jp] = name_cn

    def fandom_quests(self):
        def _with_subs(title: str, is_event: bool):
            titles = [title]
            text = FANDOM.get_page_text(title)
            title = title.replace("_", " ")
            for x in text.replace("_", " ").split(title)[1:]:
                for subtitle in re.findall(r"^\/([^\}\]\|]*)(?:\}\}|\]\])", x):
                    if len(subtitle) > 100 or "\n" in subtitle:
                        continue
                    if not is_event or "quest" in str(subtitle).lower():
                        titles.append(f"{title}/{subtitle}")
            for title in titles:
                text = FANDOM.get_page_text(title)
                for params in parse_template_list(text, r"^{{Questheader"):
                    spot_jp = params.get2("jpnodename")
                    spot_en = params.get2("ennodename")
                    if spot_jp and spot_en:
                        self.fandom_transl.spot_names[spot_jp] = spot_en
                    name_jp = params.get2("jpname")
                    name_en = params.get2("enname")
                    if name_jp and name_en:
                        self.fandom_transl.quest_names[name_jp] = name_en

        # event
        events: list[EventW] = []
        for idx in (1, 2):
            events.extend(
                parse_file_as(
                    list[EventW], settings.output_dist / f"wiki.events.{idx}.json"
                )
            )
        for event in events:
            if event.fandomLink:
                _with_subs(event.fandomLink, True)

        # main scenario
        quest_nav = FANDOM.get_page_text("Template:quest_nav")
        links = FANDOM.resolve_all_wikilinks(quest_nav)
        for link in links:
            title = str(link.title)
            if title in (
                "Chaldea Gate",
                "Daily Event Quests: Chaldea Gate",
                "Interlude: Chaldea Gate",
                "Servant Strengthening Quests",
            ):
                continue
            _with_subs(title, False)

        # Hunting Quests and Advanced Quests
        for event in self.wiki_data.events.values():
            if not event.fandomLink:
                continue
            if (event.script.huntingId or 0) > 0:
                _with_subs(event.fandomLink, False)
            if re.match(r"^Advanced.Quest", event.fandomLink):
                _with_subs(event.fandomLink, True)

    def fandom_extra(self):
        for page_name in [
            "Sub:Costume_Dress/Full_Costume_List",
            "Sub:Costume_Dress/Simple_Costume_List",
        ]:
            costume_page = FANDOM.get_page_text(page_name)
            for row in wikitextparser.parse(costume_page).tables[0].data()[1:]:
                names = re.split(r"<br\s*/>", row[2])
                if len(names) != 2:
                    continue
                name_jp = remove_tag(names[0])
                name_na = remove_tag(names[1].strip().strip("'"))
                if name_jp and name_na:
                    self.fandom_transl.costume_names[name_jp] = name_na

    def check_invalid_wikilinks(self):
        def _check_page(title: str | None):
            if not title:
                return
            text = FANDOM.get_page_text(title)
            if not text:
                self._fandom.invalid_links.append(title)
                logger.warning(f'Fandom page not found, may be moved: "{title}"')

        for event in self.wiki_data.events.values():
            _check_page(event.fandomLink)
        for war in self.wiki_data.wars.values():
            _check_page(war.fandomLink)
        for summon in self.wiki_data.summons.values():
            _check_page(summon.fandomLink)

        count = len(self._mc.invalid_links) + len(self._fandom.invalid_links)
        if count > 0:
            msg = f"{count} wiki pages Not Found!"
            if self._mc.invalid_links:
                msg += f"\n  Mooncell pages: {self._mc.invalid_links}"
            if self._fandom.invalid_links:
                msg += f"\n  Fandom pages: {self._fandom.invalid_links}"
            logger.warning(msg)
            discord.wiki_links(self._mc.invalid_links, self._fandom.invalid_links)

    def check_webcrow(self):
        webcrow_mappings = parse_file_as(
            dict[int, int], settings.output_wiki / "webcrowMapping.json"
        )
        try:
            resp = requests.get(
                "https://raw.githubusercontent.com/FGOSim/Material/main/js/ServantDBData.min.js"
            )
            db_str: str = resp.content.decode("utf8")
        except Exception:
            logger.exception("download webcrow data failed")
            return
        msg: list[str] = []
        for wid in re.findall(r"\{id:(\d+),", db_str):
            wid = int(wid)
            if wid not in webcrow_mappings:
                msg.append(f"**ID: {wid}**")
                start = db_str.index(f"id:{wid},")
                msg.append(f"```\n{db_str[start-1:start+50]}\n```")
        if msg:
            webhook = discord.get_webhook()
            em = discord.DiscordEmbed(title="Webcrow ID Updated")
            em.set_description("\n".join(msg))
            webhook.add_embed(em)
            # discord._execute(webhook)

    def sort(self):
        self.wiki_data.sort()

    def save_data(self):
        self.sort()
        self.wiki_data.save(full_version=True)
        dump_json(
            sort_dict(self.unknown_chara_mapping),
            settings.output_mapping / "chara_names.json",
        )


def _mc_index_data(page: str) -> dict[int, dict[str, str]]:
    text = MOONCELL.get_page_text(page, allow_cache=settings.is_debug)
    data: dict[int, dict[str, str]] = {}
    for block in text.split("\n\n"):
        d = {}
        for row in block.split("\n"):
            key, value = row.split("=", 1)
            value = value.strip()
            # if value:
            d[key] = value
        idx = parse_int(d["id"])
        if idx and d.get("name_link"):
            data[idx] = d
    return data


def _mc_smw_card_list(category: str, prop: str) -> dict[int, str]:
    query = f"https://fgo.wiki/w/特殊:询问/format%3Djson/sort%3D{prop}/order%3Ddesc/offset%3D0/limit%3D100/-5B-5B分类:{category}-5D-5D/-3F{prop}/mainlabel%3D/prettyprint%3Dtrue/unescape%3Dtrue/searchlabel%3DJSON"
    logger.info(query)
    try:
        resp = requests.get(query)
        assert resp.status_code == 200, (resp, resp.text)
    except:
        logger.exception(f"smw failed; {category}  {prop}")
        return {}
    results: dict = resp.json()["results"]
    out: dict[int, str] = {}
    for item in results.values():
        col_no = int(item["printouts"][prop][0])
        if col_no < 10000:
            out[col_no] = item["fulltext"]
    return out


def _gen_jp_notice_key(jp_url: str | None) -> Optional[str]:
    if not jp_url:
        return None
    assert "fate-go.jp" in jp_url.lower(), jp_url
    try:
        return urlparse(jp_url).path.strip("/").replace("/", "_")
    except:
        return None


def parse_int(x) -> int | None:
    try:
        return int(x)
    except:
        return None
