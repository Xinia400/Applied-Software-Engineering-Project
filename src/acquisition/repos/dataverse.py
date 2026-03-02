from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import requests

QDA_EXTS = {".qdpx", ".qdp", ".nvpx", ".atlproj", ".mx", ".mxd"}

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

def _looks_qda(text: str) -> bool:
    t = (text or "").lower()
    return any(ext in t for ext in QDA_EXTS) or "qdpx" in t or "nvp" in t or "atlas.ti" in t or "maxqda" in t

def search_dataverse(base_url: str, query: str, max_pages: int = 1, per_page: int = 10, api_token: Optional[str] = None) -> List[FoundFile]:
    """
    Dataverse Search API: GET {base_url}/api/search?q=...&type=dataset&start=...&per_page=...
    Docs: Dataverse Search API. :contentReference[oaicite:5]{index=5}
    """
    headers = {"User-Agent": "QDArchiveSeeder/1.0"}
    if api_token:
        headers["X-Dataverse-key"] = api_token

    out: List[FoundFile] = []
    start = 0
    for _ in range(max_pages):
        params = {"q": query, "type": "dataset", "start": start, "per_page": per_page}
        r = requests.get(f"{base_url.rstrip('/')}/api/search", params=params, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()
        items = (data.get("data") or {}).get("items") or []

        for it in items:
            # Dataverse search results do not always contain file lists.
            # We store dataset-level URL; later you can call dataset API by persistentId to list files.
            title = it.get("name")
            desc = it.get("description")
            doi = it.get("global_id")  # often "doi:..."
            dataset_url = it.get("url")

            # Only keep results that likely mention QDA
            if not _looks_qda(f"{title} {desc}"):
                continue

            # Placeholder qda_url: we don't know file links yet from search endpoint alone.
            # We'll represent dataset as "headless candidate" and later enrich by calling dataset API.
            out.append(FoundFile(
                qda_url=dataset_url,           # temporary anchor; you can enrich later
                repository="dataverse",
                dataset_url=dataset_url,
                title=title,
                license=None,
                uploader_name=None,
                uploader_email=None,
                description=desc,
                doi=doi,
                year=None
            ))
        start += per_page
    return out