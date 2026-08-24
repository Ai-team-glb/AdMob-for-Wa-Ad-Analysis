from datetime import datetime
import json
from typing import List, Optional, Literal
from urllib.parse import urlparse

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
    ValidationError
)


class OutgoingURL(BaseModel):
    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
    )

    start_url: str
    redirect_urls: List[str] = Field(default_factory=list)
    destination_url: str

    @field_validator("start_url", "destination_url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value:
            raise ValueError("URL cannot be empty")

        parsed = urlparse(value)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(f"Invalid HTTP/HTTPS URL: {value}")

        return value

    @field_validator("redirect_urls")
    @classmethod
    def validate_redirect_urls(cls, urls: List[str]) -> List[str]:
        for url in urls:
            parsed = urlparse(url)

            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(f"Invalid redirect URL: {url}")

        return urls


class WhatsAppInfo(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    domain: str
    path: str

    # Keep phone as string.
    phone: str

    button: Optional[str] = None
    message: Optional[str] = None

    # Accept existing typo from incoming payload.
    first_detected: datetime = Field(alias="first_detected")
    last_detected: datetime

    state: Optional[str] = None
    city: Optional[str] = None

    # Accept existing typo from incoming payload.
    country: Optional[str] = Field(default=None, alias="countrty")

    @field_validator("domain")
    @classmethod
    def validate_domain(cls, value: str) -> str:
        value = value.lower().strip()

        if "." not in value:
            raise ValueError("domain must be a valid domain name")

        return value

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        if not value:
            return value

        if value.startswith("http://") or value.startswith("https://"):
            return value

        if not value.startswith("/"):
            value = f"/{value}"

        return value

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        # Normalize common formatting
        cleaned = (
            value.replace("+", "")
            .replace(" ", "")
            .replace("-", "")
            .replace("(", "")
            .replace(")", "")
        )

        if not cleaned.isdigit():
            raise ValueError("phone must contain only numeric digits")

        # E.164 allows max 15 digits.
        # Minimum is kept reasonably permissive.
        if not 7 <= len(cleaned) <= 15:
            raise ValueError(
                "phone number must contain between 7 and 15 digits"
            )

        return cleaned

    @field_validator("state", "city", "country")
    @classmethod
    def empty_string_to_none(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        return value or None

    @model_validator(mode="after")
    def validate_detection_dates(self):
        if self.first_detected > self.last_detected:
            raise ValueError(
                "first_detected cannot be after last_detected"
            )

        return self


class AdMobAd(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    ad_id: str

    # 0 = fresh
    # 1 = pending
    # 2 = repeat
    status: Literal[0, 1, 2]

    platform: str

    destinations: Optional[str] = None

    html_path: Optional[str] = None
    screen_shot: Optional[str] = None
    html_content: Optional[str] = None

    domain_registered_date: Optional[datetime] = None

    domain_age: int = Field(
        default=0,
        ge=0,
    )

    country_iso: List[str] = Field(default_factory=list)

    outgoing_url: List[OutgoingURL] = Field(default_factory=list)

    redirects: List[str] = Field(default_factory=list)

    source_app: Optional[str] = None

    whatsapp: List[WhatsAppInfo] = Field(default_factory=list)

    campaign_id: Optional[str] = None

    created: datetime
    updated: datetime

    @field_validator("ad_id")
    @classmethod
    def validate_ad_id(cls, value: str) -> str:
        if not value:
            raise ValueError("ad_id cannot be empty")

        return value

    @field_validator("destinations")
    @classmethod
    def validate_destination(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        parsed = urlparse(value)

        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError(
                f"Invalid destinations URL: {value}"
            )

        return value

    @field_validator("redirects")
    @classmethod
    def validate_redirects(cls, urls: List[str]) -> List[str]:
        for url in urls:
            parsed = urlparse(url)

            if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                raise ValueError(
                    f"Invalid redirect URL: {url}"
                )

        return urls

    @field_validator("country_iso")
    @classmethod
    def validate_country_iso(
        cls,
        countries: List[str],
    ) -> List[str]:
        normalized = []

        for country in countries:
            country = country.strip().upper()

            if len(country) != 2 or not country.isalpha():
                raise ValueError(
                    f"Invalid ISO country code: {country}"
                )

            normalized.append(country)

        # Deduplicate while maintaining order
        return list(dict.fromkeys(normalized))

    @field_validator("html_path", "screen_shot")
    @classmethod
    def validate_storage_path(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if not value:
            return value

        if not value.startswith("/"):
            raise ValueError(
                "storage path must start with '/'"
            )

        return value

    @field_validator("campaign_id")
    @classmethod
    def validate_campaign_id(
        cls,
        value: Optional[str],
    ) -> Optional[str]:
        if value is None:
            return None

        value = value.strip()

        if not value:
            return None

        if not value.isdigit():
            raise ValueError(
                "campaign_id must contain numeric characters only"
            )

        return value

    @model_validator(mode="after")
    def validate_timestamps(self):
        if self.created > self.updated:
            raise ValueError(
                "created cannot be after updated"
            )

        return self


if __name__ == "__main__":
    # payload = {
    #     "ad_id": "393b2a99a0d23d76912d7dbf",
    #     "status": 0,
    #     "platform": "12",
    #     "destinations": (
    #         "https://reddydelivery.store/"
    #         "?gad_source=5&gad_campaignid=24144585336"
    #     ),
    #     "html_path": (
    #         "/pas-dev/stream/admob/whiteHatAd/"
    #         "202608/393b2a99a0d23d76912d7dbf.zip"
    #     ),
    #     "screen_shot": (
    #         "/pas-dev/stream/admob/whiteHatAd/"
    #         "202608/393b2a99a0d23d76912d7dbf.png"
    #     ),
    #     "html_content": "text/html content",
    #     "domain_registered_date": None,
    #     "domain_age": 0,
    #     "country_iso": ["IN"],
    #     "outgoing_url": [
    #         {
    #             "start_url": (
    #                 "https://reddydelivery.store/"
    #                 "?gad_source=5&gad_campaignid=24144585336"
    #             ),
    #             "redirect_urls": [],
    #             "destination_url": (
    #                 "https://reddydelivery.store/"
    #                 "?gad_source=5&gad_campaignid=24144585336"
    #             ),
    #         }
    #     ],
    #     "redirects": [
    #         (
    #             "https://reddydelivery.store/"
    #             "?gad_source=5&gad_campaignid=24144585336"
    #         )
    #     ],
    #     "source_app": "crex",
    #     "whatsapp": [
    #         {
    #             "domain": "wa.link",
    #             "path": "/reddylive2",
    #             "phone": "918810993624",
    #             "button": "Book delivery ↗️",
    #             "message": "HI, I NEED INFO AND I:D",
    #             "fisrt_detected": "2024-06-05T12:00:00Z",
    #             "last_detected": "2024-06-05T12:00:00Z",
    #             "state": "IN",
    #             "city": "IN",
    #             "countrty": "IN",
    #         }
    #     ],
    #     "campaign_id": "24144585336",
    #     "created": "2024-06-05T12:00:00Z",
    #     "updated": "2024-06-05T12:00:00Z",
    # }
    def validate_ad(payload: dict , show_error=True) -> bool:
        try:
            AdMobAd.model_validate(payload)
            return True
        except ValidationError as e:
            if show_error:
                print(e)
            return False


    # with open("AdMod_Data.json", "r", encoding="utf-8") as f:
    with open("AdMod_Data.json", "r", encoding="utf-8") as f:
        payloads = json.load(f)
    for ind,pay in enumerate(payloads):
        is_valid = validate_ad(pay)
        print(ind, is_valid)
        break
