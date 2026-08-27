"""OCR client for extracting post-owner name from lander screenshots.

Sends a small upper-portion screenshot to the external OCR API and returns
the extracted post_owner_name.  Fully isolated — failures never crash the
main AdMob scraper pipeline.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import aiohttp

import config

logger = logging.getLogger("admob_scraper")


async def extract_post_owner(screenshot_path: str, ad_id: str) -> Optional[str]:
    """Send *screenshot_path* to the OCR API and return ``post_owner_name``.

    Returns ``None`` (without raising) on any failure — timeout, HTTP error,
    invalid JSON, missing field, empty value, etc.
    """
    ocr_url = config.POST_OWNER_OCR_URL
    api_key = config.POST_OWNER_OCR_API_KEY

    if not ocr_url:
        logger.warning("[PostOwner] OCR URL not configured; skipping for ad_id=%s", ad_id)
        return None

    if not api_key:
        logger.warning("[PostOwner] ADMOB_OCR_API_KEY is not configured; skipping for ad_id=%s", ad_id)
        return None

    ss_file = Path(screenshot_path)
    if not ss_file.exists():
        logger.warning("[PostOwner] Screenshot file not found: %s", screenshot_path)
        return None

    try:
        timeout = aiohttp.ClientTimeout(total=30)
        headers = {
            "accept": "application/json",
            "X-API-Key": api_key,
        }

        data = aiohttp.FormData()
        data.add_field(
            "image",
            open(ss_file, "rb"),
            filename=ss_file.name,
            content_type="image/webp",
        )

        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(ocr_url, headers=headers, data=data) as resp:
                status = resp.status
                body = await resp.text()

                if status != 200:
                    logger.warning(
                        "[PostOwner] OCR API returned HTTP %d for ad_id=%s: %s",
                        status, ad_id, body[:300],
                    )
                    return None

                import json
                try:
                    result = json.loads(body)
                except json.JSONDecodeError:
                    logger.warning("[PostOwner] Invalid JSON from OCR API for ad_id=%s", ad_id)
                    return None

                owner = result.get("post_owner_name")
                if owner and isinstance(owner, str) and owner.strip():
                    owner = owner.strip()
                    logger.info("[PostOwner] Extracted post_owner='%s' for ad_id=%s", owner, ad_id)
                    return owner

                logger.info("[PostOwner] No valid post_owner_name in OCR response for ad_id=%s", ad_id)
                return None

    except Exception as exc:
        logger.warning("[PostOwner] OCR API call failed for ad_id=%s: %s", ad_id, exc)
        return None
