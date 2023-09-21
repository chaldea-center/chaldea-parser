import re
from typing import Callable, Literal


_Region = Literal["JP", "CN", "TW", "NA", "KR"]
Regions: list[_Region] = ["JP", "CN", "TW", "NA", "KR"]
Mapping = dict[str, dict[_Region, str | None]]
_VReplacer = dict[_Region, str | None] | None
_Replacer = Callable[[str], _VReplacer]


def autofill_mapping(mappings: dict[str, Mapping]) -> dict:
    # actually not dict[str,Mapping], but here only use this kind of format
    quest_names: Mapping = mappings["quest_names"]
    svt_names: Mapping = mappings["svt_names"]
    entity_names: Mapping = mappings["entity_names"]
    event_names: Mapping = mappings["event_names"]
    war_names: Mapping = mappings["war_names"]
    item_names: Mapping = mappings["item_names"]
    buff_names: Mapping = mappings["buff_names"]
    skill_names: Mapping = mappings["skill_names"]
    skill_detail: Mapping = mappings["skill_detail"]
    event_war: Mapping = event_names | war_names

    def _repl_svt(name_jp: str):
        return svt_names.get(name_jp) or entity_names.get(name_jp)

    def _repl_item(name_jp: str) -> dict[_Region, str | None] | None:
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

    def _repl0(x: str) -> _VReplacer:
        return {"CN": x, "TW": x, "NA": x, "KR": x}

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
        "典位+級": {"CN": "典位+级", "TW": "典位+級", "NA": "Pride+ Rank", "KR": "전위+급"},
        "典位++級": {"CN": "典位++级", "TW": "典位++級", "NA": "Pride++ Rank", "KR": "전위++급"},
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
            "NA": "Advanced Quest Vol. {0}",
            "KR": "어드밴스드 퀘스트 {0}탄",
        },
        krepls=[_repl0],
    )
    update_k(
        event_names,
        pattern=re.compile(r"^「巡霊の祝祭 第(\d+)弾」関連サーヴァント 獲得経験値(\d+)倍！$"),
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
        buff_names,
        pattern=re.compile(r"^『(.+)』において与えるダメージをアップ$"),
        templates={
            "CN": "在『{0}』中造成的伤害提升",
            "TW": "在『{0}』中造成的傷害提升",
            "NA": 'Increase damage dealt during "{0}"',
        },
        krepls=[_repl_event],
    )

    update_k(
        skill_names,
        pattern=re.compile(r"^(.+)のドロップ獲得数アップ$"),
        templates={
            "CN": "{0}的掉落获得数提升",
            "TW": "{0}的掉落獲得數提升",
            "NA": "Increase amount of {0} per drop",
            "KR": "{0} 획득 UP",
        },
        krepls=[_repl_item],
    )

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
