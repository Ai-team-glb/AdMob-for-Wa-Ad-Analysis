"""Captures the chain of URLs visited during navigation and the final destination.
Includes redirect loop protection as required by SRS Section 18.
"""
from __future__ import annotations
import logging
from typing import List, Optional
from playwright.async_api import Page, Frame

import config
from error_handler import ErrorType, ScraperException

logger = logging.getLogger("admob_scraper")


class RedirectTracker:
    """Listens to main-frame navigation events on a page and records every
    URL the browser lands on, in order, from the original input URL to the
    final destination.
    """

    def __init__(self, page: Page, start_url: str):
        self.start_url = start_url
        self._chain: List[str] = [start_url]
        self._page = page
        self._loop_detected = False
        page.on("framenavigated", self._on_frame_navigated)

    def _on_frame_navigated(self, frame: Frame) -> None:
        if frame == self._page.main_frame:
            url = frame.url
            if not self._chain or self._chain[-1] != url:
                self._chain.append(url)
                if len(self._chain) > config.MAX_REDIRECTS:
                    self._loop_detected = True
                    logger.warning("Redirect loop limit reached (%d hops) for %s", config.MAX_REDIRECTS, self.start_url)

    @property
    def loop_detected(self) -> bool:
        return self._loop_detected

    def check_loop(self) -> None:
        if self._loop_detected:
            raise ScraperException(
                ErrorType.REDIRECT_LOOP_ERROR,
                f"Exceeded max redirects ({config.MAX_REDIRECTS})"
            )

    @property
    def redirect_urls(self) -> List[str]:
        """All URLs traversed in the redirect chain before reaching destination, or full chain."""
        return list(self._chain)

    @property
    def destination_url(self) -> Optional[str]:
        return self._chain[-1] if self._chain else None
