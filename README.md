# AdMob Multi-Geolocation Advertisement Data Extraction System

Automated Playwright-based system that processes a configurable list of target URLs and collects advertisement-related information across multiple Bright Data ISP proxy geolocations.

Strictly adheres to **SRS 2.0 Specifications**:
- **Core Data Rule**: **1 Target URL = 1 `add-id`** containing up to 10 unique proxy geolocation observations in its `"country"` list.
- **Scope**: Scrapes only publicly visible web content, follows redirect chains, extracts campaign parameters (`camplainid`, `gad_source`, `gclid`), discovers & deduplicates public WhatsApp links (`wa_data`), and records actual exit IP geolocation info from Bright Data.
- **Reliability & Resilience**: Automatic Playwright driver recovery, crash handling, redirect loop protection, incremental atomic JSON persistence, and interruption resumption.

---

## 1. System Architecture & Data Flow

```
                      TARGET URL LIST (data/urls.json)
                                     │
                                     ▼
                              SCRAPING MANAGER
                                     │
                                     ▼
                                 Target URL
                   ┌─────────────────┼─────────────────┐
                   ▼                 ▼                 ▼
             Proxy Country 1   Proxy Country 2   Proxy Country 3 ... (Up to 10)
                   │                 │                 │
                   ▼                 ▼                 ▼
             Observation 1     Observation 2     Observation 3
                   │                 │                 │
                   └─────────────────┼─────────────────┘
                                     │
                                     ▼
                              DATA AGGREGATOR
                                     │
                                     ▼
                            ONE Advertisement Record
                                 (add-id: 1)
                                     │
                                     ▼
                            Pydantic Validation
                                     │
                                     ▼
                        Atomic Write to AdMob_Data.json
```

---

## 2. Prerequisites

- Python 3.10+
- Bright Data Account with an **ISP Proxy Zone**
- Chromium browser binaries for Playwright

---

## 3. Setup & Installation

### Step 1: Virtual Environment Setup

```bash
# Clone/open the repository
cd admob_scraper

# Create and activate virtual environment
python -m venv .venv

# On Windows:
.\.venv\Scripts\activate

# On Linux/macOS:
source .venv/bin/activate
```

### Step 2: Install Dependencies & Playwright Browser

```bash
pip install -r requirements.txt
playwright install chromium
```

### Step 3: Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Open `.env` and configure your settings and Bright Data ISP proxy credentials:

```env
NETWORK=admob
DATABASE=pasdev_admob

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

TARGET_URL_FILE=data/urls.json
OUTPUT_FILE=data/AdMob_Data.json
LOG_FILE=logs/scraper.log

# --- Bright Data ISP Proxy credentials ---
BRIGHTDATA_CUSTOMER=hl_5c822482
BRIGHTDATA_ZONE=isp_proxy1
BRIGHTDATA_PASSWORD=your_password
BRIGHTDATA_HOST=brd.superproxy.io
BRIGHTDATA_PORT=44445
```

> **Security Note**: Never commit `.env` to Git. Credentials are never written to `AdMob_Data.json` or logs.

---

## 4. Configuring Target URLs

Edit `data/urls.json` to add or remove target URLs without touching code:

```json
{
  "urls": [
    "https://mahadevelectronic.blogspot.com/2026/08/mahadev-electronics-premium-appliances.html?gad_source=5&gad_campaignid=24105002864&gclid=CjwKCAjwvsvTBhBaEiwAmf-3nne-uLHMD1oYrhPNHq9m-ffC8e4Zdb5ufyqTTJOBdKEM88_OI4zxrRoCqFUQAvD_BwE"
  ]
}
```

---

## 5. Running the Project

Run the scraper using:

```bash
python main.py
```

