"""Create a ZIP archive containing the rendered landing-page HTML."""
from __future__ import annotations
import logging
import zipfile
from pathlib import Path

logger = logging.getLogger("admob_scraper")


def create_html_zip(html_content: str, ad_id: str, output_dir: Path) -> Path:
    """Write rendered HTML into a ZIP file and return the path.

    The ZIP contains a single ``index.html`` entry.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    zip_path = output_dir / f"{ad_id}_lander.zip"

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("index.html", html_content)

    logger.info("HTML ZIP created: %s (%.1f KB)", zip_path.name, zip_path.stat().st_size / 1024)
    return zip_path
