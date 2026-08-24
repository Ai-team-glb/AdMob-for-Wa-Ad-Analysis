# AdMob Lander Implementation

This document is the working contract for the AdMob lander flow.

It explains:

- what the DS team sends
- what the PAS API stores and returns
- which parts are explicit DS responsibilities
- which parts are handled by our API and migrations
- how the new lander pipeline fits into the existing AdMob stack

## Why this exists

Before this work, AdMob did not have a dedicated lander pipeline for destination-page scrape data.
That meant there was no clean place to store:

- final rendered landing-page HTML
- landing-page screenshots
- WhatsApp links and prefilled text
- source website and tracking parameters
- VPN comparison details
- phone numbers found in the page HTML
- contact buttons
- campaign tags
- audit data for later review

The new AdMob lander flow fixes that by adding an AdMob-only API plus additive MySQL and
Elasticsearch upgrades. We did not rewrite legacy network code.

## What DS team owns vs what PAS API owns

| Area | DS team provides | PAS API provides |
| --- | --- | --- |
| Base lander scrape | `ad_id`, `status`, `crawled_by`, destination URL, screenshot, HTML content, domain data, outgoing URLs, redirects, category | Validation, persistence, and search indexing |
| WhatsApp enrichment | WhatsApp URL, domain, path, phone, message, parameters, source website, source parameters, location snapshots, comparison data | Flattening, storage, and ES projection |
| Rotator / volume signal | Explicit `whatsapp_rotator_detected` or `high_volume_lead_campaign` and optional `whatsapp_rotator_phone_count` | Store it exactly as sent, do not infer it from a single comparison |
| Contact evidence | WhatsApp links, prefilled texts, phone numbers, contact buttons | Store raw and normalized representations |
| Asset upload | Media or zip files produced by the scrape job | Upload to NAS and clean up temporary files |
| Schema upgrades | Nothing | Additive SQL migration and ES mapping scripts |

## What we provide

We added a new AdMob-only lander flow under `src/services/admob/landers/`.

The API is auto-mounted by the service registry under:

- `GET /api/v1/admob/landers/get_ads_for_blackhat`
- `POST /api/v1/admob/landers/upload_admob_blackhat`
- `POST /api/v1/admob/landers/insert_html_content`

This is isolated from the other network services.

## What each endpoint does

### `GET /api/v1/admob/landers/get_ads_for_blackhat`

Returns AdMob rows that are ready for lander processing.

Use this when the scraper or pipeline needs the next ad to work on.

Request shape:

- HTTP method: `GET`
- Request body: none
- Query string: none required by the current implementation

Example request:

```http
GET /api/v1/admob/landers/get_ads_for_blackhat
```

Response shape:

```json
{
  "code": 200,
  "message": "Ads fetched successfully",
  "data": [
    {
      "id": 123,
      "ad_id": "ad-123",
      "destination_url": "https://example-landing.com/whitehat",
      "country": ["US", "CA"]
    }
  ],
  "exe_time": 0.012
}
```

Common variations:

- `message: "No Ads found"` with `data: []`
- `message: "Ads not found in Elasticsearch"` with `data: []`
- `code: 503` when the MySQL or Elasticsearch connection is unavailable

### `POST /api/v1/admob/landers/upload_admob_blackhat`

Uploads the media and zip assets produced by the scrape job.

Accepted multipart fields:

- `media`
- `zip`

This route stores the files on NAS and deletes the temporary upload files afterward.
It does not save the lander payload into MySQL.

Request shape:

- HTTP method: `POST`
- Content-Type: `multipart/form-data`
- File fields:
  - `media` for the rendered image or screenshot bundle
  - `zip` for the HTML bundle
- Body fields read by the service:
  - `ad_id`
  - `status` must be `1` or `2`
  - `country_iso` or `country`
- At least one file field must be present

Example request:

```http
POST /api/v1/admob/landers/upload_admob_blackhat
Content-Type: multipart/form-data

ad_id=12345
status=2
country_iso=US
media=@screenshot.png
zip=@lander.zip
```

Response shape:

```json
{
  "code": 200,
  "message": "files are stored successfully",
  "country": "US",
  "image_path": "/nas/admob/WHITEHAT/12345/image.png",
  "html_path": "/nas/admob/WHITEHAT/12345/lander.zip"
}
```

Common variations:

- `code: 404` with `message: "no file found"` when neither file is provided
- `code: 400` with `message: "status must be 1 (blackhat) or 2 (whitehat)"` when the status is invalid
- `code: 400` with `message: "Error occured in the function uploadBlackhatContent"` on upload/runtime failure

### `POST /api/v1/admob/landers/insert_html_content`

This is the main lander ingestion endpoint.

It validates the payload, stores the lander content in MySQL, and refreshes the Elasticsearch
document.

Request shape:

- HTTP method: `POST`
- Content-Type: `application/json`
- Accepted body styles:
  - a single JSON object
  - an object wrapped in `insertData`
  - an object with `ads: []`
  - a raw array of objects

Example request:

