"""
python -m scripts.sheet -um
"""

# %%
import argparse
import datetime
from collections import defaultdict
from copy import deepcopy
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, TypeVar

import orjson

from scripts._dir import MAPPINGS_DIR, PROJECT_ROOT, WIKI_DIR
from scripts._gs import get_worksheet
from src.schemas.mappings import EnumMapping
from src.utils.helper import (
    dump_json,
    dump_json_beautify,
    parse_json_file_as,
    parse_json_obj_as,
)


# %%

ARB_DIR = PROJECT_ROOT / "chaldea/lib/l10n"

assert ARB_DIR.exists() and MAPPINGS_DIR.exists()


_KT = TypeVar("_KT")

Mapping = dict[str, dict[_KT, Any]]


class ArbLang(StrEnum):
    en = "en"
    ja = "ja"
    zh = "zh"
    zh_Hant = "zh_Hant"
    ko = "ko"
    es = "es"
    ru = "ru"
    ar = "ar"

    @property
    def path(self) -> Path:
        return Path(ARB_DIR) / f"intl_{self}.arb"

    def read(self) -> dict[str, str | None]:
        return orjson.loads(self.path.read_text())

    def save(self, data):
        self.path.write_bytes(
            orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_APPEND_NEWLINE)
        )


def get_time() -> str:
    now = datetime.datetime.now(datetime.UTC)
    return now.strftime("%m-%d %H:%M UTC")


class Region(StrEnum):
    JP = "JP"
    CN = "CN"
    TW = "TW"
    NA = "NA"
    KR = "KR"


# %%
MAPPING_FILES = [
    "enums",
    "bgm_names",
    "buff_detail",
    "buff_names",
    "cc_names",
    "ce_names",
    "chara_names",
    "costume_detail",
    "costume_names",
    "cv_names",
    "entity_names",
    "event_names",
    "event_trait",
    "func_popuptext",
    "illustrator_names",
    "item_names",
    "mc_detail",
    "mc_names",
    "quest_names",
    "skill_detail",
    "skill_names",
    "spot_names",
    "summon_names",
    "svt_names",
    "td_detail",
    "td_names",
    "td_ruby",
    "td_types",
    "trait",
    "voice_line_names",
    "war_names",
]


# %%
def merge_dict(d1: Mapping[_KT], d2: Mapping[_KT], force=False):
    """Merge d2 into d1"""
    out: Mapping[_KT] = deepcopy(d1)
    for k, v in d2.items():
        if not k:
            continue
        t = out.setdefault(k, {})
        for kk, vv in v.items():
            if not vv:
                continue
            # if kk != "NA":
            #     continue
            if force:
                t[kk] = vv
            else:
                t[kk] = t.get(kk) or vv
    return out


def sheet2json(table: list[list], column: Callable[[str], _KT]) -> Mapping[_KT]:
    remote_data: Mapping[_KT] = defaultdict(dict)
    header: list[str] = table[0] if table else []
    for row_index, row in enumerate(table):
        if row_index == 0:
            continue
        for col_index, value in enumerate(row):
            if col_index == 0 or not value:
                continue
            key: str = row[0]
            value = str(value)
            col_str = header[col_index] if col_index < len(header) else None
            col: _KT | None = None
            try:
                if col_str:
                    col = column(col_str)
            except:
                ...
            if col is None or not key:
                continue
            remote_data[key][col] = value
    return remote_data


def upload_l10n():
    print("uploading l10n...")
    sh = get_worksheet("l10n")

    local_data: Mapping[ArbLang] = defaultdict(dict)

    for lang in ArbLang:
        data = lang.read()
        for k, v in data.items():
            if v is not None:
                local_data[k][lang] = v

    remote_data = sheet2json(sh.get_values(), ArbLang.__call__)
    unused_keys = set(remote_data.keys()).difference(local_data.keys())
    if unused_keys:
        print("  unused remote keys:", unused_keys)
    merged = merge_dict(local_data, remote_data, force=False)
    # merged = merge_dict(remote_data, local_data, force=True)

    cells: list[list[str]] = []
    cells.append([f"key ({get_time()})"] + [f"{x}" for x in ArbLang])
    for key, values in merged.items():
        cells.append([key] + [values.get(lang, "") or "" for lang in ArbLang])
    sh.update(cells)


