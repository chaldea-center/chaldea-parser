import time

import requests
from app.schemas.common import Region


def get_time():
    return int(time.time())


class DownUrl:
    @classmethod
    def download(cls, url: str):
        return requests.get(url).json()

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
        return requests.get(url, headers={"cache-control": "no-cache"}).json()
