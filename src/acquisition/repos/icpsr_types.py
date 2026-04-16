from __future__ import annotations
from dataclasses import dataclass

@dataclass
class ICPSRRecord:
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

    access_class: str | None = None
    acquisition_mode: str | None = None
    content_scope: str | None = None