from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any

from src.acquisition.repos.zenodo import search_zenodo, FoundFile as ZFound
from src.acquisition.repos.dataverse import search_dataverse, FoundFile as DFound
from src.acquisition.repos.dryad import search_dryad, FoundFile as RFound


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

def search_from_config(cfg: Dict[str, Any]) -> List[FoundQDA]:
    out: List[FoundQDA] = []

    for repo in cfg.get("repositories", []):
        rtype = repo.get("type")
        name = repo.get("name", rtype or "unknown")
        query = repo.get("query", "")
        max_pages = int(repo.get("max_pages", 1))

        if rtype == "zenodo":
            hits = search_zenodo(query=query, max_pages=max_pages)
            for h in hits:
                out.append(FoundQDA(**h.__dict__))

        elif rtype == "dataverse":
            base_url = repo.get("base_url")
            if not base_url:
                raise ValueError("dataverse repo requires base_url")
            hits = search_dataverse(base_url=base_url, query=query, max_pages=max_pages)
            for h in hits:
                out.append(FoundQDA(**h.__dict__))

        elif rtype == "dryad":
            hits = search_dryad(query=query, max_pages=max_pages)
            for h in hits:
                out.append(FoundQDA(**h.__dict__))

        else:
            # fallback: manual list
            for u in repo.get("qda_urls", []):
                out.append(FoundQDA(qda_url=u, repository=name))

    return out