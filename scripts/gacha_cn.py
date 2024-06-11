"""
python -m scripts.gacha_cn

Manually added CN gacha info before 2019
"""

from pydantic import BaseModel

from scripts._dir import STATIC_DIR
from scripts._gs import get_worksheet
from src.utils.helper import dump_json


class MstGacha(BaseModel):
    id: int
    # imageId: int
    name: str
    type: int
    openedAt: int
    closedAt: int


def main():
    sh = get_worksheet("cn_gacha")
    table: list[list] = sh.get_all_values()
    gacha_list: list[MstGacha] = []
    for row in table[2:]:
        if not row[0]:
            continue
        gacha = MstGacha(
            id=int(row[0]),
            # imageId=0,
            name=str(row[6]).strip(),
            type=int(row[1]),
            openedAt=int(row[7]),
            closedAt=int(row[8]),
        )
        assert (
            gacha.id > 0 and gacha.type in (1, 7) and gacha.closedAt > gacha.openedAt
        ), gacha
        gacha_list.append(gacha)
    dump_json(gacha_list, STATIC_DIR / "mstGachaCNExtra.json")
    print(f"dump {len(gacha_list)} CN gachas")


if __name__ == "__main__":
    main()
