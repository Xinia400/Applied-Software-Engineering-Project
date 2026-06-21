from __future__ import annotations

import logging
import zipfile
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

from pypdf import PdfReader


TIER2_EXTRACTOR_VERSION = "tier2-extractor-v1"

SUPPORTED_TIER2_EXTENSIONS = {"txt", "pdf"}

MAX_PDF_PAGES_PER_FILE = 3
MAX_TEXT_CHARS_PER_FILE = 20_000

logging.getLogger("pypdf").setLevel(logging.ERROR)


@dataclass(frozen=True)
class ExtractedPrimaryFile:
    internal_path: str
    file_name: str
    extension: str
    extraction_method: str
    extraction_status: str
    extracted_characters: int
    pages_examined: int | None
    text: str
    error: str | None = None

    def as_metadata(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("text")
        return payload


def _normalize_text(value: str) -> str:
    return " ".join(value.replace("\x00", " ").split())


def _limit_text(value: str) -> str:
    return value[:MAX_TEXT_CHARS_PER_FILE]


def extract_txt_text(payload: bytes) -> str:
    return _limit_text(
        _normalize_text(
            payload.decode("utf-8", errors="replace")
        )
    )


def extract_pdf_text(payload: bytes) -> tuple[str, int]:
    reader = PdfReader(BytesIO(payload), strict=False)
    pages = reader.pages[:MAX_PDF_PAGES_PER_FILE]

    text = "\n".join(
        page.extract_text() or ""
        for page in pages
    )

    return _limit_text(_normalize_text(text)), len(pages)


def extract_qdpx_primary_text(
    archive_path: Path,
) -> tuple[list[ExtractedPrimaryFile], dict[str, Any]]:
    """Extract bounded Tier 2 text from QDPX internal primary files.

    Only sources/*.txt and sources/*.pdf are read. Unsupported file types
    are not treated as failures because their content is intentionally not
    parsed in this deterministic, lightweight extractor.
    """
    extracted: list[ExtractedPrimaryFile] = []

    with zipfile.ZipFile(archive_path) as archive:
        members = sorted(
            (
                item.filename
                for item in archive.infolist()
                if not item.is_dir()
                and item.filename.casefold().startswith("sources/")
            ),
            key=str.casefold,
        )

        for internal_path in members:
            extension = Path(internal_path).suffix.casefold().lstrip(".")

            if extension not in SUPPORTED_TIER2_EXTENSIONS:
                continue

            payload = archive.read(internal_path)

            try:
                if extension == "txt":
                    text = extract_txt_text(payload)
                    method = "UTF8_TEXT"
                    pages_examined = None
                else:
                    text, pages_examined = extract_pdf_text(payload)
                    method = "PYPDF_FIRST_3_PAGES"

                status = (
                    "EXTRACTED"
                    if text
                    else "EMPTY_TEXT"
                )

                extracted.append(
                    ExtractedPrimaryFile(
                        internal_path=internal_path,
                        file_name=Path(internal_path).name,
                        extension=extension,
                        extraction_method=method,
                        extraction_status=status,
                        extracted_characters=len(text),
                        pages_examined=pages_examined,
                        text=text,
                    )
                )

            except Exception as error:
                extracted.append(
                    ExtractedPrimaryFile(
                        internal_path=internal_path,
                        file_name=Path(internal_path).name,
                        extension=extension,
                        extraction_method=(
                            "UTF8_TEXT"
                            if extension == "txt"
                            else "PYPDF_FIRST_3_PAGES"
                        ),
                        extraction_status="EXTRACTION_FAILED",
                        extracted_characters=0,
                        pages_examined=None,
                        text="",
                        error=f"{type(error).__name__}: {error}",
                    )
                )

    extracted_count = sum(
        item.extraction_status == "EXTRACTED"
        for item in extracted
    )

    failed_count = sum(
        item.extraction_status == "EXTRACTION_FAILED"
        for item in extracted
    )

    summary = {
        "extractor_version": TIER2_EXTRACTOR_VERSION,
        "archive_path": str(archive_path),
        "candidate_file_count": len(extracted),
        "extracted_file_count": extracted_count,
        "failed_file_count": failed_count,
        "empty_file_count": sum(
            item.extraction_status == "EMPTY_TEXT"
            for item in extracted
        ),
        "total_extracted_characters": sum(
            item.extracted_characters
            for item in extracted
        ),
        "files_by_extension": {
            extension: sum(
                item.extension == extension
                for item in extracted
            )
            for extension in sorted(
                {item.extension for item in extracted}
            )
        },
    }

    return extracted, summary
