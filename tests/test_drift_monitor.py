from __future__ import annotations

import zipfile
from pathlib import Path

from src.automation.drift_monitor import (
    classify_archive_drift,
    classify_project_drift,
    qdpx_internal_manifest,
    qdpx_project_lookup,
)


def test_qdpx_project_lookup_uses_dans_qda_titles() -> None:
    projects = [
        {
            "id": 1,
            "repository_id": 5,
            "type": "QDA_PROJECT",
            "title": "Example Project.qdpx",
        },
        {
            "id": 2,
            "repository_id": 5,
            "type": "OTHER_PROJECT",
            "title": "Metadata Export.xml",
        },
        {
            "id": 3,
            "repository_id": 15,
            "type": "QDA_PROJECT",
            "title": "Wrong Repository.qdpx",
        },
    ]

    result = qdpx_project_lookup(projects)

    assert result == {
        "example project.qdpx": {
            "project_id": "1",
            "project_title": "Example Project.qdpx",
        }
    }


def test_project_drift_requires_reclassification_for_metadata_change() -> None:
    current = {
        "metadata_sha256": "new-metadata",
        "classification_sha256": "same-classification",
    }
    previous = {
        "metadata_sha256": "old-metadata",
        "classification_sha256": "same-classification",
    }

    result = classify_project_drift(current, previous)

    assert result["status"] == "RECLASSIFICATION_REQUIRED"
    assert result["reclassification_required"] is True
    assert result["reasons"] == ["METADATA_CHANGED"]


def test_project_drift_detects_unchanged_project() -> None:
    fingerprint = {
        "metadata_sha256": "same-metadata",
        "classification_sha256": "same-classification",
    }

    result = classify_project_drift(fingerprint, fingerprint)

    assert result["status"] == "UNCHANGED"
    assert result["reclassification_required"] is False
    assert result["reasons"] == ["UNCHANGED"]


def test_archive_drift_requires_reclassification_when_archive_changes() -> None:
    current = {
        "archive_sha256": "new-archive",
        "manifest_sha256": "same-manifest",
        "zip_status": "ZIP_CONTAINER",
    }
    previous = {
        "archive_sha256": "old-archive",
        "manifest_sha256": "same-manifest",
        "zip_status": "ZIP_CONTAINER",
    }

    result = classify_archive_drift(current, previous)

    assert result["status"] == "RECLASSIFICATION_REQUIRED"
    assert result["reclassification_required"] is True
    assert result["reasons"] == ["QDPX_ARCHIVE_CHANGED"]


def test_qdpx_internal_manifest_is_stable(tmp_path: Path) -> None:
    archive_path = tmp_path / "example.qdpx"

    with zipfile.ZipFile(archive_path, "w") as archive:
        archive.writestr("sources/example.txt", "hello")
        archive.writestr("project.qde", "<project />")

    first = qdpx_internal_manifest(archive_path)
    second = qdpx_internal_manifest(archive_path)

    assert first["zip_status"] == "ZIP_CONTAINER"
    assert first["internal_file_count"] == 2
    assert first["manifest_sha256"] == second["manifest_sha256"]


def test_qdpx_internal_manifest_handles_non_zip_file(tmp_path: Path) -> None:
    invalid_path = tmp_path / "broken.qdpx"
    invalid_path.write_text("not a zip archive", encoding="utf-8")

    result = qdpx_internal_manifest(invalid_path)

    assert result == {
        "zip_status": "NOT_A_ZIP_CONTAINER",
        "internal_file_count": 0,
        "manifest_sha256": None,
    }
