# %%
import re
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests
from app.schemas.gameenums import NiceEventType
from app.schemas.nice import NiceEvent
from lxml import etree  # type: ignore

from ...config import settings
from ...schemas.wiki_data import EventWBase, LimitedSummonBase, WarW
from ...utils import discord
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
    jp_events: dict[int, NiceEvent] | None = None,
):
    if jp_events is not None:
        fill_jp_event_notice_links(events, jp_events)

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
            except Exception as e:  # noqa: BLE001
                logger.exception(e)
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
        if event.noticeLink.JP:
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


def _normalize_event_name(name: str) -> str:
    return re.sub(r"\s+", "", name).replace("･", "・")


def _unwrap_jp_quotes(value: str) -> tuple[str, str] | None:
    """Return the prefix and contents of a balanced trailing quote group."""
    pairs = {"」": "「", "』": "『"}
    if not value or value[-1] not in pairs:
        return None
    stack: list[str] = []
    quoted: tuple[str, str] | None = None
    for index in range(len(value) - 1, -1, -1):
        char = value[index]
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                return None
            if not stack and quoted is None:
                quoted = value[:index], value[index + 1 : -1]
    return quoted if not stack else None


def _jp_notice_event_names(title: str) -> set[str]:
    title = _normalize_event_name(title)
    match = re.search(r"(?:開催|開幕)！$", title)
    if not match:
        return set()
    quoted = _unwrap_jp_quotes(title[: match.start()])
    if quoted is None or "【期間限定】" not in quoted[0]:
        return set()
    name = quoted[1]
    names = {name} if name else set()
    # Only unwrap complete enclosing quotes, never an inner campaign title.
    while (quoted := _unwrap_jp_quotes(name)) is not None and not quoted[0]:
        name = quoted[1]
        if name:
            names.add(name)
    return names


def fill_jp_event_notice_links(
    events: list[EventWBase], jp_events: dict[int, NiceEvent]
):
    now = time.time()
    pending: list[tuple[EventWBase, NiceEvent]] = []
    for event in events:
        jp_event = jp_events.get(event.id)
        if (
            not event.noticeLink.JP
            and jp_event is not None
            and jp_event.type in (NiceEventType.eventQuest, NiceEventType.warBoard)
            and jp_event.id // 10000 != 7
            and 0 <= now - jp_event.startedAt <= 7 * 24 * 3600
        ):
            pending.append((event, jp_event))
    if not pending:
        return

    news_url = "https://news.fate-go.jp/"
    notices: dict[str, set[str]] = {}
    try:
        # The news index must be fresh on every run; do not use the banner cache.
        response = requests.get(news_url, timeout=30)
        response.raise_for_status()
        html = etree.HTML(response.content)  # type: ignore
        for entry in html.xpath('//ul[@class="list_news"]/li'):
            title = entry.xpath('string(p[@class="title"])')
            links = entry.xpath("a/@href")
            if not title or not links or not links[0].strip():
                continue
            url = urljoin(news_url, links[0].strip())
            for name in _jp_notice_event_names(title):
                notices.setdefault(name, set()).add(url)
    except Exception as e:  # noqa: BLE001
        logger.exception(f"Failed to parse JP news index: {e}")
        return

    added: list[str] = []
    for event, jp_event in pending:
        urls = notices.get(_normalize_event_name(jp_event.name), set())
        if len(urls) > 1:
            logger.warning(f"Ambiguous JP event notice: {event.id} {sorted(urls)}")
        elif urls:
            event.noticeLink.JP = next(iter(urls))
            row = f"{event.id}: {jp_event.name} — {event.noticeLink.JP}"
            logger.info(f"JP event notice auto-filled: {row}")
            added.append(row)
    if added:
        try:
            discord.text("\n".join(added), "JP event notice links auto-filled")
        except Exception as e:  # noqa: BLE001
            logger.exception(f"Failed to notify JP event notice links: {e}")


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
        return None
        # notice_id = re.findall(r"[^\d]\d+$", notice_id)[-1][1:]
    time.sleep(0.2)
    url = f"https://api.biligame.com/news/{notice_id}.action"
    logger.debug(f"parse CN top banner: {url}")
    resp = api.call_api(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
            "Referer": "https://www.biligame.com/",
        },
    )
    resp.raise_for_status()
    response = resp.json()

    if response.get("code") == -400:
        logger.warning(url, response)
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
    for suffix in ("_02.png", "02.png", "_2.png"):
        url2 = url.replace("top_banner.png", "top_banner" + suffix)
        resp = requests.head(url2)
        if resp.ok and resp.headers.get("content-type") == "image/png":
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
