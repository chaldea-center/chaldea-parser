import time

import requests
from app.schemas.common import Region

from .helper import retry_decorator


def get_time():
    return int(time.time())


class DownUrl:
    @retry_decorator(3, 5)
    @classmethod
    def download(cls, url: str):
        resp = requests.get(url, headers={"cache-control": "no-cache"})
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _json_fn(name: str) -> str:
        if not name.endswith(".json") and "." not in name:
            return name + ".json"
        return name

    @classmethod
    def export(cls, name: str, region: Region = Region.JP):
        name = cls._json_fn(name)
        return cls.download(
            f"https://api.atlasacademy.io/export/{region}/{name}?t={get_time()}"
        )

    @classmethod
    def gitaa(
        cls,
        name: str,
        region: Region = Region.JP,
        folder: str = "master/",
    ):
        name = cls._json_fn(name)
        url = f"https://git.atlasacademy.io/atlasacademy/fgo-game-data/raw/branch/{region}/{folder}{name}?t={get_time()}"
        return cls.download(url)
