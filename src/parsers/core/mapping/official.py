import itertools
import re
import time
from re import Match
from typing import AnyStr

from app.schemas.common import Region
from app.schemas.gameenums import (
    NiceEventOverwriteType,
    NiceFuncType,
    NiceSpotOverwriteType,
    NiceWarOverwriteType,
)
from app.schemas.nice import AscensionAddEntryStr, NiceLoreComment, NiceServant

from ....schemas.common import NEVER_CLOSED_TIMESTAMP, MappingBase, MappingStr
from ....schemas.data import CN_REPLACE, STORY_UPGRADE_QUESTS, jp_chars
from ....schemas.gamedata import MasterData
from ....schemas.wiki_data import WikiData
from ....utils import discord, logger
from .common import _KT, _KV, process_skill_detail, update_key_mapping


def merge_official_mappings(jp_data: MasterData, data: MasterData, wiki_data: WikiData):
    region = data.region
    assert region != Region.JP
    logger.info(f"merging official translations from {region}")
    mappings = jp_data.mappingData

    mappings.entity_release.update(region, sorted([svt.id for svt in data.basic_svt]))
    mappings.cc_release.update(region, sorted(data.cc_dict.keys()))
    mappings.mc_release.update(region, sorted(data.mc_dict.keys()))

    def _update_mapping(
        m: dict[_KT, MappingBase[_KV]],
        _key: _KT,
        value: _KV | None,
        skip_exists=True,
        skip_unknown_key=False,
    ):
        if _key in (None, "", "-"):
            return
        m.setdefault(_key, MappingBase())
        if value == _key:
            return
        if region in (Region.CN, Region.TW) and isinstance(value, str):
            if jp_chars.search(value):
                return
        return update_key_mapping(
            region,
            key_mapping=m,
            _key=_key,
            value=value,
            skip_exists=skip_exists,
            skip_unknown_key=skip_unknown_key,
        )

    def _set_key(m: dict[_KT, MappingBase[_KV]], _key: _KT):
        if _key in (None, "", "-"):
            return
        m.setdefault(_key, MappingBase())

    # str key
    for item_jp in jp_data.nice_item:
        item = data.item_dict.get(item_jp.id)
        _update_mapping(mappings.item_names, item_jp.name, item.name if item else None)
    for cv_jp in jp_data.nice_cv:
        cv = data.cv_dict.get(cv_jp.id)
        _update_mapping(mappings.cv_names, cv_jp.name, cv.name if cv else None)
        cv_names = [str(s).strip() for s in re.split(r"[&＆]+", cv_jp.name) if s]
        if len(cv_names) > 1:
            for one_name in cv_names:
                _set_key(mappings.cv_names, one_name)
    for illustrator_jp in jp_data.nice_illustrator:
        illustrator = data.illustrator_dict.get(illustrator_jp.id)
        if re.match(r"^[\w\.\- ]+$", illustrator_jp.name) and (
            not illustrator or illustrator.name == illustrator_jp.name
        ):
            continue
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
                if re.match(r"^[\w\.\- ]+$", one_name):
                    continue
                _set_key(mappings.illustrator_names, one_name)
    for bgm_jp in jp_data.nice_bgm:
        bgm = data.bgm_dict.get(bgm_jp.id)
        _update_mapping(mappings.bgm_names, bgm_jp.name, bgm.name if bgm else None)

    tower_names = mappings.misc.setdefault("TowerName", {})
    recipe_names = mappings.misc.setdefault("RecipeName", {})
    trade_goods_names = mappings.misc.setdefault("TradeGoodsName", {})
    for event_jp in jp_data.nice_event:
        event_extra = wiki_data.get_event(event_jp.id, event_jp.name)
        event_extra.startTime.JP = event_jp.startedAt
        event_extra.endTime.JP = event_jp.endedAt
        _set_key(mappings.event_names, event_jp.name)
        for event_add in event_jp.eventAdds:
            if event_add.overwriteType == NiceEventOverwriteType.name_:
                _set_key(mappings.event_names, event_add.overwriteText)

        for point_jp in event_jp.pointGroups:
            point = data.event_point_groups.get(point_jp.groupId)
            _update_mapping(
                mappings.item_names, point_jp.name, point.name if point else None
            )
        # TowerName
        for tower_jp in event_jp.towers:
            tower_id = event_jp.id * 100 + tower_jp.towerId
            tower = data.event_towers.get(tower_id)
            _update_mapping(tower_names, tower_jp.name, tower.name if tower else None)
        # RecipeName
        for recipe_jp in event_jp.recipes:
            recipe = data.event_recipes.get(recipe_jp.id)
            _update_mapping(
                recipe_names, recipe_jp.name, recipe.name if recipe else None
            )
        # TradeGoodsName
        for trade_jp in event_jp.tradeGoods:
            trade = data.event_trades.get(trade_jp.id)
            _update_mapping(
                trade_goods_names, trade_jp.name, trade.name if trade else None
            )

        event = data.event_dict.get(event_jp.id)
        if event is None:
            continue
        if event.startedAt < NEVER_CLOSED_TIMESTAMP:
            event_extra.startTime.update(region, event.startedAt)
            event_extra.endTime.update(region, event.endedAt)
        # don't include unreleased events' name
        if event.startedAt > time.time():
            continue
        _update_mapping(mappings.event_names, event_jp.name, event.name)
        _update_mapping(mappings.event_names, event_jp.shortName, event.shortName)
    for campaign in wiki_data.campaigns.values():
        _update_mapping(mappings.event_names, campaign.name, None)
    for mm_jp in jp_data.nice_master_mission:
        mm = data.mm_dict.get(mm_jp.id)
        if mm_jp.script.missionIconDetailText:
            _update_mapping(
                mappings.event_names,
                mm_jp.script.missionIconDetailText,
                mm.script.missionIconDetailText if mm else None,
            )

    war_release = mappings.war_release.of(region) or []
    for war_jp in jp_data.nice_war:
        if war_jp.id < 1000:
            wiki_data.get_war(war_jp.id)
        _set_key(mappings.war_names, war_jp.name)
        _set_key(mappings.war_names, war_jp.longName)
        for war_add in war_jp.warAdds:
            if war_add.type in [
                NiceWarOverwriteType.longName,
                NiceWarOverwriteType.name_,
            ]:
                _set_key(mappings.war_names, war_add.overwriteStr)
        war = data.war_dict.get(war_jp.id)
        if war is None or (war.id < 1000 and war.lastQuestId == 0):
            continue
        if war.id == 8098 and region == Region.NA:
            # for NA: 8098 is Da Vinci and the 7 Counterfeit Heroic Spirits
            continue
        if not war.spots and data.mstConstant["LAST_WAR_ID"] < war.id < 1000:
            # or check war.lastQuestId
            continue
        event = data.event_dict.get(war.eventId)
        if war.id > 1000 and event and event.startedAt > time.time():
            continue
        war_release.append(war.id)
        # if war.id < 11000 and war.lastQuestId == 0:  # not released wars
        #     continue
        _update_mapping(mappings.war_names, war_jp.longName, war.longName)
        _update_mapping(mappings.war_names, war_jp.name, war.name)
    mappings.war_release.update(region, sorted(war_release))
    for spot_jp in jp_data.spot_dict.values():
        spot = data.spot_dict.get(spot_jp.id)
        _update_mapping(mappings.spot_names, spot_jp.name, spot.name if spot else None)
        for add_jp in spot_jp.spotAdds:
            if add_jp.overrideType == NiceSpotOverwriteType.name_:
                spot_add = next(
                    (
                        add
                        for add in (spot.spotAdds if spot else [])
                        if (add.overrideType, add.priority, add.condTargetId)
                        == (add_jp.overrideType, add_jp.priority, add_jp.condTargetId)
                    ),
                    None,
                )
                _update_mapping(
                    mappings.spot_names,
                    add_jp.targetText,
                    spot_add.targetText if spot_add else None,
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
        if svt_jp.collectionNo > 0:
            wiki_data.get_svt(svt_jp.collectionNo)
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
        skill_priority = mappings.skill_priority.setdefault(svt_jp.id, MappingBase())
        skill_priority.update(
            region, {skill.id: skill.priority for skill in svt.skills}
        )
        td_priority = mappings.td_priority.setdefault(svt_jp.id, MappingBase())
        td_priority.update(region, {td.id: td.priority for td in svt.noblePhantasms})
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

    ce_ids = {x.collectionNo for x in data.nice_equip_lore}
    ce_ids = ce_ids.difference({x.collectionNo for x in jp_data.nice_equip_lore})
    if ce_ids:
        rows = [
            f"- [{ce_id}-{data.ce_dict[ce_id].name}](https://apps.atlasacademy.io/db/{region}/craft-essence/{ce_id})"
            for ce_id in ce_ids
        ]
        discord.text("\n".join(rows), f"**New {region} specific CE**")
    for ce_jp in jp_data.nice_equip_lore:
        ce = data.ce_id_dict.get(ce_jp.id)
        ce_w = wiki_data.get_ce(ce_jp.collectionNo)
        if ce_jp.profile and ce_jp.profile.comments:
            if len(ce_jp.profile.comments) > 1:
                logger.debug(
                    f"{ce_jp.collectionNo}-{ce_jp.name} has {len(ce_jp.profile.comments)} lores"
                )
            ce_w.profile.JP = _get_comment(ce_jp.profile.comments).comment
        _update_mapping(
            mappings.ce_names,
            ce_jp.name,
            ce.name if ce and ce.collectionNo < 100000 else None,
        )
        if not ce or ce.collectionNo > 100000:
            continue
        if region != Region.JP and ce.profile and ce.profile.comments:
            comment = _get_comment(ce.profile.comments).comment
            if comment and comment != ce_w.profile.JP:
                ce_w.profile.update(region, comment)

    for cc_jp in jp_data.nice_command_code:
        cc = data.cc_id_dict.get(cc_jp.id)
        _update_mapping(mappings.cc_names, cc_jp.name, cc.name if cc else None)
        cc_w = wiki_data.get_cc(cc_jp.collectionNo)
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
        skill = data.skill_dict.get(skill_jp.id) or data.base_skills.get(skill_jp.id)
        if (
            skill_jp.name not in mappings.ce_names
            and skill_jp.name not in mappings.cc_names
        ):
            _update_mapping(
                mappings.skill_names, skill_jp.name, skill.name if skill else None
            )

        select_add_mappings = mappings.misc.setdefault("SelectAddInfo", {})
        for index, add_jp in enumerate(skill_jp.script.SelectAddInfo or []):
            add = (
                skill.script.SelectAddInfo[index]
                if skill
                and skill.script.SelectAddInfo
                and index < len(skill.script.SelectAddInfo)
                else None
            )
            _update_mapping(
                select_add_mappings, add_jp.title, add.title if add else None
            )
            for btn_index, btn_jp in enumerate(add_jp.btn):
                btn = add.btn[btn_index] if add and btn_index < len(add.btn) else None
                _update_mapping(
                    select_add_mappings, btn_jp.name, btn.name if btn else None
                )
        detail_jp = process_skill_detail(skill_jp.unmodifiedDetail)
        if not detail_jp:
            continue
        _update_mapping(
            mappings.skill_detail,
            detail_jp,
            process_skill_detail(skill.unmodifiedDetail if skill else None),
        )
    for td_jp in itertools.chain(jp_data.td_dict.values(), jp_data.base_tds.values()):
        td = data.td_dict.get(td_jp.id) or data.base_tds.get(td_jp.id)
        _update_mapping(mappings.td_names, td_jp.name, td.name if td else None)
        if region != Region.NA:  # always empty for NA
            _update_mapping(mappings.td_ruby, td_jp.ruby, td.ruby if td else None)
        _update_mapping(mappings.td_types, td_jp.type, td.type if td else None)
        detail_jp = process_skill_detail(td_jp.unmodifiedDetail)
        if not detail_jp:
            continue
        _update_mapping(
            mappings.td_detail,
            detail_jp,
            process_skill_detail(td.unmodifiedDetail if td else None),
        )
    for buff_jp in jp_data.buff_dict.values():
        buff = data.buff_dict.get(buff_jp.id)
        _update_mapping(mappings.buff_names, buff_jp.name, buff.name if buff else None)
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
    for func_type in NiceFuncType:
        if func_type.value.startswith("damageNp"):
            _update_mapping(mappings.func_popuptext, func_type.value, None)
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

    for master_id, name_jp in jp_data.enemy_master_names.items():
        if not name_jp.strip():
            name_jp = f"Master {master_id}"
        name = data.enemy_master_names.get(master_id)
        if not name:
            name = mappings.svt_names.get(name_jp, MappingStr()).of(region)
        _update_mapping(mappings.misc.setdefault("master_name", {}), name_jp, name)

    jp_data.mappingData = mappings
    del data


def fix_cn_transl_qab(data: dict[str, dict[str, str | None]]):
    # QAB
    color_regexes = [
        re.compile(
            r"(?<![击御威])([力技迅])(?=提升|攻击|指令卡|下降|性能|耐性|威力|暴击)"
        ),
        re.compile(r"(?<=[:：])([力技迅])$"),
        re.compile(r"(?<=[〔（(])[力技迅](?=[)）〕])"),
    ]
    extra_regexes = [re.compile(r"额外(?=攻击|职阶)")]

    def _repl(match: Match[AnyStr]) -> str:
        return {"力": "Buster", "技": "Arts", "迅": "Quick", "额外": "Extra"}[
            str(match.group(0))
        ]

    for jp_name, regions in data.items():
        cn_name2 = cn_name = regions["CN"]
        if not cn_name or not cn_name2:
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


def fix_cn_transl_svt_class(data: dict, patterns: list[str]):
    # Svt Class
    cls_replace = {
        "剑士": "Saber",
        "弓兵": "Archer",
        "枪兵": "Lancer",
        "骑兵": "Rider",
        "魔术师": "Caster",
        "暗匿者": "Assassin",
        "狂战士": "Berserker",
        "裁定者": "Ruler",
        "复仇者": "Avenger",
        "月之癌": "MoonCancer",
        "他人格": "Alterego",
        "降临者": "Foreigner",
        "身披角色者": "Pretender",
        "盾兵": "Shielder",
    }

    def replace_cls(s: str, cls_cn: str):
        if cls_cn not in s:
            return s
        for pattern in patterns:
            s = s.replace(pattern.format(cls_cn), pattern.format(cls_replace[cls_cn]))
        return s

    def _iter(obj):
        if not isinstance(obj, dict):
            return
        v = obj.get("CN")
        if isinstance(v, str):
            for a, b in CN_REPLACE.items():
                v = v.replace(a, b)
            for cls_cn in cls_replace.keys():
                v = replace_cls(v, cls_cn)
            obj["CN"] = v
        for k, v in obj.items():
            _iter(v)

    _iter(data)
