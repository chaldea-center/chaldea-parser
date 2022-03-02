import os
import platform
import threading
import time
from operator import itemgetter
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Generic,
    Mapping,
    Optional,
    Sequence,
    Type,
    TypeVar,
    Union,
)

import orjson
import requests
from pydantic import BaseModel
from pydantic.json import pydantic_encoder
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util import Retry

from .log import logger


if TYPE_CHECKING:
    from _typeshed import StrOrBytesPath

Model = TypeVar("Model", bound=BaseModel)

_KT = TypeVar("_KT")
_NUM_KV = TypeVar("_NUM_KV", bound=Union[int, float])

req_session = requests.Session()
req_session.mount("https://", HTTPAdapter(max_retries=Retry(total=5)))


class NumDict(dict, Generic[_KT, _NUM_KV]):
    def add(self, other: dict[_KT, _NUM_KV]):
        for k, v in other.items():
            self.add_one(k, v)

    def add_one(self, key: _KT, value: _NUM_KV):
        self[key] = self.get(key, 0) + value

    def drop_negative(self):
        for k in list(self.keys()):
            if self[k] <= 0:
                self.pop(k)


def sort_dict(d: Mapping) -> dict:
    return dict(sorted(d.items(), key=itemgetter(0)))


def load_json(fp: "StrOrBytesPath", default=None) -> Optional[Any]:
    fp = Path(fp)
    if fp.exists():
        obj = orjson.loads(fp.read_bytes())
        return obj
    return default


def dump_json(
    obj,
    fp: "StrOrBytesPath" = None,
    default: Optional[Callable[[Any], Any]] = pydantic_encoder,
    indent2: bool = True,
    non_str_keys: bool = True,
    append_newline: bool = True,
    option: Optional[int] = None,
) -> Optional[str]:
    if option is None:
        option = 0
    if indent2:
        option = option | orjson.OPT_INDENT_2
    if non_str_keys:
        option = option | orjson.OPT_NON_STR_KEYS
    if append_newline:
        option = option | orjson.OPT_APPEND_NEWLINE
    _bytes = orjson.dumps(obj, default=default, option=option)
    if fp is not None:
        fp = Path(fp)
        if not fp.parent.exists():
            fp.parent.mkdir(parents=True)
        fp.write_bytes(_bytes)
    else:
        return _bytes.decode()


def json_xpath(data: Union[dict, list], path: Union[str, Sequence], default=None):
    if isinstance(path, str):
        path = path.split("/")
    assert path, f"Invalid key: {path}"
    try:
        for node in path:
            if isinstance(data, dict):
                data = data[node]
            elif isinstance(data, (list, tuple)):
                node = int(node)
                data = data[node]
        return data
    except KeyError:
        return default


def deepcopy_model_list(items: list[Model]) -> list[Model]:
    return [x.copy(deep=True) for x in items]


def parse_model_list(objs: list, base_cls: Type[Model]) -> list[Model]:
    return [base_cls.parse_obj(obj) for obj in objs]


FULL2HALF = dict((i + 0xFEE0, i) for i in range(0x20, 0x7F))


def full2half(s: str):
    """
    when place/placeJp as quest's indexKey, get rid of the effect of half chars
    only free quest related desired
    """
    if s:
        return s.translate(FULL2HALF)
    return s


def catch_exception(func):
    """Catch exception then print error and traceback to logger.

    Decorator can be applied to multi-threading but multiprocessing
    """

    def catch_exception_wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except:  # noqas
            s = f"=== Error in {threading.current_thread()}, {func} ===\n"
            if args:
                s += f"args={str(args):.200s}\n"
            if kwargs:
                s += f"kwargs={str(kwargs):.200s}\n"
            logger.exception(s)

    return catch_exception_wrapper


def retry_decorator(retry_times=5, lapse=3):
    def decorator(func):
        def wrapper(*args, **kwargs):
            nonlocal retry_times
            while retry_times > 0:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    print("retry_times", retry_times, e)
                    retry_times -= 1
                    time.sleep(lapse)

        return wrapper

    return decorator


@retry_decorator(retry_times=2)
def test():
    raise NotImplementedError("haha")


def count_time(func):
    """Count time wrapper"""

    def count_time_wrapper(*args, **kwargs):
        t0 = time.time()
        res = func(*args, **kwargs)
        dt = time.time() - t0
        logger.info(f"========= Time: {func} run for {dt:.3f} secs =========")
        return res

    return count_time_wrapper


def is_windows():
    return platform.system().lower() == "windows"


def is_macos():
    return platform.system().lower() == "darwin"


class LocalProxy:
    _HTTP_PROXY = "http_proxy"
    _HTTPS_PROXY = "https_proxy"
    _ALL_PROXY = "ALL_PROXY"

    keys = (_HTTP_PROXY, _HTTPS_PROXY, _ALL_PROXY)

    def __init__(self, enabled: bool = True):
        self._cached_values: dict[str, Optional[str]] = {}
        self._enabled: bool = enabled

    def _cache(self):
        for key in self.keys:
            self._cached_values[key] = os.environ.get(key)

    def _restore(self):
        for key in self.keys:
            value = self._cached_values.get(key)
            if value:
                os.environ[key] = value
            else:
                os.unsetenv(key)

    @staticmethod
    def _set(key: str, value):
        if value:
            os.environ[key] = value

    def __enter__(self):
        from ..config import settings

        self._cache()
        if self._enabled:
            self._set(self._HTTP_PROXY, settings.x_http_proxy)
            self._set(self._HTTPS_PROXY, settings.x_https_proxy)
            self._set(self._ALL_PROXY, settings.x_all_proxy)

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._restore()
