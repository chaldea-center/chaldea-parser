"""
python -m scripts.gacha

Generate Mooncell gacha prob table from html
"""
import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

import requests
from app.schemas.basic import BasicServant
from app.schemas.raw import MstSvtChange
from pydantic import parse_file_as

from src.parsers.core.aa_export import update_exported_files
from src.utils.helper import parse_html_xpath


STAR = "★"


@dataclass
class GachaGroup:
    is_svt: bool
    rarity: int
    indiv_prob: str
    cards: list[BasicServant]

    def get_total_prob(self):
        assert self.indiv_prob.endswith("%")
        return float(self.indiv_prob[:-1]) * len(self.cards)


def format_prob(v: float) -> str:
    s = str(round(v, 1))
    if s.endswith(".0"):
        return s[:-2]
    return s


def get_gacha_html(gacha_id: int) -> str:
    fp = Path(f"cache/Banners/{gacha_id}.html")
    if fp.exists():
        return fp.read_text()
    resp = requests.get(
        f"https://static.atlasacademy.io/file/aa-fgo/GameData-uTvNN4iBTNInrYDa/JP/Banners/{gacha_id}/index.html"
    )
    text = resp.text
    fp.write_text(text)
    return text


def get_prob_table(text: str, table_index: int, col_num: int):
    columns: list[list[str]] = []
    for col_index in range(col_num):
        col = parse_html_xpath(
            text, f"//table[{table_index}]/tbody/tr/td[{col_index+1}]/text()"
        )
        col = [str(x).strip() for x in col]
        columns.append(col)
    return [
        [columns[col_index][row_index] for col_index in range(col_num)]
        for row_index in range(len(columns[0]))
    ]


def dump_result(table: list[list[str]]):
    output = "\n".join(["\t".join(row) for row in table])
    print(output)
    return output


def parse_gacha(gacha_id: int) -> str:
    mstSvt = parse_file_as(list[BasicServant], "cache/atlas_export/JP/basic_svt.json")
    mstSvtChange = parse_file_as(
        list[MstSvtChange],
        "/Users/narumi/Projects/atlas/fgo-game-data-jp/master/mstSvtChange.json",
    )
    mstClass = parse_file_as(list[dict], "cache/atlas_export/JP/NiceClass.json")
    class_map: dict[str, int] = {
        mst_cls["name"]: mst_cls["id"]
        for mst_cls in mstClass
        if mst_cls["supportGroup"] < 20
    }

    def find_svt(name: str, rarity: int, class_id: int) -> BasicServant:
        targets: dict[int, BasicServant] = {}
        for svt in mstSvt:
            if (
                svt.name == name
                and svt.classId == class_id
                and svt.rarity == rarity
                and svt.collectionNo > 0
            ):
                targets[svt.id] = svt
        if not targets:
            svt_change_ids = set(
                change.svtId for change in mstSvtChange if change.name == name
            )
            for svt in mstSvt:
                if (
                    svt.id in svt_change_ids
                    and svt.classId == class_id
                    and svt.rarity == rarity
                    and svt.collectionNo > 0
                ):
                    targets[svt.id] = svt

        if len(targets) == 1:
            return list(targets.values())[0]
        if not targets:
            raise Exception(f"NotFound: {name}-R{rarity}-{class_id}")
        raise Exception(f"Multiple Found: {name}-R{rarity}-{class_id}: ", targets)

    group_dict: dict[str, GachaGroup] = {}

    text = get_gacha_html(gacha_id)
    table_count = text.count("<table")

    if table_count == 4:
        # svt_class, rarity, name, prob
        svt_table = get_prob_table(text, 2, 4)
        # rarity, name, prob
        ce_table = get_prob_table(text, 3, 3)
    elif table_count == 6:
        svt_table = get_prob_table(text, 2, 4) + get_prob_table(text, 4, 4)
        ce_table = get_prob_table(text, 3, 3) + get_prob_table(text, 5, 3)
    else:
        raise Exception("unexpected table count:", table_count)

    for row in svt_table:
        svt_class, rarity, name, prob = row
        class_id = class_map[svt_class]
        rarity = rarity.count(STAR)
        svt = find_svt(name, rarity, class_id)
        key = f"svt-{rarity}-{prob}"
        group = group_dict.setdefault(
            key, GachaGroup(is_svt=True, rarity=rarity, indiv_prob=prob, cards=[])
        )
        group.cards.append(svt)

    for row in ce_table:
        rarity, name, prob = row
        rarity = rarity.count(STAR)
        ce = find_svt(name, rarity, 1001)
        key = f"ce-{rarity}-{prob}"
        group = group_dict.setdefault(
            key, GachaGroup(is_svt=False, rarity=rarity, indiv_prob=prob, cards=[])
        )
        group.cards.append(ce)

    groups = list(group_dict.values())
    groups.sort(key=lambda x: (-int(x.is_svt), -x.rarity, len(x.cards)))
    outputs = [["type", "star", "weight", "display", "ids"]]
    for row in groups:
        ids = [x.collectionNo for x in row.cards]
        outputs.append(
            [
                "svt" if row.is_svt else "ce",
                str(row.rarity),
                format_prob(row.get_total_prob()),
                "1" if row.rarity == 5 and len(ids) == 1 else "0",
                ", ".join([str(x) for x in sorted(ids)]),
            ]
        )
    return dump_result(outputs)


def main(ids: list[int]) -> str:
    outputs: list[str] = []
    for id in ids:
        outputs.append(parse_gacha(id))
    return "\n\n".join(outputs)


if __name__ == "__main__":
    # cd fgo-game-data-jp && git pull
    # update_exported_files([], False)
    parser = argparse.ArgumentParser(
        description="Parse gacha detail html to Mooncell gacha simulator prob data"
    )
    parser.add_argument("mst", type=str, help="path of fgo-game-data-jp/master")
    parser.add_argument("dest", type=str, help="output filepath")
    parser.add_argument("ids", nargs="+", type=int)
    args = parser.parse_args()
    main(args.ids)
