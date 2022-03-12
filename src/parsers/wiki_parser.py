"""
SVT,CE,CC: 基本信息+个人资料+愚人节
Event: wiki_data/events.json + MC data
  - 狩猎关卡: quests
Summon: wiki_data/summons.json + MC data
"""
import re
from typing import Optional

import wikitextparser
from app.schemas.gameenums import NiceCondType
from app.schemas.nice import NiceLoreComment

from ..config import settings
from ..schemas.common import CEObtain, MappingStr, SummonType, SvtObtain
from ..schemas.wiki_data import (
    EventW,
    LimitedSummon,
    MooncellTranslation,
    ProbGroup,
    ServantW,
    SubSummon,
    WarW,
    WikiData,
)
from ..utils import Worker, count_time, dump_json, load_json, logger, sort_dict
from ..wiki import FANDOM, MOONCELL
from ..wiki.template import mwparse, parse_template, parse_template_list, remove_tag


# noinspection DuplicatedCode
class WikiParser:
    def __init__(self):
        self.wiki_data: WikiData = WikiData()
        self.summons: dict[str, LimitedSummon] = {}
        self.basic_summons: dict[str, LimitedSummon] = {}  # actually LimitedSummonBase
        self.basic_events: dict[int, EventW] = {}  # actually EventWBase
        self.wars: dict[int, WarW] = {}
        self.mc_translation = MooncellTranslation()
        self.unknown_chara_mapping: dict[str, MappingStr] = {}

    @count_time
    def start(self):
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
        logger.info("[Mooncell] parsing event/war data")
        self.mc_events()
        self.mc_wars()
        logger.info("[Mooncell] parsing summon data")
        self.mc_summon()
        logger.info("[Fandom] parsing servant data")
        self.fandom_svt()
        logger.info("[Fandom] parsing craft essence data")
        self.fandom_ce()
        logger.info("[Fandom] parsing command code data")
        self.fandom_cc()
        logger.info("[FGOSim] add servant id mapping")
        self.add_fsm_svt_mapping()
        logger.info("Saving data...")
        self.save_data()
        MOONCELL.save_cache()
        FANDOM.save_cache()

    def add_fsm_svt_mapping(self):
        # fmt: off
        self.wiki_data.fsmSvtIdMapping = {
            149: 150, 150: 153, 151: 154, 152: 196, 153: 155, 154: 156, 155: 157, 156: 158, 157: 159, 158: 160,
            159: 161, 160: 162, 161: 163, 162: 164, 163: 165, 164: 166, 165: 167, 166: 169, 167: 170, 168: 171,
            169: 172, 170: 173, 171: 174, 172: 175, 173: 176, 174: 177, 175: 178, 176: 182, 177: 179, 178: 180,
            179: 181, 180: 183, 181: 184, 182: 185, 183: 186, 184: 187, 185: 188, 186: 189, 187: 190, 188: 192,
            189: 193, 190: 194, 191: 195, 192: 197, 193: 198, 194: 199, 195: 200, 196: 201, 197: 202, 198: 203,
            199: 204, 200: 205, 201: 206, 202: 207, 203: 208, 204: 209, 205: 210, 206: 211, 207: 212, 208: 213,
            209: 214, 210: 215, 211: 191, 212: 216, 213: 217, 214: 218, 215: 219, 216: 220, 217: 221, 218: 222,
            219: 223, 220: 224, 221: 225, 222: 226, 223: 227, 224: 228, 225: 231, 226: 230, 227: 229, 228: 232,
            229: 233, 230: 234, 231: 235, 232: 236, 233: 237, 234: 238, 235: 239, 295: 301, 296: 300, 297: 302,
            298: 303, 299: 304, 300: 305, 301: 306, 302: 307, 303: 308, 304: 309, 305: 310, 306: 311, 307: 312,
            308: 313, 309: 314, 310: 315, 311: 316, 312: 317, 313: 318, 314: 319, 315: 320, 316: 321, 317: 322,
            318: 323, 319: 324, 320: 325, 321: 326, 322: 327, 323: 328, 324: 329, 325: 330, 326: 331, 327: 332,
            328: 334, 329: 335, 330: 336
        }
        # fmt: on

    def init_wiki_data(self):
        for event_data in load_json(settings.output_wiki / "events_base.json") or []:
            event = EventW.parse_obj(event_data)
            self.basic_events[event.id] = event
        for war_data in load_json(settings.output_wiki / "main_stories.json") or []:
            war = WarW.parse_obj(war_data)
            self.wars[war.id] = war
        for summon_data in load_json(settings.output_wiki / "summons_base.json"):
            summon = LimitedSummon.parse_obj(summon_data)
            self.basic_summons[summon.id] = summon
        self.unknown_chara_mapping = {
            k: MappingStr.parse_obj(v)
            for k, v in load_json(
                settings.output_mapping / "chara_names.json", {}
            ).items()
        }

    def mc_svt(self):
        index_data = _mc_index_data("英灵图鉴/数据")

        def _parse_one(record: dict):
            svt_add = self.wiki_data.get_svt(int(record["id"]))
            svt_add.mcLink = record["name_link"]
            svt_add.nameOther = [s.strip() for s in record["name_other"].split("&")]
            obtains = [SvtObtain.from_cn(m) for m in record["method"].split("<br>")]
            obtains = sorted(set(obtains))
            svt_add.obtains = obtains
            # profile

            wikitext = mwparse(MOONCELL.get_page_text(svt_add.mcLink))
            params = parse_template(wikitext, r"^{{基础数值")
            name_cn = params.get("中文名")
            if name_cn:
                self.mc_translation.svt_names[svt_add.collectionNo] = name_cn
            svt_add.nameOther.extend(re.split(r"[,，&]", params.get2("昵称", "")))
            svt_add.nameOther = [s for s in set(svt_add.nameOther) if s]

            for index in range(1, 15):
                if "愚人节" in params.get(f"立绘{index}", ""):
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

            # for priority, params in enumerate(parse_template_list(wikitext, r"^{{个人资料")):
            #     comments: list[NiceLoreComment] = []
            #     for index in range(8):
            #         prefix = "详情" if index == 0 else f"资料{index}"
            #         comments.append(
            #             NiceLoreComment(
            #                 id=index,
            #                 priority=priority,
            #                 condMessage=params.get2(prefix + "条件", ""),
            #                 comment=params.get2(prefix, ""),
            #                 condType=NiceCondType.none,
            #                 condValue2=0,
            #             )
            #         )
            #     svt_add.profileComment.CN = comments

            for params in parse_template_list(wikitext, r"^{{持有技能"):
                text_cn, text_jp = params.get2(2), params.get2(3)
                if text_cn and text_jp:
                    self.mc_translation.skill_names[text_jp] = text_cn

            for params in parse_template_list(wikitext, r"^{{宝具"):
                td_name_cn, td_ruby_cn = params.get2("中文名"), params.get2("国服上标")
                td_name_jp, td_ruby_jp = params.get2("日文名"), params.get2("日服上标")
                if td_name_cn and td_name_jp:
                    self.mc_translation.td_names[td_name_jp] = td_name_cn
                if td_ruby_cn and td_ruby_jp:
                    self.mc_translation.td_ruby[td_ruby_jp] = td_ruby_cn

        worker = Worker.from_map(_parse_one, index_data)
        worker.wait()

    def mc_ce(self):
        index_data = _mc_index_data("礼装图鉴/数据")

        def _parse_one(record: dict):
            ce_add = self.wiki_data.get_ce(int(record["id"]))
            ce_add.mcLink = record["name_link"]
            ce_add.obtain = CEObtain.from_cn(record["type"])

            wikitext = mwparse(MOONCELL.get_page_text(ce_add.mcLink))
            params = parse_template(wikitext, r"^{{概念礼装")
            name_cn = params.get2("名称")
            if name_cn:
                self.mc_translation.ce_names[ce_add.collectionNo] = name_cn
            profile_cn = params.get2("解说")
            if profile_cn:
                ce_add.profile.CN = profile_cn
            for index in range(20):
                key = "出场角色" if index == 0 else index
                chara = params.get2(key)
                if not chara or chara in self.unknown_chara_mapping:
                    continue
                svt_text = MOONCELL.get_page_text(chara)
                param_svt = parse_template(svt_text, r"^{{基础数值")
                svt_no = param_svt.get("序号", cast=int)
                if svt_no:
                    ce_add.characters.append(svt_no)
                else:
                    ce_add.unknownCharacters.append(chara)
                    self.unknown_chara_mapping.setdefault(chara, MappingStr())

        worker = Worker.from_map(_parse_one, index_data)
        worker.wait()

    def mc_cc(self):
        index_data = _mc_index_data("指令纹章图鉴/数据")

        def _parse_one(record: dict):
            cc_add = self.wiki_data.get_cc(int(record["id"]))
            cc_add.mcLink = record["name_link"]

            wikitext = mwparse(MOONCELL.get_page_text(cc_add.mcLink))
            params = parse_template(wikitext, r"^{{指令纹章")
            name_cn = params.get2("名称")
            if name_cn:
                self.mc_translation.cc_names[cc_add.collectionNo] = name_cn
            profile_cn = params.get2("解说")
            if profile_cn:
                cc_add.profile.CN = profile_cn
            for index in range(20):
                key = "出场角色" if index == 0 else index
                chara = params.get2(key)
                if not chara or chara in self.unknown_chara_mapping:
                    continue
                svt_text = MOONCELL.get_page_text(chara)
                param_svt = parse_template(svt_text, r"^{{基础数值")
                svt_no = param_svt.get("序号", cast=int)
                if svt_no:
                    cc_add.characters.append(svt_no)
                else:
                    cc_add.unknownCharacters.append(chara)
                    self.unknown_chara_mapping.setdefault(chara, MappingStr())

        worker = Worker.from_map(_parse_one, index_data)
        worker.wait()

    def fandom_svt(self):
        def _parse_one(collection_no: int, link: str):
            svt_add: ServantW = self.wiki_data.get_svt(collection_no)
            svt_add.fandomLink = link
            text = FANDOM.get_page_text(link)
            for priority, params in enumerate(
                parse_template_list(text, r"^{{Biography")
            ):
                comments: list[NiceLoreComment] = []
                for index in range(8):
                    if index == 0:
                        suffix = "def"
                    elif index == 6:
                        suffix = "ex"
                    else:
                        suffix = f"b{index}"
                    comment = params.get2("n" + suffix) or params.get2(suffix) or ""
                    comments.append(
                        NiceLoreComment(
                            id=index,
                            priority=priority,
                            condMessage=params.get2("exunlock", "")
                            if suffix == "ex"
                            else "",
                            comment=comment,
                            condType=NiceCondType.none,
                            condValue2=0,
                        )
                    )
                # svt_add.profileComment.NA = comments
                apex = params.get2("apex")
                if apex:
                    if svt_add.aprilFoolProfile.NA:
                        svt_add.aprilFoolProfile.NA += f"\n\n{apex}"
                    else:
                        svt_add.aprilFoolProfile.NA = apex

        worker = Worker()
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
            params = parse_template(FANDOM.get_page_text(link), r"^{{Craftlore")
            ce_add.profile.NA = params.get2("na") or params.get2("en")

        worker = Worker()
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
            params = parse_template(FANDOM.get_page_text(fa_link), r"^{{Craftlore")
            cc_add.profile.NA = params.get2("na") or params.get2("en")

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
                logger.warning(
                    f'Mooncell event page not found, may be moved: "{event.mcLink}"'
                )
                return
            params = parse_template(text, r"^{{活动信息")
            name_jp = params.get2("名称jp")
            name_cn = params.get2("名称cn")
            if name_jp and name_cn:
                self.mc_translation.event_names[name_jp] = name_cn

            event.titleBanner.CN = MOONCELL.get_file_url(params.get("标题图文件名cn"))
            event.titleBanner.JP = MOONCELL.get_file_url(params.get("标题图文件名jp"))
            event.noticeLink.CN = params.get("官网链接cn")
            event.noticeLink.JP = params.get("官网链接jp")
            event.rarePrism = params.get2("稀有棱镜", 0, cast=int)
            event.grail = params.get2("圣杯", 0, cast=int)
            event.grail2crystal = params.get2("圣杯转结晶", 0, cast=int)
            event.crystal = params.get2("传承结晶", 0, cast=int) - event.grail2crystal
            event.foukun4 = params.get2("★4芙芙", 0, cast=int)
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

        worker = Worker.from_map(_parse_one, self.basic_events.values())
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
                logger.warning(
                    f'Mooncell main story page not found, may be moved: "{war.mcLink}"'
                )
                return
            params = parse_template(text, r"^{{活动信息")

            war.titleBanner.CN = MOONCELL.get_file_url(params.get("标题图文件名cn"))
            war.titleBanner.JP = MOONCELL.get_file_url(params.get("标题图文件名jp"))
            war.noticeLink.CN = params.get("官网链接cn")
            war.noticeLink.JP = params.get("官网链接jp")
            self.wiki_data.wars[war.id] = war

        worker = Worker.fake(_parse_one, self.wars.values())
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
            summon = self.basic_summons.get(key, LimitedSummon(id=key))
            summon.mcLink = title
            summon.name.JP = params.get2("卡池名jp")
            summon.name.CN = params.get2("卡池名cn") or params.get2("卡池名ha") or title
            summon.startTime.JP = MOONCELL.get_timestamp(params.get("卡池开始时间jp"))
            if not summon.startTime.JP:
                print(f"[Summon] unknown startTimeJP: {summon.mcLink}")
            summon.startTime.CN = MOONCELL.get_timestamp(params.get("卡池开始时间cn"))
            summon.endTime.JP = MOONCELL.get_timestamp(params.get("卡池结束时间jp"))
            summon.endTime.CN = MOONCELL.get_timestamp(params.get("卡池结束时间cn"))
            summon.banner.JP = MOONCELL.get_file_url(params.get("卡池图文件名jp"))
            summon.banner.CN = MOONCELL.get_file_url(params.get("卡池图文件名cn"))
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
                if f"子名称{i}" in sim_params and f"数据{i}" in sim_params:
                    sub_summon = SubSummon(title=sim_params.get(f"子名称{i}"))
                    data_page_name = sim_params.get(f"数据{i}").replace(
                        "{{PAGENAME}}", f"{title}/模拟器"
                    )
                    data_page_name = remove_tag(data_page_name)
                    table_str = MOONCELL.get_page_text(data_page_name)
                    if table_str:
                        t_summon_data_table(table_str, sub_summon)
                        summon.subSummons.append(sub_summon)
            self.summons[summon.id] = summon

        worker = Worker()
        for answer in MOONCELL.ask_query("[[分类:限时召唤]]"):
            worker.add(_parse_one, answer["fulltext"])
        worker.wait()

    def sort(self):
        self.wiki_data.servants = sort_dict(self.wiki_data.servants)
        self.wiki_data.craftEssences = sort_dict(self.wiki_data.craftEssences)
        self.wiki_data.commandCodes = sort_dict(self.wiki_data.commandCodes)
        # self.wiki_data.mysticCodes = sort_dict(self.wiki_data.mysticCodes)

        self.wiki_data.events = sort_dict(self.wiki_data.events)
        self.wiki_data.wars = sort_dict(self.wiki_data.wars)
        summons = list(self.summons.values())
        summons.sort(key=lambda s: s.startTime.JP or 0)
        self.summons = {k.id: k for k in summons}

    def save_data(self):

        dump_json(
            self.wiki_data,
            settings.output_wiki / "wiki_data.json",
            indent2=False,
            append_newline=False,
        )
        dump_json(
            list(self.summons.values()),
            settings.output_wiki / "summons.json",
            indent2=False,
            append_newline=False,
        )
        dump_json(
            self.mc_translation,
            settings.output_wiki / "mc_translation.json",
            indent2=False,
            append_newline=False,
        )
        dump_json(
            self.unknown_chara_mapping, settings.output_mapping / "chara_names.json"
        )


def _mc_index_data(page: str) -> list[dict[str, Optional[str]]]:
    text = MOONCELL.get_page_text(page)
    data: list[dict[str, Optional[str]]] = []
    for block in text.split("\n\n"):
        d = {}
        for row in block.split("\n"):
            key, value = row.split("=", 1)
            d[key] = value
        data.append(d)
    return data


def _gen_summon_key(jp_url: str) -> Optional[str]:
    if not jp_url:
        return None
    key_match = re.search(r"^https://news\.fate-go\.jp/(.+)$", jp_url)
    if key_match:
        return key_match.group(1).strip("/").replace("/", "_")
