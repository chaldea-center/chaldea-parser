"""
Update mappings from distributed data

So make sure all changes here have been token affect in distribution before `update_repo`

- output/mappings/
  update from exported files and wiki data
- output/wiki/summons_base
  from release/summons.json
"""
from src.config import settings
from src.schemas.common import DataVersion
from src.schemas.gamedata import MappingData
from src.utils.helper import dump_json_beautify, load_json, logger, sort_dict


def run_mapping_update(mappings: MappingData | None = None):
    if mappings is None:
        version = DataVersion.parse_file(settings.output_dist / "version.json")
        obj = {}
        for file in version.files.values():
            if file.key == "mappingData":
                part = load_json(settings.output_dist / file.filename)
                assert part
                obj.update(part)
        mappings = MappingData.parse_obj(obj)
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
            "mc_release",
            "war_release",
            "quest_release",
        ):
            # release->MappingBase[list[int]]
            continue
        fp = folder / f"{key}.json"
        if key in ("chara_names", "event_trait"):
            # they won't be changed by atlas parser
            trans = load_json(fp) or {}
        if key not in (
            "cn_replace",
            "enums",
            "misc",
            "override_mappings",
            "event_trait",
        ):
            trans = sort_dict(trans)
        logger.debug(f"writing to {fp}")
        dump_json_beautify(trans, fp)


if __name__ == "__main__":
    run_mapping_update()
