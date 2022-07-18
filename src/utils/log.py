import logging
from pathlib import Path

from ..config import settings


logger = logging.getLogger("chaldea-parser")
_formatter = logging.Formatter(
    fmt="{asctime} [{filename}:{lineno:>3d}] {levelname:<5s}: {message}",
    datefmt="%H:%M:%S",
    style="{",
)
logger.handlers.clear()
console_handler = logging.StreamHandler()
console_handler.setFormatter(_formatter)
console_handler.setLevel(logging.DEBUG)
file_handler = logging.FileHandler(filename=Path(settings.log_dir) / "parser.log")
file_handler.setFormatter(_formatter)
file_handler.setLevel(logging.INFO)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)
