import re
from typing import Any, Callable, Iterable, TypeVar, Union

from mwparserfromhell import parse as mwparse
from mwparserfromhell.nodes import Template, Wikilink
from mwparserfromhell.nodes.extras import Parameter
from mwparserfromhell.wikicode import Wikicode

from ..utils import logger


Wikitext = Union[str, Wikicode, Template]
kAllTags = (
    "ref",
    "br",
    "comment",
    "del",
    "sup",
    "include",
    "heimu",
    "trja",
    "nowiki",
    "texing",
    "link",
    "ruby",
    "bold",
    "html_tag",
    "event",
    "fandom",
)

_T = TypeVar("_T")


class Params(dict[Any, str]):
    def get(self, k, default=None, tags=None, nullable=True) -> str | None:
        """
        :param k: dict key.
        :param default: default value if key not in dict.
        :param tags: tags to be removed.
        :param nullable:
        :return:
        """
        # 1->'1'
        if isinstance(k, int) and k not in self and str(k) in self:
            k = str(k)
        if k not in self:
            assert nullable or default is not None
            return default
        # if tags is True:
        #     tags = kAllTags
        v = super(Params, self).get(k)
        if isinstance(v, str) and tags is not None:
            v = remove_tag(v, tags)
        assert nullable or v is not None
        return v

    def get2(self, k, default=None, nullable=True):
        return self.get(k, default, True, nullable)

    def get_cast(
        self, k, cast: Callable[[str], _T], default=None, tags=None, nullable=True
    ) -> _T | None:
        v = self.get(k, default, tags=tags, nullable=nullable)
        if v:
            try:
                # remove ","
                if cast == int:
                    v = str(v).replace(",", "")
                return cast(v)
            except:  # noqas
                return default


def remove_tag(string: str, tags: Iterable[str] = kAllTags, console=False):
    if not string:
        return string
    if tags is True:
        tags = kAllTags
    string = string.strip()
    code = mwparse(string)

    # html tags
    # REMOVE - ref/comment
    for tag_name in ("ref",):
        if tag_name in tags:
            for tag in code.filter_tags(matches=r"^<" + tag_name):
                string = string.replace(str(tag), "")
    if "comment" in tags:
        for comment in code.filter_comments():
            string = string.replace(str(comment), "")
    if "br" in tags:
        string = re.sub(r"<br[\s/\\]*>", "\n", string)
    # Replace with contents - sup/del/noinclude
    for tag_name in ("del", "sup"):
        if tag_name in tags:
            for tag in code.filter_tags(matches=r"^<" + tag_name):
                string = string.replace(str(tag), str(tag.contents))

    if "nowiki" in tags:
        string = re.sub(r"<[\s/]*nowiki[\s/]*>", "", string)
    if "include" in tags:
        # may be nested
        string = re.sub(
            r"<[\s/]*(include|onlyinclude|includeonly|noinclude)[\s/]*>", "", string
        )

    # wiki templates
    # just keep 1st
    if "heimu" in tags:
        for template in code.filter_templates(matches=r"^{{(??????|heimu|??????|??????)"):
            params = parse_template(template)
            string = string.replace(str(template), params.get("1") or "")
        for template in code.filter_templates(matches=r"^{{color"):
            params = parse_template(template)
            string = string.replace(str(template), params.get("2") or "")

    # replace
    if "texing" in tags:
        for template in code.filter_templates(matches=r"^{{(??????|??????)"):
            params = parse_template(template)
            replace = (params.get("2") or params.get("1") or "").strip("??????")
            string = string.replace(str(template), f"???{replace}???")
    if "ruby" in tags:
        for template in code.filter_templates(matches=r"^{{ruby"):
            params = parse_template(template)
            string = string.replace(
                str(template), f"{params.get('1')}[{params.get('2')}]"
            )
    if "event" in tags:
        for template in code.filter_templates(matches=r"^{{??????"):
            params = parse_template(template)
            string = string.replace(str(template), f"???{params.get('2')}???")
    if "link" in tags:
        # remove [[File:a.jpg|b|c]] - it show img
        string = re.sub(r"\[\[(??????|File):([^\[\]]*?)]]", "", string)
        for wiki_link in code.filter_wikilinks():
            wiki_link: Wikilink
            # [[??????????????????::somebody]]
            link = re.split(r":+", str(wiki_link.title))[-1]
            shown_text = wiki_link.text
            if shown_text:
                shown_text = str(shown_text).split("|", maxsplit=1)[0]
            string = string.replace(str(wiki_link), shown_text or link)
    if "trja" in tags:
        for template in code.filter_templates(matches=r"^{{trja"):
            params = parse_template(template)
            string = string.replace(
                str(template), params.get("1") or params.get("2") or ""
            )
    if "fandom" in tags:
        for template in code.filter_templates(matches=r"^{{Seffect"):
            params = parse_template(template)
            string = string.replace(str(template), "")
    if "html_tag" in tags:
        for tag_node in code.filter_tags(recursive=False):
            string = string.replace(str(tag_node), str(tag_node.contents))

    # if 'Nihongo' in tags:
    #     for template in code.filter_templates(matches=r'^{{Nihongo'):
    #         params = parse_template(template)
    #         string = string.replace(str(template), params.get(1) or params.get(2) or '')
    # special
    if "bold" in tags:
        string = re.sub(r"'''([^']*?)'''", r"\1", string)
    # final check
    old_string = str(code)
    if string != old_string and console:
        logger.info(
            f"remove tags: from {len(old_string)}->{len(string)}\n"
            f"Old string:{old_string}\n\nNew string: {string}"
        )
    if string in ("-", "???", ""):
        return ""
    return string


def remove_unused_html_tags(s):
    return re.sub(
        r"<\s*/?\s*(include|onlyinclude|includeonly|noinclude)/?\s*>",
        "",
        s,
        flags=re.RegexFlag.IGNORECASE,
    )


def trim(s: str, chars=None):
    return s.strip(chars)


def parse_template(template: Wikitext, matches: str | None = None) -> Params:
    if not isinstance(template, Template):

        templates = mwparse(template).filter_templates(matches=matches)
        if len(templates) == 0:
            return Params()
        tmpl: Template = templates[0]
    else:
        tmpl = template
    params = Params()
    for p in tmpl.params:
        p: Parameter
        value = trim(p.value)
        if value not in ("-", "???", ""):
            params[trim(p.name)] = value
    return params


def parse_template_list(code, matches: str | None = None) -> list[Params]:
    results = []
    for tmpl in mwparse(code).filter_templates(matches=matches):
        results.append(parse_template(tmpl, matches))
    return results
