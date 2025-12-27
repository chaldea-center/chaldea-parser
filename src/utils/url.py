import time
from pathlib import Path

import requests
from app.schemas.common import Region

from .helper import load_json, retry_decorator


def get_time():
    return int(time.time())


class DownUrl:
    @classmethod
    @retry_decorator(3, 5)
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
    def mst_data(
        cls,
        name: str,
        region: Region = Region.JP,
        folder: str = "master/",
    ):
        name = cls._json_fn(name)
        url = f"https://api.atlasacademy.io/repo/{region}/{folder}{name}?t={get_time()}"
        return cls.download(url)

    @classmethod
    def git_jp(cls, name: str, folder: str = "master/"):
        from ..config import settings

        fp = Path(settings.game_data_jp_dir) / folder / cls._json_fn(name)
        return load_json(fp)
