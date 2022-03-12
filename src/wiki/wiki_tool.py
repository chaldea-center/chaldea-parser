import contextlib
import re
import time
from datetime import datetime
from hashlib import sha1
from pathlib import Path
from typing import Optional
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


class WikiTool:
    def __init__(self, host: str, path="/", limit: int = 10):
        from ..config import settings

        self.host: str = host
        self.limit: int = limit
        self.site: mwclient.Site = mwclient.Site(host=host, path=path)
        self.site2 = pywikibot.Site(url=f"https://{host}/api.php")
        self._fp = Path(settings.cache_dir) / "wiki" / f"{host}.json"
        _now = int(time.time())
        self.cache = WikiCache(host=self.host, created=_now, updated=_now)
        self._temp_disabled = False
        self._count = 0

    def load(self):
        self._fp.resolve().parent.mkdir(exist_ok=True, parents=True)
        if self._fp.exists():
            try:
                data = load_json(self._fp) or {}
                if "images" in data and data["images"]:
                    value1 = list(data["images"].values())[0]
                    if "imageinfo" not in value1:
                        data["images"] = {}
                self.cache = WikiCache.parse_obj(data)
                self.cache.host = self.host
                print(f"wiki {self.host}: loaded {len(self.cache.pages)} cached")
            finally:
                ...

    @sleep_and_retry
    @limits(4, 2)
    def _call_request(
        self, name: str, is_image: bool = False
    ) -> WikiPageInfo | WikiImageInfo | None:
        retry_n, retry = 0, 10
        while retry_n < retry:
            try:
                now = int(time.time())
                if is_image:
                    cached = self.cache.images[name] = WikiImageInfo(
                        name=name,
                        updated=now,
                        imageinfo=self.site.images[name].imageinfo,
                    )
                else:
                    page = pywikibot.Page(self.site2, name)
                    text = page.text
                    if not text:
                        print(f'{self.site.host}: "{name}" empty')
                    redirect = page
                    while redirect.isRedirectPage():
                        redirect = redirect.getRedirectTarget()
                    if redirect == page:
                        self.cache.pages[self.norm_key(page.title())] = WikiPageInfo(
                            name=page.title(), text=page.text, updated=now
                        )
                    else:
                        self.cache.pages[self.norm_key(page.title())] = WikiPageInfo(
                            name=page.title(),
                            redirect=redirect.title(),
                            text=page.text,
                            updated=now,
                        )
                        self.cache.pages[
                            self.norm_key(redirect.title())
                        ] = WikiPageInfo(
                            name=redirect.title(), text=redirect.text, updated=now
                        )
                    cached = redirect
                if retry_n > 0:
                    logger.warning(f'downloaded "{name}" after {retry_n} retry')
                else:
                    print(f"download wikitext/imageinfo: {name}")
                self._count += 1
                if self._count > 100:
                    self._count = 0
                    self.save_cache()
                return cached
            except Exception as e:
                retry_n += 1
                if retry_n >= retry:
                    logger.warning(f'Fail download "{name}" after {retry_n} retry: {e}')
                time.sleep(2)

    def get_page_text(self, name: str, allow_cache=True, clear_tag=True):
        name = self.norm_key(name)
        if not name:
            # print('name empty')
            return None
        key = name.strip().replace("%26", "&")
        if key.startswith("#"):
            print(f"wiki page title startwith #: {key}")
            return ""
        result = None
        if allow_cache:
            result = self.get_cache(key)
        # if result:
        #     print(f'{key}: use cached')
        if result is None:
            page = self._call_request(name)
            if page:
                result = page.text
        result = result or ""
        if clear_tag:
            result = self.remove_html_tags(result)
        # print(f'{key}: {len(result)}')
        return result

    def _process_url(self, image: WikiImageInfo) -> str:
        origin_url = unquote(image.imageinfo["url"])
        sha1value = image.imageinfo["sha1"]
        url = re.sub(r"^http://", "https://", origin_url)
        url += "?sha1=" + sha1value
        filepath = Path(settings.static_dir) / self.host / sha1value
        if (
            not filepath.exists()
            or sha1(filepath.read_bytes()).hexdigest() != sha1value
        ):
            if not settings.is_debug:
                self._download_image(origin_url, filepath)
        return url

    @sleep_and_retry
    @limits(2, 5)
    @retry_decorator()
    def _download_image(self, url: str, filepath: Path):
        filepath = Path(filepath)
        filepath.resolve().parent.mkdir(exist_ok=True, parents=True)
        filepath.write_bytes(requests.get(url).content)
        logger.info(f"Download image {filepath} from {url}")

    def get_file_url(self, name: str):
        name = self.norm_key(name)
        if not name:
            return None
        cached = self.cache.images.get(name)
        if cached and cached.imageinfo.get("url"):
            return self._process_url(cached)
        image = self._call_request(name, True)
        if not image or not image.imageinfo:
            return None
        return self._process_url(image)

    def get_cache(self, name: str) -> NoneStr:
        name = self.norm_key(name)
        page = self.cache.pages.get(name)
        if not page:
            return
        if page.redirect:
            page = self.cache.pages.get(page.redirect)
            if page:
                if not page.text and page.outdated():
                    return None
                return page.text
            else:
                self.cache.pages.pop(name)
        else:
            if not page.text and page.outdated():
                return None
            return page.text

    @staticmethod
    def get_timestamp(s: str, tz: str = "Asia/Shanghai") -> Optional[int]:
        if not s:
            return None
        m = re.match(r"^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+)", s)
        if not m:
            return None
        seq = [int(x) for x in m.groups()]
        t = datetime(*seq, tzinfo=None)
        t.replace(tzinfo=pytz.timezone(tz))
        return int(t.timestamp())

    @retry_decorator()
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
        return self.site.recentchanges(
            start=start,
            end=end,
            dir=dir,
            namespace=namespace,
            prop=prop,
            show=show,
            limit=limit,
            type=type,
            toponly=toponly,
        )

    @retry_decorator()
    def ask_query(self, query, title=None):
        return self.site.ask(query, title)

    def remove_recent_changed(self, days: float | None = None):
        _now = int(time.time())
        if days is not None:
            last_timestamp = datetime.utcnow().timestamp() - days * 24 * 3600
        else:
            last_timestamp = self.cache.updated - 1 * 24 * 3600
        changes = self.recent_changes(
            start=datetime.fromtimestamp(last_timestamp).isoformat(),
            dir="newer",
            limit="max",
            type="new|edit",
            toponly=1,
        )
        dropped = 0
        for record in changes:
            title = self.norm_key(record.get("title"))
            page = self.cache.pages.pop(title, None)
            if page:
                dropped += 1
                print(f'{self.host}: drop outdated: {dropped} - "{title}"')
        self.cache.updated = _now

    def save_cache(self):
        logger.debug(
            f"[{self.host}] save cache({len(self.cache.pages)} pages,"
            f" {len(self.cache.images)} images) to {self._fp}"
        )
        dump_json(self.cache, self._fp)

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

    @staticmethod
    def resolve_wikilink(s: str):
        links = mwparserfromhell.parse(s).filter_wikilinks()
        if links:
            return str(links[0].title)

    @staticmethod
    def norm_key(name: str):
        if not name:
            return name
        return name.strip().replace(" ", "_")
