#%%
import os
import re
from pathlib import Path


if not os.getcwd().endswith("chaldea-parser"):
    raise KeyError(os.getcwd())

import orjson
from pydantic import BaseModel
from pydantic.json import pydantic_encoder

from src.utils import HttpApiUtil


_fp_cache = "tmp/explorer/cache"
_fp_data = "tmp/explorer/"

ExplorerCache = HttpApiUtil(
    api_server="https://explorer.atlasacademy.io",
    rate_calls=8,
    rate_period=1,
    db_path=_fp_cache,
    expire_after=3600 * 24 * 60,
)


class _Data(BaseModel):
    failed: list[str] = []
    success: list[str] = []
    files: list[str] = []
    token: str

    def sort(self):
        self.failed = sorted(set(self.failed))
        self.success = sorted(set(self.success))
        self.files = sorted(set(self.files))


def _iter_dir(data: _Data, path: str, recursive: int = 2):
    if not path.startswith("/"):
        path = "/" + path
    try:
        resp = ExplorerCache.call_api(
            path,
            headers={
                "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
                "authorization": data.token,
                "Referer": "https://explorer.atlasacademy.io/",
            },
        )
        if resp.status_code != 200:
            data.failed.append(path)
            print(f"{path}: {resp.status_code}")
            print(resp.text)
            return
        # data.success.add(path)
        # TODO: public folder not supported
        for m in re.findall(r'<a\s+href="([^"]+)"', resp.text):
            m = str(m)
            prefix = "https://static.atlasacademy.io/file"
            if m.startswith(prefix):
                m = m[len(prefix) :]
            if m.startswith(path) and m != path:
                if not m.endswith("/"):
                    data.files.append(m)
                if m.endswith("/") and recursive > 0:
                    # pool.submit(_iter_dir, m, recursive - 1)
                    _iter_dir(data, m, recursive - 1)

    except Exception as e:
        print(e)
        data.failed.append(path)


def main(root: str | None = None):
    root = root or "/aa-fgo-extract-jp/"
    folder = Path(_fp_data)
    fp_data = folder / "data.json"
    data = _Data.parse_file(fp_data)
    data.success.clear()
    data.files.clear()
    _iter_dir(data, root, 10)
    data.sort()
    Path(fp_data).write_bytes(orjson.dumps(data, pydantic_encoder, orjson.OPT_INDENT_2))

    files: dict = {}
    for f in sorted(data.files):
        if f.endswith("/"):
            continue
        segments = f.strip("/").split("/")
        d = files
        for s in segments[:-1]:
            d = d.setdefault(s, {})
        d.setdefault("_files_", []).append(segments[-1])
    Path(folder / "files.json").write_bytes(
        orjson.dumps(files, pydantic_encoder, orjson.OPT_INDENT_2)
    )
    print("done")


#%%
if __name__ == "__main__":
    main()
