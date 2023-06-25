from typing import TypeVar

from app.schemas.common import Region

from ....schemas.common import MappingBase


_T = TypeVar("_T")
_KT = TypeVar("_KT", str, int)
_KV = TypeVar("_KV", str, int)


def update_key_mapping(
    region: Region,
    key_mapping: dict[_KT, MappingBase[_KV]],
    _key: _KT,
    value: _KV | None,
    skip_exists=False,
    skip_unknown_key=False,
):
    if _key is None or (isinstance(_key, str) and _key.strip("-") == ""):
        return
    if value is None or (isinstance(value, str) and value.strip("-") == ""):
        return
    if skip_unknown_key and _key not in key_mapping:
        return
    one = key_mapping.setdefault(_key, MappingBase())
    if region == Region.JP and _key == value:
        value = None
    one.update(region, value, skip_exists)


def process_skill_detail(detail: str | None):
    if not detail:
        return detail
    return detail.replace("[g][o]▲[/o][/g]", "▲")
