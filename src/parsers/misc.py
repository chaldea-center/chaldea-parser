from app.schemas.common import Region

from src.config import settings
from src.schemas.common import MappingStr
from src.utils import AtlasApi
from src.utils.helper import dump_json, load_json, sort_dict
from src.utils.log import logger


_ce_cc_names: dict[str, MappingStr] = {}


def add_enemy_skill_np_trans():
    AtlasApi.api_server = "http://127.0.0.1:8000"
    logger.level = 20
    _ce_cc_names.clear()
    _ce_cc_names.update(
        _load_mapping(settings.output_mapping / "ce_names.json")
        | _load_mapping(settings.output_mapping / "cc_names.json")
    )
    _add_enemy_skill_trans()
    _add_enemy_td_trans()


def _load_mapping(fp) -> dict[str, MappingStr]:
    return {k: MappingStr.parse_obj(v) for k, v in (load_json(fp) or {}).items()}


def _add_enemy_skill_trans():
    skills: list[dict] = load_json(settings.output_dist / "baseSkills.json") or []
    mappings: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "skill_names.json"
    )
    skills = [s for s in skills if s["name"] and s["name"] not in _ce_cc_names]
    for index, skill in enumerate(skills):
        skill_id, skill_name = skill["id"], skill["name"]
        if not str(skill_name).strip() or skill_name in _ce_cc_names:
            continue
        trans = mappings.setdefault(skill_name, MappingStr())
        print(f"\rfetch skill {skill_id} ({index}/{len(skills)})", end="")
        for region in Region.__members__.values():
            if region == Region.JP:
                continue
            if trans.of(region) is not None:
                continue
            skill_r = AtlasApi.api_json(
                f"/nice/{region}/skill/{skill_id}", expire_after=0
            )
            if skill_r is None or "id" not in skill_r:
                continue
            if skill_r["name"] != skill_name:
                trans.update(region, skill_r["name"], True)
    mappings = sort_dict(mappings)
    dump_json(mappings, settings.output_mapping / "skill_names.json")


def _add_enemy_td_trans():
    tds: list[dict] = load_json(settings.output_dist / "baseTds.json") or []
    names: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "td_names.json"
    )
    rubies: dict[str, MappingStr] = _load_mapping(
        settings.output_mapping / "td_ruby.json"
    )
    for index, td in enumerate(tds):
        td_id, td_name, td_ruby = td["id"], td["name"], td["ruby"]
        if not str(td_name).strip() or td_name in _ce_cc_names:
            continue
        name_trans = names.setdefault(td_name, MappingStr())
        ruby_trans = rubies.setdefault(td_ruby, MappingStr())
        print(f"\rfetch td {td_id} ({index}/{len(tds)})", end="")
        for region in Region.__members__.values():
            if region == Region.JP:
                continue
            if name_trans.of(region) is not None:
                continue
            td_r = AtlasApi.api_json(f"/nice/{region}/NP/{td_id}", expire_after=0)
            if td_r is None or "id" not in td_r:
                continue
            if td_r["name"] != td_name:
                name_trans.update(region, td_r["name"], True)
            if region != Region.NA and td_r["ruby"] != td_ruby:
                ruby_trans.update(region, td_r["ruby"], True)
    names = sort_dict(names)
    rubies.pop("-", None)
    rubies = sort_dict(rubies)
    dump_json(names, settings.output_mapping / "td_names.json")
    dump_json(rubies, settings.output_mapping / "td_ruby.json")


if __name__ == "__main__":
    add_enemy_skill_np_trans()
