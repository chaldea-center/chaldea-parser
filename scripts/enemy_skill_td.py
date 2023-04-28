#%%
import httpx
from app.schemas.common import Region
from app.schemas.raw import MstSkill, MstTreasureDevice
from pydantic import parse_file_as, parse_obj_as

from src.config import settings
from src.schemas.common import MappingStr
from src.utils.helper import dump_json, load_json, sort_dict


def _mstFile(region: Region, name: str):
    url = f"https://git.atlasacademy.io/atlasacademy/fgo-game-data/raw/branch/{region}/master/{name}"
    print(f"reading: {url}")
    return httpx.get(url).json()


def add_enemy_skill_td_trans():
    _add_enemy_skill_trans()
    _add_enemy_td_trans()
    print("done")


def _load_mapping(fp) -> dict[str, MappingStr]:
    return {k: MappingStr.parse_obj(v) for k, v in (load_json(fp) or {}).items()}


def _add_enemy_skill_trans():
    skills_jp: list[dict] = load_json(settings.output_dist / "baseSkills.json") or []
    skill_names: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "skill_names.json"
    )
    skill_details: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "skill_detail.json"
    )
    for skill in skills_jp:
        detail_jp: str | None = skill.get("unmodifiedDetail")
        if not detail_jp:
            continue
        detail_jp = str(detail_jp).replace("[g][o]▲[/o][/g]", "▲")
        if detail_jp not in skill_details:
            skill_details[detail_jp] = MappingStr()

    for region in Region.__members__.values():
        if region == Region.JP:
            continue
        skills_r: dict[int, MstSkill] = {
            skill["id"]: MstSkill.parse_obj(skill)
            for skill in _mstFile(region, "mstSkill.json")
        }
        for skill_jp in skills_jp:
            name_jp = skill_jp["name"]
            if not str(name_jp).strip() or name_jp not in skill_names:
                continue
            trans = skill_names[name_jp]
            if trans.of(region) is not None:
                continue
            skill_r = skills_r.get(skill_jp["id"])
            if not skill_r:
                continue
            name_r = skill_r.name
            if not name_r or name_r == name_jp:
                continue
            trans.update(region, name_r, True)
    dump_json(skill_names, settings.output_mapping / "skill_names.json")
    dump_json(sort_dict(skill_details), settings.output_mapping / "skill_detail.json")


def _add_enemy_td_trans():
    tds_jp: list[dict] = load_json(settings.output_dist / "baseTds.json") or []
    td_names: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "td_names.json"
    )
    td_rubies: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "td_ruby.json"
    )
    td_details: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "td_detail.json"
    )
    for td in tds_jp:
        detail_jp: str | None = td.get("unmodifiedDetail")
        if not detail_jp:
            continue
        detail_jp = str(detail_jp).replace("[g][o]▲[/o][/g]", "▲")
        if detail_jp not in td_details:
            td_details[detail_jp] = MappingStr()

    for region in Region.__members__.values():
        if region == Region.JP:
            continue
        tds_r: dict[int, MstTreasureDevice] = {
            td["id"]: MstTreasureDevice.parse_obj(td)
            for td in _mstFile(region, "mstTreasureDevice.json")
        }
        for td_jp in tds_jp:
            # name
            name_jp = td_jp["name"]
            if not str(name_jp).strip() or name_jp not in td_names:
                continue
            trans = td_names[name_jp]
            if trans.of(region) is not None:
                continue
            td_r = tds_r.get(td_jp["id"])
            if not td_r:
                continue
            name_r = td_r.name
            if not name_r or name_r == name_jp:
                continue
            trans.update(region, name_r, True)
        for td_jp in tds_jp:
            # ruby
            if region == Region.NA:
                continue
            ruby_jp = td_jp["ruby"]
            if not str(ruby_jp).strip() or ruby_jp not in td_rubies:
                continue
            trans = td_rubies[ruby_jp]
            if trans.of(region) is not None:
                continue
            td_r = tds_r.get(td_jp["id"])
            if not td_r:
                continue
            ruby_r = td_r.ruby
            if not ruby_r or ruby_r == ruby_jp or ruby_r == "-":
                continue
            trans.update(region, ruby_r, True)
    dump_json(td_names, settings.output_mapping / "td_names.json")
    dump_json(td_rubies, settings.output_mapping / "td_ruby.json")
    dump_json(sort_dict(td_details), settings.output_mapping / "td_detail.json")


#%%
if __name__ == "__main__":
    add_enemy_skill_td_trans()

# %%
