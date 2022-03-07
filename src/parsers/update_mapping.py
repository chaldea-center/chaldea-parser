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
from src.schemas.wiki_data import LimitedSummonBase
from src.utils import NEVER_CLOSED_TIMESTAMP
from src.utils.helper import dump_json, load_json


def run_mapping_update():
    _update_mapping_files()
    _update_summons()


def _update_mapping_files():
    mappings = MappingData.parse_file(settings.output_dist / "mapping_data.json")
    folder = settings.output_mapping
    folder.mkdir(exist_ok=True, parents=True)
    mapping_dict = mappings.dict()
    for key, trans in mapping_dict.items():
        if not settings.is_debug and key in (
            "skill_state",
            "td_state",
            "svt_release",
            "ce_release",
            "cc_release",
        ):
            # release->MappingBase[list[int]]
            continue
        if key == "chara_names":
            continue
        fp = folder / f"{key}.json"
        print(f"writing to {fp}")
        dump_json(trans, fp)


def _update_summons():
    wiki_folder = settings.output_wiki
    wiki_folder.mkdir(exist_ok=True, parents=True)

    # summons
    summons_release: dict[str, LimitedSummonBase] = {
        obj["id"]: LimitedSummonBase.parse_obj(obj)
        for obj in load_json(settings.output_dist / "summons.json") or []
    }
    summons_base_list = list(summons_release.values())
    summons_base_list.sort(key=lambda x: x.startTime.JP or NEVER_CLOSED_TIMESTAMP)
    dump_json(summons_base_list, wiki_folder / "summons_base.json")


if __name__ == "__main__":
    run_mapping_update()
