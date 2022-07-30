"""
SVT,CE,CC: 基本信息+个人资料+愚人节
Event: wiki_data/events.json + MC data
  - 狩猎关卡: quests
Summon: wiki_data/summons.json + MC data
"""
import re
from typing import Optional

import requests
import wikitextparser
from app.schemas.nice import NiceServant

from ..config import settings
from ..schemas.common import CEObtain, MappingStr, Region, SummonType, SvtObtain
from ..schemas.wiki_data import (
    EventW,
    LimitedSummon,
    ProbGroup,
    ServantW,
    SubSummon,
    WarW,
    WikiData,
    WikiTranslation,
)
from ..utils import Worker, count_time, dump_json, load_json, logger
from ..utils.helper import sort_dict
from ..wiki import FANDOM, MOONCELL
from ..wiki.template import mwparse, parse_template, parse_template_list, remove_tag
from ..wiki.wiki_tool import KnownTimeZone
from .wiki import replace_banner_url


class _WikiTemp:
    def __init__(self, region: Region) -> None:
        self.region = region
        self.invalid_links: list[str] = []
        self.released_svts: dict[int, NiceServant] = {}

    def _get_svts(self):
        for svt in requests.get(
            f"https://api.atlasacademy.io/export/{self.region}/nice_servant_lore.json"
        ).json():
            self.released_svts[svt["collectionNo"]] = NiceServant.parse_obj(svt)
        assert self.released_svts, len(self.released_svts)


