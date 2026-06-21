from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MONITOR_VERSION = "drift-monitor-v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_json(value: Any) -> str:
    serialized = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256_bytes(serialized.encode("utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def sqlite_columns(
    connection: sqlite3.Connection,
    table_name: str,
) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(
            f"PRAGMA table_info({table_name})"
        )
    }


def read_delivery_database(
    database_path: Path,
) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        project_columns = sqlite_columns(
            connection,
            "PROJECTS",
        )
        file_columns = sqlite_columns(
            connection,
            "FILES",
        )

        selected_project_fields = [
            field
            for field in (
                "id",
                "repository_id",
                "repository_url",
                "project_url",
                "title",
                "description",
                "language",
                "doi",
                "type",
                "primary_section_code",
                "primary_division_code",
                "class",
                "secondary_section_code",
                "secondary_division_code",
                "secondary_class",
                "classification_rule",
                "confidence",
                "classifier_version",
                "classified_at_utc",
            )
            if field in project_columns
        ]

        project_query = (
            "SELECT "
            + ", ".join(selected_project_fields)
            + " FROM PROJECTS "
            + "WHERE repository_id IN (5, 15) "
            + "ORDER BY repository_id, id"
        )

        project_rows = [
            dict(row)
            for row in connection.execute(project_query)
        ]

        selected_file_fields = [
            field
            for field in (
                "id",
                "project_id",
                "file_name",
                "file_type",
                "file_origin",
                "file_reference",
                "is_primary_data",
            )
            if field in file_columns
        ]

        file_query = (
            "SELECT "
            + ", ".join(selected_file_fields)
            + " FROM FILES "
            + "WHERE project_id IN ("
            + "SELECT id FROM PROJECTS "
            + "WHERE repository_id IN (5, 15)"
            + ") "
            + "ORDER BY project_id, id"
        )

        file_rows = [
            dict(row)
            for row in connection.execute(file_query)
        ]

        schema_rows = []

        for table_name in (
            "PROJECTS",
            "FILES",
            "KEYWORDS",
            "LICENSES",
            "PERSON_ROLE",
            "PROJECT_TYPE_CLASSIFICATIONS",
            "ISIC_PROJECT_CLASSIFICATIONS",
            "ISIC_FILE_CLASSIFICATIONS",
            "delivery_metadata",
        ):
            columns = [
                dict(row)
                for row in connection.execute(
                    f"PRAGMA table_info({table_name})"
                )
            ]

            schema_rows.append(
                {
                    "table": table_name,
                    "columns": columns,
                }
            )

        return {
            "database_sha256": sha256_file(database_path),
            "schema_fingerprint": sha256_json(schema_rows),
            "projects": project_rows,
            "files": file_rows,
        }

    finally:
        connection.close()


