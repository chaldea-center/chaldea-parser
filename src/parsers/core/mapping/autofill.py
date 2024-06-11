import re
from pathlib import Path
from typing import Callable, Literal

from ....utils.helper import parse_json_file_as


_Region = Literal["JP", "CN", "TW", "NA", "KR"]
Regions: list[_Region] = ["JP", "CN", "TW", "NA", "KR"]
Mapping = dict[str, dict[_Region, str | None]]
_VReplacer = dict[_Region, str | None] | None
_Replacer = Callable[[str], _VReplacer]


def autofill_mapping(mappings: dict[str, Mapping]):
    # actually not dict[str,Mapping], but here only use this kind of format
    quest_names: Mapping = mappings["quest_names"]
    svt_names: Mapping = mappings["svt_names"]
    entity_names: Mapping = mappings["entity_names"]
    event_names: Mapping = mappings["event_names"]
    war_names: Mapping = mappings["war_names"]
    item_names: Mapping = mappings["item_names"]
    buff_names: Mapping = mappings["buff_names"]
    buff_detail: Mapping = mappings["buff_detail"]
    skill_names: Mapping = mappings["skill_names"]
    skill_detail: Mapping = mappings["skill_detail"]
    cv_names: Mapping = mappings["cv_names"]
    event_war: Mapping = event_names | war_names

    def _repl_svt(name_jp: str):
        return svt_names.get(name_jp) or entity_names.get(name_jp)

    def _repl_item(name_jp: str) -> _VReplacer:
        items = [x.strip() for x in name_jp.split("、")]
        names = {}
        for r in Regions:
            _names = [(item_names.get(x) or {}).get(r) for x in items]
            _names2 = [x for x in _names if x]
            if len(_names) != len(_names2):
                continue
            if r == "CN" or r == "TW":
                names[r] = "、".join(_names2)
            elif r == "NA" or r == "KR":
                names[r] = ", ".join(_names2)
        return names

    def _repl_event(name_jp: str):
        return event_war.get(name_jp)

    def _repl_mlb(name_jp: str) -> _VReplacer:
        if not name_jp:
            return _repl0(name_jp)
        assert name_jp == "[最大解放]"
        return {"CN": "[最大解放]", "TW": "[最大解放]", "NA": "[MAX] "}

    def _repl0(x: str) -> _VReplacer:
        return {"CN": x, "TW": x, "NA": x, "KR": x}

    def _repl_simple(names: Mapping):
        def _repl(name_jp: str):
            return names.get(name_jp)

        return _repl

    update_k(
        quest_names,
        pattern=re.compile(r"^強化クエスト (.+?)( \d)?$"),
        templates={
            "CN": "强化关卡 {0}{1}",
            "TW": "強化任務 {0}{1}",
            "NA": "Rank Up Quest: {0}{1}",
            "KR": "강화 퀘스트 {0}{1}",
        },
        krepls=[_repl_svt, _repl0],
    )
    for names in [quest_names, event_names]:
        update_k(
            names,
            pattern=re.compile(r"^(.+)体験クエスト$"),
            templates={
                "CN": "{0}体验关卡",
                "TW": "{0}體驗任務",
                "NA": "{0} Trial Quest",
                "KR": "{0} 체험 퀘스트",
            },
            krepls=[_repl_svt],
        )

    ranks: dict[str, dict[_Region, str | None]] = {
        "開位級": {"CN": "开位级", "TW": "開位級", "NA": "Cause Rank", "KR": "개위급"},
        "祭位級": {"CN": "祭位级", "TW": "祭位級", "NA": "Fes Rank", "KR": "제위급"},
        "典位級": {"CN": "典位级", "TW": "典位級", "NA": "Pride Rank", "KR": "전위급"},
        "典位+級": {
            "CN": "典位+级",
            "TW": "典位+級",
            "NA": "Pride+ Rank",
            "KR": "전위+급",
        },
        "典位++級": {
            "CN": "典位++级",
            "TW": "典位++級",
            "NA": "Pride++ Rank",
            "KR": "전위++급",
        },
    }
    update_kw(
        quest_names,
        pattern=re.compile(r"^(?P<enemy>.+)・ハント (?P<rank>.+級)$"),
        templates={
            "CN": "{enemy}·狩猎 {rank}",
            "TW": "{enemy}．狩獵 {rank}",
            "NA": "{enemy} Hunt - {rank}",
            "KR": "{enemy} 헌트【{rank}】",
        },
        kwrepls={"enemy": _repl_svt, "rank": lambda x: ranks.get(x)},
    )
    update_k(
        event_names,
        pattern=re.compile(r"^(.+?)\s*獲得経験値2倍！$"),
        templates={
            "CN": "{0}获得经验值2倍！",
            "TW": "{0}獲得經驗值2倍！",
            "NA": "{0} 2X EXP!",
            "KR": "{0} 획득 경험치 2배!",
        },
        krepls=[_repl_svt],
    )
    update_k(
        event_names,
        pattern=re.compile(r"^アドバンスドクエスト 第(\d+)弾$"),
        templates={
            "CN": "进阶关卡 第{0}弹",
            "TW": "進階關卡 第{0}彈",
            "NA": "Advanced Quest: Part {0}",
            "KR": "어드밴스드 퀘스트 {0}탄",
        },
        krepls=[_repl0],
    )
    update_k(
        event_names,
        pattern=re.compile(
            r"^「巡霊の祝祭 第(\d+)弾」関連サーヴァント 獲得経験値(\d+)倍！$"
        ),
        templates={
            "CN": "「巡灵的祝祭 第{0}弹」关联从者获得经验值{1}倍！",
            "TW": "「巡靈的祝祭 第{0}彈」特定從者獲得經驗值{1}倍！",
            "NA": '"Evocation Vestival Part {0}" Related Servants {1}X EXP!',
        },
        krepls=[_repl0, _repl0],
    )

    update_k(
        item_names,
        pattern=re.compile(r"^(\d+)月交換券\((20\d\d)\)$"),
        templates={"CN": "{0}月交换券({1} JP)", "TW": "{0}月交換券({1} JP)"},
        krepls=[_repl0, _repl0],
    )
    update_k(
        buff_detail,
        pattern=re.compile(r"^『(.+)』において与えるダメージをアップ$"),
        templates={
            "CN": "在『{0}』中造成的伤害提升",
            "TW": "在『{0}』中造成的傷害提升",
            "NA": 'Increase damage dealt during "{0}"',
        },
        krepls=[_repl_event],
    )

    kwrepls_skill = {
        "item": _repl_item,
        "count": _repl0,
        "mlb": _repl_mlb,
        "event": _repl_event,
    }

    update_k(
        skill_names,
        pattern=re.compile(r"^(.+)のドロップ獲得数アップ$"),
        templates={
            "CN": "{0}的掉落获得数提升",
            "TW": "{0}的掉落獲得數提升",
            "NA": "Increase amount of {0} per drop",
        },
        krepls=[_repl_item],
    )
    update_k(
        skill_names,
        pattern=re.compile(r"^(.+)のドロップ獲得量アップ$"),
        templates={
            "CN": "{0}的掉落获得量提升",
            "TW": "{0}的掉落獲得量提升",
            "NA": "Increase amount of {0} per drop",
        },
        krepls=[_repl_item],
    )
    update_k(
        skill_names,
        pattern=re.compile(r"^(.+)獲得量アップ$"),
        templates={
            "CN": "{0}获得量提升",
            "TW": "{0}獲得量提升",
            "NA": "Increase amount of {0}",
        },
        krepls=[_repl_item],
    )
    update_k(
        skill_names,
        pattern=re.compile(r"^(.+) ((?:A|B|C|D|E|EX)[\-+]*)$"),
        templates={r: "{0} {1}" for r in Regions},
        krepls=[_repl_simple(buff_names), _repl0],
    )

    update_kw(
        skill_detail,
        pattern=re.compile(
            r"^(?P<item>.+)のドロップ獲得数を(?P<count>[\d%]+)個増やす(?P<mlb>\[最大解放\]|)【『(?P<event>.+)』イベント期間限定】$"
        ),
        templates={
            "CN": "{item}的掉落获得数增加{count}个{mlb}【『{event}』活动限定】",
            "TW": "{item}的掉落獲得數增加{count}個{mlb}【『{event}』活動限定】",
            "NA": "Increase {item} amount per drop by {count} {mlb}[Event Only]",
        },
        kwrepls=kwrepls_skill,
    )

    update_kw(
        skill_detail,
        pattern=re.compile(
            r"^自身の『(?P<event>.+?)』における攻撃の威力を(?P<count>\d+)%アップ(?P<mlb>\[最大解放\]|)【『(?P=event)』イベント期間限定】$"
        ),
        templates={
            "CN": "自身在『{event}』中的攻击威力提升{count}%{mlb}【『{event}』活动限定】",
            "TW": "自身在『{event}』中的攻擊威力提升{count}%【『{event}』活動限定】",
            "NA": 'Increase your ATK Strength by {count}% in "{event}" [Event Only]',
        },
        kwrepls=kwrepls_skill,
    )
    update_kw(
        skill_detail,
        pattern=re.compile(
            r"^『(?P<event>.+?)』において、自身の攻撃の威力を(?P<count>\d+)%アップ(?P<mlb>\[最大解放\]|)【『(?P=event)』イベント期間限定】$"
        ),
        templates={
            "CN": "自身在『{event}』中的攻击威力提升{count}%{mlb}【『{event}』活动限定】",
            "TW": "自身在『{event}』中的攻擊威力提升{count}%{mlb}【『{event}』活動限定】",
            "NA": 'Increase your ATK Strength by {count}% in "{event}" {mlb}[Event Only]',
        },
        kwrepls=kwrepls_skill,
    )
    update_kw(
        skill_detail,
        pattern=re.compile(
            r"^自身の『(?P<event>.*?)』における攻撃の威力を(?P<count>\d+)%アップ＆クエストクリア時に得られる絆を(?P<count2>\d+)%増やす【『(?P=event)』イベント期間限定】$"
        ),
        templates={
            "CN": "自身在『{event}』中的攻击威力提升{count}%＆关卡通关时获得的牵绊值提升{count2}%【『{event}』活动限定】",
            "TW": "自身在『{event}』中的攻擊威力提升{count}%＆關卡通關時獲得的羈絆值提升{count2}%【『{event}』活動限定】",
            "NA": 'Increase your ATK Strength by {count}% in "{event}" & increase Bond gained when completing quests by {count2}% [Event Only]',
        },
        kwrepls=kwrepls_skill | {"count2": _repl0},
    )

    update_kw(
        skill_detail,
        pattern=re.compile(
            # "自身の『     』における攻撃の威力を50%アップ ＋ 味方全体＜控え含む＞の『ワンジナ・ワールドツアー！』のクエストクリア時に得られる絆を5%アップ(サポート時は無効)【『ワンジナ・ワールドツアー！』イベント期間限定】": {
            r"^自身の『(?P<event>.+)』における攻撃の威力を(?P<count>\d+)%アップ ＋ 味方全体[＜<]控え含む[＞>]の『(?P=event)』のクエストクリア時に得られる絆を(?P<count2>\d+)%(?:アップ|増やす)\(サポート時は無効\)【『(?P=event)』イベント期間限定】$"
        ),
        templates={
            "CN": "自身的攻击威力提升{count}%＋己方全体<包括替补>在关卡通关时获得的牵绊值提升{count2}%(作为助战时无效)【『{event}』活动限定】",
            "TW": "自身的攻擊威力提升{count}%＋我方全體<包括替補>在關卡通關時獲得的羈絆值提升{count2}%(作為助戰時無效)【『{event}』活動限定】",
            "NA": 'Increase your ATK Strength by {count}% & increase Bond gained for all allies <including sub-members> when completing quests in "{event}" by {count2}% (No effect when equipped as Support) [Event Only]',
        },
        kwrepls=kwrepls_skill | {"count2": _repl0},
    )

    _update_cvs(cv_names)

    return mappings


