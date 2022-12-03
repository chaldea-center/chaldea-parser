#%%
import re
from dataclasses import dataclass
from typing import Literal, Pattern

from src.utils import dump_json, load_json


Region = Literal["JP", "CN", "TW", "NA", "KR"]

_SKILL_NAME_REPLACES: dict[Pattern, dict[Region, str]] = {
    re.compile(r"^(.+)のドロップ獲得数アップ$"): {
        "CN": "{0}的掉落获得数提升",
        "NA": "Increase amount of {0} per drop",
    },
    re.compile(r"^(.+)のドロップ獲得量アップ$"): {
        "CN": "{0}的掉落获得量提升",
        "NA": "Increase amount of {0} per drop",
    },
    re.compile(r"^(.+)獲得量アップ$"): {
        "CN": "{0}获得量提升",
        "NA": "Increase amount of {0} per drop",
    },
}
# 犬士ポイントのドロップ獲得量を30%増やす【『南溟弓張八犬伝』イベント期間限定】
@dataclass
class _SkillDetail:
    pattern: Pattern
    item_count_event: tuple[int, int, int]
    mapping: dict[Region, str]


_SKILL_DETAIL_REPLACES: list[_SkillDetail] = [
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得数を(\d+)個増やす【『(.+)』イベント期間限定】$"),
        item_count_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得数增加{count}个【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得数を(\d+)個増やす\[最大解放\]【『(.+)』イベント期間限定】$"),
        item_count_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得数增加{count}个[最大解放]【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [MAX] [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得量を(\d+)個増やす【『(.+)』イベント期間限定】$"),
        item_count_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得量增加{count}个【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得量を(\d+)個増やす\[最大解放\]【『(.+)』イベント期間限定】$"),
        item_count_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得量增加{count}个[最大解放]【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [MAX] [Event Only]",
        },
    ),
]


def _get_item_transl(
    text_jp: str,
    region: Region,
    items: dict[str, dict[Region, str | None]],
):
    names = []
    items_jp = text_jp.split("、")
    for name in items_jp:
        if name not in items:
            return None
        v = items[name][region]
        if not v:
            return None
        names.append(v)
    if region == "CN":
        return "、".join(names)
    elif region == "NA":
        return ", ".join(names)
    else:
        raise KeyError(f"Unimplemented: {region}")


def _update_skill_name(
    text_jp: str,
    transl: dict[Region, str | None],
    region: Region,
    items: dict[str, dict[Region, str | None]],
):
    if transl[region] is not None:
        return
    for pattern, mapping in _SKILL_NAME_REPLACES.items():
        repl = mapping.get(region)
        if not repl:
            continue
        matches = pattern.findall(text_jp)
        if not matches:
            continue
        assert isinstance(matches[0], str)
        name = _get_item_transl(matches[0], region, items)
        if not name:
            continue
        transl[region] = repl.format(name)


def _update_skill_detail(
    text_jp: str,
    transl: dict[Region, str | None],
    region: Region,
    items: dict[str, dict[Region, str | None]],
    events: dict[str, dict[Region, str | None]],
):
    if transl[region] is not None:
        return
    for detail in _SKILL_DETAIL_REPLACES:
        repl = detail.mapping.get(region)
        if not repl:
            continue
        matches = detail.pattern.findall(text_jp)
        if not matches:
            continue
        item_jp, count, event_jp = [matches[0][i] for i in detail.item_count_event]
        item = _get_item_transl(item_jp, region, items)
        if detail.item_count_event[0] >= 0 and not item:
            continue
        event: str | None = None
        if event_jp in events:
            event = events[event_jp].get(region)
        for k, v in {
            "{item}": item,
            "{count}": count,
            "{event}": event or "{event_name}",
        }.items():
            if v:
                repl = repl.replace(k, v)
        transl[region] = repl


def main():
    item_names = load_json("data/mappings/item_names.json")
    skill_names = load_json("data/mappings/skill_names.json")
    skill_details = load_json("data/mappings/skill_detail.json")
    assert item_names and skill_names and skill_details
    for text_jp, transl in skill_names.items():
        for region in ("JP", "CN", "TW", "NA", "KR"):
            _update_skill_name(text_jp, transl, region, item_names)
    dump_json(skill_names, "data/mappings/skill_names.json")

    for text_jp, transl in skill_details.items():
        for region in ("JP", "CN", "TW", "NA", "KR"):
            _update_skill_detail(text_jp, transl, region, item_names, {})
    dump_json(skill_details, "data/mappings/skill_detail.json")


if __name__ == "__main__":
    main()

# %%
