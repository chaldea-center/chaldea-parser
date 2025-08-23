import abc
import asyncio
import functools
import re
import time
from contextlib import contextmanager
from datetime import timedelta
from typing import Generator, Type, TypeVar

import orjson
import requests
import requests_cache
from app.schemas.common import Region
from app.schemas.nice import NiceMasterMission, NiceQuestPhase
from pydantic import ValidationError
from ratelimit import limits, sleep_and_retry
from requests import Response
from requests_cache import CachedSession
from requests_cache.backends.sqlite import SQLiteCache
from requests_cache.cache_control import ExpirationTime
from requests_cache.models.response import CachedResponse

from .helper import parse_json_obj_as


__all__ = ["HttpApiUtil"]

from requests_cache.session import FILTER_FN

from .helper import Model
from .log import logger


_T = TypeVar("_T")

FILTER_FN2 = FILTER_FN | bool | None


@contextmanager
def http_cache_enabled(**kwargs) -> Generator[CachedSession, None, None]:
    session = CachedSession(
        backend=kwargs.pop(
            "backend", SQLiteCache(db_path=".cache/http_cache/http_cache")
        ),
        expire_after=kwargs.pop("expire_after", timedelta(days=1)),
        urls_expire_after=kwargs.pop(
            "urls_expire_after",
            {
                "*/quest/*": timedelta(days=7),
            },
        ),
        # allowable_codes: Iterable[int] = (200,),
        # allowable_methods: Iterable['str'] = ('GET', 'HEAD'),
        # filter_fn: Callable = None,
        # stale_if_error: bool = False,
        # session_factory: Type[OriginalSession] = CachedSession,
        **kwargs,
    )
    try:
        yield session
    finally:
        requests_cache.uninstall_cache()


class HttpApiUtil(abc.ABC):
    def __init__(
        self,
        api_server: str,
        rate_calls: int = 90,
        rate_period: int = 1,
        db_path: str = "http_cache",
        expire_after=2592000,
    ):
        self.api_server = api_server
        self.cache_storage: SQLiteCache = SQLiteCache(db_path=db_path)

        retry_at = 0

        @sleep_and_retry
        @limits(calls=rate_calls, period=rate_period)
        def _call_api(url, retry_n=5, **kwargs):
            nonlocal retry_at
            origin_kwargs = dict(kwargs)
            t0 = time.time()
            if t0 < retry_at:
                time.sleep(retry_at - t0)
                t0 = time.time()

            cache_session: CachedSession = CachedSession(
                backend=self.cache_storage,
                expire_after=kwargs.pop("expire_after", expire_after),
            )  # pyright: ignore[reportArgumentType]
            r = cache_session.get(url, **kwargs)
            if r.status_code == 429:
                logger.warning(r.text)
                try:
                    header = r.headers.get("Retry-After")
                    match = re.match(r"wait (\d+) second", r.text)
                    if header:
                        retry_after = float(header) + 1
                    elif match:
                        retry_after = float(match.group(1)) + 1
                    else:
                        retry_after = 6
                except:
                    retry_after = 6
                retry_at = max(retry_at, time.time() + retry_after)
                logger.debug(f"retry after {int(retry_after)} seconds")
                time.sleep(retry_after)
                return _call_api(url, retry_n - 1, **origin_kwargs)
            logger.debug(f"GOT url: {time.time() - t0:.3f}s: {url}")
            return r

        self._limit_api_func = _call_api

    def call_api(
        self,
        url,
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ) -> Response | CachedResponse:
        """
        :param url: only path or full url
        :param filter_fn: if return True, it should ignore cache and fetch again
        :param kwargs:
        :return:
        """
        url = self.full_url(url)
        key = self.cache_storage.create_key(
            url=url, method="GET"
        )  # pyright: ignore[reportArgumentType]
        resp = self.cache_storage.get_response(key)
        should_delete = False
        if resp and resp.is_expired:
            should_delete = True

        if (
            not should_delete
            and resp
            and isinstance(expire_after, int)
            and expire_after >= 0
        ):
            if time.time() > resp.created_at.timestamp() + expire_after:
                should_delete = True
        if not should_delete and resp and filter_fn is not None:
            try:
                should_delete = (
                    filter_fn if isinstance(filter_fn, bool) else filter_fn(resp)
                )
            except Exception as e:
                logger.error(f"error in filter_fn: {e}")
                should_delete = True
        if should_delete and self.cache_storage.has_url(url):
            logger.debug(f"delete matched url:{url}")
            self.cache_storage.delete_url(url)
            resp = None
        if resp is None:
            resp = self._limit_api_func(url, **kwargs)

        return resp  # type: ignore

    def api_json(
        self,
        url,
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ):
        url = self.full_url(url)
        response = self.call_api(url, expire_after, filter_fn, **kwargs)
        return response.json()

    def api_model(
        self,
        url,
        model: Type[_T],
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ) -> _T | None:
        url = self.full_url(url)
        response = self.call_api(url, expire_after, filter_fn, **kwargs)

        def _parse_model(_response: Response, retry=False):
            if _response.status_code == 200:
                try:
                    return parse_json_obj_as(model, orjson.loads(_response.content))
                except ValidationError as e:
                    print(e)
                    if not retry:
                        raise
                    print("validation error, delete and retry:", url)
                    self.cache_storage.delete_url(url)
                    # todo: not called
                    return _parse_model(self._limit_api_func(url, **kwargs), False)  # type: ignore
            elif _response.status_code == 404:
                return None
            else:
                logger.error(
                    f"parsing api model failed: {(_response.status_code, _response.content)}"
                )
                # raise (_response.status_code, _response.content)
                return None

        return _parse_model(response, True)

    @sleep_and_retry
    @limits(calls=60, period=150)
    def quest_phase(
        self,
        quest_id: int,
        phase: int,
        enemyHash: str | None = None,
        region=Region.JP,
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ):
        url = f"/nice/{region}/quest/{quest_id}/{phase}"
        if enemyHash:
            url += f"?hash={enemyHash}"
        return self.api_model(
            url,
            NiceQuestPhase,
            expire_after,
            filter_fn,
            **kwargs,
        )

    def master_mission(
        self,
        mm_id: int,
        region=Region.JP,
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ):
        url = f"/nice/{region}/mm/{mm_id}"
        return self.api_model(url, NiceMasterMission, expire_after, filter_fn, **kwargs)

    def full_url(self, _path: str):
        if _path.startswith(self.api_server):
            return _path
        from urllib.parse import urljoin

        return urljoin(self.api_server, _path)

    def remove(self, filter_fn: FILTER_FN):
        keys = []
        for key in self.cache_storage.responses.keys():
            resp = self.cache_storage.get_response(key)
            if resp and filter_fn(resp):
                keys.append(key)
        print(f"removing {len(keys)} keys")
        self.cache_storage.bulk_delete(keys)


# FandomApi
async def to_async(
    func,
    *args,
    **kwargs,
) -> requests.Response:
    return await asyncio.get_event_loop().run_in_executor(
        None,
        functools.partial(
            func,
            *args,
            **kwargs,
        ),
    )  # type: ignore
