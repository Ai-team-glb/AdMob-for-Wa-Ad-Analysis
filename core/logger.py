"""Structured logging setup: console output + rotating log file."""
import logging
import logging.handlers
from pathlib import Path

import config


def setup_logger() -> logging.Logger:
    logger = logging.getLogger("admob_scraper")
    if logger.handlers:
        return logger  # already configured (e.g. re-imported)

    logger.setLevel(logging.INFO)

    fmt = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")

    console = logging.StreamHandler()
    console.setFormatter(fmt)
    logger.addHandler(console)

    log_path = Path(config.LOG_FILE)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.handlers.RotatingFileHandler(
        log_path, maxBytes=5_000_000, backupCount=20, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger


import json
from typing import Any, Dict


def log_insert_transaction(
    ad_data: Dict[str, Any],
    insert_data: Dict[str, Any],
    api_response: Any,
) -> None:
    """Persist one JSONL line per ad insert transaction to logs/api_transactions.jsonl.

    Structure: {"request": <ads.json object>, "payload": <insert payload>, "post_api_response": <API response>}

    This function is observational only.  If writing fails the main pipeline
    continues unaffected.
    """
    try:
        # request = the original ad object from ads.json (pass-through, no transform)
        request_obj = ad_data

        # payload = a sanitised copy of the insert payload for audit logging.
        # outgoing_url is excluded (always empty list in log, not useful for audit).
        # crawled_by is an internal field not meant for the transaction log.
        payload_obj = {
            k: ([] if k == "outgoing_url" else v)
            for k, v in insert_data.items()
            if k != "crawled_by"
        }

        # post_api_response = the actual API response body
        response_obj: Any = None
        if api_response is not None:
            if isinstance(api_response, str):
                try:
                    response_obj = json.loads(api_response)
                except (json.JSONDecodeError, ValueError):
                    response_obj = api_response
            else:
                response_obj = api_response

        transaction = {
            "request": request_obj,
            "payload": payload_obj,
            "post_api_response": response_obj,
        }

        log_dir = Path(config.LOG_FILE).parent
        log_dir.mkdir(parents=True, exist_ok=True)
        jsonl_path = log_dir / "api_transactions.jsonl"

        line = json.dumps(transaction, ensure_ascii=False, default=str)
        with open(jsonl_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()

    except Exception as exc:
        _logger = logging.getLogger("admob_scraper")
        _logger.warning("[JSONL Logging] Failed to write API transaction log: %s", exc)
