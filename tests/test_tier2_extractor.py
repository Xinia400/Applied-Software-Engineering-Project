from __future__ import annotations

import zipfile
from pathlib import Path

from src.classification.tier2_extractor import (
    MAX_TEXT_CHARS_PER_FILE,
    extract_qdpx_primary_text,
)


def test_extracts_txt_from_sources_folder(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "example.qdpx"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "sources/interview.txt",
            "International criminal law prosecution",
        )
        archive.writestr(
            "project.qde",
            "<project />",
        )
        archive.writestr(
            "notes/ignored.txt",
            "This must not be read.",
        )

    extracted, summary = extract_qdpx_primary_text(archive_path)

    assert len(extracted) == 1
    assert extracted[0].file_name == "interview.txt"
    assert extracted[0].extraction_status == "EXTRACTED"
    assert "criminal law" in extracted[0].text
    assert summary["candidate_file_count"] == 1
    assert summary["extracted_file_count"] == 1
    assert summary["failed_file_count"] == 0


def test_limits_long_txt_content(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "large.qdpx"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr(
            "sources/large.txt",
            "a" * (MAX_TEXT_CHARS_PER_FILE + 500),
        )

    extracted, _ = extract_qdpx_primary_text(archive_path)

    assert len(extracted) == 1
    assert extracted[0].extracted_characters == MAX_TEXT_CHARS_PER_FILE


def test_ignores_non_tier2_file_types(
    tmp_path: Path,
) -> None:
    archive_path = tmp_path / "mixed.qdpx"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("sources/audio.mp3", b"audio")
        archive.writestr("sources/image.png", b"image")
        archive.writestr("sources/readme.md", "ignored")

    extracted, summary = extract_qdpx_primary_text(archive_path)

    assert extracted == []
    assert summary["candidate_file_count"] == 0
    assert summary["extracted_file_count"] == 0
