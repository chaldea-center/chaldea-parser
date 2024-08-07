# %%
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests
from lxml import etree

from ...config import settings
from ...schemas.wiki_data import EventWBase, LimitedSummonBase, WarW
from ...utils.helper import dump_json_beautify, load_json, parse_json_obj_as
from ...utils.http_cache import HttpApiUtil
from ...utils.log import logger


api = HttpApiUtil(
    api_server="",
    rate_calls=5,
    rate_period=1,
    db_path=str(settings.cache_http_cache / "banners"),
    expire_after=100 * 24 * 3600,
)


# %%
def main(
    wars: list[WarW],
    events: list[EventWBase],
    summons: list[LimitedSummonBase],
    force: bool = False,
):
    def _check_parse(
        official: str | None, url: str | None, parser: Callable[[str], str | None]
    ):
        if official and not force:
            return official
        if url:
            try:
                official_new = parser(url)
                if official_new:
                    return official_new
            except Exception as e:
                logger.error(e)
                return official
        return official

    for war in wars:
        if war.titleBanner.JP:
            war.officialBanner.JP = _check_parse(
                war.officialBanner.JP, war.noticeLink.JP, parse_jp_top_banner
            )
        if war.titleBanner.CN:
            war.officialBanner.CN = _check_parse(
                war.officialBanner.CN, war.noticeLink.CN, parse_cn_top_banner
            )
        if war.titleBanner.TW:
            war.officialBanner.TW = _check_parse(
                war.officialBanner.TW, war.noticeLink.TW, parse_tw_top_banner
            )
        war.officialBanner.NA = _check_parse(
            war.officialBanner.NA, war.noticeLink.NA, parse_na_top_banner
        )

    for event in events:
        if event.titleBanner.JP:
            before_banner = event.officialBanner.JP
            after_banner = _check_parse(
                before_banner, event.noticeLink.JP, parse_jp_top_banner
            )
            if before_banner is None and after_banner:
                after_banner = try_get_jp_02(after_banner)
            event.officialBanner.JP = after_banner
        if event.titleBanner.CN:
            event.officialBanner.CN = _check_parse(
                event.officialBanner.CN, event.noticeLink.CN, parse_cn_top_banner
            )
        if event.titleBanner.TW:
            event.officialBanner.TW = _check_parse(
                event.officialBanner.TW, event.noticeLink.TW, parse_tw_top_banner
            )
        event.officialBanner.NA = _check_parse(
            event.officialBanner.NA, event.noticeLink.NA, parse_na_top_banner
        )

    for summon in summons:
        if summon.banner.JP:
            summon.officialBanner.JP = _check_parse(
                summon.officialBanner.JP, summon.noticeLink.JP, parse_jp_top_banner
            )
        if summon.banner.CN:
            summon.officialBanner.CN = _check_parse(
                summon.officialBanner.CN, summon.noticeLink.CN, parse_cn_top_banner
            )
        if summon.banner.TW:
            summon.officialBanner.TW = _check_parse(
                summon.officialBanner.TW, summon.noticeLink.TW, parse_tw_top_banner
            )
        summon.officialBanner.NA = _check_parse(
            summon.officialBanner.NA, summon.noticeLink.NA, parse_na_top_banner
        )


def _get_xpath(source, xpath) -> Any | None:
    html = etree.HTML(source)  # type: ignore
    results = html.xpath(xpath)
    if results:
        return results[0]


def _join(base: str | None, url: str | None):
    if base and url:
        return urljoin(base, url)
    return url


def parse_jp_top_banner(url: str):
    source = api.call_api(url).text
    source = re.sub(r"<!--\s*/?block\s*--->", "", source)
    img = _get_xpath(source, '//div[@class="article"]//img[@width="800"]/@src')
    img2 = _get_xpath(source, '//div[@class="article"]//img/@src')
    if img and img2 and "top_banner" in img2 and "top_banner" not in img:
        img = img2

    return _join(url, img)


def parse_na_top_banner(url: str):
    source = api.call_api(url).text
    source = re.sub(r"<!--\s*/?block\s*--->", "", source)
    img = _get_xpath(source, '//div[@class="article"]//img/@src')
    return _join(url, img)


def parse_cn_top_banner(notice_id: str):
    if not notice_id.isdigit():
        notice_id = re.findall(r"[^\d]\d+$", notice_id)[-1][1:]
    response = api.call_api(f"https://api.biligame.com/news/{notice_id}.action").json()
    if response.get("code") == -400:
        logger.warning(f"https://api.biligame.com/news/{notice_id}.action", response)
        return
    source = response["data"]["content"]
    img = _get_xpath(source, "//img/@src")
    return _join("https://game.bilibili.com/fgo/news.html", img)


def parse_tw_top_banner(notice_id: str):
    if not notice_id.isdigit:
        notice_id = re.findall(r"[^\d]\d+$", notice_id)[-1][1:]
    response = api.call_api(
        f"https://www.fate-go.com.tw/newsmng/{notice_id}.json"
    ).json()
    source = response["content"]
    img = _get_xpath(source, "//img/@src")
    return _join("https://www.fate-go.com.tw/news.html", img)


def try_get_jp_02(url: str) -> str:
    url = url.replace("http://", "https://")
    assert url.startswith("https://news.fate-go.jp/wp-content/uploads/"), url
    if not url.endswith("top_banner.png"):
        return url
    for suffix in ("_02.png", "02.png"):
        url2 = url.replace("top_banner.png", "top_banner" + suffix)
        resp = requests.head(url2)
        if resp.status_code == 200 and resp.headers.get("content-type") == "image/png":
            length = resp.headers.get("content-length")
            if length and int(length) > 0:
                return url2
    return url


# %%
if __name__ == "__main__":
    wiki_folder = Path(settings.output_wiki)

    war_path = wiki_folder / "wars.json"
    wars = [parse_json_obj_as(WarW, obj) for obj in load_json(war_path) or []]
    event_path = wiki_folder / "eventsBase.json"
    events = [parse_json_obj_as(EventWBase, obj) for obj in load_json(event_path) or []]
    summon_path = wiki_folder / "summonsBase.json"
    summons = [
        parse_json_obj_as(LimitedSummonBase, obj)
        for obj in load_json(summon_path) or []
    ]

    main(wars, events, summons, force=False)

    dump_json_beautify(wars, war_path)
    dump_json_beautify(events, event_path)
    dump_json_beautify(summons, summon_path)


# %%
