# %%
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, wait
from datetime import datetime
from pathlib import Path


if not os.getcwd().endswith("chaldea-parser"):
    raise KeyError(os.getcwd())

import orjson
from pydantic import BaseModel

from src.utils import HttpApiUtil
from src.utils.helper import parse_json_file_as, pydantic_encoder


pool = ThreadPoolExecutor()
asxsa = {
    "/Audio/": 2,
    "/Back/": 2,
    "/Bg/": 2,
    # "/CharaFigure/": 2,
    # "/CharaGraph/": 2,
    # "/Image/": 2,
    "/Servants/": 2,
    "/Tutorial/": 2,
}

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


page_count = 0


def _iter_dir(data: _Data, path: str, recursive: int = 2, depth=1):
    if not path.startswith("/"):
        path = "/" + path
    global page_count
    page_count += 1
    print(f"\r{page_count}: {path}", end="", flush=True)
    sys.stdout.write("\033[K")
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
        need_iter = True
        for x, y in asxsa.items():
            if path.endswith(x) and y == depth:
                need_iter = False
                break

        futures = []
        for m in re.findall(r'<a\s+href="([^"]+)"', resp.text):
            m = str(m)
            prefix = "https://static.atlasacademy.io/file"
            if m.startswith(prefix):
                m = m[len(prefix) :]
            if m.startswith(path) and m != path:
                if not m.endswith("/"):
                    data.files.append(m)
                if m.endswith("/") and recursive > 0 and need_iter:
                    # pool.submit(_iter_dir, m, recursive - 1)
                    # _iter_dir(data, m, recursive - 1,depth+1)
                    futures.append(
                        pool.submit(_iter_dir, data, m, recursive - 1, depth + 1)
                    )
        # wait(futures)

    except Exception as e:
        print(type(e), e)
        data.failed.append(path)


def save(data: _Data):
    if data is None:
        return
    Path(Path(_fp_data) / "tmp.json").write_bytes(
        orjson.dumps(data, pydantic_encoder, orjson.OPT_INDENT_2)
    )


def main(root: str | None = None):
    global data, page_count
    root = root or "/aa-fgo-extract-jp/"
    folder = Path(_fp_data)
    t = datetime.now()
    date = f"{t.month:0>2}-{t.day:0>2}-{t.hour:0>2}-{t.minute:0>2}"
    fp_data = folder / f"data.json"
    data = parse_json_file_as(_Data, fp_data)
    data.success.clear()
    data.files.clear()
    _iter_dir(data, root, 10, 1)
    pool._work_queue
    while True:
        a = page_count
        # ??? use async instead
        time.sleep(0.5)
        time.sleep(0.5)
        time.sleep(0.5)
        time.sleep(0.5)
        time.sleep(0.5)
        if a != page_count:
            save(data)
        else:
            break
    data.sort()
    Path(fp_data).write_bytes(orjson.dumps(data, pydantic_encoder, orjson.OPT_INDENT_2))
    Path(folder / f"data-{date}.json").write_bytes(
        orjson.dumps(data, pydantic_encoder, orjson.OPT_INDENT_2)
    )

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
    Path(folder / f"files-{date}.json").write_bytes(
        orjson.dumps(files, pydantic_encoder, orjson.OPT_INDENT_2)
    )
    print("done")


# %%
if __name__ == "__main__":
    main()

# %%
