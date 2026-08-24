"""Single geolocation observation execution and data collection.
Aligns with SRS Sections 15, 16, 17, 19, 20, 24, 35.
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Dict, Any, Optional

from playwright.async_api import TimeoutError as PlaywrightTimeoutError

import config
from services import geo_service
from services import url_parser
from services import whatsapp_parser
from services.browser_manager import BrowserManager
from core.error_handler import ErrorType, ScraperException, classify_error
from services.proxy_manager import ProxyManager
from services.redirect_tracker import RedirectTracker

logger = logging.getLogger("admob_scraper")

# Regex to find phone numbers in visible page text
_PHONE_RE = re.compile(r"(?<!\d)(\+?\d[\d\s\-().]{6,18}\d)(?!\d)")


async def _extract_phone_numbers(page) -> list[str]:
    """Extract phone numbers from the visible page text."""
    try:
        text = await page.inner_text("body")
    except Exception:
        return []
    raw = _PHONE_RE.findall(text)
    # Normalise: strip whitespace/dashes, deduplicate, ignore very short matches
    seen: set[str] = set()
    result: list[str] = []
    for r in raw:
        cleaned = re.sub(r"[\s\-().]", "", r)
        if len(cleaned) >= 8 and cleaned not in seen:
            seen.add(cleaned)
            result.append(cleaned)
    return result


async def _extract_contact_buttons(page) -> list[dict]:
    """Extract contact-related buttons/links (tel:, mailto:, whatsapp hrefs)."""
    try:
        buttons = await page.eval_on_selector_all(
            "a[href], button[onclick]",
            """els => els.map(e => ({
                text: (e.innerText || e.textContent || '').trim().substring(0, 200),
                href: e.href || e.getAttribute('onclick') || ''
            }))"""
        )
    except Exception:
        return []

    contact_keywords = ("tel:", "mailto:", "whatsapp", "wa.me", "wa.link", "w.app")
    result = []
    seen: set[str] = set()
    for b in buttons:
        href = (b.get("href") or "").strip()
        if not href:
            continue
        lower_href = href.lower()
        if any(kw in lower_href for kw in contact_keywords) and href not in seen:
            seen.add(href)
            result.append({"text": b.get("text", ""), "href": href})
    return result


async def execute_country_observation(
    browser_mgr: BrowserManager,
    target_url: str,
    country: str,
    screenshot_dir: Optional[Path] = None,
    ad_id_for_screenshot: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a single observation for a specific country proxy:
    1. Connect via Bright Data proxy for `country`
    2. Navigate to target URL & track redirects
    3. Extract destination URL & campaign parameters
    4. Extract WhatsApp links & details
    5. Fetch actual exit IP geolocation from geo endpoint
    6. Capture full rendered HTML
    7. Take a screenshot
    8. Extract phone numbers and contact buttons
    Returns a dict containing the collected observation data.
    """
    proxy = ProxyManager.build_proxy_config(country)
    try:
        browser, context = await browser_mgr.new_context(proxy)
    except Exception as exc:
        logger.warning("Failed to initialize proxy context: %s. Using direct connection.", exc)
        proxy = None
        browser, context = await browser_mgr.new_context(None)

    try:
        # Route abort for third-party ad networks/trackers that cause hanging connections on proxy tunnels
        await context.route(
            "**/{googletagmanager,google-analytics,doubleclick,googlesyndication,facebook,analytics}/**",
            lambda route: route.abort()
        )
        page = await context.new_page()
        tracker = RedirectTracker(page, target_url)

        logger.info("Navigation started: %s (proxy country=%s)", target_url, country.upper() if proxy else "DIRECT")
        try:
            await page.goto(target_url, wait_until="domcontentloaded", timeout=12000 if proxy else config.PAGE_TIMEOUT)
        except PlaywrightTimeoutError as exc:
            if proxy is not None:
                logger.warning("Navigation timeout via proxy on %s. Attempting fallback via direct connection...", target_url)
                try:
                    await context.close()
                except Exception:
                    pass
                try:
                    await browser.close()
                except Exception:
                    pass

                proxy = None
                browser, context = await browser_mgr.new_context(None)
                await context.route(
                    "**/{googletagmanager,google-analytics,doubleclick,googlesyndication,facebook,analytics}/**",
                    lambda route: route.abort()
                )
                page = await context.new_page()
                tracker = RedirectTracker(page, target_url)
                logger.info("Navigation started (direct fallback): %s", target_url)
                try:
                    await page.goto(target_url, wait_until="domcontentloaded", timeout=config.PAGE_TIMEOUT)
                except PlaywrightTimeoutError as exc2:
                    logger.warning("Navigation timeout on direct fallback for %s", target_url)
                    raise ScraperException(ErrorType.NAVIGATION_TIMEOUT, "Navigation timed out", exc2)
            else:
                logger.warning("Navigation timeout on %s for country %s", target_url, country.upper())
                raise ScraperException(ErrorType.NAVIGATION_TIMEOUT, "Navigation timed out", exc)

        tracker.check_loop()

        # Check for access challenge or CAPTCHA (SRS Section 35)
        content_snippet = ""
        try:
            content_snippet = (await page.content())[:2000].lower()
        except Exception:
            pass
        if "captcha" in content_snippet or "cf-browser-verification" in content_snippet:
            logger.warning("Access challenge/CAPTCHA detected for country %s", country.upper())
            raise ScraperException(ErrorType.CAPTCHA_DETECTED, "CAPTCHA/challenge encountered")

        try:
            await page.wait_for_load_state("networkidle", timeout=5000)
        except PlaywrightTimeoutError:
            pass  # Non-fatal: ad-tech pages might keep connections open

        destination_url = tracker.destination_url or page.url
        redirect_urls = tracker.redirect_urls
        logger.info("Redirects detected: %d | Destination: %s", len(redirect_urls), destination_url)

        campaign_params = url_parser.extract_campaign_params(destination_url)
        whatsapp_data = await whatsapp_parser.extract_whatsapp_data(page)
        logger.info("WhatsApp links found: %d", len(whatsapp_data))

        geo_data = await geo_service.fetch_geo_info(context)
        detected_country = geo_data.get("country") if geo_data else "unknown"
        logger.info("Geolocation detected: %s (requested: %s)", detected_country, country.upper())

        # --- Extended data collection for API pipeline ---
        # Full rendered HTML
        rendered_html = ""
        try:
            rendered_html = await page.content()
        except Exception as exc:
            logger.warning("Failed to capture rendered HTML: %s", exc)

        # Rendered visible text content
        rendered_text = ""
        try:
            raw_text = await page.locator("body").inner_text()
            if not raw_text:
                raw_text = await page.evaluate("() => document.body ? document.body.innerText : ''")
            if raw_text:
                lines = [line.strip() for line in raw_text.splitlines()]
                cleaned_lines = []
                prev_empty = False
                for line in lines:
                    if line:
                        cleaned_lines.append(line)
                        prev_empty = False
                    elif not prev_empty:
                        cleaned_lines.append("")
                        prev_empty = True
                rendered_text = "\n".join(cleaned_lines).strip()
        except Exception as exc:
            logger.warning("Failed to extract rendered text content: %s", exc)

        # Screenshot
        screenshot_path: Optional[str] = None
        if screenshot_dir and ad_id_for_screenshot:
            try:
                screenshot_dir_path = Path(screenshot_dir)
                screenshot_dir_path.mkdir(parents=True, exist_ok=True)
                ss_file = screenshot_dir_path / f"{ad_id_for_screenshot}.png"
                await page.screenshot(path=str(ss_file), full_page=True)
                screenshot_path = str(ss_file)
                logger.info("Screenshot saved: %s", ss_file.name)
            except Exception as exc:
                logger.warning("Failed to take screenshot: %s", exc)

        # Phone numbers
        phone_numbers = await _extract_phone_numbers(page)
        logger.info("Phone numbers found: %d", len(phone_numbers))

        # Contact buttons
        contact_buttons = await _extract_contact_buttons(page)
        logger.info("Contact buttons found: %d", len(contact_buttons))

        return {
            "country_requested": country,
            "redirect_urls": redirect_urls,
            "destination_url": destination_url,
            "campaign_params": campaign_params,
            "whatsapp_data": whatsapp_data,
            "geo_data": geo_data,
            "rendered_html": rendered_html,
            "rendered_text": rendered_text,
            "screenshot_path": screenshot_path,
            "phone_numbers": phone_numbers,
            "contact_buttons": contact_buttons,
        }

    except Exception as exc:
        err_type = classify_error(exc)
        logger.debug("[%s] Country observation exception (%s): %s", err_type.value, country.upper(), exc)
        raise
    finally:
        try:
            await context.close()
        except Exception:
            pass
        try:
            await browser.close()
        except Exception:
            pass

