from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUALITY_GATE_VERSION = "release-quality-gate-v1"

REQUIRED_TABLES = {
    "PROJECTS",
    "FILES",
    "KEYWORDS",
    "LICENSES",
    "PERSON_ROLE",
    "PROJECT_TYPE_CLASSIFICATIONS",
    "ISIC_PROJECT_CLASSIFICATIONS",
    "ISIC_FILE_CLASSIFICATIONS",
    "delivery_metadata",
}

EXPECTED_PROJECT_TYPE_COUNTS = {
    "5|QDA_PROJECT": 4,
    "15|OTHER_PROJECT": 5,
}

EXPECTED_PROJECT_ISIC_COUNTS = {
    "69|Legal and accounting activities": 3,
    "72|Scientific research and development": 1,
}

EXPECTED_FILE_ISIC_COUNTS = {
    "69|Legal and accounting activities": 499,
    "72|Scientific research and development": 8,
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def add_check(
    checks: list[dict[str, Any]],
    *,
    name: str,
    passed: bool,
    expected: Any,
    observed: Any,
    severity: str = "error",
) -> None:
    checks.append(
        {
            "name": name,
            "passed": passed,
            "severity": severity,
            "expected": expected,
            "observed": observed,
        }
    )


def fetch_scalar(
    connection: sqlite3.Connection,
    query: str,
) -> Any:
    return connection.execute(query).fetchone()[0]


def fetch_count_map(
    connection: sqlite3.Connection,
    query: str,
) -> dict[str, int]:
    return {
        str(row[0]): int(row[1])
        for row in connection.execute(query)
    }


def run_quality_gate(
    *,
    database_path: Path,
    drift_report_path: Path | None = None,
    require_drift_report: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    if not database_path.exists():
        add_check(
            checks,
            name="database_exists",
            passed=False,
            expected="Existing SQLite database file",
            observed="Missing",
        )
        return build_report(
            database_path=database_path,
            checks=checks,
        )

    connection = sqlite3.connect(
        f"file:{database_path}?mode=ro",
        uri=True,
    )

    try:
        integrity_result = fetch_scalar(
            connection,
            "PRAGMA integrity_check;",
        )
        add_check(
            checks,
            name="sqlite_integrity",
            passed=integrity_result == "ok",
            expected="ok",
            observed=integrity_result,
        )

        foreign_key_rows = list(
            connection.execute("PRAGMA foreign_key_check;")
        )
        add_check(
            checks,
            name="foreign_key_check",
            passed=len(foreign_key_rows) == 0,
            expected=0,
            observed=len(foreign_key_rows),
        )

        tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        missing_tables = sorted(REQUIRED_TABLES - tables)
        add_check(
            checks,
            name="required_tables",
            passed=not missing_tables,
            expected=sorted(REQUIRED_TABLES),
            observed={
                "missing": missing_tables,
                "available": sorted(tables),
            },
        )

        project_count = int(
            fetch_scalar(
                connection,
                "SELECT COUNT(*) FROM PROJECTS;",
            )
        )
        add_check(
            checks,
            name="official_project_count",
            passed=project_count == 9,
            expected=9,
            observed=project_count,
        )

        repository_ids = [
            int(row[0])
            for row in connection.execute(
                """
                SELECT DISTINCT repository_id
                FROM PROJECTS
                ORDER BY repository_id
                """
            )
        ]
        add_check(
            checks,
            name="official_repository_scope",
            passed=repository_ids == [5, 15],
            expected=[5, 15],
            observed=repository_ids,
        )

        project_type_counts = fetch_count_map(
            connection,
            """
            SELECT
                CAST(repository_id AS TEXT) || '|' || type,
                COUNT(*)
            FROM PROJECTS
            GROUP BY repository_id, type
            ORDER BY repository_id, type
            """,
        )
        add_check(
            checks,
            name="project_type_distribution",
            passed=project_type_counts
            == EXPECTED_PROJECT_TYPE_COUNTS,
            expected=EXPECTED_PROJECT_TYPE_COUNTS,
            observed=project_type_counts,
        )

        eligible_project_count = int(
            fetch_scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM PROJECTS
                WHERE type IN ('QDA_PROJECT', 'QD_PROJECT')
                """,
            )
        )
        add_check(
            checks,
            name="eligible_project_count",
            passed=eligible_project_count == 4,
            expected=4,
            observed=eligible_project_count,
        )

        classified_project_count = int(
            fetch_scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM PROJECTS
                WHERE type IN ('QDA_PROJECT', 'QD_PROJECT')
                  AND primary_division_code IS NOT NULL
                  AND class IS NOT NULL
                """,
            )
        )
        add_check(
            checks,
            name="eligible_project_classification_coverage",
            passed=classified_project_count
            == eligible_project_count,
            expected=eligible_project_count,
            observed=classified_project_count,
        )

        project_isic_counts = fetch_count_map(
            connection,
            """
            SELECT
                primary_division_code || '|' || class,
                COUNT(*)
            FROM PROJECTS
            WHERE type IN ('QDA_PROJECT', 'QD_PROJECT')
            GROUP BY primary_division_code, class
            ORDER BY primary_division_code, class
            """,
        )
        add_check(
            checks,
            name="project_isic_distribution",
            passed=project_isic_counts
            == EXPECTED_PROJECT_ISIC_COUNTS,
            expected=EXPECTED_PROJECT_ISIC_COUNTS,
            observed=project_isic_counts,
        )

        file_count = int(
            fetch_scalar(
                connection,
                "SELECT COUNT(*) FROM FILES;",
            )
        )
        add_check(
            checks,
            name="classified_primary_file_count",
            passed=file_count == 507,
            expected=507,
            observed=file_count,
        )

        classified_file_count = int(
            fetch_scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM FILES
                WHERE primary_division_code IS NOT NULL
                  AND class IS NOT NULL
                """,
            )
        )
        add_check(
            checks,
            name="file_classification_coverage",
            passed=classified_file_count == file_count,
            expected=file_count,
            observed=classified_file_count,
        )

        file_isic_counts = fetch_count_map(
            connection,
            """
            SELECT
                primary_division_code || '|' || class,
                COUNT(*)
            FROM FILES
            GROUP BY primary_division_code, class
            ORDER BY primary_division_code, class
            """,
        )
        add_check(
            checks,
            name="file_isic_distribution",
            passed=file_isic_counts
            == EXPECTED_FILE_ISIC_COUNTS,
            expected=EXPECTED_FILE_ISIC_COUNTS,
            observed=file_isic_counts,
        )

        orphan_file_count = int(
            fetch_scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM FILES AS f
                LEFT JOIN PROJECTS AS p
                    ON p.id = f.project_id
                WHERE p.id IS NULL
                """,
            )
        )
        add_check(
            checks,
            name="orphan_file_records",
            passed=orphan_file_count == 0,
            expected=0,
            observed=orphan_file_count,
        )

    finally:
        connection.close()

    if drift_report_path is not None:
        validate_drift_report(
            checks=checks,
            drift_report_path=drift_report_path,
            required=require_drift_report,
        )

    return build_report(
        database_path=database_path,
        checks=checks,
    )


