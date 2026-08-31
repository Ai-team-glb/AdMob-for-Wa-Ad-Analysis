# AdMob Multi-Geolocation Web Data Extraction & Lander Pipeline System

An enterprise-grade, automated **Playwright** scraping engine and lander ingestion pipeline built in Python. The system fetches target ads from external AdMob lander APIs (or local caches), navigates destination URLs through country-pinned **Bright Data ISP Proxies**, follows redirect chains, performs extensive pre-rendering triggers (keyboard actions, lazy-load expansion), captures full-page & header screenshots, packages rendered HTML, extracts campaign metadata, WhatsApp links & rotators, contacts, phone numbers, conducts post-owner OCR analysis, retrieves exit-node IP geolocation, validates payloads with **Pydantic**, atomically persists records, uploads media/lander packages, commits structured records to backend AdMob APIs, and maintains synchronous JSONL transaction audit logs.

---

## 1. System Architecture & End-to-End Pipeline

```
                                CONFIG & ENVIRONMENT
                        (config.yaml / .env / urls.json)
                                       │
                                       ▼
                             MAIN EXECUTION CYCLE
                                  (main.py)
                                       │
                ┌──────────────────────┴──────────────────────┐
                ▼                                             ▼
       HIT_GET_API = true                            HIT_GET_API = false
  Fetch batch from GET API                    Check local data/ads.json cache
  (Cache raw -> data/ads.json)                (Fallback to GET API if empty)
                │                                             │
                └──────────────────────┬──────────────────────┘
                                       │
                                       ▼
                       FILTER UNPROCESSED AD BATCH
                 (Exclude data/processed_ads.json entries)
                                       │
                                       ▼
                     REGISTER ADS IN AdMob_Data.json
                             (status: 0 = Fresh)
                                       │
                                       ▼
                   SCRAPING MANAGER (engine/scraping_manager.py)
               ┌───────────────────────────────────────────────┐
               │  For each Ad Record in batch:                 │
               │                                               │
               │  1. STATUS UPDATE -> status: 1 (Scraping)     │
               │                                               │
               │  2. PLAYWRIGHT NAVIGATION (engine/scraper.py) │
               │     • Bright Data ISP Proxy (Pinned ISO)      │
               │     • Ad-tracker Request Aborting             │
               │     • Direct Connection Fallback on Timeout   │
               │     • Redirect Chain & Loop Tracking          │
               │     • 404 / 4xx / 5xx HTTP Error Detection    │
               │     • CAPTCHA / Access Challenge Detection    │
               │                                               │
               │  3. PAGE PRE-RENDERING & ASSET EXPANSION      │
               │     • 3x Incremental Viewport Scroll          │
               │     • Keyboard 'End' (Bottom Lazy Trigger)    │
               │     • Keyboard 'Home' (Scroll Back to Top)    │
               │     • Force Lazy-Image Loading & Font Ready   │
               │                                               │
               │  4. DATA EXTRACTION & ANALYSIS                │
               │     • Cleaned Visible Body Text Content       │
               │     • Full-Page Screenshot (.png)             │
               │     • Upper Viewport Header Screenshot (.webp)│
               │     • Campaign Params (camplainid, etc.)      │
               │     • WhatsApp Links & Shortlink Resolution   │
               │     • WhatsApp Rotator Detection & Count      │
               │     • Phone Numbers & Contact Buttons         │
               │     • Exit IP & ASN Geolocation Verification  │
               │                                               │
               │  5. POST-OWNER OCR EXTRACTION (services/ocr)  │
               │     • Isolated OCR API Query (Non-fatal)      │
               │                                               │
               │  6. HTML ZIP PACKAGING (services/html_packager)│
               │     • Generate <ad_id>_lander.zip             │
               │                                               │
               │  7. ASSET UPLOAD (api/admob_api.py)           │
               │     • POST /upload_admob_blackhat (Multipart) │
               │                                               │
               │  8. PYDANTIC VALIDATION & ATOMIC PERSISTENCE  │
               │     • Validate Schema (AdMobDataRecord)       │
               │     • Atomic Write -> data/AdMob_Data.json    │
               │     • Snapshot -> data/validated_payload.json │
               │     • Track Processed -> processed_ads.json   │
               │                                               │
               │  9. INGESTION INSERT API & AUDIT LOGGING      │
               │     • POST /insert_html_content (JSON)        │
               │     • Write Transaction -> api_transactions   │
               │                                               │
               │  10. CLEANUP                                  │
               │     • Remove temporary ZIP (keep screenshots) │
               └───────────────────────────────────────────────┘
                                       │
                                       ▼
                       CYCLE INTERVAL / POLL SLEEP
               (Sleep TIME_GAP_IN_INSTANCES if no ads; repeat)
```

