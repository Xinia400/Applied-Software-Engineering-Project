from __future__ import annotations
import os
from typing import List
from urllib.parse import quote_plus
import requests

from src.acquisition.repos.icpsr_types import ICPSRRecord

def search_icpsr_metadata_api(query: str) -> List[ICPSRRecord]:
    """
    Strong lane 1:
    Use official ICPSR Metadata Export API if credentials are available.
    If not available, return an empty list gracefully.

    Environment variables:
      ICPSR_METADATA_API_URL
      ICPSR_METADATA_API_TOKEN
    """
    base_url = os.getenv("ICPSR_METADATA_API_URL")
    token = os.getenv("ICPSR_METADATA_API_TOKEN")

    if not base_url or not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "User-Agent": "QDArchiveSeeder/1.0",
    }

    # Keep this generic because the exact query syntax can vary by deployment.
    # We only need a robust discovery attempt.
    url = f"{base_url.rstrip('/')}/search?q={quote_plus(query)}"

    out: List[ICPSRRecord] = []

    try:
        r = requests.get(url, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()

        items = data if isinstance(data, list) else data.get("items", [])

        for item in items:
            title = item.get("title") or item.get("name") or f"ICPSR metadata result: {query}"
            dataset_url = item.get("url") or item.get("landingPage") or item.get("id")
            doi = item.get("doi")
            desc = item.get("description") or item.get("summary")

            out.append(
                ICPSRRecord(
                    qda_url=dataset_url or f"metadata-api:{query}",
                    repository="icpsr",
                    dataset_url=dataset_url,
                    title=title,
                    license=None,
                    uploader_name=None,
                    uploader_email=None,
                    description=desc or "Record discovered via ICPSR Metadata API.",
                    doi=doi,
                    year=None,
                    filename=None,
                    metadata_only=True,
                    status_hint="METADATA_API_FOUND",
                    access_class="UNKNOWN",
                    acquisition_mode="METADATA_API",
                    content_scope="METADATA",
                )
            )
    except Exception as e:
        out.append(
            ICPSRRecord(
                qda_url=f"metadata-api:{query}",
                repository="icpsr",
                dataset_url=None,
                title=f"ICPSR metadata API query: {query}",
                license=None,
                uploader_name=None,
                uploader_email=None,
                description=f"Metadata API attempt failed: {e}",
                doi=None,
                year=None,
                filename=None,
                metadata_only=True,
                status_hint="METADATA_API_FAILED",
                access_class="UNKNOWN",
                acquisition_mode="METADATA_API",
                content_scope="METADATA",
            )
        )

    return out