from .domus_aurea import run_drop_rate_update
from .main_parser import MainParser
from .update_mapping import run_mapping_update
from .wiki_parser import WikiParser


def run_main_parser():
    MainParser().start()


def run_wiki_parser():
    WikiParser().start()