### What Happens During Execution:
1. Loads target URLs from `data/urls.json`.
2. Inspects `data/AdMob_Data.json` to automatically skip URLs that were already completed in previous runs.
3. For each URL:
   - Randomly rotates through proxy countries from `config.PROXY_COUNTRIES` without repeating attempts.
   - Launches an isolated Playwright browser context configured with the country-specific ISP proxy.
   - Navigates to the URL, captures all redirect hops, and identifies the final destination.
   - Extracts URL parameters: `camplainid`, `gad_source`, `gclid`.
   - Inspects the destination page for publicly visible WhatsApp links (`wa.me`, `api.whatsapp.com`, `chat.whatsapp.com`) and deduplicates them.
   - Queries Bright Data's geo verification endpoint (`https://geo.brdtest.com/welcome.txt?product=isp&method=native`) to retrieve actual exit IP, ASN, and geo coordinates.
   - Loops until 10 unique successful geolocations are collected.
   - Builds 1 `AdRecord` with 1 `add-id` and atomically commits the validated record to `data/AdMob_Data.json`.

---

## 6. Testing & Validation

Run the automated compliance and integration test suites:

```bash
# 1. Run SRS Compliance Tests (Models, URL Parser, WhatsApp Parser, Serializer)
python test_compliance.py

# 2. Run Integration Tests (Playwright browser lifecycle, parsing)
python test_integration.py
```

---

## 7. Output Format (`data/AdMob_Data.json`)

The persisted output strictly matches the SRS 2.0 data schema:

```json
{
  "network": "admob",
  "database": "pasdev_admob",
  "count": 1,
  "ads": [
    {
      "add-id": 1,
      "extracted_at": "2026-08-20T10:26:14.991Z",
      "url": "https://example.com/?gad_source=5&gad_campaignid=24107228296&gclid=ABC123",
      "redirect_urls": [
        "https://example.com/?gad_source=5&gad_campaignid=24107228296&gclid=ABC123",
        "https://destination.example.com/"
      ],
      "Destination_urls": "https://destination.example.com/",
      "camplainid": "24107228296",
      "gad_source": "5",
      "gclid": "ABC123",
      "wa_data": [
        {
          "whatsapp-url": "https://wa.me/123456789?text=Hello",
          "whatsapp-profile": null,
          "whatsapp-number": "123456789",
          "whatsapp-message": "Hello"
        }
      ],
      "country": [
        {
          "ip_version": 4,
          "country": "GB",
          "asn": {
            "asnum": 12345,
            "org_name": "Example ISP"
          },
          "geo": {
            "city": "London",
            "region": "LND",
            "region_name": "London",
            "postal_code": "SW1A",
            "latitude": 51.5074,
            "longitude": -0.1278,
            "tz": "Europe/London",
            "lum_city": "london",
            "lum_region": "lnd"
          }
        },
        {
          "ip_version": 4,
          "country": "US",
          "asn": {
            "asnum": 54321,
            "org_name": "Example ISP"
          },
          "geo": {
            "city": "New York",
            "region": "NY",
            "region_name": "New York",
            "postal_code": "10001",
            "latitude": 40.7128,
            "longitude": -74.0060,
            "tz": "America/New_York",
            "lum_city": "newyork",
            "lum_region": "ny"
          }
        }
      ]
    }
  ]
}
```

---

## 8. Error Handling & Recovery Matrix

| Scenario | Handled By | Behavior |
| --- | --- | --- |
| **Driver Connection Broken** (`BrowserType.launch: Connection closed`) | `browser_manager.py` | Automatically re-initializes Playwright driver and retries launch up to `BROWSER_START_RETRIES`. |
| **Navigation Timeout / Slow Page** | `scraper.py` | Logs timeout error, discards country attempt, proceeds to next random unused proxy country. |
| **Proxy Failure / Bad Exit Node** | `scraping_manager.py` | Failed attempt does not count toward 10 required successes; chooses another country. |
| **Redirect Loop** | `redirect_tracker.py` | Stops tracking when `MAX_REDIRECTS` is reached and marks country attempt failed. |
| **CAPTCHA / Challenge Detected** | `scraper.py` | Detects challenge text/verification page, safely logs and skips without attempting bypass. |
| **Process Interruption (Ctrl+C / Crash)** | `storage.py` & `main.py` | Atomic writes prevent JSON corruption; on restart, completed URLs are skipped automatically. |
