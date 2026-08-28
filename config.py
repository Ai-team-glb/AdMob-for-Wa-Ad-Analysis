"""
Configuration for the AdMob Multi-Geolocation Web Data Extraction System.

All values here are either safe defaults or loaded from environment
variables (see .env.example). Nothing sensitive is hardcoded here.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

import yaml

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent

# --- Load YAML Configuration ------------------------------------------------
CONFIG_YAML_PATH = BASE_DIR / "config.yaml"
YAML_CONFIG = {}
if CONFIG_YAML_PATH.exists():
    try:
        with open(CONFIG_YAML_PATH, "r", encoding="utf-8") as f:
            YAML_CONFIG = yaml.safe_load(f) or {}
    except Exception as exc:
        print(f"Warning: Could not parse config.yaml: {exc}")

_defaults = YAML_CONFIG.get("default_settings", {})
_net_admob = YAML_CONFIG.get("network", {}).get("admob", {})

# --- Default Settings from YAML / env ----------------------------------------
INSTANCES = int(_defaults.get("INSTANCES", os.getenv("INSTANCES", 10)))
TIME_GAP_IN_INSTANCES = float(_defaults.get("TIME_GAP_IN_INSTANCES", os.getenv("TIME_GAP_IN_INSTANCES", 30)))
DEV_MODE = bool(_defaults.get("DEV_MODE", os.getenv("DEV_MODE", "true").lower() in ("1", "true", "yes")))
HIT_GET_API = bool(_defaults.get("HIT_GET_API", os.getenv("HIT_GET_API", "false").lower() in ("1", "true", "yes")))
BRIGHT_PROXIES = bool(_defaults.get("BRIGHT_PROXIES", os.getenv("BRIGHT_PROXIES", "true").lower() in ("1", "true", "yes")))
MAX_ADS_PER_CYCLE = int(_defaults.get("MAX_ADS_PER_CYCLE", os.getenv("MAX_ADS_PER_CYCLE", 2)))

if "Headless" in _defaults:
    HEADLESS = bool(_defaults["Headless"])
elif "HEADLESS" in _defaults:
    HEADLESS = bool(_defaults["HEADLESS"])
else:
    HEADLESS = os.getenv("HEADLESS", "true").lower() in ("1", "true", "yes")

# --- General -----------------------------------------------------------------
NETWORK = os.getenv("NETWORK", "admob")
DATABASE = os.getenv("DATABASE", "pasdev_admob")

# --- Business rules ------------------------------------------------------------
MIN_SUCCESSFUL_GEOLOCATIONS = int(os.getenv("MIN_SUCCESSFUL_GEOLOCATIONS", 10))

# --- Retry / timeouts ------------------------------------------------------------
MAX_RETRIES = int(os.getenv("MAX_RETRIES", 3))
RETRY_BACKOFF_SECONDS = float(os.getenv("RETRY_BACKOFF_SECONDS", 2))
PAGE_TIMEOUT = int(os.getenv("PAGE_TIMEOUT", 30_000))              # ms
NAVIGATION_TIMEOUT = int(os.getenv("NAVIGATION_TIMEOUT", 30_000))  # ms
GEO_TIMEOUT = int(os.getenv("GEO_TIMEOUT", 10_000))                # ms
BROWSER_START_TIMEOUT = int(os.getenv("BROWSER_START_TIMEOUT", 30_000))  # ms
BROWSER_START_RETRIES = int(os.getenv("BROWSER_START_RETRIES", 3))
MAX_REDIRECTS = int(os.getenv("MAX_REDIRECTS", 30))

# --- Files -----------------------------------------------------------------------
def _resolve(env_key: str, default: Path) -> str:
    """Resolve a file path from env, making relative paths relative to BASE_DIR."""
    raw = os.getenv(env_key)
    if raw is None:
        return str(default)
    p = Path(raw)
    return str(p if p.is_absolute() else BASE_DIR / p)

TARGET_URL_FILE = _resolve("TARGET_URL_FILE", BASE_DIR / "data" / "urls.json")
ADS_CACHE_FILE = _resolve("ADS_CACHE_FILE", BASE_DIR / "data" / "ads.json")
PROCESSED_ADS_FILE = _resolve("PROCESSED_ADS_FILE", BASE_DIR / "data" / "processed_ads.json")
OUTPUT_FILE = _resolve("OUTPUT_FILE", BASE_DIR / "data" / "AdMob_Data.json")
LOG_FILE = _resolve("LOG_FILE", BASE_DIR / "logs" / "scraper.log")

# --- External API URLs from YAML or env --------------------------------------
DEV_GET_API = str(_net_admob.get("DEV_GET_API") or os.getenv("DEV_GET_API", "")).strip()
DEV_UPLOAD_API = str(_net_admob.get("DEV_UPLOAD_API") or _net_admob.get("DEV_S3_API") or os.getenv("DEV_UPLOAD_API", os.getenv("DEV_S3_API", ""))).strip()
DEV_S3_API = DEV_UPLOAD_API
DEV_INSERT_API = str(_net_admob.get("DEV_INSERT_API") or os.getenv("DEV_INSERT_API", "")).strip()

ADMOB_API_BASE_URL = os.getenv("ADMOB_API_BASE_URL", "")
ADMOB_GET_ADS_ENDPOINT = os.getenv("ADMOB_GET_ADS_ENDPOINT", "/api/v1/admob/landers/get_ads_for_blackhat")
ADMOB_UPLOAD_ENDPOINT = os.getenv("ADMOB_UPLOAD_ENDPOINT", "/api/v1/admob/landers/upload_admob_blackhat")
ADMOB_INSERT_ENDPOINT = os.getenv("ADMOB_INSERT_ENDPOINT", "/api/v1/admob/landers/insert_html_content")
ADMOB_API_TIMEOUT = int(os.getenv("ADMOB_API_TIMEOUT", 60))  # seconds
ADMOB_CRAWLED_BY = os.getenv("ADMOB_CRAWLED_BY", ".net")

# --- Post Owner OCR API --------------------------------------------------------
POST_OWNER_OCR_URL = os.getenv("POST_OWNER_OCR_URL", "https://admob-ocr-dev.poweradspy.ai/extract?ocr=false")
POST_OWNER_OCR_API_KEY = os.getenv("ADMOB_OCR_API_KEY") or os.getenv("POST_OWNER_OCR_API_KEY", "")
POST_OWNER_SCREENSHOT_DIR = _resolve("POST_OWNER_SCREENSHOT_DIR", BASE_DIR / "post_owner" / "screenshots")

# --- Screenshot / temp files ----------------------------------------------------------
SCREENSHOT_DIR = _resolve("SCREENSHOT_DIR", BASE_DIR / "data" / "screenshots")

# --- Proxy countries ----------------------------------------------------------------
PROXY_COUNTRIES = [
    "us", "gb", "de", "fr", "in", "jp", "ca", "au", "sg", "it",
    "nl", "es", "br", "mx", "kr", "se", "ch", "ie", "nz", "za",
]

# --- Bright Data ISP proxy credentials (secret — from environment only) --------------
BRIGHTDATA_CUSTOMER = os.getenv("BRIGHTDATA_CUSTOMER", "")
BRIGHTDATA_ZONE = os.getenv("BRIGHTDATA_ZONE", "")
BRIGHTDATA_PASSWORD = os.getenv("BRIGHTDATA_PASSWORD", "")
BRIGHTDATA_HOST = os.getenv("BRIGHTDATA_HOST", "brd.superproxy.io")
BRIGHTDATA_PORT = os.getenv("BRIGHTDATA_PORT", "44445")

# --- Geolocation verification endpoint -------------------------------------------------
GEO_CHECK_URL = "https://geo.brdtest.com/welcome.txt?product=isp&method=native"

# --- WhatsApp URL patterns (publicly documented WhatsApp click-to-chat domains) --------
WHATSAPP_DOMAINS = [
    "wa.me",
    "wa.link",
    "api.whatsapp.com",
    "chat.whatsapp.com",
    "web.whatsapp.com",
    "w.app",
]


def validate_proxy_credentials() -> None:
    """Fail fast and clearly if required secrets are missing."""
    missing = [
        name for name, val in [
            ("BRIGHTDATA_CUSTOMER", BRIGHTDATA_CUSTOMER),
            ("BRIGHTDATA_ZONE", BRIGHTDATA_ZONE),
            ("BRIGHTDATA_PASSWORD", BRIGHTDATA_PASSWORD),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            f"Missing required proxy credentials in environment: {', '.join(missing)}. "
            "Set them in your .env file (see .env.example)."
        )