def download_l10n():
    print("downloading l10n...")
    sh = get_worksheet("l10n")
    remote_data = sheet2json(sh.get_values(), ArbLang.__call__)

    for lang in ArbLang:
        # if lang !=ArbLang.ko:
        #     continue
        data = lang.read()
        for k, v in remote_data.items():
            vv = v.get(lang)
            if vv:
                data[k] = vv
        lang.save(data)


def upload_mapping(name: str):
    print(f"uploading {name}...")
    fp = MAPPINGS_DIR / f"{name}.json"
    sh = get_worksheet(name)
    remote_table = sh.get_values()
    remote_data = sheet2json(remote_table, Region.__call__)
    if name == "event_trait":
        event_traits = parse_json_file_as(Mapping[str], fp)
        for v in event_traits.values():
            del v["eventId"]
        local_data = parse_json_obj_as(Mapping[Region], event_traits)
    elif name == "enums":
        local_data: Mapping[Region] = parse_enums(fp)
    else:
        local_data = parse_json_file_as(Mapping[Region], fp)

    unused_keys = set(remote_data.keys()).difference(local_data.keys())
    if unused_keys:
        print("  unused remote keys:", unused_keys)

    merged = merge_dict(local_data, remote_data, force=False)

    cells: list[list[str]] = []
    cells.append([f"key ({get_time()})"] + [f"{x}" for x in Region])
    for key, values in merged.items():
        cells.append([key] + [values.get(region, "") or "" for region in Region])

    if str(remote_table[1:]) == str(cells[1:]):
        # print(f"          {name}: no change, skip uploading")
        pass
    else:
        # Path(f"temp/a.{name}.1.txt").write_text(
        #     "\n".join([str(x) for x in remote_table])
        # )
        # Path(f"temp/a.{name}.2.txt").write_text("\n".join([str(x) for x in cells]))
        print(f"  !!! UPDATED {name}")
        sh.update(cells)


def parse_enums(fp: str | Path) -> Mapping:
    enums = parse_json_file_as(dict[str, Mapping[str]], fp)
    data: Mapping[str] = {}
    for enum_type, d in enums.items():
        for k, v in d.items():
            data[f"{enum_type}.{k}"] = v
    return data


def dump_enums(data: Mapping[str], fp: str | Path):
    enums: dict[str, Mapping[str]] = {}
    for k, v in data.items():
        a, b = k.split(".")
        assert a and b, k
        enums.setdefault(a, {})[b] = v
    dump_json(enums, fp)
    # dump_json(parse_json_obj_as(EnumMapping, enums), fp)


def download_mapping(name: str):
    print(f"downloading {name}...")
    fp = MAPPINGS_DIR / f"{name}.json"
    sh = get_worksheet(name)
    remote_data = sheet2json(sh.get_values(), str)
    parse_json_obj_as(Mapping[str], remote_data)  # validate
    if name == "enums":
        local_data: Mapping[str] = parse_enums(fp)
        merged = merge_dict(local_data, remote_data, force=True)
        dump_enums(merged, fp)
    else:
        local_data = parse_json_file_as(Mapping[str], fp)
        merged = merge_dict(local_data, remote_data, force=True)
        dump_json(merged, fp)


def upload_all_mappings():
    for name in MAPPING_FILES:
        upload_mapping(name)


def download_all_mappings():
    for name in MAPPING_FILES:
        download_mapping(name)


# %%
if __name__ == "__main__":
    print(datetime.datetime.now().isoformat())
    parser = argparse.ArgumentParser()
    parser.add_argument("-dl", help="download l10n", action="store_true")
    parser.add_argument("-ul", help="upload l10n", action="store_true")
    parser.add_argument("-dm", help="download mappings", action="store_true")
    parser.add_argument("-um", help="upload i10n", action="store_true")

    args = parser.parse_args()

    if args.dl:
        download_l10n()
    elif args.ul:
        upload_l10n()
    if args.dm:
        download_all_mappings()
    elif args.um:
        upload_all_mappings()
