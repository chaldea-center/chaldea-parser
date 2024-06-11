"""
python -m scripts.enemy_skill_td

Add enemy skill/td translations from raw data, usually called after new main story released
"""

# %%
import re

import httpx
from app.schemas.common import Region
from app.schemas.raw import MstSkill, MstTreasureDevice

from src.config import settings
from src.parsers.core.mapping.official import fix_cn_transl_qab, fix_cn_transl_svt_class
from src.schemas.common import MappingStr
from src.utils.helper import dump_json, load_json, parse_json_obj_as, sort_dict


def _mstFile(region: Region, name: str):
    url = f"https://git.atlasacademy.io/atlasacademy/fgo-game-data/raw/branch/{region}/master/{name}"
    print(f"reading: {url}")
    return httpx.get(url).json()
    # return parse_json_file_as(
    #     list[dict],
    #     f"FOLDER/fgo-game-data-{region.value.lower()}/master/{name}",
    # )


def add_enemy_skill_td_trans():
    _add_enemy_skill_trans()
    _add_enemy_td_trans()
    print("done")


jp_chars = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")


def _fix_cn(data: dict[str, MappingStr]) -> dict[str, dict]:
    data2 = {k: v.model_dump() for k, v in data.items()}
    fix_cn_transl_qab(data2)
    fix_cn_transl_svt_class(data2, ["对{0}", "({0})", "（{0}）", "〔{0}〕", "{0}职阶"])
    return data2


def _load_mapping(fp) -> dict[str, MappingStr]:
    return {
        k: parse_json_obj_as(MappingStr, v) for k, v in (load_json(fp) or {}).items()
    }


def _add_enemy_skill_trans():
    folder = settings.output_mapping
    cc_ce_names: set[str] = set(load_json(folder / "ce_names.json")) | set(
        load_json(folder / "cc_names.json")
    )
    skills_jp: list[dict] = load_json(settings.output_dist / "baseSkills.json") or []
    skill_names: dict[str, MappingStr] = _load_mapping(folder / "skill_names.json")
    skill_details: dict[str, MappingStr] = _load_mapping(folder / "skill_detail.json")
    for skill in skills_jp:
        detail_jp: str | None = skill.get("unmodifiedDetail")
        if not detail_jp:
            continue
        detail_jp = str(detail_jp).replace("[g][o]▲[/o][/g]", "▲")
        if detail_jp not in skill_details:
            skill_details[detail_jp] = MappingStr()

    for region in Region:
        if region == Region.JP:
            continue
        skills_r: dict[int, MstSkill] = {
            skill["id"]: parse_json_obj_as(MstSkill, skill)
            for skill in _mstFile(region, "mstSkill.json")
        }
        for skill_jp in skills_jp:
            name_jp = str(skill_jp["name"]).strip()
            if not name_jp or name_jp in ("-",) or name_jp in cc_ce_names:
                continue
            trans = skill_names.setdefault(name_jp, MappingStr())
            # if trans.of(region) is not None:
            #     continue
            skill_r = skills_r.get(skill_jp["id"])
            if not skill_r:
                continue
            name_r = skill_r.name
            if not name_r or name_r == name_jp or jp_chars.search(name_r):
                continue
            trans.update(region, name_r, False)
    dump_json(sort_dict(_fix_cn(skill_names)), folder / "skill_names.json")
    dump_json(sort_dict(_fix_cn(skill_details)), folder / "skill_detail.json")


def _add_enemy_td_trans():
    folder = settings.output_mapping
    tds_jp: list[dict] = load_json(settings.output_dist / "baseTds.json") or []
    td_names: dict[str, MappingStr] = _load_mapping(folder / "td_names.json")
    td_rubies: dict[str, MappingStr] = _load_mapping(folder / "td_ruby.json")
    td_details: dict[str, MappingStr] = _load_mapping(folder / "td_detail.json")
    for td in tds_jp:
        detail_jp: str | None = td.get("unmodifiedDetail")
        if not detail_jp:
            continue
        detail_jp = str(detail_jp).replace("[g][o]▲[/o][/g]", "▲")
        if detail_jp not in td_details:
            td_details[detail_jp] = MappingStr()

    for region in Region:
        if region == Region.JP:
            continue
        tds_r: dict[int, MstTreasureDevice] = {
            td["id"]: parse_json_obj_as(MstTreasureDevice, td)
            for td in _mstFile(region, "mstTreasureDevice.json")
        }
        for td_jp in tds_jp:
            # name
            name_jp = str(td_jp["name"]).strip()
            if not name_jp or name_jp in ("-",):
                continue
            trans = td_names.setdefault(name_jp, MappingStr())
            if trans.of(region) is not None:
                continue
            td_r = tds_r.get(td_jp["id"])
            if not td_r:
                continue
            name_r = td_r.name
            if not name_r or name_r == name_jp or jp_chars.search(name_r):
                continue
            trans.update(region, name_r, False)
        for td_jp in tds_jp:
            # ruby
            if region == Region.NA:
                continue
            ruby_jp = str(td_jp["ruby"]).strip()
            if not ruby_jp or ruby_jp in ("-",):
                continue
            trans = td_rubies.setdefault(ruby_jp, MappingStr())
            # if trans.of(region) is not None:
            #     continue
            td_r = tds_r.get(td_jp["id"])
            if not td_r:
                continue
            ruby_r = td_r.ruby
            if (
                not ruby_r
                or ruby_r == ruby_jp
                or ruby_r == "-"
                or jp_chars.search(ruby_r)
            ):
                continue
            trans.update(region, ruby_r, False)
    dump_json(sort_dict(_fix_cn(td_names)), folder / "td_names.json")
    dump_json(sort_dict(_fix_cn(td_rubies)), folder / "td_ruby.json")
    dump_json(sort_dict(_fix_cn(td_details)), folder / "td_detail.json")


# %%
if __name__ == "__main__":
    add_enemy_skill_td_trans()

# %%
