"""HTTP client for the AdMob Lander API.

Endpoints handled:
    GET  /api/v1/admob/landers/get_ads_for_blackhat
    POST /api/v1/admob/landers/upload_admob_blackhat   (multipart)
    POST /api/v1/admob/landers/insert_html_content      (JSON)
"""
from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import aiohttp

import config
from error_handler import ErrorType, ScraperException
from retry import async_retry, PermanentError

logger = logging.getLogger("admob_scraper")


def _url(endpoint_or_full_url: str) -> str:
    """Build a full URL from config or use full URL directly if provided."""
    if not endpoint_or_full_url:
        return ""
    if endpoint_or_full_url.startswith("http://") or endpoint_or_full_url.startswith("https://"):
        return endpoint_or_full_url
    base = config.ADMOB_API_BASE_URL.rstrip("/")
    return f"{base}{endpoint_or_full_url}"


ADMOB_GET_HEADERS = {"x-scraper-name": "python-lander"}


# ---------------------------------------------------------------------------
# GET ADS
# ---------------------------------------------------------------------------

@async_retry(max_retries=config.MAX_RETRIES, backoff_seconds=config.RETRY_BACKOFF_SECONDS,
             exceptions=(aiohttp.ClientError, TimeoutError, OSError))
async def get_ads() -> List[Dict[str, Any]]:
    """Fetch ads from the API.  Returns the list of ad dicts.

    Gracefully handles empty data, "No Ads found", ES lookup failures,
    HTTP errors, and timeouts.
    """
    url = _url(config.DEV_GET_API or config.ADMOB_GET_ADS_ENDPOINT)
    logger.info("GET ads request started: %s (headers=%s)", url, ADMOB_GET_HEADERS)

    timeout = aiohttp.ClientTimeout(total=config.ADMOB_API_TIMEOUT)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url, headers=ADMOB_GET_HEADERS) as resp:
            status = resp.status
            body = await resp.text()

            if status != 200:
                logger.error("GET ads HTTP %d: %s", status, body[:500])
                raise ScraperException(ErrorType.API_SERVER_ERROR,
                                       f"GET ads returned HTTP {status}")

            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                logger.error("GET ads response is not valid JSON: %s", body[:500])
                raise ScraperException(ErrorType.API_SERVER_ERROR,
                                       "Invalid JSON from GET ads", exc)

            api_code = payload.get("code")
            message = payload.get("message", "")

            if api_code != 200:
                logger.warning("GET ads API code=%s message=%s", api_code, message)
                # Known empty-result messages — not an error, just no work to do
                if message in ("No Ads found", "Ads not found in Elasticsearch"):
                    logger.info("No ads available from API: %s", message)
                    return []
                raise ScraperException(ErrorType.API_SERVER_ERROR,
                                       f"GET ads API error: code={api_code} message={message}")

            data = payload.get("data")
            if not data:
                logger.info("GET ads returned empty data list")
                return []

            logger.info("GET ads returned %d ad(s)", len(data))
            return data


# ---------------------------------------------------------------------------
# UPLOAD MEDIA + ZIP
# ---------------------------------------------------------------------------

@async_retry(max_retries=config.MAX_RETRIES, backoff_seconds=config.RETRY_BACKOFF_SECONDS,
             exceptions=(aiohttp.ClientError, TimeoutError, OSError))
async def upload_media(
    ad_id: str,
    status: int,
    country_iso: str,
    media_path: Optional[str] = None,
    zip_path: Optional[str] = None,
) -> Dict[str, str]:
    """Upload screenshot + HTML ZIP to the API.

    Returns ``{"image_path": "...", "html_path": "..."}``.
    """
    url = _url(config.DEV_S3_API or config.ADMOB_UPLOAD_ENDPOINT)
    logger.info("Upload started for ad_id=%s country=%s", ad_id, country_iso)

    if not media_path and not zip_path:
        raise PermanentError("At least one file (media or zip) must be provided for upload")

    timeout = aiohttp.ClientTimeout(total=config.ADMOB_API_TIMEOUT * 3)  # uploads can be large
    data = aiohttp.FormData()
    data.add_field("ad_id", str(ad_id))
    data.add_field("status", str(status))
    data.add_field("country_iso", country_iso)

    if media_path:
        mp = Path(media_path)
        if not mp.exists():
            raise PermanentError(f"Media file not found: {media_path}")
        data.add_field("media", open(mp, "rb"),
                       filename=mp.name, content_type="image/png")

    if zip_path:
        zp = Path(zip_path)
        if not zp.exists():
            raise PermanentError(f"ZIP file not found: {zip_path}")
        data.add_field("zip", open(zp, "rb"),
                       filename=zp.name, content_type="application/zip")

    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(url, data=data) as resp:
            resp_status = resp.status
            body = await resp.text()

            # 404 — no file provided (permanent, do not retry)
            if resp_status == 404:
                logger.error("Upload 404 for ad_id=%s: %s", ad_id, body[:500])
                raise PermanentError(f"Upload 404 (no file found) for ad_id={ad_id}")

            # 400 — invalid status or runtime failure (permanent, do not retry)
            if resp_status == 400:
                logger.error("Upload 400 for ad_id=%s: %s", ad_id, body[:500])
                raise PermanentError(f"Upload 400 for ad_id={ad_id}: {body[:200]}")

            if resp_status != 200:
                logger.error("Upload HTTP %d for ad_id=%s: %s", resp_status, ad_id, body[:500])
                raise ScraperException(ErrorType.UPLOAD_ERROR,
                                       f"Upload returned HTTP {resp_status}")

            try:
                payload = json.loads(body)
            except json.JSONDecodeError as exc:
                raise ScraperException(ErrorType.UPLOAD_ERROR,
                                       "Invalid JSON from upload", exc)

            api_code = payload.get("code")
            if api_code != 200:
                raise ScraperException(ErrorType.UPLOAD_ERROR,
                                       f"Upload API error: code={api_code} message={payload.get('message')}")

            image_path = payload.get("image_path", "")
            html_path = payload.get("html_path", "")

            if not image_path and media_path:
                logger.warning("Upload response missing image_path for ad_id=%s", ad_id)
            if not html_path and zip_path:
                logger.warning("Upload response missing html_path for ad_id=%s", ad_id)

            logger.info("Upload completed for ad_id=%s — image_path=%s html_path=%s",
                        ad_id, image_path, html_path)
            return {"image_path": image_path, "html_path": html_path}


