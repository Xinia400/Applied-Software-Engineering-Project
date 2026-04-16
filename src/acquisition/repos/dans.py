from __future__ import annotations
from dataclasses import dataclass
from typing import List
import requests

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
    filename: str | None = None
    metadata_only: bool = False
    status_hint: str | None = None


def _is_qda(filename: str) -> bool:
    return (filename or "").lower().endswith(QDA_EXTS)


def search_dans(base_url: str, query: str, max_pages: int = 1, per_page: int = 25) -> List[FoundFile]:
    """
    Robust DANS search:
    - Safe against timeouts
    - Does NOT crash pipeline
    - Returns partial results if possible
    """

    out: List[FoundFile] = []

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    start = 0

    for page in range(max_pages):
        params = {
            "q": query,
            "type": "file",
            "start": start,
            "per_page": per_page
        }

        url = f"{base_url.rstrip('/')}/api/search"

        print(f"[DANS] Requesting page {page+1}: {url}")

        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            r.raise_for_status()
            data = r.json()

        except requests.exceptions.RequestException as e:
            print(f"[DANS ERROR] Skipping DANS due to: {e}")
            break   # stop DANS but DO NOT crash whole system

        items = (data.get("data") or {}).get("items") or []

        if not items:
            print("[DANS] No more items found")
            break

        for item in items:
            name = item.get("name") or ""

            if not _is_qda(name):
                continue

            dataset_url = item.get("url")
            description = item.get("description")
            doi = item.get("global_id") or item.get("identifier")
            title = item.get("name")

            file_id = item.get("file_id") or item.get("entity_id")

            if file_id:
                qda_url = f"{base_url.rstrip('/')}/api/access/datafile/{file_id}"
            else:
                qda_url = dataset_url

            out.append(
                FoundFile(
                    qda_url=qda_url,
                    repository="dans",
                    dataset_url=dataset_url,
                    title=title,
                    license=None,
                    uploader_name=None,
                    uploader_email=None,
                    description=description,
                    doi=doi,
                    year=None,
                    filename=name,
                    metadata_only=False,
                    status_hint="OK"
                )
            )

        start += per_page

    print(f"[DANS] Total QDA files found: {len(out)}")

    return out