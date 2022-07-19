import dataclasses
import time
from datetime import datetime
from ntpath import join


@dataclasses.dataclass
class _StopwatchRecord:
    time: datetime
    action: str
    lapse: float


def _get_time():
    return datetime.now()


class Stopwatch:
    def __init__(self, name: str | None = None) -> None:
        self.name = name
        self.start_time: datetime = _get_time()
        self.records: list[_StopwatchRecord] = []

    def start(self):
        self.start_time = _get_time()
        self.records.clear()

    def log(self, action: str):
        t = _get_time()
        if self.records:
            lapse = t.timestamp() - self.records[-1].time.timestamp()
        else:
            lapse = 0
        self.records.append(_StopwatchRecord(t, action, lapse))

    def output(self):
        output = [f"=== Stopwatch({self.name}) records ==="]
        width = max([len(r.action) for r in self.records])
        for record in self.records:
            output.append(
                "  ".join(
                    [
                        record.action.ljust(width),
                        record.time.strftime("%H:%M:%S"),
                        f"{record.lapse:5.2f}s",
                    ]
                )
            )
        return "\n".join(output)
