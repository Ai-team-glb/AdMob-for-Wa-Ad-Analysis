"""Scraping workflow manager.
Coordinates multiple geolocation observations per target URL, aggregates data,
and drives the full AdMob Lander API pipeline (upload → insert).
Aligns with SRS Sections 1, 4, 7, 8, 9, 10, 27, 28, 33, 34, 48, 49.
"""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from urllib.parse import urlparse

import json
import config
from api import admob_api
from services import url_parser
from pydantic import ValidationError
from services.browser_manager import BrowserManager
from services.html_packager import create_html_zip
from core.models import AdRecord, WhatsAppData, GeoData, AdMobDataRecord
from services.proxy_manager import ProxyManager, normalize_country_code
from engine.scraper import execute_country_observation
from core.storage import Storage

logger = logging.getLogger("admob_scraper")


class ScrapingManager:
    """Manages the full end-to-end extraction lifecycle for target URLs."""

    def __init__(self, browser_mgr: BrowserManager, storage: Storage, proxy_mgr: ProxyManager):
        self.browser_mgr = browser_mgr
        self.storage = storage
        self.proxy_mgr = proxy_mgr

    # ------------------------------------------------------------------
    # ORIGINAL local-file pipeline (preserved for backward-compatibility)
    # ------------------------------------------------------------------

    async def process_target_url(self, target_url: str) -> Optional[AdRecord]:
        """Process one target URL across at least MIN_SUCCESSFUL_GEOLOCATIONS unique countries.
        Aggregates observations into 1 AdRecord with 1 add-id.
        """
        logger.info("==================================================")
        logger.info("Processing Target URL: %s", target_url)
        logger.info("==================================================")

        successful_observations: List[dict] = []
        geolocations: List[GeoData] = []
        all_whatsapp_dict: dict = {}
        best_destination_url: Optional[str] = None
        best_redirect_urls: List[str] = []
        best_campaign_params: dict = {"camplainid": None, "gad_source": None, "gclid": None}

        successful_count = 0

        while successful_count < config.MIN_SUCCESSFUL_GEOLOCATIONS:
            if not self.proxy_mgr.has_unused_country(target_url):
                logger.warning(
                    "Exhausted all available proxy countries for URL: %s. Completed %d/%d geolocations.",
                    target_url, successful_count, config.MIN_SUCCESSFUL_GEOLOCATIONS
                )
                break

            country = self.proxy_mgr.get_random_unused_country(target_url)
            self.proxy_mgr.mark_used(target_url, country)
            logger.info("Selected proxy country: %s (Targeting %d/%d)", country.upper(), successful_count + 1, config.MIN_SUCCESSFUL_GEOLOCATIONS)

            observation_success = False
            for retry_attempt in range(1, config.MAX_RETRIES + 1):
                try:
                    obs = await execute_country_observation(self.browser_mgr, target_url, country)

                    # Geolocation must be valid to count as a successful observation
                    if obs.get("geo_data"):
                        geo_model = GeoData.model_validate(obs["geo_data"])
                        geolocations.append(geo_model)

                    # Aggregate redirects and destination from best available observation
                    if obs.get("destination_url") and not best_destination_url:
                        best_destination_url = obs["destination_url"]
                        best_redirect_urls = obs.get("redirect_urls", [])

                    # Aggregate campaign params
                    cp = obs.get("campaign_params", {})
                    for k in ("camplainid", "gad_source", "gclid"):
                        if cp.get(k) and not best_campaign_params.get(k):
                            best_campaign_params[k] = cp[k]

                    # Deduplicate WhatsApp links
                    for wa in obs.get("whatsapp_data", []):
                        wa_url = wa.get("whatsapp-url")
                        if wa_url and wa_url not in all_whatsapp_dict:
                            all_whatsapp_dict[wa_url] = WhatsAppData.model_validate(wa)

                    successful_observations.append(obs)
                    successful_count += 1
                    observation_success = True
                    logger.info("Successful geolocations: %d/%d", successful_count, config.MIN_SUCCESSFUL_GEOLOCATIONS)
                    break  # Success, move to next country

                except Exception as exc:
                    logger.warning("Attempt %d/%d failed for country %s: %s", retry_attempt, config.MAX_RETRIES, country.upper(), exc)
                    if retry_attempt < config.MAX_RETRIES:
                        await asyncio.sleep(config.RETRY_BACKOFF_SECONDS)

            if not observation_success:
                logger.info("Moving to next country for %s", target_url)

        # Handle incomplete or successful record generation
        if successful_count == 0:
            logger.error("Failed to obtain any successful geolocations for %s", target_url)
            return None

        ad_id = str(self.storage.next_ad_id())
        dest_url = best_destination_url or target_url

        # Build WhatsApp info
        whatsapp_info = {}
        if all_whatsapp_dict:
            first_wa = list(all_whatsapp_dict.values())[0]
            wa_dict = first_wa.model_dump(by_alias=True) if hasattr(first_wa, "model_dump") else dict(first_wa)
            wa_url_str = wa_dict.get("whatsapp-url", "")
            try:
                parsed_wa = urlparse(wa_url_str)
                from urllib.parse import parse_qs
                wa_qs = parse_qs(parsed_wa.query)
                whatsapp_info = {
                    "domain": parsed_wa.netloc,
                    "path": parsed_wa.path,
                    "phone": wa_dict.get("whatsapp-number", ""),
                    "message": wa_dict.get("whatsapp-message", ""),
                    "parameters": {
                        "phone": wa_dict.get("whatsapp-number", ""),
                        "text": wa_dict.get("whatsapp-message", ""),
                        "type": "phone_number",
                        **{k: v[0] if len(v) == 1 else v for k, v in wa_qs.items()},
                    },
                }
            except Exception:
                whatsapp_info = {}

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        admob_data_record = {
            "ad_id": str(ad_id),
            "status": 2,
            "platform": "12",
            "destinations": dest_url,
            "html_path": "",
            "screen_shot": "",
            "html_content": "",
            "domain_registered_date": None,
            "domain_age": 0,
            "country_iso": [g.country.upper() for g in geolocations if getattr(g, "country", None)],
            "outgoing_url": [
                {
                    "start_url": target_url,
                    "redirect_urls": best_redirect_urls[1:] if len(best_redirect_urls) > 1 else [],
                    "destination_url": dest_url,
                }
            ] if best_redirect_urls else [],
            "redirects": best_redirect_urls if best_redirect_urls else ["NA"],
            "source_app": "crex",
            "whatsapp": [],
            "campaign_id": best_campaign_params.get("camplainid", "") or "",
            "created": now_iso,
            "updated": now_iso,
        }

        self.storage.upsert_record(admob_data_record)
        logger.info("Successfully persisted 1 advertisement payload to AdMob_Data.json for %s (ad_id=%s, geolocations=%d)", target_url, ad_id, len(geolocations))
        return admob_data_record

    # ------------------------------------------------------------------
    # API-driven pipeline: GET ads → SCRAPE → UPLOAD → INSERT
    # ------------------------------------------------------------------

    async def process_api_ad(self, ad_data: Dict[str, Any]) -> bool:
        """Process a single ad from the API through the full lander pipeline.

        Returns True on success, False on failure (pipeline continues to next ad).
        """
        ad_id = str(ad_data.get("ad_id", ad_data.get("id", "")))
        destination_url = ad_data.get("destination_url", "")
        countries = ad_data.get("country", [])
        db_id = ad_data.get("id")

        if not ad_id or not destination_url:
            logger.error("Skipping ad with missing ad_id or destination_url: %s", ad_data)
            return False

        logger.info("=" * 60)
        logger.info("API Pipeline: ad_id=%s destination=%s countries=%s", ad_id, destination_url, countries)
        logger.info("=" * 60)

        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Update record in AdMob_Data.json when scraping starts (status = 1 if fresh, preserve 2 if repeat)
        existing_rec = self.storage.get_record(ad_id)
        current_status = 1
        created_timestamp = now_iso
        if existing_rec:
            created_timestamp = existing_rec.get("created") or now_iso
            if existing_rec.get("status") == 2:
                current_status = 2

        initial_record: Dict[str, Any] = {
            "ad_id": str(ad_id),
            "status": current_status,
            "platform": str(ad_data.get("platform", "12")),
            "destinations": destination_url,
            "html_path": "",
            "screen_shot": "",
            "html_content": "",
            "domain_registered_date": ad_data.get("domain_registered_date"),
            "domain_age": int(ad_data.get("domain_age") or 0),
            "country_iso": [normalize_country_code(c).upper() for c in countries] if countries else ["IN"],
            "outgoing_url": [],
            "redirects": [],
            "source_app": str(ad_data.get("source_app") or ad_data.get("app_name") or "crex"),
            "whatsapp": [],
            "campaign_id": str(ad_data.get("campaign_id") or ""),
            "created": created_timestamp,
            "updated": now_iso,
        }
        try:
            self.storage.upsert_record(initial_record)
            logger.info("Updated AdMob_Data.json record for ad_id=%s (status=%d)", ad_id, current_status)
        except Exception as exc:
            logger.warning("Could not update AdMob_Data.json record for ad_id=%s: %s", ad_id, exc)

        # Determine which countries to scrape
        scrape_countries = [normalize_country_code(c) for c in countries] if countries else [config.PROXY_COUNTRIES[0]]

        screenshot_dir = Path(config.SCREENSHOT_DIR)
        temp_files: List[str] = []  # track temp ZIP files for cleanup

        # --- STEP 1: SCRAPE the destination URL for the first country ---
        best_obs: Optional[Dict[str, Any]] = None
        all_whatsapp_data: List[dict] = []
        all_whatsapp_links: List[str] = []
        all_phone_numbers: List[str] = []
        all_contact_buttons: List[dict] = []
        all_redirect_urls: List[str] = []
        geo_data_with_vpn: Optional[Dict[str, Any]] = None
        primary_country_iso = normalize_country_code(countries[0]).upper() if countries else "US"

        for country_code in scrape_countries:
            logger.info("Scraping ad_id=%s via proxy country=%s", ad_id, country_code.upper())

            for attempt in range(1, config.MAX_RETRIES + 1):
                try:
                    obs = await execute_country_observation(
                        self.browser_mgr,
                        destination_url,
                        country_code,
                        screenshot_dir=screenshot_dir,
                        ad_id_for_screenshot=ad_id,
                    )

                    # Keep first successful observation as primary
                    if best_obs is None:
                        best_obs = obs

                    # Aggregate geo data
                    if obs.get("geo_data"):
                        geo_data_with_vpn = obs["geo_data"]

                    # Aggregate redirects
                    for r in obs.get("redirect_urls", []):
                        if r not in all_redirect_urls:
                            all_redirect_urls.append(r)

                    # Aggregate WhatsApp
                    for wa in obs.get("whatsapp_data", []):
                        wa_url = wa.get("whatsapp-url", "")
                        if wa_url and wa_url not in all_whatsapp_links:
                            all_whatsapp_links.append(wa_url)
                            all_whatsapp_data.append(wa)

                    # Aggregate phone numbers
                    for pn in obs.get("phone_numbers", []):
                        if pn not in all_phone_numbers:
                            all_phone_numbers.append(pn)

                    # Aggregate contact buttons
                    seen_hrefs = {b["href"] for b in all_contact_buttons}
                    for cb in obs.get("contact_buttons", []):
                        if cb.get("href") and cb["href"] not in seen_hrefs:
                            all_contact_buttons.append(cb)
                            seen_hrefs.add(cb["href"])

                    logger.info("Scrape completed for ad_id=%s country=%s", ad_id, country_code.upper())
                    break  # success

                except Exception as exc:
                    logger.warning("Scrape attempt %d/%d failed for ad_id=%s country=%s: %s",
                                  attempt, config.MAX_RETRIES, ad_id, country_code.upper(), exc)
                    if attempt < config.MAX_RETRIES:
                        await asyncio.sleep(config.RETRY_BACKOFF_SECONDS)

        if best_obs is None:
            logger.error("All scrape attempts failed for ad_id=%s", ad_id)
            return False

        logger.info("Scraping completed for ad_id=%s", ad_id)

        # --- STEP 2: SCREENSHOT (captured and saved locally as screenshots/<ad_id>.png) ---
        screenshot_path = best_obs.get("screenshot_path")
        if screenshot_path:
            logger.info("Screenshot generated and stored locally: %s", screenshot_path)
        else:
            logger.warning("No screenshot available for ad_id=%s", ad_id)

        # --- STEP 3: HTML ZIP ---
        rendered_html = best_obs.get("rendered_html", "")
        zip_path: Optional[str] = None
        if rendered_html:
            try:
                zip_file = create_html_zip(rendered_html, ad_id, screenshot_dir)
                zip_path = str(zip_file)
                temp_files.append(zip_path)
                logger.info("ZIP generated: %s", zip_path)
            except Exception as exc:
                logger.error("Failed to create HTML ZIP for ad_id=%s: %s", ad_id, exc)

        # --- STEP 4: UPLOAD media + ZIP via existing DB/API flow ---
        image_path_remote = ""
        html_path_remote = ""

        if screenshot_path or zip_path:
            try:
                status_code = 2  # normal lander content
                upload_result = await admob_api.upload_media(
                    ad_id=ad_id,
                    status=status_code,
                    country_iso=primary_country_iso,
                    media_path=screenshot_path,
                    zip_path=zip_path,
                )
                image_path_remote = upload_result.get("image_path", "")
                html_path_remote = upload_result.get("html_path", "")
                logger.info("Upload completed — image_path=%s html_path=%s", image_path_remote, html_path_remote)
            except Exception as exc:
                logger.error("Upload failed for ad_id=%s: %s", ad_id, exc)
                # Continue — we can still try to insert with what we have
        else:
            logger.warning("No media/ZIP to upload for ad_id=%s", ad_id)

        # --- STEP 5: BUILD payloads ---
        campaign_params = best_obs.get("campaign_params", {})
        dest_url = best_obs.get("destination_url", destination_url)

        # Build WhatsApp info from first detected link for insertData API compatibility
        whatsapp_info: Dict[str, Any] = {}
        whatsapp_texts: List[str] = []
        whatsapp_list: List[Dict[str, Any]] = []

        if all_whatsapp_data:
            first_wa = all_whatsapp_data[0]
            wa_url_str = first_wa.get("whatsapp-url", "")
            try:
                parsed_wa = urlparse(wa_url_str)
                from urllib.parse import parse_qs
                wa_qs = parse_qs(parsed_wa.query)
                whatsapp_info = {
                    "domain": parsed_wa.netloc,
                    "path": parsed_wa.path,
                    "phone": first_wa.get("whatsapp-number") or "",
                    "message": first_wa.get("whatsapp-message") or "",
                    "parameters": {
                        "phone": first_wa.get("whatsapp-number") or "",
                        "text": first_wa.get("whatsapp-message") or "",
                        "type": "phone_number" if first_wa.get("whatsapp-number") else "",
                        **{k: v[0] if len(v) == 1 else v for k, v in wa_qs.items()},
                    },
                }
            except Exception:
                whatsapp_info = {}

            # Build whatsapp array for new AdMob_Data.json schema
            for wa in all_whatsapp_data:
                msg = wa.get("whatsapp-message")
                if msg and msg not in whatsapp_texts:
                    whatsapp_texts.append(msg)

                wa_url = wa.get("whatsapp-url", "")
                try:
                    p_wa = urlparse(wa_url)
                    btn_text = ""
                    for cb in all_contact_buttons:
                        if cb.get("href") == wa_url or p_wa.netloc in cb.get("href", ""):
                            btn_text = cb.get("text", "")
                            break

                    whatsapp_list.append({
                        "domain": p_wa.netloc,
                        "path": wa_url,
                        "phone": str(wa.get("whatsapp-number") or ""),
                        "button": btn_text,
                        "message": str(wa.get("whatsapp-message") or ""),
                        "first_detected": now_iso,
                        "last_detected": now_iso,
                        "state": primary_country_iso,
                        "city": primary_country_iso,
                        "countrty": primary_country_iso,
                    })
                except Exception:
                    pass

        # Build outgoing_url
        outgoing_url: List[Dict[str, Any]] = []
        if all_redirect_urls:
            outgoing_url.append({
                "start_url": destination_url,
                "redirect_urls": all_redirect_urls[1:] if len(all_redirect_urls) > 1 else [],
                "destination_url": all_redirect_urls[-1] if all_redirect_urls else dest_url,
            })
        else:
            outgoing_url.append({
                "start_url": destination_url,
                "redirect_urls": [],
                "destination_url": dest_url,
            })

        # Build redirects — contract shows ["NA"] when there are no actual redirects
        redirects = all_redirect_urls if all_redirect_urls else [destination_url]

        # Build location (VPN data)
        location: Dict[str, Any] = {}
        if geo_data_with_vpn:
            location["with_vpn"] = {
                "ip": "",  # IP not returned by geo endpoint
                "country": geo_data_with_vpn.get("country", ""),
                "country_code": geo_data_with_vpn.get("country", ""),
            }
            location["without_vpn"] = {}  # No direct scrape in current architecture

        # Build comparison
        comparison: Dict[str, Any] = {}
        if location.get("with_vpn") and location.get("without_vpn"):
            comparison = {
                "location_changed": False,
                "country_changed": False,
                "whatsapp_data_changed": False,
                "campaign_id_changed": False,
            }

        # Source info — contract shows full URL for source_website
        source_website = destination_url
        source_parameters = url_parser.extract_source_params(destination_url)

        # Campaign ID
        campaign_id = campaign_params.get("camplainid", "") or str(ad_data.get("campaign_id") or "")

        # Country ISO list from API
        country_iso = [normalize_country_code(c).upper() for c in countries] if countries else [primary_country_iso]

        # WhatsApp rotator detection — only if we have actual evidence
        unique_wa_phones = set()
        for wa in all_whatsapp_data:
            num = wa.get("whatsapp-number")
            if num:
                unique_wa_phones.add(num)
        whatsapp_rotator_detected = len(unique_wa_phones) > 1
        whatsapp_rotator_phone_count = len(unique_wa_phones) if whatsapp_rotator_detected else 0

        # Visible text content for html_content
        rendered_text = best_obs.get("rendered_text", "")

        # --- Build the insertData payload for existing DB/API posting ---
        insert_data: Dict[str, Any] = {
            "ad_id": str(ad_id),
            "status": 2,
            "platform": str(ad_data.get("platform") or "12"),
            "source_app": str(ad_data.get("source_app") or ad_data.get("app_name") or "crex"),
            "crawled_by": config.ADMOB_CRAWLED_BY,
            "destinations": dest_url,
            "html_path": html_path_remote,
            "screen_shot": image_path_remote,
            "html_content": rendered_text,
            "domain_registered_date": ad_data.get("domain_registered_date"),
            "domain_age": int(ad_data.get("domain_age") or 0),
            "country_iso": country_iso,
            "outgoing_url": outgoing_url,
            "redirects": redirects,
            "ad_category": None,
            "source_website": source_website,
            "source_parameters": source_parameters,
            "whatsapp": whatsapp_info,
            "campaign_id": campaign_id,
            "location": location,
            "comparison": comparison,
            "whatsapp_links": all_whatsapp_links,
            "whatsapp_texts": whatsapp_texts,
            "phone_numbers": all_phone_numbers,
            "contact_buttons": all_contact_buttons,
            "whatsapp_rotator_detected": whatsapp_rotator_detected,
            "whatsapp_rotator_phone_count": whatsapp_rotator_phone_count,
            "lead_campaign_tag": "",
        }

        # --- Build NEW AdMob_Data.json record format ---
        updated_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        admob_data_record: Dict[str, Any] = {
            "ad_id": str(ad_id),
            "status": 2,  # 2 = repeat / completed
            "platform": str(ad_data.get("platform", "12")),
            "destinations": dest_url,
            "html_path": html_path_remote,
            "screen_shot": image_path_remote or screenshot_path or "",
            "html_content": rendered_text,
            "domain_registered_date": ad_data.get("domain_registered_date"),
            "domain_age": int(ad_data.get("domain_age") or 0),
            "country_iso": country_iso,
            "outgoing_url": [],
            "redirects": redirects,
            "source_app": str(ad_data.get("source_app") or ad_data.get("app_name") or "crex"),
            "whatsapp": whatsapp_list,
            "campaign_id": campaign_id,
            "created": created_timestamp,
            "updated": updated_iso,
        }

        # --- Pydantic Validation & Local Persistence in data/AdMob_Data.json ---
        try:
            validated_model = AdMobDataRecord.model_validate(admob_data_record)
            logger.info("Pydantic validation PASSED for ad_id=%s", ad_id)
            validated_payload = validated_model.model_dump()

            # Save single validated payload to data/validated_payload.json
            try:
                val_file = Path(config.OUTPUT_FILE).parent / "validated_payload.json"
                val_file.write_text(json.dumps(validated_payload, indent=2, ensure_ascii=False), encoding="utf-8")
                logger.info("Saved single validated payload to %s", val_file)
            except Exception as exc:
                logger.warning("Could not write to validated_payload.json: %s", exc)

            self.storage.upsert_record(validated_payload)
            logger.info("Persisted validated AdMob_Data.json record locally for ad_id=%s", ad_id)
        except ValidationError as err:
            logger.error("Pydantic validation FAILED for ad_id=%s: %s", ad_id, err)
            for error in err.errors():
                logger.error("  Field: %s | Error: %s | Msg: %s", '.'.join(map(str, error['loc'])), error['type'], error['msg'])
            self.storage.upsert_record(admob_data_record)

        # --- Validate required fields before sending to API ---
        missing_fields = []
        if not insert_data.get("ad_id"):
            missing_fields.append("ad_id")
        if not insert_data.get("crawled_by"):
            missing_fields.append("crawled_by")
        if insert_data.get("status") in (1, 2):
            if not insert_data.get("destinations"):
                missing_fields.append("destinations")
            if not insert_data.get("screen_shot"):
                missing_fields.append("screen_shot")
            if not insert_data.get("html_content"):
                missing_fields.append("html_content")

        if missing_fields:
            logger.error("Insert payload missing required fields for ad_id=%s: %s", ad_id, missing_fields)
            if "screen_shot" in missing_fields or "html_content" in missing_fields:
                logger.info("Switching to status=3 (redirect-only) for ad_id=%s", ad_id)
                insert_data["status"] = 3

        # --- STEP 6: POST insert_html_content (Existing DB/API insertion flow) ---
        try:
            result = await admob_api.insert_lander(ad_id, insert_data)
            api_data = result.get("data", {})
            logger.info(
                "Pipeline COMPLETE for ad_id=%s — mysql_saved=%s elastic_indexed=%s redirect_status=%s",
                ad_id,
                api_data.get("mysql_saved"),
                api_data.get("elastic_indexed"),
                api_data.get("redirect_status"),
            )
        except Exception as exc:
            logger.error("Insert failed for ad_id=%s: %s", ad_id, exc)
            return False
        finally:
            # --- STEP 7: CLEANUP temp files (ZIP files only; local screenshots are preserved) ---
            self._cleanup_temp_files(temp_files)

        return True

    @staticmethod
    def _cleanup_temp_files(file_paths: List[str]) -> None:
        """Remove temporary screenshot/ZIP files after successful upload."""
        for fp in file_paths:
            try:
                p = Path(fp)
                if p.exists():
                    p.unlink()
                    logger.debug("Cleaned up temp file: %s", fp)
            except Exception as exc:
                logger.warning("Failed to clean up temp file %s: %s", fp, exc)
