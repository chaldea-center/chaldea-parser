import abc
import asyncio
import functools
import time
from contextlib import contextmanager
from datetime import timedelta
from typing import Generator, Type

import requests
import requests_cache
from app.schemas.common import Region
from app.schemas.nice import NiceQuestPhase
from pydantic import ValidationError
from ratelimit import limits, sleep_and_retry
from requests import Response
from requests_cache import CachedSession
from requests_cache.backends.sqlite import SQLiteCache
from requests_cache.cache_control import ExpirationTime
from requests_cache.models.response import CachedResponse


__all__ = ["HttpApiUtil"]

from requests_cache.session import FILTER_FN

from .helper import Model
from .log import logger


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

        @sleep_and_retry
        @limits(calls=rate_calls, period=rate_period)
        def _call_api(url, retry_n=5, **kwargs):
            origin_kwargs = dict(kwargs)
            t0 = time.time()
            cache_session: CachedSession = CachedSession(
                backend=self.cache_storage,
                expire_after=kwargs.pop("expire_after", expire_after),
            )
            r = cache_session.get(url, **kwargs)
            if r.status_code == 429:
                logger.warning(r.text)
                retry_after = float(r.headers.get("Retry-After") or "5")
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
        key = self.cache_storage.create_key(url=url, method="GET")
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
            resp.created_at
            try:
                should_delete = (
                    filter_fn if isinstance(filter_fn, bool) else filter_fn(resp)
                )
            except Exception as e:
                logger.error(f"error in filter_fn: {e}")
                should_delete = True
        if should_delete:
            logger.debug(f"delete matched url:{url}")
            self.cache_storage.delete_url(url)
            resp = None
        if resp is None:
            resp = self._limit_api_func(url, expire_after=expire_after, **kwargs)

        return resp

    def api_json(
        self,
        url,
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ) -> dict:
        url = self.full_url(url)
        response = self.call_api(url, expire_after, filter_fn, **kwargs)
        return response.json()

    def api_model(
        self,
        url,
        model: Type[Model],
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ) -> Model | None:
        url = self.full_url(url)
        response = self.call_api(url, expire_after, filter_fn, **kwargs)

        def _parse_model(_response: Response, retry=False):
            if _response.status_code == 200:
                try:
                    return model.parse_raw(_response.content)
                except ValidationError as e:
                    print(e)
                    if not retry:
                        raise
                    print("validation error, delete and retry:", url)
                    self.cache_storage.delete_url(url)
                    # todo: not called
                    return _parse_model(self._limit_api_func(url, **kwargs), False)
            elif _response.status_code == 404:
                return None
            else:
                logger.error(
                    "parsing api model failed",
                    (_response.status_code, _response.content),
                )
                # raise (_response.status_code, _response.content)
                return None

        return _parse_model(response, True)

    def quest_phase(
        self,
        quest_id: int,
        phase: int,
        region=Region.JP,
        expire_after: ExpirationTime = None,
        filter_fn: FILTER_FN2 = None,
        **kwargs,
    ):
        return self.api_model(
            f"/nice/{region}/quest/{quest_id}/{phase}",
            NiceQuestPhase,
            expire_after,
            filter_fn,
            **kwargs,
        )

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
    )
