from __future__ import annotations
from dataclasses import dataclass
from typing import List, Optional
import requests

ZENODO_API = "https://zenodo.org/api"

QDA_EXTS = (
    ".qdpx", ".qdp",
    ".nvpx", ".nvp",
    ".atlproj", ".hpr7", ".atl",
    ".mx", ".mx20", ".mx22",
    ".ddsx", ".qdm", ".f4p", ".qrk"
)

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
    filename: str | None = None   # use Zenodo file name (avoids "content")

def _is_qda(filename: str) -> bool:
    fn = (filename or "").lower()
    return fn.endswith(QDA_EXTS)

def search_zenodo(query: str, max_pages: int = 1, page_size: int = 25, token: Optional[str] = None) -> List[FoundFile]:
    headers = {"User-Agent": "QDArchiveSeeder/1.0"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    out: List[FoundFile] = []

    for page in range(1, max_pages + 1):
        params = {"q": query, "page": page, "size": page_size}
        r = requests.get(f"{ZENODO_API}/records", params=params, headers=headers, timeout=60)
        r.raise_for_status()
        data = r.json()

        hits = (data.get("hits") or {}).get("hits") or []
        for hit in hits:
            meta = hit.get("metadata") or {}
            files = hit.get("files") or []

            title = meta.get("title")
            description = meta.get("description")
            doi = meta.get("doi") or hit.get("doi")

            year = None
            pub = meta.get("publication_date")
            if pub and len(pub) >= 4 and pub[:4].isdigit():
                year = int(pub[:4])

            license_id = None
            lic = meta.get("license")
            if isinstance(lic, dict):
                license_id = lic.get("id") or lic.get("title")
            elif isinstance(lic, str):
                license_id = lic

            creators = meta.get("creators") or []
            uploader_name = creators[0].get("name") if creators and isinstance(creators[0], dict) else None

            dataset_url = (hit.get("links") or {}).get("html")

            # ✅ This loop must be INSIDE the function:
            for f in files:
                key = f.get("key") or f.get("filename") or ""
                if not _is_qda(key):
                    continue

                qda_url = (f.get("links") or {}).get("self") or (f.get("links") or {}).get("download")
                if not qda_url:
                    continue

                out.append(FoundFile(
                    qda_url=qda_url,
                    repository="zenodo",
                    dataset_url=dataset_url,
                    title=title,
                    license=license_id,
                    uploader_name=uploader_name,
                    uploader_email=None,
                    description=description,
                    doi=doi,
                    year=year,
                    filename=key
                ))

    return out