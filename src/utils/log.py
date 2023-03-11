import logging
import sys
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
file_handler.setLevel(logging.DEBUG)
logger.addHandler(console_handler)
logger.addHandler(file_handler)
logger.setLevel(logging.DEBUG)


def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))


sys.excepthook = handle_exception
