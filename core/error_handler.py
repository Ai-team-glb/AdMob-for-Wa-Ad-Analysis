"""Error categorization and classification for the AdMob scraper system.
Aligns with SRS Section 32 (Error Handling Architecture).
"""
from __future__ import annotations
from enum import Enum
from typing import Optional
from playwright.async_api import TimeoutError as PlaywrightTimeoutError


class ErrorType(str, Enum):
    BROWSER_STARTUP_ERROR = "BROWSER_STARTUP_ERROR"
    BROWSER_CRASH = "BROWSER_CRASH"
    PLAYWRIGHT_DRIVER_ERROR = "PLAYWRIGHT_DRIVER_ERROR"
    PROXY_CONNECTION_ERROR = "PROXY_CONNECTION_ERROR"
    PROXY_AUTHENTICATION_ERROR = "PROXY_AUTHENTICATION_ERROR"
    NAVIGATION_TIMEOUT = "NAVIGATION_TIMEOUT"
    NAVIGATION_ERROR = "NAVIGATION_ERROR"
    REDIRECT_LOOP_ERROR = "REDIRECT_LOOP_ERROR"
    DESTINATION_ERROR = "DESTINATION_ERROR"
    GEOLOCATION_ERROR = "GEOLOCATION_ERROR"
    WHATSAPP_EXTRACTION_ERROR = "WHATSAPP_EXTRACTION_ERROR"
    JSON_STORAGE_ERROR = "JSON_STORAGE_ERROR"
    INVALID_URL_ERROR = "INVALID_URL_ERROR"
    CAPTCHA_DETECTED = "CAPTCHA_DETECTED"
    API_CONNECTION_ERROR = "API_CONNECTION_ERROR"
    API_TIMEOUT_ERROR = "API_TIMEOUT_ERROR"
    API_VALIDATION_ERROR = "API_VALIDATION_ERROR"
    API_SERVER_ERROR = "API_SERVER_ERROR"
    UPLOAD_ERROR = "UPLOAD_ERROR"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class ScraperException(Exception):
    def __init__(self, error_type: ErrorType, message: str, original_exc: Optional[Exception] = None):
        super().__init__(f"[{error_type.value}] {message}")
        self.error_type = error_type
        self.original_exc = original_exc


def classify_error(exc: Exception) -> ErrorType:
    """Map arbitrary python/playwright exceptions into standard SRS error categories."""
    msg = str(exc).lower()

    if "connection closed while reading from the driver" in msg or "driver" in msg:
        return ErrorType.BROWSER_STARTUP_ERROR
    if "target page, context or browser has been closed" in msg or "browser has been closed" in msg:
        return ErrorType.BROWSER_CRASH
    if isinstance(exc, PlaywrightTimeoutError) or "timeout" in msg:
        return ErrorType.NAVIGATION_TIMEOUT
    if "net::err_proxy" in msg or "proxy" in msg or "tunnel connection failed" in msg:
        return ErrorType.PROXY_CONNECTION_ERROR
    if "407" in msg or "proxy authentication" in msg:
        return ErrorType.PROXY_AUTHENTICATION_ERROR
    if "redirect" in msg and "loop" in msg:
        return ErrorType.REDIRECT_LOOP_ERROR
    if "captcha" in msg or "recaptcha" in msg or "challenge" in msg or "cf-browser-verification" in msg:
        return ErrorType.CAPTCHA_DETECTED
    if "geo" in msg:
        return ErrorType.GEOLOCATION_ERROR
    if "json" in msg:
        return ErrorType.JSON_STORAGE_ERROR

    return ErrorType.UNKNOWN_ERROR