def validate_drift_report(
    *,
    checks: list[dict[str, Any]],
    drift_report_path: Path,
    required: bool,
) -> None:
    if not drift_report_path.exists():
        add_check(
            checks,
            name="drift_monitor_report",
            passed=not required,
            expected=(
                "Present and valid"
                if required
                else "Optional"
            ),
            observed="Missing",
            severity="error" if required else "warning",
        )
        return

    try:
        payload = json.loads(
            drift_report_path.read_text(encoding="utf-8")
        )

        reclassification_count = payload.get(
            "reclassification_required_count"
        )
        qdpx_count = payload.get(
            "official_qdpx_archive_count"
        )

        passed = (
            reclassification_count == 0
            and qdpx_count == 4
            and payload.get(
                "automatic_database_modification_performed"
            ) is False
        )

        add_check(
            checks,
            name="drift_monitor_report",
            passed=passed,
            expected={
                "official_qdpx_archive_count": 4,
                "reclassification_required_count": 0,
                "automatic_database_modification_performed": False,
            },
            observed={
                "official_qdpx_archive_count": qdpx_count,
                "reclassification_required_count": (
                    reclassification_count
                ),
                "automatic_database_modification_performed": (
                    payload.get(
                        "automatic_database_modification_performed"
                    )
                ),
            },
        )

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        add_check(
            checks,
            name="drift_monitor_report",
            passed=False,
            expected="Readable valid JSON report",
            observed=f"Invalid: {error}",
        )


def build_report(
    *,
    database_path: Path,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    failed_checks = [
        check
        for check in checks
        if not check["passed"]
        and check["severity"] == "error"
    ]

    warnings = [
        check
        for check in checks
        if not check["passed"]
        and check["severity"] == "warning"
    ]

    return {
        "quality_gate_version": QUALITY_GATE_VERSION,
        "created_at_utc": utc_now_iso(),
        "database_path": str(database_path),
        "passed": len(failed_checks) == 0,
        "failed_check_count": len(failed_checks),
        "warning_count": len(warnings),
        "checks": checks,
        "database_modified": False,
    }