def qdpx_project_lookup(
    projects: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Map official DANS QDA project titles to local QDPX archives.

    The delivery FILES table intentionally contains classified internal
    QDPX primary files only. Therefore, outer archive discovery is based
    on the DANS QDA project title, which is the original QDPX filename.
    """
    lookup: dict[str, dict[str, Any]] = {}

    for project in projects:
        repository_id = str(project.get("repository_id") or "")
        project_type = str(project.get("type") or "")
        title = str(project.get("title") or "").strip()

        if repository_id != "5":
            continue

        if project_type != "QDA_PROJECT":
            continue

        if Path(title).suffix.casefold() != ".qdpx":
            continue

        lookup[Path(title).name.casefold()] = {
            "project_id": str(project["id"]),
            "project_title": title,
        }

    return lookup


def qdpx_internal_manifest(
    archive_path: Path,
) -> dict[str, Any]:
    if not zipfile.is_zipfile(archive_path):
        return {
            "zip_status": "NOT_A_ZIP_CONTAINER",
            "internal_file_count": 0,
            "manifest_sha256": None,
        }

    with zipfile.ZipFile(archive_path) as archive:
        members = [
            {
                "path": item.filename,
                "crc": item.CRC,
                "compressed_size": item.compress_size,
                "uncompressed_size": item.file_size,
            }
            for item in archive.infolist()
            if not item.is_dir()
        ]

    return {
        "zip_status": "ZIP_CONTAINER",
        "internal_file_count": len(members),
        "manifest_sha256": sha256_json(members),
    }


def inspect_official_qdpx_archives(
    raw_data_root: Path,
    qdpx_lookup: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    found_names: set[str] = set()

    for archive_path in sorted(raw_data_root.rglob("*.qdpx")):
        if not archive_path.is_file():
            continue

        archive_key = archive_path.name.casefold()

        if archive_key not in qdpx_lookup:
            continue

        found_names.add(archive_key)

        record = {
            "archive_name": archive_path.name,
            "archive_path": str(archive_path),
            "project_id": qdpx_lookup[archive_key]["project_id"],
            "project_title": qdpx_lookup[archive_key][
                "project_title"
            ],
            "archive_sha256": sha256_file(archive_path),
            "archive_bytes": archive_path.stat().st_size,
        }

        record.update(qdpx_internal_manifest(archive_path))
        results.append(record)

    for archive_key, project_info in qdpx_lookup.items():
        if archive_key in found_names:
            continue

        results.append(
            {
                "archive_name": archive_key,
                "archive_path": None,
                "project_id": project_info["project_id"],
                "project_title": project_info["project_title"],
                "archive_sha256": None,
                "archive_bytes": None,
                "zip_status": "ARCHIVE_NOT_FOUND",
                "internal_file_count": 0,
                "manifest_sha256": None,
            }
        )

    return sorted(
        results,
        key=lambda item: (
            str(item["project_id"]),
            item["archive_name"],
        ),
    )


def project_fingerprints(
    projects: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}

    metadata_fields = (
        "repository_id",
        "repository_url",
        "project_url",
        "title",
        "description",
        "language",
        "doi",
    )

    classification_fields = (
        "type",
        "primary_section_code",
        "primary_division_code",
        "class",
        "secondary_section_code",
        "secondary_division_code",
        "secondary_class",
        "classification_rule",
        "confidence",
        "classifier_version",
    )

    for project in projects:
        project_id = str(project["id"])

        metadata = {
            key: project.get(key)
            for key in metadata_fields
        }

        classification = {
            key: project.get(key)
            for key in classification_fields
        }

        output[project_id] = {
            "title": project.get("title"),
            "metadata_sha256": sha256_json(metadata),
            "classification_sha256": sha256_json(
                classification
            ),
        }

    return output


def classify_project_drift(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    if previous is None:
        return {
            "status": "BASELINE_CREATED",
            "reclassification_required": False,
            "reasons": ["No previous snapshot exists."],
        }

    reasons: list[str] = []
    reclassification_required = False

    if (
        current["metadata_sha256"]
        != previous.get("metadata_sha256")
    ):
        reasons.append("METADATA_CHANGED")
        reclassification_required = True

    if (
        current["classification_sha256"]
        != previous.get("classification_sha256")
    ):
        reasons.append("CLASSIFICATION_OUTPUT_CHANGED")

    if not reasons:
        reasons.append("UNCHANGED")

    return {
        "status": (
            "RECLASSIFICATION_REQUIRED"
            if reclassification_required
            else reasons[0]
        ),
        "reclassification_required": reclassification_required,
        "reasons": reasons,
    }


def classify_archive_drift(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    if previous is None:
        return {
            "status": "BASELINE_CREATED",
            "reclassification_required": False,
            "reasons": ["No previous archive snapshot exists."],
        }

    reasons: list[str] = []

    if current.get("archive_sha256") != previous.get(
        "archive_sha256"
    ):
        reasons.append("QDPX_ARCHIVE_CHANGED")

    if current.get("manifest_sha256") != previous.get(
        "manifest_sha256"
    ):
        reasons.append("QDPX_INTERNAL_MANIFEST_CHANGED")

    if current.get("zip_status") != previous.get("zip_status"):
        reasons.append("QDPX_STATUS_CHANGED")

    if not reasons:
        reasons.append("UNCHANGED")

    return {
        "status": (
            "RECLASSIFICATION_REQUIRED"
            if reasons != ["UNCHANGED"]
            else "UNCHANGED"
        ),
        "reclassification_required": reasons != ["UNCHANGED"],
        "reasons": reasons,
    }


def load_previous_snapshot(
    latest_snapshot_path: Path,
) -> dict[str, Any] | None:
    if not latest_snapshot_path.exists():
        return None

    return json.loads(
        latest_snapshot_path.read_text(encoding="utf-8")
    )


def build_drift_monitor_report(
    database_path: Path,
    raw_data_root: Path,
    previous_snapshot: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    delivery = read_delivery_database(database_path)

    qdpx_lookup = qdpx_project_lookup(
        delivery["projects"],
    )

    archives = inspect_official_qdpx_archives(
        raw_data_root,
        qdpx_lookup,
    )

    current_projects = project_fingerprints(
        delivery["projects"]
    )

    previous_projects = (
        previous_snapshot.get("project_fingerprints", {})
        if previous_snapshot
        else {}
    )

    previous_archives = {
        item["project_id"]: item
        for item in previous_snapshot.get(
            "qdpx_archives",
            [],
        )
    } if previous_snapshot else {}

    project_drift = {
        project_id: classify_project_drift(
            current,
            previous_projects.get(project_id),
        )
        for project_id, current in current_projects.items()
    }

    archive_drift = {
        str(archive["project_id"]): classify_archive_drift(
            archive,
            previous_archives.get(str(archive["project_id"])),
        )
        for archive in archives
    }

    reclassification_projects = sorted(
        {
            project_id
            for project_id, result in project_drift.items()
            if result["reclassification_required"]
        }
        | {
            project_id
            for project_id, result in archive_drift.items()
            if result["reclassification_required"]
        }
    )

    report = {
        "monitor_version": MONITOR_VERSION,
        "created_at_utc": utc_now_iso(),
        "database_path": str(database_path),
        "raw_data_root": str(raw_data_root),
        "previous_snapshot_available": previous_snapshot
        is not None,
        "database_sha256": delivery["database_sha256"],
        "database_changed": (
            previous_snapshot is not None
            and delivery["database_sha256"]
            != previous_snapshot.get("database_sha256")
        ),
        "schema_fingerprint": delivery["schema_fingerprint"],
        "project_count": len(delivery["projects"]),
        "official_qdpx_archive_count": len(archives),
        "project_drift": project_drift,
        "archive_drift": archive_drift,
        "reclassification_required_project_ids": (
            reclassification_projects
        ),
        "reclassification_required_count": len(
            reclassification_projects
        ),
        "automatic_reclassification_performed": False,
        "automatic_database_modification_performed": False,
    }

    snapshot = {
        "monitor_version": MONITOR_VERSION,
        "created_at_utc": report["created_at_utc"],
        "database_sha256": delivery["database_sha256"],
        "schema_fingerprint": delivery["schema_fingerprint"],
        "project_fingerprints": current_projects,
        "qdpx_archives": archives,
    }

    return report, snapshot


def run_drift_monitor(
    *,
    database_path: Path,
    raw_data_root: Path,
    snapshot_dir: Path,
    report_path: Path,
) -> dict[str, Any]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    latest_snapshot_path = snapshot_dir / "latest.json"
    previous_snapshot = load_previous_snapshot(
        latest_snapshot_path
    )

    report, snapshot = build_drift_monitor_report(
        database_path=database_path,
        raw_data_root=raw_data_root,
        previous_snapshot=previous_snapshot,
    )

    timestamp = report["created_at_utc"].replace(
        ":", "-"
    )

    history_path = snapshot_dir / f"snapshot_{timestamp}.json"

    history_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    latest_snapshot_path.write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    return report
