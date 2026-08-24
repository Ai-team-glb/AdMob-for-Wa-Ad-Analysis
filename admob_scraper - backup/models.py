"""Pydantic data models used to validate every observation before it is persisted.
Aligns strictly with AdMob Multi-Geolocation Advertisement Data Extraction SRS 2.0.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict


class WhatsAppData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    whatsapp_url: str = Field(alias="whatsapp-url")
    whatsapp_profile: Optional[str] = Field(default=None, alias="whatsapp-profile")
    whatsapp_number: Optional[str] = Field(default=None, alias="whatsapp-number")
    whatsapp_message: Optional[str] = Field(default=None, alias="whatsapp-message")


class ASNInfo(BaseModel):
    asnum: Optional[int] = None
    org_name: Optional[str] = None


class GeoDetails(BaseModel):
    city: Optional[str] = None
    region: Optional[str] = None
    region_name: Optional[str] = None
    postal_code: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    tz: Optional[str] = None
    lum_city: Optional[str] = None
    lum_region: Optional[str] = None


class GeoData(BaseModel):
    ip_version: Optional[int] = None
    country: Optional[str] = None
    asn: Optional[ASNInfo] = None
    geo: Optional[GeoDetails] = None


class AdRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    add_id: int = Field(alias="add-id")
    extracted_at: datetime
    url: str
    redirect_urls: List[str] = Field(default_factory=list)
    destination_urls: Optional[str] = Field(default=None, alias="Destination_urls")
    camplainid: Optional[str] = None
    gad_source: Optional[str] = None
    gclid: Optional[str] = None
    wa_data: List[WhatsAppData] = Field(default_factory=list)
    country: List[GeoData] = Field(default_factory=list)


class AdMobData(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    network: str
    database: str
    count: int = 0
    ads: List[AdRecord] = Field(default_factory=list)


class WhatsAppItem(BaseModel):
    domain: str = ""
    path: str = ""
    phone: str = ""
    button: str = ""
    message: str = ""
    first_detected: str
    last_detected: str
    state: str = ""
    city: str = ""
    countrty: str = ""


class AdModDataRecord(BaseModel):
    ad_id: str
    status: int
    platform: str = "12"
    destinations: str
    html_path: Optional[str] = ""
    screen_shot: Optional[str] = ""
    html_content: Optional[str] = ""
    domain_registered_date: Optional[str] = None
    domain_age: int = 0
    country_iso: List[str] = Field(default_factory=list)
    outgoing_url: List[Dict[str, Any]] = Field(default_factory=list)
    redirects: List[str] = Field(default_factory=list)
    source_app: str = "crex"
    whatsapp: List[WhatsAppItem] = Field(default_factory=list)
    campaign_id: str = ""
    created: str
    updated: str

