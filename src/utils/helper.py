import datetime
import os
import platform
import re
import subprocess
import threading
import time
from decimal import Decimal
from enum import Enum
from operator import itemgetter
from pathlib import Path
from typing import Any, Callable, Generic, Iterable, Sequence, Type, TypeVar

import orjson
import pydantic_core
from app.schemas.common import Region
from lxml import etree
from pydantic import BaseModel, TypeAdapter
from pydantic.main import TupleGenerator

from .log import logger


Model = TypeVar("Model", bound=BaseModel)

_KT = TypeVar("_KT")
_KV = TypeVar("_KV")
_NUM_KV = TypeVar("_NUM_KV", int, float)


def parse_json_file_as(type: type[_KT], path: str | Path) -> _KT:
    return TypeAdapter(type).validate_json(Path(path).read_text())


def parse_json_obj_as(type: type[_KT], obj) -> _KT:
    return TypeAdapter(type).validate_python(obj)


def iter_model(
    model: BaseModel,
    # to_dict: bool = False,
    # by_alias: bool = False,
    include: set | None = None,
    exclude: set | None = None,
    # exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
) -> TupleGenerator:
    for key, value in model.__iter__():
        if value is None and exclude_none:
            continue
        field_info = model.model_fields.get(key)
        if (
            field_info
            and exclude_defaults
            and value == field_info.get_default(call_default_factory=True)
        ):
            continue
        if exclude and key in exclude:
            continue
        if include and key not in include:
            continue
        yield key, value


def isoformat(o: datetime.date | datetime.time) -> str:
    return o.isoformat()


ENCODERS_BY_TYPE: dict[Type[Any], Callable[[Any], Any]] = {
    bytes: lambda o: o.decode(),
    # Color: str,
    datetime.date: isoformat,
    datetime.datetime: isoformat,
    datetime.time: isoformat,
    datetime.timedelta: lambda td: td.total_seconds(),
    Decimal: float,
    Enum: lambda o: o.value,
    frozenset: list,
    # deque: list,
    # GeneratorType: list,
    # IPv4Address: str,
    # IPv4Interface: str,
    # IPv4Network: str,
    # IPv6Address: str,
    # IPv6Interface: str,
    # IPv6Network: str,
    # NameEmail: str,
    Path: str,
    # Pattern: lambda o: o.pattern,
    # SecretBytes: str,
    # SecretStr: str,
    set: list,
    # UUID: str,
    pydantic_core.Url: str,
}


def pydantic_encoder(obj):
    from dataclasses import asdict, is_dataclass

    from pydantic import BaseModel

    if isinstance(obj, BaseModel):
        return obj.model_dump()
    elif is_dataclass(obj):
        return asdict(obj)

    # Check the class type and its superclasses for a matching encoder
    for base in obj.__class__.__mro__[:-1]:
        try:
            encoder = ENCODERS_BY_TYPE[base]
        except KeyError:
            continue
        return encoder(obj)
    else:  # We have exited the for loop without finding a suitable encoder
        raise TypeError(
            f"Object of type '{obj.__class__.__name__}' is not JSON serializable"
        )


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


def sort_dict(d: dict[_KT, _KV]) -> dict[_KT, _KV]:
    return dict(sorted(d.items(), key=itemgetter(0)))


def load_json(fp: str | Path, default=None) -> Any:
    fp = Path(fp)
    if fp.exists():
        obj = orjson.loads(fp.read_bytes())
        return obj
    return default


def dump_json(
    obj,
    fp: str | Path | None = None,
    default: Callable[[Any], Any] | None = pydantic_encoder,
    indent2: bool = True,
    non_str_keys: bool = True,
    new_line: bool = True,
    option: int | None = None,
    sort_keys: bool | None = None,
) -> str:
    if option is None:
        option = 0
    if new_line:
        option = option | orjson.OPT_APPEND_NEWLINE
    if non_str_keys:
        option = option | orjson.OPT_NON_STR_KEYS
    if sort_keys:
        option = option | orjson.OPT_SORT_KEYS
    if indent2:
        option = option | orjson.OPT_INDENT_2
    _bytes = orjson.dumps(obj, default=default, option=option)
    text = _bytes.decode()
    if fp is not None:
        fp = Path(fp)
        if not fp.parent.exists():
            fp.parent.mkdir(parents=True)
        fp.write_bytes(_bytes)
    return text


def dump_json_beautify(
    obj,
    fp: str | Path,
    default: Callable[[Any], Any] | None = pydantic_encoder,
    option: int | None = None,
    sort_keys: bool | None = None,
) -> str | None:
    dump_json(
        obj,
        fp,
        default,
        indent2=False,
        non_str_keys=True,
        new_line=False,
        option=option,
        sort_keys=sort_keys,
    )
    beautify_file(fp)


def beautify_file(fp: str | Path):
    result = subprocess.run(["js-beautify", "-r", "-s=2", "-n", str(fp)])
    if result.returncode != 0:
        logger.error(
            f"beautify run failed, exit={result.returncode}\n"
            f"{result.stderr}\n{result.stdout}"
        )
    result.check_returncode()


def json_xpath(data: dict | list, path: str | Sequence, default=None):
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
    return [x.model_copy(deep=True) for x in items]


def parse_model_list(objs: list, base_cls: Type[Model]) -> list[Model]:
    return [parse_json_obj_as(base_cls, obj) for obj in objs]


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
                    logger.error(f"retry_times: {retry_times}, error: {e}")
                    retry_times -= 1
                    if retry_times <= 0:
                        raise
                    time.sleep(lapse)

        return wrapper

    return decorator


def count_time(func):
    """Count time wrapper"""

    def count_time_wrapper(*args, **kwargs):
        t0 = time.time()
        res = func(*args, **kwargs)
        dt = time.time() - t0
        func_name = re.findall(r"<(function .*) at 0x[0-9a-f]+>", str(func))
        func_name = func_name[0] if func_name else str(func)
        logger.info(f"========= Time: <{func_name}> run for {dt:.3f} secs =========")
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
        self._cached_values: dict[str, str | None] = {}
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


def parse_html_xpath(text: str, path: str):
    html = etree.HTML(text)  # type: ignore
    return html.xpath(path)


def describe_regions(regions: list[Region]) -> str:
    if not regions:
        return ""
    return "[" + ",".join([str(r) for r in regions]) + "] "


def mean(xs: Iterable[int | float]):
    return sum(xs) / len(list(xs))
