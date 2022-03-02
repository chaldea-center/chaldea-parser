import contextlib
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import unquote

import mwclient
import mwparserfromhell
import pytz
import pywikibot
from pydantic import NoneStr
from ratelimit import limits, sleep_and_retry

from ..schemas.wiki_cache import WikiCache, WikiPageInfo
from ..utils import dump_json, logger
from ..utils.helper import retry_decorator


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
                self.cache = WikiCache.parse_file(self._fp)
                self.cache.host = self.host
                print(f"wiki {self.host}: loaded {len(self.cache.pages)} cached")
            finally:
                ...

    @sleep_and_retry
    @limits(5, 1)
    def _call_request(self, name: str):
        retry_n, retry = 0, 10
        while retry_n < retry:
            try:
                page = pywikibot.Page(self.site2, name)
                text = page.text
                if not text:
                    print(f'{self.site.host}: "{name}" empty')
                    return text
                redirect = page
                while redirect.isRedirectPage():
                    redirect = redirect.getRedirectTarget()
                now = int(time.time())
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
                    self.cache.pages[self.norm_key(redirect.title())] = WikiPageInfo(
                        name=redirect.title(), text=redirect.text, updated=now
                    )
                if retry_n > 0:
                    logger.warning(f'downloaded "{name}" after {retry_n} retry')
                else:
                    print(f"download wikitext: {name}")
                self._count += 1
                if self._count > 100:
                    self._count = 0
                    self.save_cache()
                return redirect.text
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
        if not result:
            result = self._call_request(name)
        result = result or ""
        if clear_tag:
            result = self.remove_html_tags(result)
        # print(f'{key}: {len(result)}')
        return result

    def get_file_url(self, name: str):
        name = self.norm_key(name)
        if not name:
            return None
        cached = self.cache.images.get(name)
        if cached and cached.get("url"):
            return unquote(cached["url"])
        image = self.site.images[name]
        if not image.imageinfo:
            return None
        self.cache.images[name] = image.imageinfo
        url = image.imageinfo["url"]
        if url:
            url = unquote(url)
        return url

    def get_cache(self, name: str) -> NoneStr:
        name = self.norm_key(name)
        page = self.cache.pages.get(name)
        if not page:
            return
        if page.redirect:
            page = self.cache.pages.get(page.redirect)
            if page:
                return page.text
            else:
                self.cache.pages.pop(name)
        else:
            return page.text

    @staticmethod
    def get_timestamp(s: str, tz: str = "Asia/Shanghai") -> Optional[int]:
        if s:
            m = re.match(r"^(\d+)-(\d+)-(\d+)\s+(\d+):(\d+)", s)
            seq = [int(x) for x in m.groups()]
            t = datetime(*seq)
            t.replace(tzinfo=pytz.timezone(tz))
            return int(t.timestamp())
        return None

    @retry_decorator()
    def recent_changes(
        self,
        start=None,
        end=None,
        dir="older",
        namespace=None,
        prop=None,
        show=None,
        limit=None,
        type=None,
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

    def remove_recent_changed(self, days: float = None):
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
        for index, record in enumerate(changes):
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
