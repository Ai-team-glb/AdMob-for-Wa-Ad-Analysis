"""Retrieves and normalizes proxy/IP geolocation info from Bright Data's
geo-check endpoint, fetched through the SAME proxied browser context used
for the scrape. Aligns with SRS Section 24 and 25.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Optional, Dict, Any
from playwright.async_api import BrowserContext

import config
from error_handler import ErrorType, ScraperException

logger = logging.getLogger("admob_scraper")


async def fetch_geo_info(context: BrowserContext) -> Optional[Dict[str, Any]]:
    """Fetch geolocation info for the exit proxy in this browser context."""
    page = await context.new_page()
    try:
        response = await page.goto(config.GEO_CHECK_URL, timeout=config.GEO_TIMEOUT)
        if response is None:
            raise ScraperException(ErrorType.GEOLOCATION_ERROR, "No response from geo-check endpoint")
        body = await response.text()
        return _normalize(body)
    except Exception as exc:
        logger.warning("Failed to fetch geo info: %s", exc)
        return None
    finally:
        try:
            await page.close()
        except Exception:
            pass


def _normalize(raw_body: str) -> Optional[Dict[str, Any]]:
    """Normalize both JSON and plain-text formats returned by Bright Data welcome.txt/mygeo endpoints."""
    if not raw_body:
        return None

    # Try parsing as JSON first
    try:
        data = json.loads(raw_body)
        geo = data.get("geo") or {}
        asn = data.get("asn") or {}

        return {
            "ip_version": data.get("ip_version") or data.get("ipVersion"),
            "country": data.get("country") or geo.get("country"),
            "asn": {
                "asnum": asn.get("asnum"),
                "org_name": asn.get("org_name"),
            } if asn else None,
            "geo": {
                "city": geo.get("city"),
                "region": geo.get("region"),
                "region_name": geo.get("region_name"),
                "postal_code": geo.get("postal_code"),
                "latitude": geo.get("latitude"),
                "longitude": geo.get("longitude"),
                "tz": geo.get("tz"),
                "lum_city": geo.get("lum_city"),
                "lum_region": geo.get("lum_region"),
            } if geo else None,
        }
    except json.JSONDecodeError:
        pass

    # Fallback to parsing text format from welcome.txt
    patterns = {
        "country": r"Country:\s*([^\r\n]+)",
        "latitude": r"Latitude:\s*([^\r\n]+)",
        "longitude": r"Longitude:\s*([^\r\n]+)",
        "tz": r"Timezone:\s*([^\r\n]+)",
        "asnum": r"ASN number:\s*([^\r\n]+)",
        "org_name": r"ASN Organization name:\s*([^\r\n]+)",
        "ip_version": r"IP version:\s*IPv?(\d+)",
    }
    extracted = {}
    for key, pattern in patterns.items():
        m = re.search(pattern, raw_body, re.IGNORECASE)
        extracted[key] = m.group(1).strip() if m else None

    if not extracted.get("country"):
        logger.warning("Unrecognized geo endpoint body format: %s", raw_body[:100])
        return None

    asnum_int = None
    if extracted.get("asnum"):
        try:
            asnum_int = int(extracted["asnum"])
        except ValueError:
            pass

    ip_ver_int = None
    if extracted.get("ip_version"):
        try:
            ip_ver_int = int(extracted["ip_version"])
        except ValueError:
            pass

    lat_float = None
    if extracted.get("latitude"):
        try:
            lat_float = float(extracted["latitude"])
        except ValueError:
            pass

    lon_float = None
    if extracted.get("longitude"):
        try:
            lon_float = float(extracted["longitude"])
        except ValueError:
            pass

    return {
        "ip_version": ip_ver_int,
        "country": extracted.get("country"),
        "asn": {
            "asnum": asnum_int,
            "org_name": extracted.get("org_name"),
        } if (asnum_int or extracted.get("org_name")) else None,
        "geo": {
            "city": None,
            "region": None,
            "region_name": None,
            "postal_code": None,
            "latitude": lat_float,
            "longitude": lon_float,
            "tz": extracted.get("tz"),
            "lum_city": None,
            "lum_region": None,
        } if (lat_float or lon_float or extracted.get("tz")) else None,
    }
