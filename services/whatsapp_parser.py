"""Detection, parsing, resolution, and deduplication of publicly visible WhatsApp links.
Aligns with SRS Sections 20, 21, 22, and 23.
Supports:
- Direct wa.me, api.whatsapp.com, chat.whatsapp.com, web.whatsapp.com links
- Shortlinks like wa.link, w.app (with HTTP resolution to extract phone & message)
- Parsing of whatsapp-url, whatsapp-profile, whatsapp-number, whatsapp-message
- Complete deduplication of unique WhatsApp records
"""
from __future__ import annotations
import logging
import re
import urllib.request
from urllib.parse import urlparse, parse_qs, unquote
from playwright.async_api import Page

import config

logger = logging.getLogger("admob_scraper")

WA_NUMBER_RE = re.compile(r"(?:wa\.me/|phone=|send/\?phone=|send\?phone=|\+)(\d{7,15})")


async def find_whatsapp_links(page: Page) -> list[str]:
    """Collect unique WhatsApp-related hrefs or action links visible on the current page."""
    try:
        hrefs = await page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
    except Exception:
        hrefs = []

    # Also check button / onclick / data-href attributes
    try:
        data_links = await page.eval_on_selector_all(
            "[data-href], [onclick], button",
            """els => els.map(e => {
                return e.getAttribute('data-href') || e.getAttribute('onclick') || '';
            })"""
        )
    except Exception:
        data_links = []

    all_candidates = hrefs + data_links
    found, seen = [], set()

    for item in all_candidates:
        if not item or not isinstance(item, str):
            continue

        # Extract URLs matching http(s)
        extracted_urls = re.findall(r"https?://[^\s\"\'<>]+", item)
        if not extracted_urls and any(d in item.lower() for d in config.WHATSAPP_DOMAINS):
            extracted_urls = [item]

        for link in extracted_urls:
            link = link.strip().rstrip(")\"';,")
            try:
                host = urlparse(link).netloc.lower()
            except ValueError:
                continue

            if any(domain in host for domain in config.WHATSAPP_DOMAINS) and link not in seen:
                seen.add(link)
                found.append(link)

    return found


def resolve_whatsapp_shortlink(url: str) -> tuple[str, str | None, str | None, str | None]:
    """Resolve shortlinks (like wa.link or w.app) via HTTP redirect to obtain full api.whatsapp.com URL."""
    target_url = url
    profile = None
    number = None
    message = None

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            final_url = resp.geturl()
            html_content = resp.read().decode("utf-8", errors="ignore")

            # If redirected to api.whatsapp.com or wa.me
            if final_url != url:
                target_url = final_url

            # Extract profile name if present in WhatsApp intermediate page
            profile_match = re.search(r'<h3 class="_9vd5 _9scb"[^>]*>([^<]+)</h3>', html_content)
            if not profile_match:
                profile_match = re.search(r'<title>WhatsApp.*?([A-Za-z0-9\s._-]+)</title>', html_content)
            if profile_match:
                name = profile_match.group(1).strip()
                if "WhatsApp" not in name:
                    profile = name

    except Exception as exc:
        logger.debug("Could not resolve WhatsApp shortlink %s: %s", url, exc)

    # Parse details from target_url
    parsed = urlparse(target_url)
    query = parse_qs(parsed.query)

    num_match = WA_NUMBER_RE.search(target_url)
    if num_match:
        number = num_match.group(1)

    for key in ("text", "message"):
        if key in query and query[key]:
            message = unquote(query[key][0])
            break

    return target_url, profile, number, message


def parse_whatsapp_url(url: str) -> dict:
    """Extract whatsapp-url, whatsapp-profile, whatsapp-number, whatsapp-message from link."""
    # Check if shortlink needing resolution
    if any(short in url.lower() for short in ("wa.link", "w.app")):
        resolved_url, profile, number, message = resolve_whatsapp_shortlink(url)
        return {
            "whatsapp-url": url,
            "whatsapp-profile": profile,
            "whatsapp-number": number,
            "whatsapp-message": message,
        }

    parsed = urlparse(url)
    query = parse_qs(parsed.query)

    number_match = WA_NUMBER_RE.search(url)
    number = number_match.group(1) if number_match else None

    message = None
    for key in ("text", "message"):
        if key in query and query[key]:
            message = unquote(query[key][0])
            break

    return {
        "whatsapp-url": url,
        "whatsapp-profile": None,  # direct wa.me links don't carry profile in query
        "whatsapp-number": number,
        "whatsapp-message": message,
    }


async def extract_whatsapp_data(page: Page) -> list[dict]:
    """Extract and deduplicate WhatsApp data objects from the page."""
    links = await find_whatsapp_links(page)
    records = []
    seen_keys = set()

    for link in links:
        parsed_data = parse_whatsapp_url(link)
        # Deduplicate by unique URL and/or number+message combination
        dedup_key = parsed_data.get("whatsapp-url") or (parsed_data.get("whatsapp-number"), parsed_data.get("whatsapp-message"))
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)
        records.append(parsed_data)

    return records
