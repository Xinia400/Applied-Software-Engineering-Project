from __future__ import annotations
from dataclasses import dataclass
from typing import List
import requests

DRYAD_API = "https://datadryad.org/api/v2"

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

def search_dryad(query: str, max_pages: int = 1, per_page: int = 20) -> List[FoundFile]:
    """
    Dryad API supports searching datasets. :contentReference[oaicite:6]{index=6}
    """
    out: List[FoundFile] = []
    for page in range(1, max_pages + 1):
        params = {"search": query, "page": page, "per_page": per_page}
        r = requests.get(f"{DRYAD_API}/datasets", params=params, timeout=60, headers={"User-Agent":"QDArchiveSeeder/1.0"})
        r.raise_for_status()
        data = r.json()
        items = (data.get("_embedded") or {}).get("stash:datasets") or []

        for ds in items:
            title = ds.get("title")
            description = ds.get("abstract")
            doi = ds.get("identifier")
            dataset_url = (ds.get("_links") or {}).get("stash:landingPage", {}).get("href")

            # Dryad file listing typically requires following version/files endpoints.
            # For now store dataset as candidate; you can enrich later by listing files per version.
            out.append(FoundFile(
                qda_url=dataset_url or doi or title or "dryad",
                repository="dryad",
                dataset_url=dataset_url,
                title=title,
                license=None,
                uploader_name=None,
                uploader_email=None,
                description=description,
                doi=doi,
                year=None
            ))
    return out