---

## 2. Directory & Project Structure

```text
.
├── main.py                     # Main entry point: continuous pipeline loop & batch orchestrator
├── config.py                   # Configuration loader merging config.yaml (dev/prod) and .env
├── config.yaml                 # YAML runtime settings, mode flags, and API endpoint overrides
├── config.yaml.example         # Example YAML configuration template
├── .env                        # Environment variables and private proxy credentials (git-ignored)
├── .env.example                # Example environment variable template
├── requirements.txt            # Python dependencies (Playwright, Pydantic, Aiohttp, PyYAML, Dotenv)
├── README.md                   # Comprehensive system documentation
├── SRS.txt                     # Software Requirements Specification (SRS 2.0)
│
├── MD/                         # Documentation Directory
│   ├── CODEBASE_EXPLANATION.md # Detailed breakdown of all files, classes, and functions
│   └── config.md               # Line-by-line explanation of config.py (Lines 1 to 172)
│
├── api/                        # External API Client Layer
│   ├── __init__.py
│   └── admob_api.py            # Async HTTP client for GET, Upload (multipart), and Insert APIs
│
├── core/                       # Core Architecture & Infrastructure
│   ├── __init__.py
│   ├── models.py               # Pydantic data schemas (AdMobDataRecord, AdRecord, WhatsAppData, GeoData)
│   ├── storage.py              # Atomic JSON storage engine for data/AdMob_Data.json
│   ├── error_handler.py        # Error categorization Enum (20 types), exceptions, and classifier
│   ├── logger.py               # Rotating file logger & JSONL API transaction audit logger
│   └── retry.py                # Generic async retry decorator with linear backoff
│
├── engine/                     # Scraping Engine & Pipeline Orchestration
│   ├── __init__.py
│   ├── scraper.py              # Single observation executor: navigation, pre-rendering & extraction
│   └── scraping_manager.py     # Multi-geolocation lifecycle, aggregation, and API pipeline manager
│
├── services/                   # Modular Helper Services
│   ├── __init__.py
│   ├── browser_manager.py      # Playwright driver lifecycle, context isolation, and crash recovery
│   ├── proxy_manager.py        # Bright Data ISP proxy rotation, credentials & ISO normalization
│   ├── geo_service.py          # Bright Data exit IP/ASN geolocation verification
│   ├── redirect_tracker.py     # Main-frame navigation listener & redirect loop protection
│   ├── url_parser.py           # Campaign & source parameter extraction
│   ├── whatsapp_parser.py      # WhatsApp links, shortlink HTTP resolution, and deduplication
│   ├── html_packager.py        # HTML ZIP bundler
│   └── ocr_service.py          # Post-Owner OCR recognition client
│
├── logs/                       # Application & Audit Logs
│   ├── scraper.log             # Rotating application log file (max 5MB, up to 20 backups)
│   └── api_transactions.jsonl  # Synchronous JSONL audit log of all API request/response transactions
│
└── data/                       # Local Runtime Data, Cache & Artifacts
    ├── urls.json               # Input target URL list (standalone mode)
    ├── ads.json                # Cached raw responses from GET API
    ├── processed_ads.json      # List of processed ad_ids (prevents duplicate scraping)
    ├── AdMob_Data.json         # Main persisted JSON output storage
    ├── validated_payload.json  # Snapshot of the most recently validated payload
    └── screenshots/            # Full-page destination screenshots (<ad_id>.png)
```

