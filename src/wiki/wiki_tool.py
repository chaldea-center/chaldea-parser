import contextlib
import re
import time
from datetime import datetime
from enum import StrEnum
from functools import cached_property
from hashlib import md5, sha1
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import unquote

import mwclient
import mwclient.page
import mwparserfromhell
import orjson
import pytz
import pywikibot
import requests
from ratelimit import limits, sleep_and_retry

from ..config import settings
from ..schemas.wiki_cache import WikiCache, WikiImageInfo, WikiPageInfo
from ..utils import dump_json, logger
from ..utils.helper import load_json, retry_decorator


class KnownTimeZone(StrEnum):
    cst = "Etc/GMT-8"
    jst = "Etc/GMT-9"


class WikiTool:
    def __init__(self, host: str, img_url_prefix: str, path="/", user=None, pwd=None):
        self.host: str = host
        self._path: str = path
        self.img_url_prefix: str = img_url_prefix
        self.user = user
        self.pwd = pwd
        # self.site: mwclient.Site = mwclient.Site(host=host, path=path)
        self.site2 = pywikibot.Site(url=f"https://{host}/api.php")
        self._fp = Path(settings.cache_wiki) / f"{host}.json"
        _now = int(time.time())
        self.cache = WikiCache(host=self.host, created=_now, updated=_now)
        self._temp_disabled = False
        self._count = 0

        self.active_requests: set[str] = set()

    @cached_property
    def site(self):
        return mwclient.Site(host=self.host, path=self._path)

    def load(self, clear_empty: bool = False):
        self._fp.resolve().parent.mkdir(exist_ok=True, parents=True)
        if self._fp.exists():
            try:
                data = load_json(self._fp)
                self.cache = WikiCache.parse_obj(data)
                if clear_empty:
                    empty_count = 0
                    for key in list(self.cache.pages.keys()):
                        if not self.cache.pages[key].text:
                            self.cache.pages.pop(key)
                            empty_count += 1
                    if empty_count > 0:
                        logger.info(f"{self.host}: Removed {empty_count} empty pages")
                for key in list(self.cache.images.keys()):
                    img = self.cache.images[key]
                    if not img.info or img.info.get("ns") != 6:
                        self.cache.images.pop(key)
                self.cache.host = self.host
                updated = datetime.fromtimestamp(self.cache.updated).isoformat()
                logger.debug(
                    f"wiki {self.host}: loaded {len(self.cache.pages)} pages, "
                    f"{len(self.cache.images)} images, last updated: {updated}"
                )
            except Exception as e:
                logger.error(f"[{self.host}] failed to load wiki cache: {e}")

    def clear(self):
        self.cache.pages.clear()
        self.cache.images.clear()

    def _call_page_site1(self, name: str) -> tuple[WikiPageInfo, WikiPageInfo | None]:
        name_json = f'"{name}"({len(name)})'
        now = int(time.time())

        def _get_text(p: mwclient.page.Page, retry=3) -> str:
            text = p.text(cache=False)
            if p.exists and p.length and not text:
                logger.error(
                    f"Page found but text empty: {name_json}, length={page.length}"
                )
                time.sleep(3)
                if retry > 0:
                    return _get_text(p, retry - 1)
                else:
                    raise ValueError(
                        f"Page found but text empty after retries: {p.name}"
                    )
            return text

        page: mwclient.page.Page = self.site.pages.get(name)

        text = _get_text(page)
        if not page.exists or not text:
            logger.debug(f"{self.host}: {name_json} not exists")
        redirect = page
        if text:
            while redirect.redirect:
                redirect = redirect.resolve_redirect()

        if redirect == page:
            return WikiPageInfo(name=page.name, text=text, updated=now), None
        else:
            info = WikiPageInfo(
                name=page.name,
                redirect=redirect.name,
                text=text,
                updated=now,
            )
            info2 = WikiPageInfo(
                name=redirect.name, text=_get_text(redirect), updated=now
            )
            return info, info2

    def _call_page_site2(self, name: str) -> tuple[WikiPageInfo, WikiPageInfo | None]:
        name_json = f'"{name}"({len(name)})'
        now = int(time.time())
        page = pywikibot.Page(self.site2, name)
        text = page.text
        if not page.exists() or not text:
            logger.debug(f"{self.host}: {name_json} not exists")
        redirect = page
        if text:
            while redirect.isRedirectPage():
                redirect = redirect.getRedirectTarget()
        if redirect == page:
            info = WikiPageInfo(name=page.title(), text=page.text, updated=now)
            return info, None
        else:
            info = WikiPageInfo(
                name=page.title(),
                redirect=redirect.title(),
                text=page.text,
                updated=now,
            )
            info2 = WikiPageInfo(name=redirect.title(), text=redirect.text, updated=now)
            return info, info2

    @sleep_and_retry
    @limits(3, 4)
    def _call_request_page(self, name: str) -> WikiPageInfo:
        name = self.norm_key(name)
        name_json = f'"{name}"({len(name)})'  # in case there is any special char
        self.active_requests.add(name)
        retry_n, max_retry = 0, 5
        prefix = f"[{self.host}][page]"
        while True:
            try:
                page, redirect = self._call_page_site1(name)
                self.cache.pages[name] = page
                if redirect:
                    self.cache.pages[self.norm_key(redirect.name)] = redirect

                if retry_n > 0:
                    logger.warning(
                        f"{prefix} downloaded {name_json} after {retry_n} retry"
                    )
                else:
                    logger.debug(f"{prefix} download: {name_json}")
                self._count += 1
                if self._count > 100:
                    self._count = 0
                    logger.debug(
                        f"[{self.host}] cached {len(self.cache.pages)} pages,"
                        f" {len(self.cache.images)} images"
                    )

                if name in self.active_requests:
                    self.active_requests.remove(name)
                return page
            except Exception as e:
                retry_n += 1
                if retry_n >= max_retry:
                    logger.warning(
                        f"Fail download {name_json} after {retry_n} retry: {e}"
                    )
                    if name in self.active_requests:
                        self.active_requests.remove(name)
                    raise
                logger.error(f"api failed: {type(e)}: {e}")
                time.sleep(min(5 * retry_n, 30))

    @sleep_and_retry
    @limits(3, 4)
    def _call_request_img(self, name: str) -> WikiImageInfo | None:
        name = self.norm_key(name)
        name_json = f'"{name}"({len(name)})'  # in case there is any special char
        if not name:
            return
        self.active_requests.add(name)
        retry_n, max_retry = 0, 5
        prefix = f"[{self.host}][image]"
        while True:
            try:
                now = int(time.time())
                img = self.site.images[name]
                if img and img.exists:
                    info = WikiImageInfo(
                        name=name,
                        updated=now,
                        info=img._info,
                    )
                    self.cache.images[name] = info
                else:
                    info = None
                    logger.debug(f"{self.host}: {name_json} not exists")
                if retry_n > 0:
                    logger.warning(
                        f"{prefix} downloaded {name_json} after {retry_n} retry"
                    )
                else:
                    logger.debug(f"{prefix} download: {name_json}")
                self._count += 1
                if self._count > 100:
                    self._count = 0
                    logger.debug(
                        f"[{self.host}] cached {len(self.cache.pages)} pages,"
                        f" {len(self.cache.images)} images"
                    )

                if name in self.active_requests:
                    self.active_requests.remove(name)
                return info
            except Exception as e:
                retry_n += 1
                if retry_n >= max_retry:
                    logger.warning(
                        f"Fail download {name_json} after {retry_n} retry: {e}"
                    )
                    if name in self.active_requests:
                        self.active_requests.remove(name)
                    raise
                logger.error(f"api failed: {type(e)}: {e}")
                time.sleep(min(5 * retry_n, 30))

    def get_page_cache(self, name: str) -> WikiPageInfo | None:
        name = self.norm_key(name)
        page = self.cache.pages.get(name)
        if page is None:
            return
        if page.redirect:
            page = self.cache.pages.get(self.norm_key(page.redirect))
            if page:
                return page
            else:
                self.cache.pages.pop(name)
        else:
            return page

    def get_page(self, name: str, allow_cache=True) -> WikiPageInfo | None:
        name = self.norm_key(name)
        if not name:
            return None
        key = unquote(name.strip())
        if key.startswith("#"):
            logger.warning(f"wiki page title startwith #: {key}")
            return None
        result: WikiPageInfo | None = None
        if allow_cache:
            result = self.get_page_cache(key)
        # if result:
        #     print(f'{key}: use cached')
        if result is None:
            result = self._call_request_page(name)
        return result

    def get_page_text(self, name: str, allow_cache=True, clear_tag=True) -> str:
        page = self.get_page(name, allow_cache)
        text = page.text if page else ""
        if text:
            if clear_tag:
                text = self.remove_html_tags(text)
            # ----------------   LS    PS   LTR  --------------
            text = re.sub(r"[\u2028\u2029\u200e]", "", text)
        return text

    def remove_page_cache(self, name: str):
        name = self.norm_key(name)
        page = self.cache.pages.pop(name, None)
        if page and page.redirect:
            self.remove_page_cache(page.redirect)
        return page

    def get_image_cache(self, name: str) -> WikiImageInfo | None:
        name = self.norm_key(name)
        return self.cache.images.get(name)

    def get_image(self, name: str, allow_cache: bool = True) -> WikiImageInfo | None:
        if not name:
            return None
        image: WikiImageInfo | None = None
        if allow_cache:
            image = self.get_image_cache(name)
        if image is None:
            image = self._call_request_img(self.norm_key(name))
        return image

    def get_image_name(self, name: str, allow_cache: bool = True) -> str:
        image = self.get_image(name, allow_cache)
        if not image:
            return self.norm_key(name)
        return image.file_name

    def get_image_url(self, name: str) -> str:
        image = self.get_image(name)
        if not image:
            return self.hash_image_url(name)
        url = unquote(image.url)
        if self.img_url_prefix.startswith("https://") and url.startswith("http://"):
            url = url.replace("http://", "https://", 1)
        return url

    def get_image_url_null(self, name: str | None) -> str | None:
        if name:
            return self.get_image_url(name)

    def hash_image_url(self, filename: str) -> str:
        filename = self.norm_key(filename)
        _hash = md5(filename.encode()).hexdigest()
        return f"{self.img_url_prefix}/{_hash[:1]}/{_hash[:2]}/{filename}"

    @sleep_and_retry
    @limits(2, 5)
    @retry_decorator()
    def _download_image(self, url: str, filepath: Path):
        filepath = Path(filepath)
        filepath.resolve().parent.mkdir(exist_ok=True, parents=True)
        filepath.write_bytes(requests.get(url).content)
        logger.info(f"Download image {filepath} from {url}")

    @staticmethod
    def get_timestamp(s: str | None, tz: KnownTimeZone) -> Optional[int]:
        if not s:
            return None
        m = re.match(r"^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+)", s)
        if not m:
            return None
        seq = [int(x) for x in m.groups()]
        t = datetime(*seq, tzinfo=pytz.timezone(tz.value))
        return int(t.timestamp())

    @retry_decorator(3, 10)
    def recent_changes(
        self,
        start=None,
        end=None,
        dir="older",  # noqa
        namespace=None,
        prop=None,
        show=None,
        limit=None,
        type=None,  # noqa
        toponly=None,
    ):
        return self.query_listing(
            "recentchanges",
            "rc",
            limit=limit,
            params={
                "start": start,
                "end": end,
                "dir": dir,
                "namespace": namespace,
                "prop": prop,
                "show": show,
                "limit": limit,
                "type": type,
                "toponly": "1" if toponly else None,
            },
        )

    def query_listing(self, list_name: str, prefix: str, params: dict, limit=None):
        full_params = {
            "action": "query",
            "format": "json",
            "list": list_name,
            "utf8": 1,
            "limit": limit or "max",
        }
        for k, v in params.items():
            if v is None:
                continue
            full_params[f"{prefix}{k}"] = v

        return self._api_call_continue(full_params, lambda x: x["query"][list_name])

    def ask_query(self, query):
        offset = 0
        params = {
            "action": "ask",
            "query": query,
            "format": "json",
            "utf8": 1,
        }
        result = []
        while offset is not None:
            params2 = dict(params)
            params2["query"] = f"{params2['query']}|offset={offset}"
            resp: dict = self._api_call(params2)  # type: ignore
            offset = resp.get("query-continue-offset")
            answers = resp["query"].get("results", {})
            if isinstance(answers, dict):
                result.extend(answers.values())
                time.sleep(2)
            else:
                result.extend(answers)
        return result

    @retry_decorator(retry_times=3, lapse=10)
    @sleep_and_retry
    @limits(2, 5)
    def _api_call(self, params: dict) -> dict:
        logger.warning(f"[{self.host}] call api: {params}")
        return requests.get(f"https://{self.host}/api.php", params=params).json()

    def _api_call_continue(self, params: dict, getter: Callable[[dict], Any]) -> list:
        result = []
        while True:
            resp: Any = self._api_call(params)
            result.extend(getter(resp))
            if "continue" not in resp:
                break
            params = params | resp["continue"]
        return result

    def _get_expire_time(self, last_days: float, days: float | None = None):
        _now = int(time.time())
        last_timestamp = _now
        if self.cache.updated > 0:
            last_timestamp = min(
                last_timestamp, self.cache.updated - last_days * 24 * 3600
            )
        if days is not None:
            last_timestamp = min(last_timestamp, _now - days * 24 * 3600)
        return int(last_timestamp)

    def remove_recent_changed(self, days: float | None = None):
        _now = int(time.time())
        last_timestamp = self._get_expire_time(0.25, days)
        changes = self.recent_changes(
            start=datetime.fromtimestamp(last_timestamp).isoformat(),
            dir="newer",
            limit="max",
            type="new|edit",
            toponly=1,
        )
        logger.info(f"[{self.host}] recent {len(changes)} changes")
        dropped = 0
        logger.info(
            f"[{self.host}] remove recent changes, last changed:"
            f" {datetime.fromtimestamp(self.cache.updated).isoformat()}"
        )
        for record in changes:
            title = self.norm_key(record.get("title"))
            page = self.remove_page_cache(title)
            if page:
                dropped += 1
                logger.debug(f'{self.host}: drop outdated: {dropped} - "{title}"')
        self.cache.updated = _now

    def clear_moved_or_deleted(self, days: float | None = None):
        last_timestamp = self._get_expire_time(0.5, days)

        for letype in ["move", "delete"]:
            params = {
                "action": "query",
                "format": "json",
                "list": "logevents",
                "utf8": 1,
                "lestart": datetime.fromtimestamp(last_timestamp).isoformat(),
                "letype": letype,
                "ledir": "newer",
                "lenamespace": "0",
                "lelimit": "max",
            }
            log_events = self._api_call_continue(
                params, lambda x: x["query"]["logevents"]
            )
            logger.debug(log_events)
            for event in log_events:
                title: str = event["title"]
                if self.get_page_cache(title):
                    self.remove_page_cache(title)
                    logger.debug(f'{self.host}: drop {letype}d page: "{title}"')

    def save_cache(self):
        logger.debug(
            f"[{self.host}] total cache({len(self.cache.pages)} pages,"
            f" {len(self.cache.images)} images) to {self._fp}"
        )
        # in multi-threading, saving (dict/list iteration) is not safe
        try:
            dump_json(self.cache, self._fp, indent2=False)
        except orjson.JSONEncodeError:
            logger.exception("dump wiki cache failed")

    @contextlib.contextmanager
    def disable_cache(self):
        self._temp_disabled = True
        try:
            yield self
        finally:
            self._temp_disabled = False

    @staticmethod
    def remove_html_tags(s: str):
        s = re.sub(
            r"<\s*/?\s*(include|onlyinclude|includeonly|noinclude)/?\s*>",
            "",
            s,
            flags=re.RegexFlag.IGNORECASE,
        )
        s = re.sub(r"<\s*div [^>]*>", "", s, flags=re.RegexFlag.IGNORECASE)
        s = re.sub("(<!--.*?-->)", "", s, flags=re.DOTALL)
        return s

    @classmethod
    def resolve_all_wikilinks(cls, s: str) -> list[mwparserfromhell.nodes.Wikilink]:
        return mwparserfromhell.parse(s).filter_wikilinks()

    @classmethod
    def resolve_wikilink(cls, s: str) -> str | None:
        links = cls.resolve_all_wikilinks(s)
        if links:
            return str(links[0].title)

    @staticmethod
    def norm_key(name: str):
        if not name:
            return name
        return unquote(name.strip()).replace(" ", "_")
