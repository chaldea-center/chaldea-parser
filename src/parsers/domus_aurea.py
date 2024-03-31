"""
Drop data from fgo domus aurea
"""

import csv
import time
from collections import defaultdict
from dataclasses import dataclass
from io import StringIO

import requests
from app.schemas.gameenums import NiceQuestAfterClearType, NiceQuestFlag, NiceQuestType
from app.schemas.nice import NiceItem, NiceQuest, NiceWar
from app.schemas.raw import MstQuestPhase
from pydantic import parse_file_as, parse_obj_as

from src.config import settings
from src.parsers.core.aa_export import update_exported_files
from src.parsers.domus_aurea_data import FIX_SPOT_QUEST_MAPPING, ITEM_NAME_MAPPING
from src.schemas.drop_data import DomusAureaData, DropRateSheet
from src.utils import logger
from src.utils.helper import LocalProxy, dump_json_beautify
from src.utils.url import DownUrl


LOCAL_MODE = False


class DOMUS_URLS:
    drop_rate = "https://docs.google.com/spreadsheets/d/1H4x2FOF-9eHy0CByuRQR74x37qji2i5HqTKYpQw9oO8/export?gid=756436527&format=csv"
    ap_rate = "https://docs.google.com/spreadsheets/d/1H4x2FOF-9eHy0CByuRQR74x37qji2i5HqTKYpQw9oO8/export?gid=397765373&format=csv"
    drop_rate_old = "https://docs.google.com/spreadsheets/d/1npusaiDGRMD0KlG10gLUNI_KNLnM1UBDTzc-wuJZcgA/export?gid=56582984&format=csv"
    ap_rate_old = "https://docs.google.com/spreadsheets/d/1npusaiDGRMD0KlG10gLUNI_KNLnM1UBDTzc-wuJZcgA/export?gid=1041274460&format=csv"


@dataclass
class _MasterData:
    wars: dict[int, NiceWar]
    quests: dict[int, NiceQuest]
    questPhases: dict[int, MstQuestPhase]


def get_master_data():
    # check item id and name
    items = parse_file_as(
        list[NiceItem], settings.atlas_export_dir / "JP/nice_item.json"
    )
    items = {item.id: item for item in items}
    for item_name, (item_id, raw_name) in ITEM_NAME_MAPPING.items():
        assert items[item_id].name == raw_name, (
            item_name,
            (item_id, raw_name),
            items[item_id].name,
        )

    valid_items = [x[0] for x in ITEM_NAME_MAPPING.values()]
    assert len(valid_items) == len(set(valid_items))

    # wars: main story and daily(1002)
    extra_quest_ids = set(FIX_SPOT_QUEST_MAPPING.values())
    wars = parse_file_as(list[NiceWar], settings.atlas_export_dir / "JP/nice_war.json")
    valid_quests: dict[int, NiceQuest] = {}

    for war in wars:
        if war.id != 1002 and war.id >= 1000:
            continue
        for spot in war.spots:
            for quest in spot.quests:
                if (
                    quest.type == NiceQuestType.free
                    and quest.afterClear == NiceQuestAfterClearType.repeatLast
                    and NiceQuestFlag.dropFirstTimeOnly not in quest.flags
                    and NiceQuestFlag.forceToNoDrop not in quest.flags
                ) or quest.id in extra_quest_ids:
                    valid_quests[quest.id] = quest

    for quest_id in extra_quest_ids:
        valid_quests[quest_id]
        assert quest_id in valid_quests, f"quest {quest_id} not found"

    if LOCAL_MODE:
        mst_phases = parse_file_as(
            list[MstQuestPhase],
            "../../atlas/fgo-game-data-jp/master/mstQuestPhase.json",
        )
    else:
        mst_phases = parse_obj_as(list[MstQuestPhase], DownUrl.gitaa("mstQuestPhase"))

    all_quest_phases: dict[int, dict[int, MstQuestPhase]] = defaultdict(dict)
    for quest in mst_phases:
        if quest.questId in valid_quests:
            all_quest_phases[quest.questId][quest.phase] = quest
    quest_phases = {
        questId: phases[max(phases.keys())]
        for questId, phases in all_quest_phases.items()
    }

    return _MasterData(
        wars={w.id: w for w in wars},
        quests=valid_quests,
        questPhases=quest_phases,
    )