---

## 3. Core Features & Capabilities

- **Dual-Mode Execution & Continuous Polling**:
  - **API Mode (`HIT_GET_API=true`)**: Continuously polls the AdMob lander API for fresh ads, writes complete responses to `data/ads.json`, processes ads, marks them in `data/processed_ads.json`, and seamlessly cycles with configurable interval delays (`TIME_GAP_IN_INSTANCES`).
  - **Cache Mode (`HIT_GET_API=false`)**: Reads unscraped records from local cache `data/ads.json` before falling back to GET API.
  - **Standalone Mode**: Supports local URL processing from `data/urls.json` across 10 unique proxy geolocations per URL.
- **Intelligent Proxy Management & Country Routing**:
  - Bright Data ISP Proxy integration with country-pinned authentication (`brd-customer-<customer>-zone-<zone>-country-<iso>`).
  - Country code normalization supporting full country names (`India` -> `in`, `United States` -> `us`, etc.) and ISO2 codes.
  - Tracker/ad-network request aborting (`googletagmanager`, `doubleclick`, `facebook`, etc.) to accelerate tunnel loading.
  - Direct connection fallback if proxy connection times out.
- **Robust Navigation & Error Handling**:
  - **Redirect Tracking**: Real-time main-frame navigation tracker detecting every hop URL and preventing redirect loops (`MAX_REDIRECTS = 30`).
  - **404 & Unfetchable Page Detection**: Evaluates HTTP status codes (404, 410, 403, 5xx) and DOM error signatures (`"404 not found"`, `"site not found"`, `"502 bad gateway"`). Automatically marks records as `status: 3` and reports them to the ingestion API.
  - **CAPTCHA & Challenge Detection**: Flags Cloudflare/reCAPTCHA challenges without attempting unauthorized circumvention.
  - **Browser Driver Recovery**: Self-healing browser manager that handles driver disconnections (`Connection closed`) with automatic restarts and retries.
- **Advanced Pre-Rendering Engine**:
  - Incremental 3-step viewport scrolling.
  - Keyboard trigger `End` to force bottom elements and lazy components into DOM view.
  - Keyboard trigger `Home` to return viewport to the top.
  - Forces removal of `loading="lazy"` attributes and waits for `document.fonts.ready` and network idle states before capture.
- **Complete Data Extraction**:
  - **Campaign Parameters**: Extracts `camplainid` (from `gad_campaignid`, `campaign_id`, `camplainid`), `gad_source`, and `gclid`.
  - **Source Parameters**: Extracts flat dictionary of all URL query parameters.
  - **WhatsApp Links & Shortlinks**: Scans `<a>`, `<button>`, `[data-href]`, `[onclick]` for WhatsApp domains (`wa.me`, `wa.link`, `api.whatsapp.com`, `chat.whatsapp.com`, `web.whatsapp.com`, `w.app`).
  - **Shortlink HTTP Resolution**: Resolves shortlinks to extract phone number (`whatsapp-number`), custom prefilled message (`whatsapp-message`), and profile title.
  - **WhatsApp Rotator Detection**: Flags `whatsapp_rotator_detected = true` and tallies `whatsapp_rotator_phone_count` when multiple distinct WhatsApp phone numbers are discovered across links.
  - **Phone Numbers & Contact Buttons**: Body text regex parser (`_PHONE_RE`) for global phone formats; extracts `tel:`, `mailto:`, and WhatsApp action buttons.
  - **Exit Node IP Geolocation**: Queries Bright Data geo-verification endpoint from within the proxied context to extract exit IP, ASN (`asnum`, `org_name`), and geo coordinates.
  - **Post-Owner OCR Analysis**: Captures a top-800px header screenshot and queries the dedicated OCR API (`services/ocr_service.py`) in total isolation (non-blocking / non-fatal).
