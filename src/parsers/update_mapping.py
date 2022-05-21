"""
Update mappings from distributed data

So make sure all changes here have been token affect in distribution before `update_repo`

- output/mappings/
  update from exported files and wiki data
- output/wiki/summons_base
  from release/summons.json
"""
from src.config import settings
from src.schemas.gamedata import MappingData
from src.utils.helper import dump_json, load_json, logger, sort_dict


def run_mapping_update():
    _update_mapping_files()


def _update_mapping_files():
    mappings = MappingData.parse_file(settings.output_dist / "mappingData.json")
    folder = settings.output_mapping
    folder.mkdir(exist_ok=True, parents=True)
    mapping_dict = mappings.dict()
    for key, trans in mapping_dict.items():
        if not settings.is_debug and key in (
            "skill_priority",
            "td_priority",
            "svt_release",
            "ce_release",
            "cc_release",
        ):
            # release->MappingBase[list[int]]
            continue
        fp = folder / f"{key}.json"
        if key in ("chara_names", "trait_redirect"):
            dump_json(sort_dict(load_json(fp) or {}), fp)
            continue
        logger.debug(f"writing to {fp}")
        dump_json(trans, fp)


if __name__ == "__main__":
    run_mapping_update()