# ---------------------------------------------------------------------------
# INSERT LANDER CONTENT
# ---------------------------------------------------------------------------

async def insert_lander(ad_id: str, insert_data: Dict[str, Any]) -> Dict[str, Any]:
    """POST the lander payload to insert_html_content.

    Does NOT blindly retry 422 (validation) or 400 (bad request).
    Retries only on 503 (service unavailable) and transient errors.
    """
    url = _url(config.DEV_INSERT_API or config.ADMOB_INSERT_ENDPOINT)
    logger.info("Insert lander started for ad_id=%s", ad_id)

    payload = {
        "ad_id": str(ad_id),
        "insertData": insert_data,
    }

    timeout = aiohttp.ClientTimeout(total=config.ADMOB_API_TIMEOUT)

    last_exc: Optional[Exception] = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    resp_status = resp.status
                    body = await resp.text()

                    # ---- 422 Validation Error — do NOT retry ----
                    if resp_status == 422:
                        try:
                            err_payload = json.loads(body)
                        except json.JSONDecodeError:
                            err_payload = {"raw": body[:500]}
                        logger.error(
                            "Insert REJECTED (422) for ad_id=%s: message=%s",
                            ad_id, err_payload.get("message", body[:200]),
                        )
                        # Log each validation error from the errors array
                        for err_item in err_payload.get("errors", []):
                            logger.error(
                                "  Validation error: field=%s reason=%s message=%s",
                                err_item.get("field", "?"),
                                err_item.get("reason", "?"),
                                err_item.get("message", "?"),
                            )
                        raise PermanentError(f"Insert validation failed (422) for ad_id={ad_id}")

                    # ---- 400 Bad Request — do NOT retry ----
                    if resp_status == 400:
                        logger.error("Insert BAD REQUEST (400) for ad_id=%s: %s", ad_id, body[:500])
                        raise PermanentError(f"Insert bad request (400) for ad_id={ad_id}")

                    # ---- 503 Service Unavailable — retry ----
                    if resp_status == 503:
                        logger.warning(
                            "Insert SERVICE UNAVAILABLE (503) for ad_id=%s (attempt %d/%d): %s",
                            ad_id, attempt, config.MAX_RETRIES, body[:200],
                        )
                        last_exc = ScraperException(ErrorType.API_SERVER_ERROR,
                                                    f"503 from insert endpoint: {body[:200]}")
                        if attempt < config.MAX_RETRIES:
                            import asyncio
                            await asyncio.sleep(config.RETRY_BACKOFF_SECONDS * attempt)
                            continue
                        raise last_exc

                    # ---- 500 Server Error — log, do NOT retry ----
                    if resp_status == 500:
                        logger.error(
                            "Insert SERVER ERROR (500) for ad_id=%s endpoint=%s body=%s",
                            ad_id, url, body[:500],
                        )
                        raise ScraperException(ErrorType.API_SERVER_ERROR,
                                               f"500 from insert endpoint for ad_id={ad_id}")

                    # ---- Other non-200 ----
                    if resp_status not in (200, 207):
                        logger.error("Insert HTTP %d for ad_id=%s: %s", resp_status, ad_id, body[:500])
                        raise ScraperException(ErrorType.API_SERVER_ERROR,
                                               f"Insert returned HTTP {resp_status}")

                    # ---- Success (200 or 207) ----
                    try:
                        result = json.loads(body)
                    except json.JSONDecodeError:
                        raise ScraperException(ErrorType.API_SERVER_ERROR,
                                               "Invalid JSON from insert response")

                    # 207 partial success — log each item
                    if resp_status == 207:
                        logger.warning("Insert returned 207 (partial success) for ad_id=%s", ad_id)
                        items = result.get("data", result.get("results", []))
                        if isinstance(items, list):
                            for item in items:
                                logger.info("  207 item: %s", json.dumps(item)[:300])

                    # Log result details
                    data = result.get("data", {})
                    logger.info(
                        "Insert completed for ad_id=%s — id=%s mysql_saved=%s elastic_indexed=%s "
                        "redirect_status=%s skipped_content=%s",
                        ad_id,
                        data.get("id"),
                        data.get("mysql_saved"),
                        data.get("elastic_indexed"),
                        data.get("redirect_status"),
                        data.get("skipped_content"),
                    )
                    return result

        except PermanentError:
            raise
        except (aiohttp.ClientError, TimeoutError, OSError) as exc:
            last_exc = exc
            logger.warning("Insert transient error for ad_id=%s (attempt %d/%d): %s",
                          ad_id, attempt, config.MAX_RETRIES, exc)
            if attempt < config.MAX_RETRIES:
                import asyncio
                await asyncio.sleep(config.RETRY_BACKOFF_SECONDS * attempt)
                continue
            raise ScraperException(ErrorType.API_CONNECTION_ERROR,
                                   f"Insert failed after {config.MAX_RETRIES} attempts", last_exc)

    # Should not reach here, but just in case
    raise ScraperException(ErrorType.API_SERVER_ERROR,
                           f"Insert exhausted all retries for ad_id={ad_id}", last_exc)