- **Asset Packaging, Upload & Ingestion**:
  - Creates single-file HTML archives (`<ad_id>_lander.zip`).
  - Multipart upload (`POST /upload_admob_blackhat`) sending screenshots and HTML ZIPs to remote storage.
  - Ingestion insert (`POST /insert_html_content`) reporting structured data with granular status codes and handling partial success (HTTP 207), validation errors (HTTP 422), and server errors (HTTP 503 / 500).
- **Transaction Audit Logging (`logs/api_transactions.jsonl`)**:
  - Automatically records every insert API transaction in JSON Lines format with `{ "request": ..., "payload": ..., "post_api_response": ... }`.
- **Data Integrity & Atomic Persistence**:
  - **Pydantic Models**: Validates every ad record against `AdMobDataRecord` and `AdRecord` schemas.
  - **Atomic JSON Storage**: Employs write-to-temp -> JSON validate -> atomic replace mechanism in `core/storage.py` to prevent data corruption.
  - **Timestamp Preservation**: Preserves original `created` timestamp across status transitions while updating `updated` timestamp.

---

## 4. Prerequisites & Installation

### Prerequisites
- **Python**: 3.10 or higher
- **Playwright Chromium**: Browser binaries for Playwright
- **Bright Data Account**: Active account with an **ISP Proxy Zone**
- **OCR API Key** (optional): For post-owner name extraction

### Step 1: Virtual Environment Setup
```bash
# Clone or navigate to the project directory
cd "main admob"

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# Windows (cmd.exe):
.\.venv\Scripts\activate.bat
# Linux / macOS:
source .venv/bin/activate
```

### Step 2: Install Python Dependencies & Playwright Browser
```bash
pip install -r requirements.txt
playwright install chromium
```

---

## 5. Configuration Guide

The system supports unified configuration loaded from `config.yaml` with environment variable overrides from `.env`.

### Step 1: Configure `config.yaml`
Copy `config.yaml.example` to `config.yaml` (or edit existing `config.yaml`):

```yaml
default_settings:
  INSTANCES: 10                     # Concurrency instances / count setting
  TIME_GAP_IN_INSTANCES: 30         # Polling delay (seconds) when no ads are returned
  DEV_MODE: true                    # Development mode flag (true = dev, false = prod)
  HIT_GET_API: false                # true = fetch from GET API; false = use local ads.json cache
  BRIGHT_PROXIES: true              # true = enable Bright Data proxy routing; false = direct
  Headless: true                    # true = headless browser; false = visible browser window
  MAX_ADS_PER_CYCLE: 2              # Target batch size limit per iteration

network:
  admob:
    dev:
      GET_API: ""
      S3_API: ""
      INSERT_API: ""
    prod:
      GET_API: ""
      S3_API: ""
      INSERT_API: ""
```

### Step 2: Configure `.env`
Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Fill in your Bright Data credentials and API endpoints:

```env
# --- General & Database ---
NETWORK=admob
DATABASE=pasdev_admob

# --- Operational Settings ---
MIN_SUCCESSFUL_GEOLOCATIONS=10
MAX_RETRIES=3
RETRY_BACKOFF_SECONDS=2
PAGE_TIMEOUT=30000
NAVIGATION_TIMEOUT=30000
GEO_TIMEOUT=10000
BROWSER_START_TIMEOUT=30000
BROWSER_START_RETRIES=3
MAX_REDIRECTS=30
HEADLESS=true

# --- File Paths ---
TARGET_URL_FILE=data/urls.json
ADS_CACHE_FILE=data/ads.json
PROCESSED_ADS_FILE=data/processed_ads.json
OUTPUT_FILE=data/AdMob_Data.json
LOG_FILE=logs/scraper.log
SCREENSHOT_DIR=data/screenshots
POST_OWNER_SCREENSHOT_DIR=post_owner/screenshots

# --- Bright Data ISP Proxy Credentials ---
BRIGHTDATA_CUSTOMER=your_customer_id
BRIGHTDATA_ZONE=your_isp_zone
BRIGHTDATA_PASSWORD=your_password
BRIGHTDATA_HOST=brd.superproxy.io
BRIGHTDATA_PORT=44445

# --- AdMob Lander API Endpoints (if not set in config.yaml) ---
ADMOB_API_BASE_URL=https://api.example.com
ADMOB_GET_ADS_ENDPOINT=/api/v1/admob/landers/get_ads_for_blackhat
ADMOB_UPLOAD_ENDPOINT=/api/v1/admob/landers/upload_admob_blackhat
ADMOB_INSERT_ENDPOINT=/api/v1/admob/landers/insert_html_content
ADMOB_API_TIMEOUT=60
ADMOB_CRAWLED_BY=.net

# --- Post-Owner OCR API ---
POST_OWNER_OCR_URL=https://admob-ocr-dev.poweradspy.ai/extract?ocr=false
ADMOB_OCR_API_KEY=your_ocr_api_key
```

---

## 6. Execution & Operation Modes

### Running the System
```bash
python main.py
```

### Pipeline Lifecycle & Status States
Every advertisement progresses through defined lifecycle states tracked in `data/AdMob_Data.json`:
- **`status: 0` (Fresh / Received)**: When an ad is first fetched from the GET API or loaded from `data/ads.json`, it is registered into `data/AdMob_Data.json` with `status: 0` and its creation timestamp.
- **`status: 1` (Scraping in Progress)**: When the browser begins navigating and extracting the URL, the record status updates to `status: 1`.
- **`status: 2` (Completed / Valid Lander)**: Successful navigation, full pre-rendering, screenshots, ZIP generation, asset upload, and parameter extraction.
- **`status: 3` (Unfetchable / 404 / Failed)**: When a destination URL cannot be loaded (e.g. HTTP 404, 410, 502, domain not found), the system records `status: 3`, persists the failure locally, and informs the ingestion API so the ad is marked as redirect-only/unfetchable.

### Process Resumption & Deduplication
- Completed ads are appended to `data/processed_ads.json`.
- On system restart or cycle iteration, `main.py` automatically checks `data/processed_ads.json` and skips previously processed ad IDs.
- Atomic file writes in `core/storage.py` ensure `data/AdMob_Data.json` is never corrupted during sudden process terminations.

---

## 7. External AdMob APIs & Ingestion Contracts

### 1. GET `/api/v1/admob/landers/get_ads_for_blackhat`
Retrieves the queue of ads to process.
```json
{
  "code": 200,
  "message": "Ads fetched successfully",
  "data": [
    {
      "id": 123,
      "ad_id": "ad-123",
      "destination_url": "https://example-landing.com/ad",
      "country": ["US", "CA"]
    }
  ]
}
```

### 2. POST `/api/v1/admob/landers/upload_admob_blackhat`
Multipart form upload for media (screenshot PNG) and zipped HTML package.
- Form fields: `ad_id`, `status`, `country_iso`, `media` (file), `zip` (file).
- Returns: `{"code": 200, "image_path": "https://...", "html_path": "https://..."}`.

### 3. POST `/api/v1/admob/landers/insert_html_content`
Submits the final structured JSON payload into MySQL and Elasticsearch.