def update_k(
    data: Mapping,
    pattern: re.Pattern,
    templates: dict[_Region, str],
    krepls: list[_Replacer],
):
    for name_jp, transl in data.items():
        match = pattern.match(name_jp)
        if not match:
            continue
        repls = [repl_func(match.group(i + 1)) for i, repl_func in enumerate(krepls)]

        for region in list(transl.keys()):
            if transl[region] is not None or not region in templates:
                continue
            tmpl = templates[region]
            kargs = [r.get(region) if r else None for r in repls]
            if None in kargs:
                continue
            value = tmpl.format(*kargs)
            if re.search(r"\{\d*\}", value):
                print(f"{name_jp}: found unformatted '{value}'")
                continue
            transl[region] = value


def update_kw(
    data: Mapping,
    pattern: re.Pattern,
    templates: dict[_Region, str],
    kwrepls: dict[str, _Replacer],
):
    for name_jp, transl in data.items():
        match = pattern.match(name_jp)
        if not match:
            continue
        groupdict = match.groupdict()
        repls = {
            key: repl_func(groupdict[key]) if repl_func else None
            for key, repl_func in kwrepls.items()
            if key in groupdict
        }

        for region in list(transl.keys()):
            if transl[region] is not None or not region in templates:
                continue
            tmpl = templates[region]
            kwargs = {key: r.get(region) if r else None for key, r in repls.items()}
            if None in kwargs.values():
                continue
            value = tmpl.format(**kwargs)
            if re.search(r"\{\w*\}", value):
                print(f"{name_jp}: found unformatted '{value}'")
                continue
            transl[region] = value


