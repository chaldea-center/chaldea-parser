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
import mwparserfromhell
import pytz
import pywikibot
import requests
from pydantic import NoneStr
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

    def load(self):
        self._fp.resolve().parent.mkdir(exist_ok=True, parents=True)
        if self._fp.exists():
            try:
                data = load_json(self._fp) or {}
                # if "images" in data and data["images"]:
                #     value1 = list(data["images"].values())[0]
                #     if "imageinfo" not in value1:
                #         data["images"] = {}
                self.cache = WikiCache.parse_obj(data)
                self.cache.host = self.host
                logger.debug(
                    f"wiki {self.host}: loaded {len(self.cache.pages)} pages, "
                    f"{len(self.cache.images)} images"
                )
            except Exception as e:
                logger.error(f"[{self.host}] failed to load wiki cache: {e}")

    def clear(self):
        self.cache.pages.clear()
        self.cache.images.clear()

    @sleep_and_retry
    @limits(3, 4)
    def _call_request_page(self, name: str) -> WikiPageInfo:
        name_json = f'"{name}"({len(name)})'  # in case there is any special char
        self.active_requests.add(name)
        retry_n, max_retry = 0, 5
        prefix = f"[{self.host}][page]"
        while True:
            try:
                now = int(time.time())
                page = pywikibot.Page(self.site2, name)
                text = page.text
                if not text:
                    logger.debug(f"{self.host}: {name_json} empty")
                redirect = page
                if text:
                    while redirect.isRedirectPage():
                        redirect = redirect.getRedirectTarget()
                if redirect == page:
                    result = self.cache.pages[
                        self.norm_key(page.title())
                    ] = WikiPageInfo(name=page.title(), text=page.text, updated=now)
                else:
                    self.cache.pages[self.norm_key(page.title())] = WikiPageInfo(
                        name=page.title(),
                        redirect=redirect.title(),
                        text=page.text,
                        updated=now,
                    )
                    result = self.cache.pages[
                        self.norm_key(redirect.title())
                    ] = WikiPageInfo(
                        name=redirect.title(), text=redirect.text, updated=now
                    )
                if retry_n > 0:
                    logger.warning(
                        f"{prefix} downloaded {name_json} after {retry_n} retry"
                    )
                else:
                    logger.debug(f"{prefix} download: {name_json}")
                self._count += 1
                if self._count > 100:
                    self._count = 0
                    self.save_cache()
                if name in self.active_requests:
                    self.active_requests.remove(name)
                return result
            except Exception as e:
                retry_n += 1
                if retry_n >= max_retry:
                    logger.warning(
                        f"Fail download {name_json} after {retry_n} retry: {e}"
                    )
                    raise
                time.sleep(min(5 * retry_n, 30))

    @sleep_and_retry
    @limits(3, 4)
    def _call_request_img(self, name: str) -> WikiImageInfo:
        name_json = f'"{name}"({len(name)})'  # in case there is any special char
        self.active_requests.add(name)
        retry_n, max_retry = 0, 5
        prefix = f"[{self.host}][image]"
        while True:
            try:
                now = int(time.time())
                cached = self.cache.images[name] = WikiImageInfo(
                    name=name,
                    updated=now,
                    imageinfo=self.site.images[name].imageinfo,  # type: ignore
                )
                if retry_n > 0:
                    logger.warning(
                        f"{prefix} downloaded {name_json} after {retry_n} retry"
                    )
                else:
                    logger.debug(f"{prefix} download: {name_json}")
                self._count += 1
                if self._count > 100:
                    self._count = 0
                    self.save_cache()
                if name in self.active_requests:
                    self.active_requests.remove(name)
                return cached
            except Exception as e:
                retry_n += 1
                if retry_n >= max_retry:
                    logger.warning(
                        f"Fail download {name_json} after {retry_n} retry: {e}"
                    )
                    raise
                time.sleep(min(5 * retry_n, 30))

    def get_page_text(self, name: str, allow_cache=True, clear_tag=True):
        name = self.norm_key(name)
        if not name:
            # print('name empty')
            return name
        key = unquote(name.strip())
        if key.startswith("#"):
            logger.warning(f"wiki page title startwith #: {key}")
            return ""
        result = None
        if allow_cache:
            result = self.get_cache(key)
        # if result:
        #     print(f'{key}: use cached')
        if result is None:
            page = self._call_request_page(name)
            if page:
                result = page.text
        result = result or ""
        if clear_tag:
            result = self.remove_html_tags(result)
        # print(f'{key}: {len(result)}')
        if result:
            # ----------------   LS    PS    LTR  --------------
            result = re.sub(r"[\u2028\u2029\u200e]", "", result)
        return result

    def _process_url(self, image: WikiImageInfo) -> str:
        origin_url = unquote(image.imageinfo["url"])
        sha1value = image.imageinfo["sha1"]
        url = re.sub(r"^http://", "https://", origin_url)
        url += "?sha1=" + sha1value
        # # deprecated: "removed sha1 and `_download_image`"
        # filepath: Path = Path(settings.static_dir) / self.host / sha1value
        # if (
        #     not filepath.exists()
        #     or sha1(filepath.read_bytes()).hexdigest() != sha1value
        # ):
        #     if not settings.is_debug:
        #         self._download_image(origin_url, filepath)
        return url

    @staticmethod
    def norm_filename(filename: str) -> str:
        return unquote(filename).replace(" ", "_")

    def hash_file_url(self, filename: str) -> str:
        filename = self.norm_filename(filename)
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

    def get_file_url(self, name: str) -> str:
        name = self.norm_key(name)
        if not name:
            return name
        cached = self.cache.images.get(name)
        if cached and cached.imageinfo.get("url"):
            return self._process_url(cached)
        image = self._call_request_img(name)
        if not image or not image.imageinfo:
            return self.hash_file_url(name)
        return self._process_url(image)

    def get_file_url_null(self, name: str | None) -> str | None:
        if name:
            return self.get_file_url(name)

    def get_cache(self, name: str) -> NoneStr:
        name = self.norm_key(name)
        page = self.cache.pages.get(name)
        if page is None:
            return
        if page.redirect:
            page = self.cache.pages.get(self.norm_key(page.redirect))
            if page:
                return page.text
            else:
                self.cache.pages.pop(name)
        else:
            return page.text

    def remove_cache(self, name: str):
        name = self.norm_key(name)
        page = self.cache.pages.pop(name, None)
        if page and page.redirect:
            self.remove_cache(page.redirect)
        return page

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
            resp: dict = self._api_call(params2)
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
            resp = self._api_call(params)
            result.extend(getter(resp))
            if "continue" not in resp:
                break
            params = params | resp["continue"]
        return result

    def remove_recent_changed(self, days: float | None = None):
        _now = int(time.time())
        if days is not None:
            last_timestamp = datetime.utcnow().timestamp() - days * 24 * 3600
        else:
            last_timestamp = self.cache.updated - 48 * 3600
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
            page = self.remove_cache(title)
            if page:
                dropped += 1
                logger.debug(f'{self.host}: drop outdated: {dropped} - "{title}"')
        self.cache.updated = _now

    def clear_moved_or_deleted(self, days: float | None = None):
        if days is not None:
            last_timestamp = datetime.utcnow().timestamp() - days * 24 * 3600
        else:
            last_timestamp = self.cache.updated - 96 * 3600

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
                if self.get_cache(title):
                    self.remove_cache(title)
                    logger.debug(f'{self.host}: drop {letype}d page: "{title}"')

    def save_cache(self):
        logger.debug(
            f"[{self.host}] save cache({len(self.cache.pages)} pages,"
            f" {len(self.cache.images)} images) to {self._fp}"
        )
        dump_json(self.cache, self._fp, indent2=False)

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
        return name.strip().replace(" ", "_")