```json
{
  "ad_id": "12345",
  "insertData": {
    "ad_id": "12345",
    "status": 2,
    "crawled_by": ".net",
    "destinations": "https://example-landing.com/whitehat",
    "html_path": "https://cdn.example.com/lander.html",
    "screen_shot": "https://cdn.example.com/screenshot.png",
    "html_content": "<html><body><h1>Landing page</h1></body></html>",
    "domain_registered_date": "2018-03-12",
    "domain_age": 0,
    "country_iso": ["US"],
    "outgoing_url": [
      {
        "start_url": "https://example-landing.com/whitehat",
        "redirect_urls": [],
        "destination_url": "https://example-landing.com/whitehat"
      }
    ],
    "redirects": ["NA"],
    "ad_category": null,
    "source_website": "https://clickza.space/DDD/",
    "source_parameters": {
      "gad_source": "5",
      "gad_campaignid": "24090156948",
      "gclid": "CjwK..."
    },
    "whatsapp": {
      "domain": "api.whatsapp.com",
      "path": "/send/",
      "phone": "+919311475239",
      "message": "Hello",
      "parameters": {
        "phone": "+919311475239",
        "text": "Hello",
        "type": "phone_number",
        "app_absent": "0"
      }
    },
    "campaign_id": "24090156948",
    "location": {
      "without_vpn": {
        "ip": "106.51.38.160",
        "country": "India",
        "country_code": "IN"
      },
      "with_vpn": {
        "ip": "185.177.126.136",
        "country": "Netherlands",
        "country_code": "NL"
      }
    },
    "comparison": {
      "location_changed": true,
      "country_changed": true,
      "whatsapp_data_changed": false,
      "campaign_id_changed": false
    },
    "whatsapp_links": [
      "https://api.whatsapp.com/send/?phone=%2B919311475239&text=Hello&type=phone_number&app_absent=0"
    ],
    "whatsapp_texts": ["Hello"],
    "phone_numbers": ["+919311475239"],
    "contact_buttons": [
      {
        "text": "Chat on WhatsApp",
        "href": "https://api.whatsapp.com/send/?phone=%2B919311475239&text=Hello&type=phone_number&app_absent=0"
      }
    ],
    "whatsapp_rotator_detected": true,
    "whatsapp_rotator_phone_count": 7,
    "lead_campaign_tag": "spring-sale"
  }
}
```

Required fields for a normal save:

- `ad_id`
- `status`
- `crawled_by`

For `status` 1 or 2, these are also required:

- `destinations`
- `screen_shot`
- `html_content`

Response shape for a single item:

```json
{
  "code": 200,
  "status": "ok",
  "message": "Destination Lander updated successfully.",
  "data": {
    "id": 123,
    "mysql_saved": true,
    "elastic_indexed": true,
    "redirect_status": 1,
    "skipped_content": false
  },
  "exe_time": 0.083
}
```

Response shape for a batch:

```json
{
  "code": 207,
  "status": "partial",
  "message": "Processed 2 AdMob lander(s): 1 succeeded and 1 failed.",
  "data": [
    {
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
    },
    {
      "code": 422,
      "status": "rejected",
      "message": "The AdMob lander payload validation failed.",
      "hint": "Fix the listed fields and resend the same ad_id payload. No database write was attempted.",
      "errors": [
        {
          "field": "crawled_by",
          "reason": "MISSING_REQUIRED_FIELD",
          "message": "crawled_by is required and cannot be empty."
        }
      ]
    }
  ],
  "exe_time": 0.101
}
```

Common variations:

- `code: 422` with `status: "rejected"` when required fields are missing or invalid
- `code: 503` with `status: "server_error"` when MySQL or Elasticsearch is unavailable
- `code: 400` with `status: "rejected"` when the `ad_id` does not exist in `mob_ads` / `mob_search_mix`

## Payload contract

The lander endpoint accepts:

- a single JSON object
- a JSON body with `insertData`
- a JSON body with `ads: []`
- a raw array of payload objects

That means DS can keep whatever envelope best fits their pipeline.

The required fields are the same as listed in the single-item request section above.

### Status semantics

- `status = 1` or `2` means the lander content is saved normally.
- `status = 3` means redirect-only handling. The lander content row is skipped.
- `redirect_status` is computed by the API. DS does not need to send it.

### Accepted field shapes

The normalizer accepts both flat and nested forms.

Common examples:

- `destination_url` or `destinationUrl` can be used instead of `destinations`
- `screenshot_url` can be used instead of `screen_shot`
- `html` can be used instead of `html_content`
- `countryIso` can be used instead of `country_iso`
- `sourceWebsite` can be used instead of `source_website`
- `sourceParameters` can be used instead of `source_parameters`
- `whatsappUrl`, `whatsapp.url`, or `whatsapp.href` can be used for the WhatsApp URL
- `whatsappParameters` or `whatsapp.parameters` can be used for WhatsApp parameter details
- `campaignId` can be used instead of `campaign_id`
- `whatsappTexts`, `prefilledTexts`, or `prefilled_texts` can be used for prefilled WhatsApp text
- `phoneNumbers` can be used instead of `phone_numbers`
- `contactButtons` can be used instead of `contact_buttons`
- `high_volume_lead_campaign` can be used as the explicit rotator flag
- `rotator_phone_count` can be used as the explicit rotator count
- `campaign_tag` or `tracking_tag` can be used for the lead campaign tag

