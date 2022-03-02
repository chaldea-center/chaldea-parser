import logging
from pathlib import Path

from uvicorn.logging import ColourizedFormatter

from ..config import settings


class _LogFormatter(ColourizedFormatter):
    def should_use_colors(self) -> bool:
        # return sys.stderr.isatty() or hasattr(sys, "ps1")
        return True


logger = logging.getLogger("chaldea-parser")
_formatter = _LogFormatter(
    fmt="{asctime} {filename} [line:{lineno:>3d}] {levelname:<5s}: {message}",
    datefmt="%m-%d %H:%M:%S",
    style="{",
    use_colors=True,
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