def _update_cvs(cv_names: Mapping):
    seps: dict[_Region, str] = {
        "JP": "＆",
        "CN": "＆",
        "TW": "＆",
        "NA": " & ",
        "KR": "&",
    }
    for name_jp in list(cv_names.keys()):
        persons = [s.strip() for s in name_jp.split("＆")]
        if len(persons) <= 1:
            continue
        names = cv_names[name_jp]
        for region in list(names.keys()):
            name = names[region]
            if name is not None or region == "JP":
                continue
            persons2 = [cv_names.get(p, {}).get(region) or "" for p in persons]
            if not all(persons2):
                continue
            sep = seps.get(region)
            if sep:
                names[region] = sep.join(persons2)


def main(folder: Path):
    from src.utils.helper import dump_json

    mappings: dict[str, Mapping] = {}
    for fp in folder.iterdir():
        if not fp.is_file() or not fp.name.endswith(".json"):
            continue
        name = fp.name[:-5]
        try:
            fp.name
            mappings[name] = parse_json_file_as(Mapping, fp)
        except:
            print(f"unmatched mapping format, skip {fp.name}")
    autofill_mapping(mappings)
    for k, v in mappings.items():
        dump_json(v, folder / f"{k}.json")


if __name__ == "__main__":
    import sys

    main(Path(sys.argv[1]))
