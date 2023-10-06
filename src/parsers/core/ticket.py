import re

from app.schemas.gameenums import NiceItemType
from app.schemas.nice import NiceItem

from ...schemas.common import MappingBase
from ...schemas.gamedata import ExchangeTicket


def parse_exchange_tickets(nice_item: list[NiceItem]) -> list[ExchangeTicket]:
    tickets: list[ExchangeTicket] = []
    replaced: dict[int, MappingBase[list[int]]] = {
        202003: MappingBase(CN=[6537, 6514, 6534]),
        202004: MappingBase(CN=[6535, 6526, 6530]),
        202006: MappingBase(NA=[6538, 6547, 6527]),  # 2 鬼灯-线球
        202007: MappingBase(NA=[6535, 6509, 6549]),  # 3 黑灰-小钟
        202008: MappingBase(NA=[6537, 6526, 6550]),  # 3 树种-鳞粉
        202012: MappingBase(NA=[6537, 6550, 6527]),  # 2 鬼灯-鳞粉
        202102: MappingBase(NA=[6538, 6526, 6549]),  # 3 龙牙-小钟
        202206: MappingBase(CN=[]),
        202207: MappingBase(CN=[]),
        202208: MappingBase(CN=[]),  # CN skip 3 months
    }
    for item in nice_item:
        if item.type != NiceItemType.itemSelect:
            continue
        match = re.search(r"^(\d+)月交換券\((\d+)\)$", item.name)
        if not match:
            continue
        year, month = match.group(2), match.group(1)

        item_ids = []
        # if len(item.itemSelects) > 3:
        #     item.itemSelects = item.itemSelects[:3]
        # assert (
        #     len(item.itemSelects) == 3
        # ), f"exchange ticket items!=3: {item.id}-{item.name}"
        for select in item.itemSelects:
            assert len(select.gifts) == 1
            item_ids.append(select.gifts[0].objectId)
        key = int(year) * 100 + int(month)
        tickets.append(
            ExchangeTicket(
                id=key,
                year=int(year),
                month=int(month),
                items=item_ids,
                replaced=replaced.get(key),
                multiplier=4 if key >= 202208 else 1,
            )
        )
    return tickets
