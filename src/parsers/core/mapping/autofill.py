import re
from typing import Callable, Literal

from ....schemas.mappings import MappingData


_Region = Literal["JP", "CN", "TW", "NA", "KR"]
Mapping = dict[str, dict[_Region, str | None]]
_Replacer = Callable[[str], dict[_Region, str | None] | None]


def autofill_mapping(mappings: dict[str, Mapping]) -> dict:
    # actually not dict[str,Mapping], but here only use this kind of format
    quest_names: Mapping = mappings["quest_names"]
    svt_names: Mapping = mappings["svt_names"]
    entity_names: Mapping = mappings["entity_names"]

    def _repl_svt(name_jp: str) -> dict[_Region, str | None]:
        return svt_names.get(name_jp) or entity_names.get(name_jp) or {}

    def _repl0(x: str) -> dict[_Region, str | None]:
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
    update_k(
        quest_names,
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
