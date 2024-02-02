"""
Drop data from fgo domus aurea
"""

import csv
import time
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


class DOMUS_URLS:
    drop_rate = "https://docs.google.com/spreadsheets/d/1H4x2FOF-9eHy0CByuRQR74x37qji2i5HqTKYpQw9oO8/export?gid=756436527&format=csv"
    ap_rate = "https://docs.google.com/spreadsheets/d/1H4x2FOF-9eHy0CByuRQR74x37qji2i5HqTKYpQw9oO8/export?gid=397765373&format=csv"
    drop_rate_old = "https://docs.google.com/spreadsheets/d/1npusaiDGRMD0KlG10gLUNI_KNLnM1UBDTzc-wuJZcgA/export?gid=56582984&format=csv"
    ap_rate_old = "https://docs.google.com/spreadsheets/d/1npusaiDGRMD0KlG10gLUNI_KNLnM1UBDTzc-wuJZcgA/export?gid=1041274460&format=csv"


@dataclass
class _MasterData:
    quests: dict[int, NiceQuest]
    questPhases: dict[int, MstQuestPhase]
    spotNameQuestIdMap: dict[str, int]


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
    spot_map: dict[str, int] = {}
    for war in wars:
        if war.id != 1002 and war.id >= 1000:
            continue
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
                or quest.id in extra_quest_ids
            ]
            valid_quests.update({x.id: x for x in frees})
            if len(frees) == 1:
                spot_map[spot.name] = frees[0].id
    spot_map |= FIX_SPOT_QUEST_MAPPING

    for quest_id in extra_quest_ids:
        valid_quests[quest_id]
        assert quest_id in valid_quests, f"quest {quest_id} not found"

    mst_phases = parse_obj_as(list[MstQuestPhase], DownUrl.gitaa("mstQuestPhase"))
    quest_phases = {
        quest.questId: quest
        for quest in mst_phases
        if quest.questId in valid_quests
        and quest.phase == valid_quests[quest.questId].phases[-1]
    }
    phase_not_found = set(valid_quests).difference(quest_phases.keys())
    assert not phase_not_found, f"quest phases not found: {phase_not_found}"

    return _MasterData(
        quests=valid_quests,
        questPhases=quest_phases,
        spotNameQuestIdMap=spot_map,
    )


# %%
def _parse_sheet_data(csv_url: str, mst_data: _MasterData) -> DropRateSheet:
    with LocalProxy(enabled=settings.is_debug):
        csv_fp = settings.output_wiki / "domus_aurea_drop_sheet.csv"
        # csv_contents = csv_fp.read_text()
        logger.info(f"downloading sheet from {csv_url}")
        csv_contents = requests.get(csv_url).content.decode("utf8")
        csv_fp.write_text(csv_contents)
    table: list[list[str]] = list(csv.reader(StringIO(csv_contents)))

    HEAD_ROW = 2
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
    quest_id_row_map: dict[int, int] = {
        mst_data.spotNameQuestIdMap[row_data[SPOT_COL]]: row
        for row, row_data in enumerate(table)
        if row_data[SPOT_COL] in mst_data.spotNameQuestIdMap
    }
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
