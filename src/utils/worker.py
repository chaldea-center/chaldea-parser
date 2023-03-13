from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from src.config import settings
from src.utils import logger


_executor = ThreadPoolExecutor()


class Worker:
    fake_mode = False

    def __init__(
        self,
        name: str | None = None,
        func: Callable | None = None,
        fake_mode: bool | None = None,
    ) -> None:
        self.name: str | None = name
        self.func: Callable | None = func
        self._tasks: list[Future] = []
        self.fake_mode: bool = Worker.fake_mode if fake_mode is None else fake_mode

    def add(self, fn, *args, **kwargs):
        if self.fake_mode:
            fn(*args, **kwargs)
        else:
            self._tasks.append(_executor.submit(fn, *args, **kwargs))

    def add_default(self, *args, **kwargs):
        assert self.func is not None
        self.add(self.func, *args, **kwargs)

    def wait(self, show_progress=True):
        name = f"({self.name})" if self.name else ""
        finished = 0
        steps = [i for i in (2, 5, 10, 20, 50, 100) if i <= len(self._tasks) // 5]
        step = steps[-1] if steps else 1
        errors = []
        for f in as_completed(self._tasks):
            error = f.exception()
            if error:
                logger.error(error)
                errors.append(error)
            finished += 1
            if show_progress:
                if finished % step == 0:
                    logger.debug(f"Worker{name}: {finished}/{len(self._tasks)}   ")
                elif settings.is_debug:
                    print(f"\rWorker{name}: {finished}/{len(self._tasks)}   ", end="")
        msg = f"Worker{name} finished: {finished}/{len(self._tasks)}.  "
        if errors:
            msg += f"{len(errors)}/{len(self._tasks)} errors!"
            logger.error(msg)
            raise RuntimeError(msg)
        else:
            logger.info(msg)

    # @staticmethod
    # def map(fn, *iterables):
    #     return _executor.map(fn, *iterables)

    def map_add(self, fn, *iterables):
        for args in zip(*iterables):
            self.add(fn, *args)

    @staticmethod
    def from_map(fn, *iterables, name: str | None = None) -> "Worker":
        worker = Worker(name)
        worker.map_add(fn, *iterables)
        return worker

    @staticmethod
    def fake(fn, *iterables):
        for args in zip(*iterables):
            fn(*args)
        return Worker()
