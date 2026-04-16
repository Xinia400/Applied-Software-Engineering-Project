from __future__ import annotations
import os
from typing import List
import requests

from src.acquisition.repos.icpsr_types import ICPSRRecord

def search_icpsr_with_session(query: str) -> List[ICPSRRecord]:
    """
    Optional session-aware lane.
    Uses a cookie string from .env if you have a logged-in browser session.

    Environment variable:
      ICPSR_COOKIE

    This does not automate login itself.
    It only reuses an existing authenticated session.
    """
    cookie = os.getenv("ICPSR_COOKIE")
    if not cookie:
        return []

    out: List[ICPSRRecord] = []

    session = requests.Session()
    session.headers.update({
        "User-Agent": "QDArchiveSeeder/1.0",
        "Cookie": cookie,
    })

    # Minimal, safe starting point:
    # authenticated access to the same ICPSR search URL
    search_url = f"https://www.icpsr.umich.edu/web/ICPSR/search/studies?q={query}"

    try:
        r = session.get(search_url, timeout=60)
        r.raise_for_status()

        out.append(
            ICPSRRecord(
                qda_url=search_url,
                repository="icpsr",
                dataset_url=search_url,
                title=f"ICPSR session query: {query}",
                license=None,
                uploader_name=None,
                uploader_email=None,
                description="Authenticated ICPSR session was used successfully. Extend this lane to inspect account-gated documentation/public files.",
                doi=None,
                year=None,
                filename=None,
                metadata_only=True,
                status_hint="SESSION_OK",
                access_class="PUBLIC_LOGIN",
                acquisition_mode="SESSION_DOWNLOAD",
                content_scope="METADATA",
            )
        )

    except Exception as e:
        out.append(
            ICPSRRecord(
                qda_url=search_url,
                repository="icpsr",
                dataset_url=search_url,
                title=f"ICPSR session query: {query}",
                license=None,
                uploader_name=None,
                uploader_email=None,
                description=f"Authenticated session attempt failed: {e}",
                doi=None,
                year=None,
                filename=None,
                metadata_only=True,
                status_hint="FAILED",
                access_class="UNKNOWN",
                acquisition_mode="SESSION_DOWNLOAD",
                content_scope="METADATA",
            )
        )

    return out