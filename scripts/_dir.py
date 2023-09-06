from pathlib import Path


try:
    PARSER_OOT = Path(__file__).resolve().parents[1]
except:
    PARSER_OOT = Path(".").absolute()
PROJECT_ROOT = PARSER_OOT.parent.resolve()
print("Parser  root:", PARSER_OOT)
print("Project root:", PROJECT_ROOT)

MAPPINGS_DIR = PROJECT_ROOT / "chaldea-parser/data/mappings"
WIKI_DIR = PROJECT_ROOT / "chaldea-parser/data/wiki"
STATIC_DIR = PROJECT_ROOT / "chaldea-parser/data/static"
