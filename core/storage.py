"""JSON persistence layer: loading, atomic writes, ID generation, resume support.
Stores records in the exact insertData envelope format:
[
  {
    "ad_id": "...",
    "insertData": { ... }
  }
]
"""
from __future__ import annotations
import json
import logging
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import config

logger = logging.getLogger("admob_scraper")


class Storage:
    """Manages atomic JSON file storage for AdMob_Data.json."""

    def __init__(self, path: str = None):
        self.path = Path(path or config.OUTPUT_FILE)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.records: List[Dict[str, Any]] = self._load_or_init()

    def _load_or_init(self) -> List[Dict[str, Any]]:
        if self.path.exists():
            try:
                raw_text = self.path.read_text(encoding="utf-8").strip()
                if not raw_text:
                    return []
                raw = json.loads(raw_text)
                if isinstance(raw, list):
                    return raw
                elif isinstance(raw, dict) and "ads" in raw:
                    return raw["ads"]
            except Exception as exc:
                logger.error("Existing %s is invalid/corrupt (%s); starting fresh in memory.", self.path, exc)
        return []

    def next_ad_id(self) -> int:
        """Generate monotonic integer ID for local mode."""
        if not self.records:
            return 1
        ids = []
        for r in self.records:
            if isinstance(r, dict):
                aid = r.get("ad_id") or r.get("insertData", {}).get("ad_id") or r.get("add_id")
                try:
                    ids.append(int(aid))
                except (TypeError, ValueError):
                    pass
        return max(ids) + 1 if ids else 1

    def get_record(self, ad_id: str) -> Optional[Dict[str, Any]]:
        """Find an existing record by ad_id in AdMob_Data.json."""
        target_id = str(ad_id).strip()
        if not target_id:
            return None
        for item in self.records:
            if isinstance(item, dict):
                item_ad_id = str(item.get("ad_id") or item.get("insertData", {}).get("ad_id") or "").strip()
                if item_ad_id == target_id:
                    return item
        return None

    def upsert_record(self, record: Dict[str, Any]) -> None:
        """Upsert (insert or update) an ad record by ad_id in AdMob_Data.json.
        Preserves the original `created` timestamp if updating an existing record.
        """
        ad_id = str(record.get("ad_id", "")).strip()
        if not ad_id:
            self.records.append(record)
            self._atomic_write()
            return

        updated = False
        for idx, item in enumerate(self.records):
            if isinstance(item, dict):
                item_ad_id = str(item.get("ad_id") or item.get("insertData", {}).get("ad_id") or "").strip()
                if item_ad_id == ad_id:
                    # Preserve original `created` timestamp if present in existing record
                    if isinstance(item, dict) and item.get("created"):
                        record["created"] = item["created"]
                    self.records[idx] = record
                    updated = True
                    break

        if not updated:
            self.records.append(record)

        self._atomic_write()

    def append_payload(self, payload: Dict[str, Any]) -> None:
        """Append or update payload in local JSON file."""
        self.upsert_record(payload)

    def is_url_completed(self, url: str) -> bool:
        """Check if target URL/destination or ad_id is already completed in local storage."""
        if not url:
            return False
        clean_url = str(url).strip()
        for item in self.records:
            if isinstance(item, dict):
                insert_data = item.get("insertData", item)
                dest = insert_data.get("destinations") or insert_data.get("url") or item.get("url")
                if dest and str(dest).strip() == clean_url:
                    return True
                ad_id = item.get("ad_id") or insert_data.get("ad_id")
                if ad_id and str(ad_id).strip() == clean_url:
                    return True
        return False

    def get_completed_urls(self) -> Set[str]:
        urls = set()
        for item in self.records:
            if isinstance(item, dict):
                insert_data = item.get("insertData", item)
                dest = insert_data.get("destinations") or insert_data.get("url") or item.get("url")
                if dest:
                    urls.add(str(dest).strip())
        return urls

    @property
    def count(self) -> int:
        return len(self.records)

    def _atomic_write(self) -> None:
        """Atomic write: write temp file -> validate JSON -> replace target file."""
        dir_ = self.path.parent
        fd, tmp_path = tempfile.mkstemp(prefix=".tmp_admob_", dir=dir_, suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self.records, f, indent=2, ensure_ascii=False)
            with open(tmp_path, "r", encoding="utf-8") as f:
                json.load(f)  # validate before swap

            replaced = False
            for _ in range(3):
                try:
                    os.replace(tmp_path, self.path)
                    replaced = True
                    break
                except PermissionError:
                    time.sleep(0.1)

            if not replaced:
                shutil.copyfile(tmp_path, self.path)
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
        except Exception:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
            raise

