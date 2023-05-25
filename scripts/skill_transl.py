"""
python -m scripts.skill_transl
"""
import re
from dataclasses import dataclass
from pathlib import Path
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


@dataclass
class _SkillDetail:
    pattern: Pattern
    item_counts_event: tuple[int | list[int], int | list[int], int]
    mapping: dict[Region, str]

    def get_items(self) -> list[int]:
        items = self.item_counts_event[0]
        if isinstance(items, int):
            items = [items]
        return [x for x in items if x >= 0]

    def get_counts(self) -> list[int]:
        counts = self.item_counts_event[1]
        if isinstance(counts, int):
            counts = [counts]
        return [x for x in counts if x >= 0]

    def get_event(self) -> int | None:
        event = self.item_counts_event[2]
        return event if event >= 0 else None


_SKILL_DETAIL_REPLACES: list[_SkillDetail] = [
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得数を(\d+)個増やす【『(.+)』イベント期間限定】$"),
        item_counts_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得数增加{count}个【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得数を(\d+)個増やす\[最大解放\]【『(.+)』イベント期間限定】$"),
        item_counts_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得数增加{count}个[最大解放]【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [MAX] [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得量を(\d+)個増やす【『(.+)』イベント期間限定】$"),
        item_counts_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得量增加{count}个【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得量を(\d+)個増やす\[最大解放\]【『(.+)』イベント期間限定】$"),
        item_counts_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得量增加{count}个[最大解放]【活动限定】",
            "NA": "Increase {item} amount per drop by {count} [MAX] [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得量を(\d+)%増やす【『(.+)』イベント期間限定】$"),
        item_counts_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得量提升{count}%【活动限定】",
            "NA": "Increase {item} amount per drop by {count}% [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^(.+)のドロップ獲得量を(\d+)%増やす\[最大解放\]【『(.+)』イベント期間限定】$"),
        item_counts_event=(0, 1, 2),
        mapping={
            "CN": "{item}的掉落获得量提升{count}%[最大解放]【活动限定】",
            "NA": "Increase {item} amount per drop by {count}% [MAX] [Event Only]",
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^『(.+?)』において、自身の攻撃の威力を(\d+)%アップ【『(.+)』イベント期間限定】$"),
        item_counts_event=(-1, 1, 2),
        mapping={
            "CN": "自身的攻击威力提升{count}%【『{event}』活动限定】",
            "NA": 'Increase ATK Strength by {count}% for yourself in "{event}" [Event Only]',
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^『(.+?)』において、自身の攻撃の威力を(\d+)%アップ\[最大解放\]【『(.+)』イベント期間限定】$"),
        item_counts_event=(-1, 1, 2),
        mapping={
            "CN": "自身的攻击威力提升{count}%[最大解放]【『{event}』活动限定】",
            "NA": 'Increase ATK Strength by {count}% for yourself in "{event}" [MAX] [Event Only]',
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^自身の『(.+?)』における攻撃の威力を(\d+)%アップ【『(.+)』イベント期間限定】$"),
        item_counts_event=(-1, 1, 2),
        mapping={
            "CN": "自身的攻击威力提升{count}%[最大解放]【『{event}』活动限定】",
            "NA": 'Increase ATK Strength by {count}% for yourself in "{event}" [MAX] [Event Only]',
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^自身の『(.+?)』における攻撃の威力を(\d+)%アップ\[最大解放\]【『(.+)』イベント期間限定】$"),
        item_counts_event=(-1, 1, 2),
        mapping={
            "CN": "自身的攻击威力提升{count}%[最大解放]【『{event}』活动限定】",
            "NA": 'Increase ATK Strength by {count}% for yourself in "{event}" [MAX] [Event Only]',
        },
    ),
    _SkillDetail(
        pattern=re.compile(r"^自身の『(.*?)』のクエストクリア時に得られる絆を(\d+)%増やす【『(.*?)』イベント期間限定】$"),
        item_counts_event=(-1, 1, 2),
        mapping={
            "CN": "自身在关卡通关时获得的牵绊值提升{count}%【『{event}』活动限定】",
            "NA": 'Increase Bond gained when completing quests in "{event}" by {count}% for yourself [Event Only]',
        },
    ),
    _SkillDetail(
        pattern=re.compile(
            r"^自身の『(.*?)』における攻撃の威力を(\d+)%アップ＆クエストクリア時に得られる絆を(\d+)%増やす【『(.*?)』イベント期間限定】$"
        ),
        item_counts_event=(-1, [1, 2], 3),
        mapping={
            "CN": "自身的攻击威力提升{count1}%＆关卡通关时获得的牵绊值提升{count2}%【『{event}』活动限定】",
            "NA": 'Increase ATK Strength by {count1}% for yourself in "{event}" & increase Bond gained when completing quests by {count2}% [Event Only]',
        },
    ),
    _SkillDetail(
        pattern=re.compile(
            r"^自身の『(.*?)』において、攻撃の威力を(\d+)%アップ ＋ 味方全体＜控え含む＞の『(.*?)』のクエストクリア時に得られる絆を(\d+)%アップ\(サポート時は無効\)【『(.*?)』イベント期間限定】$"
        ),
        item_counts_event=(-1, [1, 3], 4),
        mapping={
            "CN": "自身的攻击威力提升{count1}%＋己方全体<包括替补>在关卡通关时获得的牵绊值提升{count2}%(作为助战时无效)【『{event}』活动限定】",
            "NA": 'Increase your ATK Strength by {count1}% & increase Bond gained for all allies <including sub-members> when completing quests in "{event}" by {count2}% (No effect when equipped as Support) [Event Only]',
        },
    ),
    _SkillDetail(
        pattern=re.compile(
            r"^自身の『(.*?)』における攻撃の威力を(\d+)%アップ ＋ 味方全体[＜<]控え含む[＞>]の『(.*?)』のクエストクリア時に得られる絆を(\d+)%(?:アップ|増やす)\(サポート時は無効\)【『(.*?)』イベント期間限定】$"
        ),
        item_counts_event=(-1, [1, 3], 4),
        mapping={
            "CN": "自身的攻击威力提升{count1}%＋己方全体<包括替补>在关卡通关时获得的牵绊值提升{count2}%(作为助战时无效)【『{event}』活动限定】",
            "NA": 'Increase your ATK Strength by {count1}% & increase Bond gained for all allies <including sub-members> when completing quests in "{event}" by {count2}% (No effect when equipped as Support) [Event Only]',
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
    if "期間限定" not in text_jp:
        return
    for detail in _SKILL_DETAIL_REPLACES:
        repl = detail.mapping.get(region)
        if not repl:
            continue
        matches = detail.pattern.findall(text_jp)
        if not matches:
            continue
        match = matches[0]
        replaces: dict[str, str] = {}
        for index, item_index in enumerate(detail.get_items()):
            item_jp: str = match[item_index]
            item = _get_item_transl(item_jp, region, items)
            if item:
                replaces[f"{{item{index+1}}}"] = item
                if index == 0:
                    replaces["{item}"] = item

        for index, count_index in enumerate(detail.get_counts()):
            count = match[count_index]
            replaces[f"{{count{index+1}}}"] = count
            if index == 0:
                replaces["{count}"] = count

        event_index = detail.get_event()
        event: str | None = None
        if event_index:
            event_jp: str = match[event_index]
            if event_jp in events:
                event = events[event_jp].get(region)
            event = event or event_jp
            if event:
                replaces["{event}"] = event

        if "{item}" in replaces and "{count}" not in replaces:
            continue

        for k, v in replaces.items():
            if v:
                repl = repl.replace(k, v)
        if "{item" in repl or "{count" in repl or "{event" in repl:
            continue
        transl[region] = repl


def main():
    mapping_dir = Path(__file__).parents[1] / "data" / "mappings"
    item_names = load_json(mapping_dir / "item_names.json")
    event_names = load_json(mapping_dir / "event_names.json")
    event_names |= load_json(mapping_dir / "war_names.json")
    skill_names = load_json(mapping_dir / "skill_names.json")
    skill_details = load_json(mapping_dir / "skill_detail.json")
    assert item_names and skill_names and skill_details
    for text_jp, transl in skill_names.items():
        for region in ("JP", "CN", "TW", "NA", "KR"):
            _update_skill_name(text_jp, transl, region, item_names)
    dump_json(skill_names, mapping_dir / "skill_names.json")

    for text_jp, transl in skill_details.items():
        for region in ("JP", "CN", "TW", "NA", "KR"):
            _update_skill_detail(text_jp, transl, region, item_names, event_names)
    dump_json(skill_details, mapping_dir / "skill_detail.json")


if __name__ == "__main__":
    main()
