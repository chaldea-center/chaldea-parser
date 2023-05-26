# %%
import argparse
import subprocess
import warnings
from pathlib import Path

from src.config import PayloadSetting, settings
from src.parsers import MainParser, WikiParser, run_drop_rate_update, run_mapping_update
from src.wiki import FANDOM, MOONCELL  # noqa


warnings.filterwarnings("ignore", category=DeprecationWarning)

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
        summary = subprocess.check_output(
            "git log -1 --pretty=format:'%an'",
            shell=True,
            text=True,
            cwd=Path(settings.output_dir).resolve(),
        )
        print("Last Author:", summary, flush=True)
        print("Payload:", payload.json(exclude_unset=True, indent=2), flush=True)
        if payload.run_wiki_parser is not None:
            should_run = payload.run_wiki_parser
        else:
            should_run = "github-actions[bot]" not in summary
        if should_run:
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
