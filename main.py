# %%
import argparse
import warnings

from src.parsers import MainParser, WikiParser, run_drop_rate_update, run_mapping_update
from src.wiki import MOONCELL, FANDOM  # noqa

warnings.filterwarnings("ignore", category=DeprecationWarning)

# %%
if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "task", nargs="?", choices=("atlas", "wiki", "mapping", "domus")
    )
    task = arg_parser.parse_known_intermixed_args()[0].task

    if task == "atlas":
        main_parser = MainParser()
        main_parser.start()
        # run_main_parser()
    elif task == "wiki":
        wiki_parser = WikiParser()
        wiki_parser.start()
        # run_wiki_parser()
    elif task == "mapping":
        run_mapping_update()
    elif task == "domus":
        run_drop_rate_update()
    else:
        arg_parser.print_help()
