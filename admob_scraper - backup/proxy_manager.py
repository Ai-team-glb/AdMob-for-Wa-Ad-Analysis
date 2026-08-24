"""Country selection and Bright Data ISP proxy configuration."""
import random
from typing import Dict, Set

import config


COUNTRY_NAME_TO_ISO = {
    "india": "in", "in": "in",
    "united states": "us", "usa": "us", "us": "us",
    "united kingdom": "gb", "uk": "gb", "gb": "gb",
    "germany": "de", "de": "de",
    "france": "fr", "fr": "fr",
    "japan": "jp", "jp": "jp",
    "canada": "ca", "ca": "ca",
    "australia": "au", "au": "au",
    "singapore": "sg", "sg": "sg",
    "italy": "it", "it": "it",
    "netherlands": "nl", "nl": "nl",
    "spain": "es", "es": "es",
    "brazil": "br", "br": "br",
    "mexico": "mx", "mx": "mx",
    "south korea": "kr", "korea": "kr", "kr": "kr",
    "sweden": "se", "se": "se",
    "switzerland": "ch", "ch": "ch",
    "ireland": "ie", "ie": "ie",
    "new zealand": "nz", "nz": "nz",
    "south africa": "za", "za": "za",
}


def normalize_country_code(country: str) -> str:
    """Normalize full country name or code (e.g. 'India', 'INDIA', 'US') to 2-letter ISO code (e.g. 'in')."""
    if not country:
        return "us"
    c_clean = str(country).strip().lower()
    if c_clean in COUNTRY_NAME_TO_ISO:
        return COUNTRY_NAME_TO_ISO[c_clean]
    if len(c_clean) == 2:
        return c_clean
    return c_clean[:2]


class ProxyManager:
    """Tracks which proxy countries have already been used per target URL,
    and builds Playwright-compatible proxy configuration dictionaries.
    """

    def __init__(self, countries=None):
        self.countries = countries or config.PROXY_COUNTRIES
        self._used_by_url: Dict[str, Set[str]] = {}

    def mark_used(self, url: str, country: str) -> None:
        self._used_by_url.setdefault(url, set()).add(country)

    def has_unused_country(self, url: str) -> bool:
        return len(self._used_by_url.get(url, set())) < len(self.countries)

    def get_random_unused_country(self, url: str) -> str:
        used = self._used_by_url.get(url, set())
        available = [c for c in self.countries if c not in used]
        if not available:
            raise RuntimeError(f"No unused proxy countries left for {url}")
        return random.choice(available)

    @staticmethod
    def build_proxy_config(country: str) -> dict | None:
        """Build a Playwright `proxy=` dict for a Bright Data ISP proxy zone,
        pinned to a given country via the username suffix.
        Returns None if credentials are not configured.
        """
        if not config.BRIGHT_PROXIES or not config.BRIGHTDATA_CUSTOMER or not config.BRIGHTDATA_PASSWORD:
            return None

        country_iso = normalize_country_code(country)
        username = (
            f"brd-customer-{config.BRIGHTDATA_CUSTOMER}"
            f"-zone-{config.BRIGHTDATA_ZONE}"
            f"-country-{country_iso}"
        )
        return {
            "server": f"http://{config.BRIGHTDATA_HOST}:{config.BRIGHTDATA_PORT}",
            "username": username,
            "password": config.BRIGHTDATA_PASSWORD,
        }

