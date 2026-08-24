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
        log_path, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    return logger
