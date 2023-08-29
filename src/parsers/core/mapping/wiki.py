import re
from pathlib import Path

import requests
from app.schemas.common import Region
from app.schemas.gameenums import NiceSvtFlag

from ....config import settings
from ....schemas.common import MappingBase, MappingStr
from ....schemas.gamedata import MasterData
from ....schemas.mappings import MappingData
from ....schemas.wiki_data import WikiTranslation
from ....utils.helper import load_json
from ....utils.log import logger
from .common import _KT, _KV, process_skill_detail, update_key_mapping


def merge_wiki_translation(
    jp_data: MasterData, region: Region, transl: WikiTranslation
):
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
        if re.findall(r"20[1-2][0-9]", str(value)) and m.get(_key, MappingBase()).CN:
            return
        return update_key_mapping(
            region,
            key_mapping=m,
            _key=_key,
            value=value,
            skip_exists=True,
            skip_unknown_key=True,
        )

    mappings = jp_data.mappingData

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
    for name_jp, name_cn in transl.item_names.items():
        _update_mapping(mappings.item_names, name_jp, name_cn)
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
    for ce in jp_data.nice_equip_lore:
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
            detail = process_skill_detail(skill.unmodifiedDetail)
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
    for cc in jp_data.nice_command_code:
        if cc.collectionNo <= 0:
            continue
        assert len(cc.skills) == 1
        detail = process_skill_detail(cc.skills[0].unmodifiedDetail)
        des = transl.cc_skill_des.get(cc.collectionNo)
        if not detail or des == detail:
            continue
        _update_mapping(
            mappings.skill_detail,
            detail,
            des,
        )


def merge_atlas_na_mapping(mappings: MappingData):
    logger.info("merging Atlas translations for NA")

    for _m in mappings.func_popuptext.values():
        if _m.NA:
            _m.NA = _m.NA.replace("\n", " ")

    import app as app_lib

    na_folder = Path(app_lib.__file__).resolve().parent.joinpath("data/mappings/")
    logger.debug(f"AA mappings path: {na_folder}")
    src_mapping: list[tuple[str, dict[str, MappingStr]]] = [
        ("bgm_names.json", mappings.bgm_names),
        ("cc_names.json", mappings.cc_names),
        # class_names.json
        ("costume_names.json", mappings.costume_names),
        ("cv_names.json", mappings.cv_names),
        # enemy_names.json
        ("entity_names.json", mappings.entity_names),
        ("equip_names.json", mappings.ce_names),
        ("event_names.json", mappings.event_names),
        ("illustrator_names.json", mappings.illustrator_names),
        ("item_names.json", mappings.item_names),
        ("mc_names.json", mappings.mc_names),
        ("np_names.json", mappings.td_names),
        ("np_names.json", mappings.td_ruby),
        ("quest_names.json", mappings.quest_names),
        ("servant_names.json", mappings.svt_names),
        ("skill_names.json", mappings.skill_names),
        ("spot_names.json", mappings.spot_names),
        ("war_names.json", mappings.war_names),
        ("war_short_names.json", mappings.war_names),
    ]

    def _read_json(fn: str) -> dict:
        if settings.is_debug:
            return load_json(na_folder / fn) or {}
        else:
            url = f"https://raw.githubusercontent.com/atlasacademy/fgo-game-data-api/master/app/data/mappings/{fn}"
            return requests.get(url).json()

    for src_fn, dest in src_mapping:
        source: dict[str, str] = _read_json(src_fn)
        if not source:
            continue
        for key, trans in dest.items():
            value = source.get(key)
            if value and value.strip() == key.strip():
                continue
            # if value and "\n" in value and "\n" not in key:
            #     if src_fn != 'quest_names.json':
            #         continue
            if re.findall(r"20[1-2][0-9]", str(value)) and trans.NA:
                continue
            trans.update(Region.NA, value, skip_exists=True)
    return mappings