```json
{
  "ad_id": "12345",
  "insertData": {
    "ad_id": "12345",
    "status": 2,
    "platform": "12",
    "crawled_by": ".net",
    "destinations": "https://landing-destination.com/page",
    "html_path": "https://cdn.example.com/landers/12345_lander.zip",
    "screen_shot": "https://cdn.example.com/screenshots/12345.png",
    "html_content": "Cleaned visible text content...",
    "domain_registered_date": "2021-05-12",
    "domain_age": 1180,
    "country_iso": ["US"],
    "outgoing_url": [],
    "redirects": [
      "https://initial-click.com/ad",
      "https://landing-destination.com/page"
    ],
    "ad_category": null,
    "source_website": "https://initial-click.com/ad",
    "source_parameters": {
      "gad_source": "5",
      "gad_campaignid": "24105002864",
      "gclid": "CjwKCAjwvsvTBhBaEiwAmf..."
    },
    "whatsapp": {
      "domain": "api.whatsapp.com",
      "path": "/send/",
      "phone": "+1234567890",
      "message": "Hello",
      "parameters": {
        "phone": "+1234567890",
        "text": "Hello",
        "type": "phone_number"
      }
    },
    "campaign_id": "24105002864",
    "location": {
      "with_vpn": {
        "ip": "",
        "country": "US",
        "country_code": "US"
      },
      "without_vpn": {}
    },
    "comparison": {},
    "whatsapp_links": [
      "https://api.whatsapp.com/send/?phone=%2B1234567890&text=Hello"
    ],
    "whatsapp_texts": ["Hello"],
    "phone_numbers": ["+1234567890"],
    "contact_buttons": [
      {
        "text": "Chat on WhatsApp",
        "href": "https://api.whatsapp.com/send/?phone=%2B1234567890&text=Hello"
      }
    ],
    "whatsapp_rotator_detected": false,
    "whatsapp_rotator_phone_count": 0,
    "lead_campaign_tag": "",
    "post_owner": "Advertiser Brand Name"
  }
}
```

---

## 8. Persisted Local Record Schema (`data/AdMob_Data.json`)

Validated against the `AdMobDataRecord` Pydantic model before being written to disk:

```json
[
  {
    "ad_id": "12345",
    "status": 2,
    "platform": "12",
    "destinations": "https://landing-destination.com/page",
    "html_path": "https://cdn.example.com/landers/12345_lander.zip",
    "screen_shot": "https://cdn.example.com/screenshots/12345.png",
    "html_content": "Full rendered visible text from page body...",
    "domain_registered_date": "2021-05-12",
    "domain_age": 1180,
    "country_iso": ["US", "CA"],
    "outgoing_url": [],
    "redirects": [
      "https://initial-click.com/ad",
      "https://landing-destination.com/page"
    ],
    "whatsapp": [
      {
        "domain": "api.whatsapp.com",
        "path": "https://api.whatsapp.com/send/?phone=1234567890&text=Hello",
        "phone": "1234567890",
        "button": "Chat on WhatsApp",
        "message": "Hello",
        "first_detected": "2026-08-28T10:30:00Z",
        "last_detected": "2026-08-28T10:30:00Z",
        "state": "US",
        "city": "US",
        "countrty": "US"
      }
    ],
    "post_owner": "Advertiser Brand Name",
    "campaign_id": "24105002864",
    "created": "2026-08-28T10:29:45Z",
    "updated": "2026-08-28T10:30:05Z"
  }
]
```

---

## 9. API Transaction Audit Logging (`logs/api_transactions.jsonl`)

Every insert transaction interacting with the backend API is recorded in `logs/api_transactions.jsonl` with strictly one JSON object per line:

