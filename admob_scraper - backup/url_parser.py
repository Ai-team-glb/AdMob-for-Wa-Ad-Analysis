"""Extraction of campaign-related query parameters from a URL.
Aligns with SRS Section 19:
- camplainid
- gad_source
- gclid
"""
from urllib.parse import urlparse, parse_qs

PARAM_MAP = {
    "camplainid": ["gad_campaignid", "campaign_id", "camplainid", "campaignid"],
    "gad_source": ["gad_source"],
    "gclid": ["gclid"],
}


def extract_campaign_params(url: str) -> dict:
    if not url:
        return {key: None for key in PARAM_MAP}

    query = parse_qs(urlparse(url).query)
    result = {}
    for out_key, candidates in PARAM_MAP.items():
        value = None
        for candidate in candidates:
            if candidate in query and query[candidate]:
                value = query[candidate][0]
                break
        result[out_key] = value
    return result


def extract_source_website(url: str) -> str:
    """Extract the domain/netloc from a URL (for the source_website field)."""
    if not url:
        return ""
    try:
        return urlparse(url).netloc
    except Exception:
        return ""


def extract_source_params(url: str) -> dict:
    """Extract ALL query parameters from a URL as a flat dict (for source_parameters)."""
    if not url:
        return {}
    try:
        qs = parse_qs(urlparse(url).query)
        return {k: v[0] if len(v) == 1 else v for k, v in qs.items()}
    except Exception:
        return {}

