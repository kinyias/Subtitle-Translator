"""Thread-safe application logger with a GUI-friendly pub/sub bridge.

The backend services and workers emit log records through :class:`AppLogger`.
The GUI subscribes to receive records on the main thread (via a queue drained
by Tkinter's ``after`` loop), so worker threads never touch widgets directly.
"""
from __future__ import annotations

import datetime as _dt
import logging
import queue
import threading
import traceback
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, List


class LogLevel(str, Enum):
    """Log severities, including a UI-only ``SUCCESS`` level."""

    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    SUCCESS = "SUCCESS"


@dataclass(frozen=True)
class LogRecord:
    """A single immutable log entry."""

    level: LogLevel
    message: str
    timestamp: _dt.datetime = field(default_factory=lambda: _dt.datetime.now())

    def formatted(self) -> str:
        return f"[{self.timestamp:%H:%M:%S}] [{self.level.value}] {self.message}"


Subscriber = Callable[[LogRecord], None]


class AppLogger:
    """Central logger that fans records out to registered subscribers.

    Subscribers are invoked on the same thread that calls :meth:`log`. GUI
    subscribers must therefore hand records to a thread-safe queue rather than
    updating widgets inline; see :class:`gui.widgets.log_console.LogConsole`.
    """

    def __init__(self) -> None:
        self._subscribers: List[Subscriber] = []
        self._history: List[LogRecord] = []
        self._lock = threading.RLock()
        self._std = logging.getLogger("capcut_tts")

    def subscribe(self, callback: Subscriber, replay: bool = True) -> None:
        """Register *callback*; optionally replay buffered history to it."""
        with self._lock:
            self._subscribers.append(callback)
            history = list(self._history) if replay else []
        for record in history:
            callback(record)

    def unsubscribe(self, callback: Subscriber) -> None:
        with self._lock:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

    def log(self, level: LogLevel, message: str) -> None:
        record = LogRecord(level=level, message=str(message))
        with self._lock:
            self._history.append(record)
            subscribers = list(self._subscribers)
        self._std.log(logging.INFO, record.formatted())
        for callback in subscribers:
            try:
                callback(record)
            except Exception:  # pragma: no cover - a broken UI sink must not kill logging
                pass

    def info(self, message: str) -> None:
        self.log(LogLevel.INFO, message)

    def warning(self, message: str) -> None:
        self.log(LogLevel.WARNING, message)

    def error(self, message: str) -> None:
        self.log(LogLevel.ERROR, message)

    def success(self, message: str) -> None:
        self.log(LogLevel.SUCCESS, message)

    def exception(self, message: str, exc: BaseException) -> None:
        """Log a short error line plus the full traceback for diagnosis."""
        self.error(f"{message}: {exc}")
        tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        self.log(LogLevel.ERROR, tb.rstrip())

    def history(self) -> List[LogRecord]:
        with self._lock:
            return list(self._history)

    def clear(self) -> None:
        with self._lock:
            self._history.clear()


class QueueLogSink:
    """Bridges the logger to a Tk event loop through a thread-safe queue.

    Worker threads push records into the queue; the GUI drains it on the main
    thread with ``widget.after`` so Tkinter is only touched from one thread.
    """

    def __init__(self) -> None:
        self._queue: "queue.Queue[LogRecord]" = queue.Queue()

    def __call__(self, record: LogRecord) -> None:
        self._queue.put(record)

    def drain(self) -> List[LogRecord]:
        records: List[LogRecord] = []
        while True:
            try:
                records.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return records


# Module-level singleton used throughout the app. Not a mutable global in the
# "avoid globals" sense: it is an immutable reference to a thread-safe service.
logger = AppLogger()
