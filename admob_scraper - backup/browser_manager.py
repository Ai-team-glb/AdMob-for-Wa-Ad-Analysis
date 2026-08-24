"""Playwright browser/context lifecycle management with robust proxy and crash recovery support.
Aligns with SRS Sections 11, 12, 13, 14, and 45.
"""
from __future__ import annotations
import asyncio
import logging
from typing import Optional, Tuple

from playwright.async_api import async_playwright, Browser, BrowserContext, Playwright

import config
from error_handler import ErrorType, ScraperException

logger = logging.getLogger("admob_scraper")


class BrowserManager:
    """Async manager that maintains Playwright driver lifecycle, performs startup recovery
    if driver or browser connections fail, and creates clean browser/context instances per proxy country.
    """

    def __init__(self):
        self._playwright: Optional[Playwright] = None

    async def start(self) -> None:
        """Start or restart the Playwright driver."""
        await self.cleanup()
        try:
            self._playwright = await async_playwright().start()
        except Exception as exc:
            logger.error("Failed to start Playwright driver: %s", exc)
            raise ScraperException(ErrorType.PLAYWRIGHT_DRIVER_ERROR, "Playwright driver startup failed", exc)

    async def cleanup(self) -> None:
        """Gracefully shut down Playwright if currently running."""
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:
                logger.debug("Error during Playwright driver stop: %s", exc)
            finally:
                self._playwright = None

    async def __aenter__(self) -> "BrowserManager":
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.cleanup()

    async def new_context(self, proxy: Optional[dict] = None) -> Tuple[Browser, BrowserContext]:
        """Launch a browser + context using the given proxy config.
        Includes recovery logic for browser startup failures (SRS Section 13 & 14).
        """
        last_exception = None

        for attempt in range(1, config.BROWSER_START_RETRIES + 1):
            if self._playwright is None:
                await self.start()

            try:
                browser = await self._playwright.chromium.launch(
                    headless=config.HEADLESS,
                    timeout=config.BROWSER_START_TIMEOUT,
                )
                context_kwargs = {
                    "ignore_https_errors": True,
                    "user_agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
                    ),
                }
                if proxy:
                    context_kwargs["proxy"] = proxy

                context = await browser.new_context(**context_kwargs)
                context.set_default_timeout(config.PAGE_TIMEOUT)
                context.set_default_navigation_timeout(config.NAVIGATION_TIMEOUT)
                return browser, context

            except Exception as exc:
                last_exception = exc
                logger.error(
                    "BROWSER_STARTUP_ERROR (attempt %d/%d): %s",
                    attempt, config.BROWSER_START_RETRIES, exc
                )
                # Cleanup driver to recover from broken pipe/connection closed errors
                await self.cleanup()
                if attempt < config.BROWSER_START_RETRIES:
                    logger.info("Attempting browser recovery...")
                    await asyncio.sleep(config.RETRY_BACKOFF_SECONDS)

        raise ScraperException(
            ErrorType.BROWSER_STARTUP_ERROR,
            f"Browser launch failed after {config.BROWSER_START_RETRIES} attempts",
            last_exception
        )
