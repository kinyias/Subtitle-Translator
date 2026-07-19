"""Background execution primitives.

Workers run service calls off the GUI thread using a shared
``ThreadPoolExecutor``. Results and errors are marshalled back onto the Tk main
thread through a :class:`TkDispatcher`, so the GUI thread never blocks and
widgets are only ever touched from the main thread.
"""
from __future__ import annotations

import queue
import tkinter as tk
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any, Callable, Generic, Optional, TypeVar

from utils.logger import logger

T = TypeVar("T")


class TkDispatcher:
    """Runs callables on the Tk main thread via a polled queue.

    Tkinter is single-threaded; calling widget methods from worker threads is
    undefined behaviour. Workers push zero-arg callables here and the GUI drains
    them with ``after`` on the main loop.
    """

    def __init__(self, widget: tk.Misc, interval_ms: int = 40) -> None:
        self._widget = widget
        self._interval = interval_ms
        self._queue: "queue.Queue[Callable[[], None]]" = queue.Queue()
        self._running = False

    def start(self) -> None:
        if not self._running:
            self._running = True
            self._pump()

    def stop(self) -> None:
        self._running = False

    def post(self, func: Callable[[], None]) -> None:
        self._queue.put(func)

    def _pump(self) -> None:
        if not self._running:
            return
        while True:
            try:
                func = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                func()
            except Exception as exc:  # never let a UI callback kill the pump
                logger.exception("UI callback failed", exc)
        try:
            self._widget.after(self._interval, self._pump)
        except tk.TclError:
            self._running = False  # widget destroyed during shutdown


@dataclass
class WorkerCallbacks(Generic[T]):
    """Optional lifecycle callbacks, all invoked on the Tk main thread."""

    on_start: Optional[Callable[[], None]] = None
    on_success: Optional[Callable[[T], None]] = None
    on_error: Optional[Callable[[Exception], None]] = None
    on_done: Optional[Callable[[], None]] = None


class WorkerPool:
    """Owns the shared executor and dispatches results to the GUI thread."""

    def __init__(self, dispatcher: TkDispatcher, max_workers: int = 4) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="capcut")
        self._dispatcher = dispatcher

    def submit(self, job: Callable[[], T], callbacks: WorkerCallbacks[T]) -> "Future[T]":
        """Run *job* in the background and route callbacks to the main thread."""
        if callbacks.on_start:
            self._dispatcher.post(callbacks.on_start)

        future: "Future[T]" = self._executor.submit(job)

        def _completed(fut: "Future[T]") -> None:
            try:
                result = fut.result()
            except Exception as exc:  # deliver failure on the UI thread
                logger.exception("Background task failed", exc)
                self._dispatcher.post(lambda e=exc: self._finish_error(callbacks, e))
            else:
                self._dispatcher.post(lambda r=result: self._finish_success(callbacks, r))

        future.add_done_callback(_completed)
        return future

    @staticmethod
    def _finish_success(callbacks: WorkerCallbacks[T], result: T) -> None:
        if callbacks.on_success:
            callbacks.on_success(result)
        if callbacks.on_done:
            callbacks.on_done()

    @staticmethod
    def _finish_error(callbacks: WorkerCallbacks[T], exc: Exception) -> None:
        if callbacks.on_error:
            callbacks.on_error(exc)
        if callbacks.on_done:
            callbacks.on_done()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