class WikiParser:
    def __init__(self):
        self.wiki_data: WikiData = WikiData()
        self.unknown_chara_mapping: dict[str, MappingStr] = {}
        self._chara_cache: dict[str, int] = {}
        self._mc = _WikiTemp(Region.CN)
        self._fandom = _WikiTemp(Region.NA)
        self._jp = _WikiTemp(Region.JP)

    @property
    def mc_transl(self) -> WikiTranslation:
        return self.wiki_data.mcTransl

    @property
    def fandom_transl(self) -> WikiTranslation:
        return self.wiki_data.fandomTransl

    @count_time
    def start(self):
        self._jp._get_svts()
        self._mc._get_svts()
        self._fandom._get_svts()
        MOONCELL.load()
        FANDOM.load()
        MOONCELL.remove_recent_changed()
        FANDOM.remove_recent_changed()
        self.init_wiki_data()
        logger.info("[Mooncell] parsing servant data")
        self.mc_svt()
        logger.info("[Mooncell] parsing craft essence data")
        self.mc_ce()
        logger.info("[Mooncell] parsing command code data")
        self.mc_cc()
        logger.info("[Mooncell] parsing event/war/quest data")
        self.mc_events()
        self.mc_wars()
        self.mc_quests()
        logger.info("[Mooncell] parsing summon data")
        self.mc_summon()
        logger.info("[Fandom] parsing servant data")
        self.fandom_svt()
        logger.info("[Fandom] parsing craft essence data")
        self.fandom_ce()
        logger.info("[Fandom] parsing command code data")
        self.fandom_cc()
        self.check_invalid_wikilinks()
        logger.info("[wiki] official banner")
        replace_banner_url.main(
            list(self.wiki_data.wars.values()),
            list(self.wiki_data.events.values()),
            list(self.wiki_data.summons.values()),
            False,
        )

        logger.info("Saving data...")
        MOONCELL.save_cache()
        FANDOM.save_cache()
        self.save_data()

    def init_wiki_data(self):
        self.wiki_data = WikiData.parse_dir(full_version=False)
        mc_transl = self.mc_transl
        for k in list(mc_transl.svt_names.keys()):
            mc_transl.svt_names.pop(k)
        for k in list(mc_transl.ce_names.keys()):
            mc_transl.ce_names.pop(k)
        for k in list(mc_transl.cc_names.keys()):
            mc_transl.cc_names.pop(k)

        chara_names: dict = (
            load_json(settings.output_mapping / "chara_names.json") or {}
        )
        self.unknown_chara_mapping = {
            k: MappingStr.parse_obj(v) for k, v in chara_names.items()
        }

    def _need_wiki_profile(self, region: Region, collectionNo: int) -> bool:
        servants = (
            self._mc.released_svts
            if region == Region.CN
            else self._fandom.released_svts
        )
        if collectionNo not in servants or collectionNo not in self._jp.released_svts:
            return True
        svt = servants[collectionNo]
        svt_jp = self._jp.released_svts[collectionNo]
        assert svt.profile and svt_jp.profile
        comments = {c.id * 10 + c.priority: c for c in svt.profile.comments}
        comments_jp = {c.id * 10 + c.priority: c for c in svt_jp.profile.comments}
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

    def mc_svt(self):
        index_data = _mc_index_data("英灵图鉴/数据")

        def _parse_one(record: dict):
            svt_add = self.wiki_data.get_svt(int(record["id"]))
            svt_add.mcLink = record["name_link"]
            nicknames: set[str] = set()
            nicknames.update([s.strip() for s in record["name_other"].split("&")])
            obtains = [
                SvtObtain.from_cn(m)
                for m in record["method"].split("<br>")
                if m not in ("活动通关奖励", "事前登录赠送")
            ]
            svt_add.obtains = sorted(set(obtains))
            # profile

            wikitext = mwparse(MOONCELL.get_page_text(svt_add.mcLink))
            params = parse_template(wikitext, r"^{{基础数值")
            name_cn, name_cn2 = params.get2("中文名"), params.get2("中文名2")
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

            for index in range(1, 15):
                if "愚人节" in (params.get(f"立绘{index}") or ""):
                    illustration = params.get(f"文件{index}")
                    if illustration:
                        svt_add.aprilFoolAssets.append(
                            MOONCELL.get_file_url(f"{illustration}.png")
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
                    if "模型" in key or "灵衣" in key and str(value).endswith(".png"):
                        svt_add.spriteModels.append(MOONCELL.hash_file_url(value))

        worker = Worker.from_map(_parse_one, index_data, name="mc_svt")
        worker.wait()

    def mc_ce(self):
        index_data = _mc_index_data("礼装图鉴/数据")
        index_data.insert(
            0,
            {
                "id": "102022",
                "name": "简中版6周年纪念",
                "name_link": "简中版6周年纪念",
                "des": "支援中获得的友情点＋10(可以重复)",
                "des_max": "",
                "tag": "",
                "type": "纪念",
            },
        )

        def _parse_one(record: dict):
            ce_add = self.wiki_data.get_ce(int(record["id"]))
            ce_add.mcLink = record["name_link"]
            ce_add.obtain = CEObtain.from_cn(record["type"])

            des = record.get("des")
            if des and des != "无效果":
                des = remove_tag(des).replace("\n", "")
                self.mc_transl.ce_skill_des[ce_add.collectionNo] = des
            des_max = record.get("des_max")
            if des_max and des_max != "无效果":
                des_max = remove_tag(des_max).replace("\n", "")
                self.mc_transl.ce_skill_des_max[ce_add.collectionNo] = des_max

            wikitext = mwparse(MOONCELL.get_page_text(ce_add.mcLink))
            params = parse_template(wikitext, r"^{{概念礼装")
            name_cn = params.get2("名称")
            name_jp = params.get2("日文名称")
            if name_cn and name_jp:
                self.mc_transl.ce_names[name_jp] = name_cn
            profile_cn = params.get2("解说")
            if profile_cn:
                ce_add.profile.CN = profile_cn
            for index in range(20):
                key = "出场角色" if index == 0 else index
                chara = params.get2(key)
                if not chara:
                    continue
                parsed_chara = self._parse_chara(chara)
                if parsed_chara:
                    ce_add.characters.append(parsed_chara)
                else:
                    ce_add.unknownCharacters.append(chara)

        worker = Worker.from_map(_parse_one, index_data, name="mc_ce")
        worker.wait()

    def mc_cc(self):
        index_data = _mc_index_data("指令纹章图鉴/数据")

        def _parse_one(record: dict):
            cc_add = self.wiki_data.get_cc(int(record["id"]))
            cc_add.mcLink = record["name_link"]

            des = record.get("des")
            if des:
                des = remove_tag(des).replace("\n", "")
                self.mc_transl.cc_skill_des[cc_add.collectionNo] = des

            wikitext = mwparse(MOONCELL.get_page_text(cc_add.mcLink))
            params = parse_template(wikitext, r"^{{指令纹章")
            name_cn = params.get2("名称")
            name_jp = params.get2("日文名称")
            if name_cn and name_jp and cc_add.collectionNo != 113:
                # 113-小犭贪
                self.mc_transl.cc_names[name_jp] = name_cn
            profile_cn = params.get2("解说")
            if profile_cn:
                cc_add.profile.CN = profile_cn
            for index in range(20):
                key = "出场角色" if index == 0 else index
                chara = params.get2(key)
                if not chara:
                    continue
                parsed_chara = self._parse_chara(chara)
                if parsed_chara:
                    cc_add.characters.append(parsed_chara)
                else:
                    cc_add.unknownCharacters.append(chara)

        worker = Worker.from_map(_parse_one, index_data, name="mc_cc")
        worker.wait()

    def _parse_chara(self, chara: str) -> int | None:
        if chara in self._chara_cache:
            return self._chara_cache[chara]
        svt_text = MOONCELL.get_page_text(chara)
        param_svt = parse_template(svt_text, r"^{{基础数值")
        svt_no = param_svt.get_cast("序号", cast=int)
        if svt_no:
            self._chara_cache[chara] = svt_no
            return svt_no
        self.unknown_chara_mapping.setdefault(chara, MappingStr())

    def fandom_svt(self):
        def _parse_one(collection_no: int, link: str):
            svt_add: ServantW = self.wiki_data.get_svt(collection_no)
            svt_add.fandomLink = link
            text = FANDOM.get_page_text(link)

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

        worker = Worker("fandom_svt")
        list_text = FANDOM.get_page_text("Servant List by ID")
        for sub in re.findall(
            r"{{:Sub:Servant[_ ]List[_ ]by[_ ]ID/([\d\-]+)}}", list_text
        ):
            # print(sub)
            subpage_text = FANDOM.get_page_text(f"Sub:Servant List by ID/{sub}")
            for row in wikitextparser.parse(subpage_text).tables[0].data()[1:]:
                worker.add(_parse_one, int(row[3]), FANDOM.resolve_wikilink(row[1]))
        worker.wait()

    def fandom_ce(self):
        def _parse_one(collection_no: int, link: str):
            ce_add = self.wiki_data.get_ce(collection_no)
            ce_add.fandomLink = link
            wikitext = mwparse(FANDOM.get_page_text(link))
            params = parse_template(wikitext, r"^{{Craftlore")
            ce_add.profile.NA = params.get2("na") or params.get2("en")

            effect_params = parse_template(wikitext, r"^{{ceeffect")
            effect1 = effect_params.get2("effect1")
            effect2 = effect_params.get2("effect2")
            if effect1 and effect1 != "N/A":
                self.fandom_transl.ce_skill_des[ce_add.collectionNo] = effect1
            if effect2 and effect2 != "N/A":
                self.fandom_transl.ce_skill_des_max[ce_add.collectionNo] = effect2

        worker = Worker("fandom_ce")
        list_text = FANDOM.get_page_text("Craft Essence List/By ID")
        # {{:Craft Essence List/By ID/1-100}}
        for sub in re.findall(
            r"{{:Craft[_ ]Essence[_ ]List/By[_ ]ID/([\d\-]+)}}", list_text
        ):
            text = FANDOM.get_page_text(f"Craft Essence List/By ID/{sub}")
            for row in wikitextparser.parse(text).tables[0].data()[1:]:
                worker.add(_parse_one, int(row[3]), FANDOM.resolve_wikilink(row[1]))
        worker.wait()

    def fandom_cc(self):
        list_text = FANDOM.get_page_text("Command Code List/By ID")
        for row in wikitextparser.parse(list_text).tables[0].data()[1:]:
            collection_no = int(row[3])
            fa_link = FANDOM.resolve_wikilink(row[1])
            cc_add = self.wiki_data.get_cc(collection_no)
            cc_add.fandomLink = fa_link
            if not fa_link:
                continue
            wikitext = mwparse(FANDOM.get_page_text(fa_link))
            params = parse_template(wikitext, r"^{{Craftlore")
            cc_add.profile.NA = params.get2("na") or params.get2("en")

            effect_params = parse_template(wikitext, r"^{{Infoboxcc")
            effect1 = effect_params.get2("effect1")
            if effect1 and effect1 != "N/A":
                self.fandom_transl.cc_skill_des[cc_add.collectionNo] = effect1

    def mc_events(self):
        def _parse_one(event: EventW):
            if event.fandomLink and not FANDOM.get_page_text(event.fandomLink):
                logger.warning(
                    f'Fandom event page not found, may be moved: "{event.mcLink}"'
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
            name_cn = params.get2("名称cn") or params.get2("名称ha")
            if name_jp and name_cn:
                self.mc_transl.event_names[name_jp] = name_cn
                self.mc_transl.event_names[name_jp.replace("･", "・")] = name_cn

            event.titleBanner.CN = MOONCELL.get_file_url_null(params.get("标题图文件名cn"))
            event.titleBanner.JP = MOONCELL.get_file_url_null(params.get("标题图文件名jp"))
            event.noticeLink.CN = params.get("官网链接cn")
            event.noticeLink.JP = params.get("官网链接jp")
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
                key = _gen_summon_key(summon_params.get("卡池官网链接jp"))
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

            war.titleBanner.CN = MOONCELL.get_file_url_null(params.get("标题图文件名cn"))
            war.titleBanner.JP = MOONCELL.get_file_url_null(params.get("标题图文件名jp"))
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
        for answer in MOONCELL.ask_query("[[分类:主线关卡 || 活动关卡]]"):
            worker.add(_parse_one, answer["fulltext"])
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

        def _parse_one(title: str):
            wikitext = mwparse(MOONCELL.get_page_text(title))
            params = parse_template(wikitext, r"^{{卡池信息")
            key = _gen_summon_key(params.get("卡池官网链接jp"))
            if not key:
                return
            summon = self.wiki_data.summons.setdefault(key, LimitedSummon(id=key))
            summon.mcLink = title
            summon.name.JP = params.get2("卡池名jp")
            summon.name.CN = params.get2("卡池名cn") or params.get2("卡池名ha") or title
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
            summon.banner.JP = MOONCELL.get_file_url_null(params.get("卡池图文件名jp"))
            summon.banner.CN = MOONCELL.get_file_url_null(params.get("卡池图文件名cn"))
            summon.noticeLink.JP = params.get("卡池官网链接jp")
            summon.noticeLink.CN = params.get("卡池官网链接cn")

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
        for answer in MOONCELL.ask_query("[[分类:限时召唤]]"):
            worker.add(_parse_one, answer["fulltext"])
        worker.wait()

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
            raise ValueError(msg)

    def sort(self):
        self.wiki_data.sort()

    def save_data(self):
        self.sort()
        self.wiki_data.save(full_version=True)
        dump_json(
            sort_dict(self.unknown_chara_mapping),
            settings.output_mapping / "chara_names.json",
        )


def _mc_index_data(page: str) -> list[dict[str, Optional[str]]]:
    text = MOONCELL.get_page_text(page, allow_cache=settings.is_debug)
    data: list[dict[str, Optional[str]]] = []
    for block in text.split("\n\n"):
        d = {}
        for row in block.split("\n"):
            key, value = row.split("=", 1)
            d[key] = value.strip()
        data.append(d)
    return data


def _gen_summon_key(jp_url: str | None) -> Optional[str]:
    if not jp_url:
        return None
    key_match = re.search(r"^https://news\.fate-go\.jp/(.+)$", jp_url)
    if key_match:
        return key_match.group(1).strip("/").replace("/", "_")
