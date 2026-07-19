"""Logs page: a full-height live log console."""
from __future__ import annotations

from gui.pages.base_page import BasePage
from gui.widgets.log_console import LogConsole


class LogsPage(BasePage):
    title = "Logs"
    subtitle = "Live, colour-coded activity for every step of the pipeline."

    def build(self) -> None:
        self._console = LogConsole(
            self.body, self.context.logger,
            auto_scroll=self.context.config.config.auto_scroll_logs,
        )
        self._console.pack(fill="both", expand=True)
