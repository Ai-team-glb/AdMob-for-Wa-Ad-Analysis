"""Entry point: AdMob Multi-Geolocation Web Data Extraction System.

Config-driven automated pipeline:
- Configured manually via config.yaml
- Supports HIT_GET_API=true (direct API call) and HIT_GET_API=false (local ads.json cache check -> fallback to GET API)
- Saves complete API responses atomically to data/ads.json
- Tracks processed ad_ids in data/processed_ads.json
- Runs continuously with TIME_GAP_IN_INSTANCES polling delay when no ads are available
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import aiohttp

from datetime import datetime, timezone

import config
from browser_manager import BrowserManager
from logger import setup_logger
from proxy_manager import ProxyManager, normalize_country_code
from scraping_manager import ScrapingManager
from storage import Storage

logger = setup_logger()


def load_processed_ad_ids() -> set[str]:
    """Load set of already processed ad_ids from data/processed_ads.json."""
    path = Path(config.PROCESSED_ADS_FILE)
    if not path.exists():
        return set()
    try:
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return set()
        data = json.loads(raw)
        if isinstance(data, list):
            return set(str(x) for x in data)
    except Exception as exc:
        logger.warning("Could not read %s: %s", path, exc)
    return set()


def mark_ad_id_processed(ad_id: str) -> None:
    """Add ad_id to data/processed_ads.json atomically."""
    path = Path(config.PROCESSED_ADS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    processed = load_processed_ad_ids()
    processed.add(str(ad_id))

    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(sorted(list(processed)), indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        logger.warning("Failed to save processed ad_id %s: %s", ad_id, exc)


def save_api_response_to_ads_json(response_obj: dict) -> None:
    """Save complete GET API response into data/ads.json (atomic write)."""
    path = Path(config.ADS_CACHE_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(response_obj, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, path)
        logger.info("Saved complete GET API response to %s", path)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        logger.error("Failed to write to %s: %s", path, exc)


def register_received_ad(ad: Dict[str, Any], storage: Storage) -> None:
    """Register ad in AdMod_Data.json: status=0 if new, status=2 if repeat."""
    ad_id = str(ad.get("ad_id") or ad.get("id") or "").strip()
    if not ad_id:
        return
    dest = (ad.get("destination_url") or "").strip()
    countries = ad.get("country", [])
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    existing = storage.get_record(ad_id)
    if existing:
        # Same ad_id received again -> status = 2 (repeat)
        if existing.get("status") != 2:
            record = dict(existing)
            record["status"] = 2
            record["updated"] = now_iso
            storage.upsert_record(record)
    else:
        # New ad received -> status = 0 (fresh)
        country_iso = [normalize_country_code(c).upper() for c in countries] if countries else ["IN"]
        record = {
            "ad_id": ad_id,
            "status": 0,  # 0 = fresh
            "platform": "12",
            "destinations": dest,
            "html_path": "",
            "screen_shot": "",
            "html_content": "",
            "domain_registered_date": ad.get("domain_registered_date"),
            "domain_age": int(ad.get("domain_age") or 0),
            "country_iso": country_iso,
            "outgoing_url": [],
            "redirects": [],
            "source_app": str(ad.get("source_app") or ad.get("app_name") or "crex"),
            "whatsapp": [],
            "campaign_id": str(ad.get("campaign_id") or ""),
            "created": now_iso,
            "updated": now_iso,
        }
        storage.upsert_record(record)


def load_ads_from_cache(storage: Storage) -> List[Dict[str, Any]]:
    """Load valid un-scraped ads from data/ads.json cache."""
    path = Path(config.ADS_CACHE_FILE)
    if not path.exists():
        return []
    try:
        raw_text = path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return []
        payload = json.loads(raw_text)
        ads_list = payload.get("data", []) if isinstance(payload, dict) else []
        if not isinstance(ads_list, list):
            return []

        # Register all ads in AdMod_Data.json upon loading
        for ad in ads_list:
            if isinstance(ad, dict):
                register_received_ad(ad, storage)

        processed_ids = load_processed_ad_ids()

        unscraped = []
        for ad in ads_list:
            if not isinstance(ad, dict):
                continue
            ad_id = str(ad.get("ad_id") or ad.get("id") or "").strip()
            dest_url = (ad.get("destination_url") or "").strip()

            if not dest_url:
                continue

            if ad_id and ad_id in processed_ids:
                continue

            unscraped.append(ad)

        return unscraped
    except Exception as exc:
        logger.warning("Could not parse ads cache from %s: %s", path, exc)
        return []


async def fetch_and_store_api_ads(storage: Storage) -> List[Dict[str, Any]]:
    """Hit GET API, save full response to data/ads.json, and return unscraped ads."""
    import admob_api

    endpoint = config.DEV_GET_API or config.ADMOB_GET_ADS_ENDPOINT
    url = admob_api._url(endpoint)
    logger.info("[GET Stage] Hitting GET API: %s", url)

    try:
        timeout = aiohttp.ClientTimeout(total=config.ADMOB_API_TIMEOUT)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=admob_api.ADMOB_GET_HEADERS) as resp:
                status = resp.status
                body = await resp.text()

                if status != 200:
                    logger.error("[GET Stage] GET ads returned HTTP %d: %s", status, body[:500])
                    return []

                try:
                    payload = json.loads(body)
                except json.JSONDecodeError as exc:
                    logger.error("[GET Stage] Invalid JSON response: %s", body[:500])
                    return []

                # Save complete API response object to data/ads.json
                save_api_response_to_ads_json(payload)

                ads = payload.get("data", []) if isinstance(payload.get("data"), list) else []
                
                # Register all ads in AdMod_Data.json upon receipt
                for ad in ads:
                    if isinstance(ad, dict):
                        register_received_ad(ad, storage)

                processed_ids = load_processed_ad_ids()

                unscraped = [
                    ad for ad in ads
                    if isinstance(ad, dict)
                    and ad.get("destination_url")
                    and str(ad.get("ad_id") or ad.get("id") or "") not in processed_ids
                ]

                return unscraped

    except Exception as exc:
        logger.error("[GET Stage] Failed to fetch ads from API: %s", exc, exc_info=True)
        return []


async def run_ads_scraping_pipeline(
    ads: List[Dict[str, Any]],
    browser_mgr: BrowserManager,
    storage: Storage,
    proxy_mgr: ProxyManager
) -> None:
    """Scrape and process API ad objects through full pipeline."""
    target_ads = ads[:config.MAX_ADS_PER_CYCLE] if config.MAX_ADS_PER_CYCLE > 0 else ads
    logger.info("Scraping %d ad(s) (MAX_ADS_PER_CYCLE=%d)...", len(target_ads), config.MAX_ADS_PER_CYCLE)

    scraping_mgr = ScrapingManager(browser_mgr, storage, proxy_mgr)
    success_count = 0
    fail_count = 0

    for idx, ad in enumerate(target_ads, 1):
        ad_id = str(ad.get("ad_id") or ad.get("id") or "?")
        dest = ad.get("destination_url", "?")
        logger.info("--- Ad %d/%d: ad_id=%s destination=%s ---", idx, len(target_ads), ad_id, dest)

        try:
            ok = await scraping_mgr.process_api_ad(ad)
            if ok:
                success_count += 1
                if ad_id != "?":
                    mark_ad_id_processed(ad_id)
            else:
                fail_count += 1
        except Exception as exc:
            # Stage failure logging per ad
            logger.error("[PIPELINE Error] Failed processing ad_id=%s destination=%s: %s", ad_id, dest, exc, exc_info=True)
            fail_count += 1
            continue

        if idx < len(target_ads) and config.TIME_GAP_IN_INSTANCES > 0:
            logger.info("Waiting %.1fs gap before next ad instance...", config.TIME_GAP_IN_INSTANCES)
            await asyncio.sleep(config.TIME_GAP_IN_INSTANCES)

    logger.info("API Ads pipeline finished: %d succeeded, %d failed out of %d ad(s)",
                success_count, fail_count, len(target_ads))


async def main() -> None:
    logger.info("Starting AdMob Multi-Geolocation Advertisement Data Extraction System")
    config.validate_proxy_credentials()

    storage = Storage()
    proxy_mgr = ProxyManager()

    logger.info("Loaded Configuration:")
    logger.info("  HIT_GET_API: %s", config.HIT_GET_API)
    logger.info("  HEADLESS: %s", config.HEADLESS)
    logger.info("  BRIGHT_PROXIES: %s", config.BRIGHT_PROXIES)
    logger.info("  INSTANCES: %d", config.INSTANCES)
    logger.info("  TIME_GAP_IN_INSTANCES: %.1fs", config.TIME_GAP_IN_INSTANCES)
    logger.info("  MAX_ADS_PER_CYCLE: %d", config.MAX_ADS_PER_CYCLE)

    async with BrowserManager() as browser_mgr:
        cycle = 0
        while True:
            cycle += 1
            logger.info("============================================================")
            logger.info("Starting Execution Cycle #%d (HIT_GET_API=%s)", cycle, config.HIT_GET_API)
            logger.info("============================================================")

            ads_to_process: List[Dict[str, Any]] = []

            if config.HIT_GET_API:
                logger.info("[HIT_GET_API=true] Directly calling GET API...")
                ads_to_process = await fetch_and_store_api_ads(storage)
            else:
                logger.info("[HIT_GET_API=false] Checking local cache file %s...", config.ADS_CACHE_FILE)
                ads_to_process = load_ads_from_cache(storage)

                if ads_to_process:
                    logger.info("Found %d uncompleted ad(s) in local %s cache.", len(ads_to_process), config.ADS_CACHE_FILE)
                else:
                    logger.info("No uncompleted ads in %s (or file does not exist). Calling GET API as fallback...", config.ADS_CACHE_FILE)
                    ads_to_process = await fetch_and_store_api_ads(storage)

            if ads_to_process:
                logger.info("Processing %d ad(s) in cycle #%d...", len(ads_to_process), cycle)
                await run_ads_scraping_pipeline(ads_to_process, browser_mgr, storage, proxy_mgr)
            else:
                logger.info("No ads available to process in cycle #%d.", cycle)

            # Continuous retry / polling gap
            gap = max(config.TIME_GAP_IN_INSTANCES, 5.0)
            logger.info("[NO DATA / CYCLE END] Waiting %.1f seconds before next GET API / cycle attempt...", gap)
            await asyncio.sleep(gap)


if __name__ == "__main__":
    asyncio.run(main())
