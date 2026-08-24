# AdMob Multi-Geolocation System - Project Directory Structure

```text
admobcontents/
├── main.py                     # Entry point: Continuous data extraction pipeline
├── config.py                   # Configuration loader and environment path resolver
├── config.yaml                 # YAML default settings and network API configurations
├── .env                        # Environment variables and API secrets
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation and quickstart guide
├── SRS.txt                     # System specification document
├── PROJECT_STRUCTURE.md        # Current project directory structure
│
├── core/                       # Core system models, storage, logging & error handling
│   ├── __init__.py
│   ├── logger.py               # Centralized logging setup
│   ├── models.py               # Pydantic data models & payload contracts
│   ├── storage.py              # Local JSON storage manager (data/AdMod_Data.json)
│   ├── error_handler.py        # Exception categorization and classifications
│   └── retry.py                # Generic async retry handler with linear backoff
│
├── services/                   # Utility services (Browser, Proxy, Geo, Parsers, Packaging)
│   ├── __init__.py
│   ├── browser_manager.py      # Playwright driver lifecycle & context manager
│   ├── proxy_manager.py        # Bright Data ISP proxy rotation & country normalizer
│   ├── geo_service.py          # IP/Proxy geolocation verifier
│   ├── redirect_tracker.py     # Main-frame navigation & redirect chain tracker
│   ├── url_parser.py           # Campaign URL parameter parser
│   ├── whatsapp_parser.py      # WhatsApp links, shortlinks & number detector
│   └── html_packager.py        # HTML ZIP bundler
│
├── api/                        # External API Client
│   ├── __init__.py
│   └── admob_api.py            # HTTP client for GET & POST AdMob Lander APIs
│
├── engine/                     # Scraping Engine & Pipeline Orchestration
│   ├── __init__.py
│   ├── scraper.py              # Single country/geolocation observation executor
│   └── scraping_manager.py     # Multi-geolocation scraping & API stage manager
│
└── data/                       # Local runtime data cache & screenshots
    ├── ads.json                # API response cache
    ├── processed_ads.json      # Processed ad_id tracker
    ├── AdMod_Data.json         # Storage persistence record file
    ├── validated_payload.json  # Last validated payload record
    └── screenshots/            # Captured page screenshots directory
```
