from pathlib import Path

from ..config import settings
from .helper import NumDict, count_time, dump_json, load_json, sort_dict
from .http_cache import HttpApiUtil
from .log import logger
from .worker import Worker


NEVER_CLOSED_TIMESTAMP = 1800000000  # 1893423600


AtlasApi = HttpApiUtil(
    api_server="https://api.atlasacademy.io",
    rate_calls=5,
    rate_period=1,
    db_path=str(Path(settings.cache_http_cache / "atlas")),
    expire_after=-1,
)

McApi = HttpApiUtil(
    api_server="https://fgo.wiki/api.php",
    rate_calls=3,
    rate_period=1,
    db_path=str(Path(settings.cache_http_cache / "mooncell")),
    expire_after=-1,
)