The API also accepts nested `whatsapp` and `location` objects.

### Important DS-facing rule

Do not rely on `comparison.whatsapp_data_changed` to mean "rotator detected".

We keep `comparison` as audit data, but the backend no longer treats it as proof that the
landing page uses a WhatsApp rotator.

If DS wants the rotator flag to be authoritative, DS must send it explicitly.

## What we store

The lander data is stored in two places:

- `mob_ads.redirect_status`
- `mob_ad_lander_content`

The SQL row keeps both structured fields and the raw payload. The ES document keeps the same
information in searchable form.

To avoid markdown table clipping, the storage map is written as bullets:

- Identity and status
  - SQL: `redirect_status`, `lander_status`, `crawled_by`
  - ES: `redirect_status`, `lander_status`, `lander_crawled_by`
- Landing page data
  - SQL: `destinations`, `html_path`, `screen_shot`, `html_content`
  - ES: `lander_destination_url`, `lander_html_path`, `lander_screen_shot`
- Domain data
  - SQL: `domain_registered_date`, `domain_age`
  - ES: `lander_domain_registered_date`, `lander_domain_age`
- Country and URL evidence
  - SQL: `country_iso_json`, `outgoing_url_json`, `redirects_json`
  - ES: `country_iso` plus the parsed JSON-backed fields
- WA source data
  - SQL: `source_website`, `source_parameters_json`
  - ES: `source_website`, `source_parameters`
- WhatsApp data
  - SQL: `whatsapp_url`, `whatsapp_domain`, `whatsapp_path`, `whatsapp_phone`, `whatsapp_message`, `whatsapp_parameters_json`
  - ES: `whatsapp_url`, `whatsapp_domain`, `whatsapp_path`, `whatsapp_phone`, `whatsapp_message`, `whatsapp_parameters`
- VPN comparison data
  - SQL: `campaign_id`, `location_without_vpn_json`, `location_with_vpn_json`, `comparison_json`
  - ES: `campaign_id`, `location_without_vpn`, `location_with_vpn`, `comparison`
- Contact and signal data
  - SQL: `whatsapp_links_json`, `whatsapp_texts_json`, `phone_numbers_json`, `contact_buttons_json`, `contact_button_count`, `whatsapp_rotator_detected`, `whatsapp_rotator_phone_count`, `lead_campaign_tag`, `raw_payload_json`
  - ES: `whatsapp_links`, `whatsapp_prefilled_texts`, `phone_numbers`, `contact_buttons`, `contact_button_count`, `whatsapp_rotator_detected`, `whatsapp_rotator_phone_count`, `lead_campaign_tag`

## What the API returns

The insert endpoint returns a normal API response and includes operational flags when relevant.

Common responses:

- `200` for a successful single insert
- `207` for a partial batch success
- `400` when the ad does not exist or the ad is not eligible
- `422` when validation fails or the batch is empty
- `503` when MySQL or Elasticsearch is unavailable
- `500` for unexpected failures

Useful response flags:

- `mysql_saved`
- `elastic_indexed`
- `redirect_status`
- `skipped_content`

## Operational behavior

The current flow is:

1. Validate the payload.
2. Check that the target ad exists in the AdMob search index.
3. Save the lander data in MySQL.
4. Refresh the ES document.

Important note:

- If the Elasticsearch preflight lookup fails, the request returns `503` and MySQL is not written.
- If MySQL succeeds but ES indexing fails afterward, the API returns `503` and reports that MySQL
  is saved while ES indexing is pending.

That means the lander flow depends on a healthy AdMob ES index for full success.

## Migration and upgrade notes

Because the SQL table and ES index already existed, we made the upgrade additive.

Use these scripts for existing environments:

- `scripts/admob/migrate-lander-fields.js`
- `scripts/admob/apply-es-mapping.js`

These scripts are safe to rerun:

- the SQL script only adds missing columns or indexes
- the ES script only adds missing fields through `PUT _mapping`

For fresh installs, the checked-in schema and mapping files are the source of truth.

## What DS should remember

- Send the final rendered landing-page data, not a partial scrape.
- Send the WhatsApp and VPN evidence as raw data when available.
- Send the rotator flag explicitly if it matters to the campaign.
- Do not reshape the payload into legacy table format.
- Do not expect the API to guess a WhatsApp rotator from one scrape comparison.

## Related files

- [AdMob ERD](erd/admob.md)
- [AdMob insertion manifest](ADMOB-INSERTION-MANIFEST.md)
- [AdMob migration README](../scripts/admob/README.md)
- [AdMob SQL schema](../scripts/admob/mobdb.schema.sql)
- [AdMob ES mapping fragment](../scripts/admob/mob_search_mix.mapping.json)
- [AdMob lander normalization](../src/services/admob/landers/normalize.js)
- [AdMob lander insert service](../src/services/admob/landers/insertHtmlService.js)
