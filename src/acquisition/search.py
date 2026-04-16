from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

from src.acquisition.repos.dans import search_dans
from src.acquisition.repos.icpsr_engine import search_icpsr_engine

@dataclass
class FoundQDA:
    qda_url: str
    repository: str
    dataset_url: str | None = None
    title: str | None = None
    license: str | None = None
    uploader_name: str | None = None
    uploader_email: str | None = None
    description: str | None = None
    doi: str | None = None
    year: int | None = None
    filename: str | None = None

    metadata_only: bool = False
    status_hint: str | None = None

    access_class: str | None = None
    acquisition_mode: str | None = None
    content_scope: str | None = None

def search_from_config(cfg: Dict[str, Any]) -> List[FoundQDA]:
    out: List[FoundQDA] = []

    for repo in cfg.get("repositories", []):
        rtype = repo.get("type")
        query = repo.get("query", "")
        max_pages = int(repo.get("max_pages", 1))

        if rtype == "dans":
            base_url = repo.get("base_url")
            hits = search_dans(base_url=base_url, query=query, max_pages=max_pages)
            for h in hits:
                out.append(FoundQDA(**h.__dict__))

        elif rtype == "icpsr":
            hits = search_icpsr_engine(
                base_url=repo.get("base_url"),
                query=repo.get("query"),
                max_pages=repo.get("max_pages", 1),
            )
            for h in hits:
                out.append(FoundQDA(**h))
        else:
            for u in repo.get("qda_urls", []):
                out.append(
                    FoundQDA(
                        qda_url=u,
                        repository=repo.get("name", "manual")
                    )
                )

    return out