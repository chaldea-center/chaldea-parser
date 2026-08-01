import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import TypedDict

from git import Repo

from ..utils.log import logger


SVT_FILE = "master/mstSvt.json"
VALID_SVT_TYPES = {1, 2, 6, 9}
JST = timezone(timedelta(hours=9))

MOST_OLD_TIMESTAMP = 1576299577


@dataclass
class SvtRelease:
    id: int
    collectionNo: int
    name: str
    type: int
    releaseTime: str | None
    timestamp: int
    commit: str


class MstSvt(TypedDict):
    id: int
    name: str
    type: int
    collectionNo: int


def get_commits_for_file(repo: Repo) -> list:
    return list(repo.iter_commits(paths=SVT_FILE, reverse=True))


def get_file_at_commit(repo: Repo, commit) -> list[MstSvt]:
    try:
        blob = commit.tree / SVT_FILE
    except KeyError:
        return []
    return json.loads(blob.data_stream.read().decode("utf-8"))


def filter_svts(svts: list[MstSvt]) -> dict[int, MstSvt]:
    return {
        s["id"]: s
        for s in svts
        if s["collectionNo"] > 0 and s["type"] in VALID_SVT_TYPES
    }


def sort_key(svt: SvtRelease):
    return (0 if svt.type != 6 else 1, svt.collectionNo)


def main(repo_path: Path, output_path: Path, ignore_first_commit: bool = False):
    repo = Repo(str(repo_path))
    commits = get_commits_for_file(repo)
    if len(commits) < 100 and not ignore_first_commit:
        raise Exception(
            f"Only {len(commits)} commits in repo, you should ignore_first_commit"
        )
    logger.info(f"Total commits touching {SVT_FILE}: {len(commits)}")

    prev_ids: set[int] = set()
    release_times: dict[int, SvtRelease] = {}
    if output_path.exists():
        _old_releases: list[dict] = json.loads(output_path.read_text())
        release_times = {v["id"]: SvtRelease(**v) for v in _old_releases}

    for i, commit in enumerate(commits):
        svts = get_file_at_commit(repo, commit)
        current = filter_svts(svts)
        current_ids = set(current.keys())

        new_ids = current_ids - prev_ids
        if new_ids:
            timestamp = commit.committed_date
            date_jst = datetime.fromtimestamp(timestamp, tz=JST)
            time_str = date_jst.strftime("%Y-%m-%d %H:%M")

            is_first = i == 0
            if is_first and ignore_first_commit:
                logger.info(
                    f"[{i + 1}/{len(commits)}] {commit.hexsha[:8]} {time_str}: "
                    f"{len(new_ids)} servant(s) skipped (first commit)"
                )
            else:
                for svt_id in new_ids:
                    svt = current[svt_id]
                    release_times[svt_id] = SvtRelease(
                        id=svt_id,
                        collectionNo=svt["collectionNo"],
                        name=svt["name"],
                        type=svt["type"],
                        releaseTime=time_str,
                        timestamp=timestamp,
                        commit=commit.hexsha[:8],
                    )
                logger.info(
                    f"[{i + 1}/{len(commits)}] {commit.hexsha[:8]} {time_str}: "
                    f"{len(new_ids)} new servant(s) - {list(new_ids)}"
                )

        prev_ids = current_ids

    results = sorted(release_times.values(), key=sort_key)
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps([asdict(r) for r in results], indent=2, ensure_ascii=False)
        )
    logger.info(f"\nTotal servants recorded: {len(results)}")
    logger.info(f"Output saved to: {output_path}")
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ignore-first-commit", action="store_true", default=False)
    args = parser.parse_args()
    main(args.repo, args.output, args.ignore_first_commit)
