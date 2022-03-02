from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from src.utils import logger


_executor = ThreadPoolExecutor()


class Worker:
    def __init__(self, name: str = None, func: Callable = None) -> None:
        self.name = name
        self.func = func
        self._tasks = []

    def add(self, fn, *args, **kwargs):
        self._tasks.append(_executor.submit(fn, *args, **kwargs))

    def add_default(self, *args, **kwargs):
        assert self.func is not None
        self.add(self.func, *args, **kwargs)

    def wait(self, show_progress=True):
        finished = 0
        for f in as_completed(self._tasks):
            error = f.exception()
            if error:
                logger.exception(error)
                raise error
            finished += 1
            if show_progress:
                name = f"({self.name})" if self.name else ""
                print(f"\rWorker{name}: {finished}/{len(self._tasks)}   ", end="")
        print("")

    @staticmethod
    def map(fn, *iterables):
        return _executor.map(fn, *iterables)

    def map_add(self, fn, *iterables):
        for args in zip(*iterables):
            self._tasks.append(_executor.submit(fn, *args))

    @staticmethod
    def from_map(fn, *iterables) -> "Worker":
        worker = Worker()
        worker.map_add(fn, *iterables)
        return worker

    @staticmethod
    def fake(fn, *iterables):
        for args in zip(*iterables):
            fn(*args)
