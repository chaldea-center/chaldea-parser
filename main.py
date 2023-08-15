# %%
import argparse
import subprocess
import warnings
from pathlib import Path

from src.config import PayloadSetting, settings
from src.parsers import MainParser, WikiParser, run_drop_rate_update, run_mapping_update
from src.wiki import FANDOM, MOONCELL  # noqa


warnings.filterwarnings("ignore", category=DeprecationWarning)


def should_run_wiki_parser(payload: PayloadSetting):
    print("Payload:", payload.json(exclude_unset=True, indent=2), flush=True)
    output_dir = Path(settings.output_dir).resolve()
    authors = subprocess.check_output(
        "git log -2 --pretty=format:'%an'",
        shell=True,
        text=True,
        cwd=output_dir,
    ).splitlines()
    changed_files = subprocess.check_output(
        "git diff-tree --no-commit-id --name-only HEAD -r",
        shell=True,
        text=True,
        cwd=output_dir,
    )
    print("Last Authors:", authors, flush=True)
    print("Commit Files:", changed_files, flush=True)
    assert authors and changed_files, "No info in authors or changed_files"
    if payload.run_wiki_parser is not None:
        print(f"Forced run_wiki_parser={payload.run_wiki_parser}", flush=True)
        return payload.run_wiki_parser

    if "github-actions[bot]" in authors[0]:
        print("bot changes, skip wiki parser", flush=True)
        return False
    if len(authors) > 1 and "github-actions[bot]" not in authors[1]:
        print("More than 1 user commit, run wiki parser", flush=True)
        return True

    for filename in changed_files.splitlines():
        if filename and not filename.startswith("mappings/"):
            print("Detected changes outside mappings/ folder", flush=True)
            return True
    print("Only mapping file changed, skip wiki parser", flush=True)
    return False


# %%
if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "task", nargs="?", choices=("atlas", "wiki", "trywiki", "mapping", "domus")
    )
    task = arg_parser.parse_known_intermixed_args()[0].task

    payload = PayloadSetting()

    if task == "atlas":
        if payload.run_atlas_parser == False:
            print("skip atlas parser")
        else:
            main_parser = MainParser()
            main_parser.start()
    elif task == "wiki":
        wiki_parser = WikiParser()
        wiki_parser.start()
        # run_wiki_parser()
    elif task == "trywiki":
        if should_run_wiki_parser(payload):
            wiki_parser = WikiParser()
            wiki_parser.start()
        else:
            print("skip wiki parser")
    elif task == "mapping":
        run_mapping_update()
    elif task == "domus":
        run_drop_rate_update()
    else:
        arg_parser.print_help()
