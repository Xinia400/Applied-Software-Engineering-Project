from __future__ import annotations

from dataclasses import dataclass
from typing import List
import requests
import re

@dataclass
class FoundFile:
    qda_url: str
    repository: str
    dataset_url: str | None
    title: str | None
    license: str | None
    uploader_name: str | None
    uploader_email: str | None
    description: str | None
    doi: str | None
    year: int | None
    filename: str | None = None


def search_icpsr(base_url: str, query: str, max_pages: int = 1) -> List[FoundFile]:
    out: List[FoundFile] = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    search_url = f"{base_url}/web/ICPSR/search/studies?q={query}"

    try:
        r = requests.get(search_url, headers=headers, timeout=60)
        r.raise_for_status()

        study_ids = set(re.findall(r'/studies/(\\d+)', r.text))
        print(f"[ICPSR] Found {len(study_ids)} study IDs")

        for sid in study_ids:
            dataset_url = f"{base_url}/web/ICPSR/studies/{sid}"
            export_url = f"{base_url}/web/ICPSR/studies/{sid}?format=DDI"

            filename = f"ICPSR_{sid}.xml"

            out.append(
                FoundFile(
                    qda_url=export_url,
                    repository="icpsr",
                    dataset_url=dataset_url,
                    title=f"ICPSR Study {sid}",
                    license=None,
                    uploader_name=None,
                    uploader_email=None,
                    description="Metadata export (DDI XML) from ICPSR",
                    doi=None,
                    year=None,
                    filename=filename
                )
            )

    except Exception as e:
        print(f"[ICPSR ERROR] {e}")

    return out