```json
{
  "request": {
    "id": 123,
    "ad_id": "12345",
    "destination_url": "https://example-landing.com/ad",
    "country": ["US"]
  },
  "payload": {
    "ad_id": "12345",
    "status": 2,
    "platform": "12",
    "destinations": "https://landing-destination.com/page",
    "html_path": "https://cdn.example.com/landers/12345_lander.zip",
    "screen_shot": "https://cdn.example.com/screenshots/12345.png",
    "html_content": "Cleaned visible text content...",
    "domain_registered_date": "2021-05-12",
    "domain_age": 1180,
    "country_iso": ["US"],
    "outgoing_url": [],
    "redirects": ["https://initial-click.com/ad", "https://landing-destination.com/page"],
    "whatsapp": { ... },
    "campaign_id": "24105002864",
    "location": { ... },
    "comparison": {},
    "whatsapp_links": ["https://api.whatsapp.com/..."],
    "whatsapp_texts": ["Hello"],
    "phone_numbers": ["+1234567890"],
    "contact_buttons": [{ "text": "Chat on WhatsApp", "href": "https://..." }],
    "whatsapp_rotator_detected": false,
    "whatsapp_rotator_phone_count": 0,
    "lead_campaign_tag": "",
    "post_owner": "Advertiser Brand Name"
  },
  "post_api_response": {
    "code": 200,
    "status": "ok",
    "message": "Destination Lander updated successfully.",
    "data": {
      "id": 123,
      "mysql_saved": true,
      "elastic_indexed": true,
      "redirect_status": 1,
      "skipped_content": false
    }
  }
}
```

---

## 10. Error Handling & Recovery Matrix

| Scenario / Exception | Detection Mechanism | System Action & Recovery |
| :--- | :--- | :--- |
| **Playwright Driver Disconnection** (`Connection closed`) | `browser_manager.py` | Gracefully cleans up `Playwright` driver and retries launch up to `BROWSER_START_RETRIES`. |
| **Proxy Tunnel Timeout** | `scraper.py` | Aborts proxy attempt, logs warning, and initiates immediate **direct connection fallback**. |
| **Navigation Abort / Frame Detach** | `scraper.py` | If browser reached a valid URL, proceeds with partial content; otherwise retries. |
| **404 / 4xx / 5xx / Domain Error** | `_check_page_error_or_404` | Categorizes failure, marks ad as `status: 3` (unfetchable), saves locally, and notifies API. |
| **Redirect Loop** | `redirect_tracker.py` | Triggers error once hop count exceeds `MAX_REDIRECTS` (30) and marks observation failed. |
| **CAPTCHA / Challenge Page** | `scraper.py` | Detects `cf-browser-verification`/reCAPTCHA snippets; safely logs and skips without bypass attempts. |
| **Post-Owner OCR Failure** | `services/ocr_service.py` | Completely isolated in a `try/except` block. Logs warning and leaves field `None` without crashing scraper. |
| **API Validation Error (HTTP 422)** | `api/admob_api.py` | Identifies rejected fields (`PermanentError`) and halts blind retries to prevent log spam. |
| **API Server Unavailable (HTTP 503)** | `api/admob_api.py` | Performs linear backoff retries (`attempt * RETRY_BACKOFF_SECONDS`). |
| **Process Interruption (Ctrl+C / Kill)** | `core/storage.py` | Atomic temporary file writing guarantees no corrupted JSON in `data/AdMob_Data.json`. |

---

## 11. Testing & Quality Verification

### Run Unit & Compliance Tests
```bash
# Test Pydantic models, JSON storage, URL/WhatsApp parsing, and retry helpers
python -m unittest discover -s tests
```

### Manual Pipeline Smoke Test
To verify the browser engine and proxy connectivity manually on a test URL:
```bash
python -c "import asyncio, config; from services.browser_manager import BrowserManager; from engine.scraper import execute_country_observation; asyncio.run(execute_country_observation(BrowserManager(), 'https://example.com', 'us'))"
```

---

## 12. Security & Best Practices

- **Never commit `.env` or sensitive proxy credentials** to version control.
- **Atomic Operations**: All state changes (`AdMob_Data.json`, `ads.json`, `processed_ads.json`, `api_transactions.jsonl`) use atomic file swap or synchronous flushing mechanisms.
- **Resource Management**: Browser contexts, pages, and network sessions are deterministically closed in `finally` blocks. Temporary ZIP packages are automatically purged after successful upload.
- **Documentation**: For code breakdowns and line-by-line file explanations, refer to [MD/CODEBASE_EXPLANATION.md](MD/CODEBASE_EXPLANATION.md) and [MD/config.md](MD/config.md).