# %%
def _parse_sheet_data(csv_url: str, mst_data: _MasterData) -> DropRateSheet:
    with LocalProxy(enabled=settings.is_debug):
        csv_fp = settings.output_wiki / "domus_aurea_drop_sheet.csv"
        logger.info(f"downloading sheet from {csv_url}")
        if LOCAL_MODE:
            csv_contents = csv_fp.read_text()
        else:
            csv_contents = requests.get(csv_url).content.decode("utf8")
        csv_fp.write_text(csv_contents)
    table: list[list[str]] = list(csv.reader(StringIO(csv_contents)))

    HEAD_ROW = 2
    WAR_COL = 0
    SPOT_COL = 1
    RUN_COL = 3
    table = table[HEAD_ROW:]

    # <itemId, col>
    item_id_col_map: dict[int, int] = {
        ITEM_NAME_MAPPING[name.strip()][0]: col
        for col, name in enumerate(table[0])
        if name.strip() in ITEM_NAME_MAPPING
    }
    item_not_found = set(v[0] for v in ITEM_NAME_MAPPING.values()).difference(
        item_id_col_map.keys()
    )
    assert not item_not_found, f"items not found: {item_id_col_map}"

    # <questId, row>
    quest_id_row_map: dict[int, int] = {}
    for row, row_data in enumerate(table):
        quest_id = get_quest_id(mst_data, row_data[WAR_COL], row_data[SPOT_COL])
        if quest_id:
            quest_id_row_map[quest_id] = row

    quest_not_found = set(mst_data.quests).difference(quest_id_row_map.keys())
    assert not quest_not_found, f"quests not found: {quest_not_found}"

    sheet = DropRateSheet()
    sheet.itemIds = list(item_id_col_map.keys())
    for quest_id, row in quest_id_row_map.items():
        ap = mst_data.quests[quest_id].consume
        bond = mst_data.questPhases[quest_id].friendshipExp
        exp = mst_data.questPhases[quest_id].playerExp
        run = int(table[row][RUN_COL].replace(",", ""))
        sheet.add_quest(quest_id, ap=ap, run=run, bond=bond, exp=exp)

    for x, item_id in enumerate(item_id_col_map.keys()):
        col = item_id_col_map[item_id]
        for y, quest_id in enumerate(quest_id_row_map.keys()):
            row = quest_id_row_map[quest_id]
            cell = table[row][col].strip()
            if not cell:
                continue
            sheet.sparseMatrix.setdefault(x, {})[y] = float(cell.replace(",", ""))
    return sheet


def get_quest_id(mst_data: _MasterData, war_name: str, spot_name: str) -> int | None:
    if not war_name or spot_name == "クエスト名":
        return
    match_wars = [
        war
        for war in mst_data.wars.values()
        if war.id < 1000 and war_name in war.longName
    ]
    if war_name.startswith("修練場"):
        war = mst_data.wars[1002]
    elif len(match_wars) == 1:
        war = match_wars[0]
    else:
        print(f'"{war_name}"-"{spot_name}": no war found')
        return None
    if spot_name in FIX_SPOT_QUEST_MAPPING:
        return FIX_SPOT_QUEST_MAPPING[spot_name]

    _fix_spot_quest_ids = list(FIX_SPOT_QUEST_MAPPING.values())
    for spot in war.spots:
        frees = [
            quest
            for quest in spot.quests
            if (
                quest.type == NiceQuestType.free
                and quest.afterClear == NiceQuestAfterClearType.repeatLast
                and NiceQuestFlag.dropFirstTimeOnly not in quest.flags
                and NiceQuestFlag.forceToNoDrop not in quest.flags
            )
            or quest.id in _fix_spot_quest_ids
        ]
        if not frees:
            continue
        if spot_name == spot.name and len(frees) == 1:
            return frees[0].id
        for quest in frees:
            if spot_name == quest.name or spot_name == f"{spot.name}（{quest.name}）":
                return quest.id
    print(f'"{war_name}"-"{spot_name}": no quest found')


def run_drop_rate_update():
    mst_data = get_master_data()
    fp = settings.output_wiki / "domusAurea.json"
    if fp.exists():
        legacy_data = DomusAureaData.parse_file(fp)
    else:
        legacy_data = None
    data = DomusAureaData(
        updatedAt=int(time.time()),
        legacyData=legacy_data.legacyData if legacy_data else DropRateSheet(),
        newData=_parse_sheet_data(DOMUS_URLS.drop_rate, mst_data=mst_data),
    )
    dump_json_beautify(data, fp)
    print("Saved drop rate data")


# %%
if __name__ == "__main__":
    update_exported_files([], False)
    run_drop_rate_update()
    pass
