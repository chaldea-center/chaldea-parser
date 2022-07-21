#%%
import re
from typing import Callable
from urllib.parse import urljoin

# import requests
from lxml import etree

from src.schemas.wiki_data import EventWBase, LimitedSummonBase, WarW
from src.utils.helper import dump_json_beautify, load_json
from src.utils.http_cache import HttpApiUtil

api = HttpApiUtil(
    api_server="https://api.atlasacademy.io",
    rate_calls=5,
    rate_period=1,
    db_path="cache/http_cache/banners",
    expire_after=100 * 24 * 3600,
)

#%%
def main(force: bool = False):
    added = 0

    def _check_parse(
        official: str | None, url: str | None, parser: Callable[[str], str | None]
    ):
        nonlocal added
        if official and not force:
            return official
        if url:
            # if added > 10:
            #     return official
            print(f"reading: {url}")
            try:
                official_new = parser(url)
                print(url, official_new)
                added += 1
                if official_new:
                    return official_new
            except Exception as e:
                print(e)
                return official
        return official
    war_path = "data/wiki/wars.json"
    wars = [WarW.parse_obj(obj) for obj in load_json(war_path) or []]
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
    dump_json_beautify(wars, war_path)

    event_path = "data/wiki/eventsBase.json"
    events = [EventWBase.parse_obj(obj) for obj in load_json(event_path) or []]
    for event in events:
        if event.titleBanner.JP:
            event.officialBanner.JP = _check_parse(
                event.officialBanner.JP, event.noticeLink.JP, parse_jp_top_banner
            )
        if event.titleBanner.CN:
            event.officialBanner.CN = _check_parse(
                event.officialBanner.CN, event.noticeLink.CN, parse_cn_top_banner
            )
        if event.titleBanner.TW:
            event.officialBanner.TW = _check_parse(
                event.officialBanner.TW, event.noticeLink.TW, parse_tw_top_banner
            )
    dump_json_beautify(events, event_path)

    summon_path = "data/wiki/summonsBase.json"
    summons = [LimitedSummonBase.parse_obj(obj) for obj in load_json(summon_path) or []]
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
    dump_json_beautify(summons, summon_path)


def _get_xpath(source, xpath) -> str | None:
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
    return _join(url, img)


def parse_cn_top_banner(notice_id: str):
    response = api.call_api(f"https://api.biligame.com/news/{notice_id}.action").json()
    if response.get("code") == -400:
        print(f"https://api.biligame.com/news/{notice_id}.action", response)
        return
    source = response["data"]["content"]
    img = _get_xpath(source, "//img/@src")
    return _join("https://game.bilibili.com/fgo/news.html", img)


def parse_tw_top_banner(notice_id: str):
    response = api.call_api(
        f"https://www.fate-go.com.tw/newsmng/{notice_id}.json"
    ).json()
    source = response["content"]
    img = _get_xpath(source, "//img/@src")
    return _join("https://www.fate-go.com.tw/news.html", img)


if __name__ == "__main__":
    main()

# %%
