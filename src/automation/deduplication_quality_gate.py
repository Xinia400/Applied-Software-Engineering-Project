from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUALITY_GATE_VERSION = "deduplication-quality-gate-v1"


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


def scalar(
    connection: sqlite3.Connection,
    query: str,
    parameters: tuple[Any, ...] = (),
) -> Any:
    return connection.execute(query, parameters).fetchone()[0]


def build_report(
    *,
    staging_database_path: Path,
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
        "staging_database_path": str(staging_database_path),
        "passed": len(failed_checks) == 0,
        "failed_check_count": len(failed_checks),
        "warning_count": len(warnings),
        "checks": checks,
        "database_modified": False,
    }


def validate_drift_report(
    *,
    checks: list[dict[str, Any]],
    report_path: Path | None,
    required: bool,
    expected_run: dict[str, Any],
) -> None:
    if report_path is None or not report_path.exists():
        add_check(
            checks,
            name="deduplication_drift_report",
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
            report_path.read_text(encoding="utf-8")
        )

        status = payload.get("deduplication_status")
        rerun_required = payload.get(
            "deduplication_rerun_required"
        )

        report_matches_run = (
            payload.get("deduplication_run_id")
            == expected_run["run_id"]
            and payload.get("raw_project_count")
            == expected_run["raw_project_count"]
            and payload.get("candidate_cluster_count")
            == expected_run["candidate_cluster_count"]
            and payload.get("confirmed_cluster_count")
            == expected_run["confirmed_cluster_count"]
            and payload.get("excluded_duplicate_count")
            == expected_run["excluded_project_count"]
            and payload.get("deduplicated_project_count")
            == expected_run["included_project_count"]
        )

        passed = (
            status in {"BASELINE_CREATED", "UNCHANGED"}
            and rerun_required is False
            and payload.get(
                "raw_staging_records_modified"
            ) is False
            and payload.get(
                "automatic_raw_record_deletion_performed"
            ) is False
            and payload.get(
                "automatic_reclassification_performed"
            ) is False
            and report_matches_run
        )

        add_check(
            checks,
            name="deduplication_drift_report",
            passed=passed,
            expected={
                "status": ["BASELINE_CREATED", "UNCHANGED"],
                "rerun_required": False,
                "raw_staging_records_modified": False,
                "automatic_raw_record_deletion_performed": False,
                "automatic_reclassification_performed": False,
                "matches_latest_run": True,
            },
            observed={
                "status": status,
                "rerun_required": rerun_required,
                "raw_staging_records_modified": payload.get(
                    "raw_staging_records_modified"
                ),
                "automatic_raw_record_deletion_performed": (
                    payload.get(
                        "automatic_raw_record_deletion_performed"
                    )
                ),
                "automatic_reclassification_performed": (
                    payload.get(
                        "automatic_reclassification_performed"
                    )
                ),
                "matches_latest_run": report_matches_run,
            },
        )

    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        add_check(
            checks,
            name="deduplication_drift_report",
            passed=False,
            expected="Readable valid JSON report",
            observed=f"Invalid: {error}",
        )


def run_deduplication_quality_gate(
    *,
    staging_database_path: Path,
    drift_report_path: Path | None = None,
    require_drift_report: bool = False,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    if not staging_database_path.exists():
        add_check(
            checks,
            name="staging_database_exists",
            passed=False,
            expected="Existing staging SQLite database",
            observed="Missing",
        )
        return build_report(
            staging_database_path=staging_database_path,
            checks=checks,
        )

    connection = sqlite3.connect(
        f"file:{staging_database_path}?mode=ro",
        uri=True,
    )

    try:
        integrity = scalar(
            connection,
            "PRAGMA integrity_check;",
        )

        add_check(
            checks,
            name="sqlite_integrity",
            passed=integrity == "ok",
            expected="ok",
            observed=integrity,
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

        required_tables = {
            "stg_projects",
            "duplicate_clusters",
            "duplicate_cluster_members",
            "deduplication_runs",
            "deduplication_decisions",
            "deduplication_audit",
            "deduplicated_projects",
            "deduplication_project_tags",
        }

        available_tables = {
            row[0]
            for row in connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                """
            )
        }

        missing_tables = sorted(
            required_tables - available_tables
        )

        add_check(
            checks,
            name="required_deduplication_tables",
            passed=not missing_tables,
            expected=sorted(required_tables),
            observed={
                "missing": missing_tables,
                "available": sorted(available_tables),
            },
        )

        latest_run = connection.execute(
            """
            SELECT
                run_id,
                raw_project_count,
                candidate_cluster_count,
                confirmed_cluster_count,
                excluded_project_count,
                included_project_count
            FROM deduplication_runs
            ORDER BY created_at_utc DESC, run_id DESC
            LIMIT 1
            """
        ).fetchone()

        if latest_run is None:
            add_check(
                checks,
                name="latest_deduplication_run",
                passed=False,
                expected="At least one completed deduplication run",
                observed="Missing",
            )
            return build_report(
                staging_database_path=staging_database_path,
                checks=checks,
            )

        (
            run_id,
            raw_project_count,
            candidate_cluster_count,
            confirmed_cluster_count,
            excluded_project_count,
            included_project_count,
        ) = latest_run

        expected_run = {
            "run_id": str(run_id),
            "raw_project_count": int(raw_project_count),
            "candidate_cluster_count": int(
                candidate_cluster_count
            ),
            "confirmed_cluster_count": int(
                confirmed_cluster_count
            ),
            "excluded_project_count": int(
                excluded_project_count
            ),
            "included_project_count": int(
                included_project_count
            ),
        }

        raw_staging_count = int(
            scalar(
                connection,
                "SELECT COUNT(*) FROM stg_projects;",
            )
        )

        add_check(
            checks,
            name="raw_project_count_matches_staging",
            passed=raw_staging_count
            == expected_run["raw_project_count"],
            expected=expected_run["raw_project_count"],
            observed=raw_staging_count,
        )

        decision_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplication_decisions
                WHERE run_id = ?
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="decision_coverage",
            passed=decision_count == raw_staging_count,
            expected=raw_staging_count,
            observed=decision_count,
        )

        analysis_row_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplicated_projects
                WHERE run_id = ?
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="deduplicated_analysis_coverage",
            passed=analysis_row_count == raw_staging_count,
            expected=raw_staging_count,
            observed=analysis_row_count,
        )

        included_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplicated_projects
                WHERE run_id = ?
                  AND included_in_analysis = 1
                """,
                (expected_run["run_id"],),
            )
        )

        excluded_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplicated_projects
                WHERE run_id = ?
                  AND included_in_analysis = 0
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="deduplication_count_conservation",
            passed=(
                included_count + excluded_count
                == raw_staging_count
            ),
            expected=raw_staging_count,
            observed=included_count + excluded_count,
        )

        add_check(
            checks,
            name="included_count_matches_run",
            passed=included_count
            == expected_run["included_project_count"],
            expected=expected_run["included_project_count"],
            observed=included_count,
        )

        add_check(
            checks,
            name="excluded_count_matches_run",
            passed=excluded_count
            == expected_run["excluded_project_count"],
            expected=expected_run["excluded_project_count"],
            observed=excluded_count,
        )

        missing_canonical_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplication_decisions AS excluded
                LEFT JOIN deduplication_decisions AS canonical
                    ON canonical.run_id = excluded.run_id
                   AND canonical.project_uid =
                       excluded.canonical_project_uid
                   AND canonical.decision = 'CANONICAL_RECORD'
                WHERE excluded.run_id = ?
                  AND excluded.decision =
                      'EXCLUDED_FROM_DEDUPLICATED_ANALYSIS'
                  AND canonical.project_uid IS NULL
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="excluded_records_have_canonical_replacement",
            passed=missing_canonical_count == 0,
            expected=0,
            observed=missing_canonical_count,
        )

        invalid_canonical_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplication_decisions
                WHERE run_id = ?
                  AND decision =
                      'EXCLUDED_FROM_DEDUPLICATED_ANALYSIS'
                  AND project_uid = canonical_project_uid
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="canonical_record_not_excluded",
            passed=invalid_canonical_count == 0,
            expected=0,
            observed=invalid_canonical_count,
        )

        missing_audit_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplication_decisions AS decision
                LEFT JOIN deduplication_audit AS audit
                    ON audit.run_id = decision.run_id
                   AND audit.project_uid = decision.project_uid
                WHERE decision.run_id = ?
                  AND audit.project_uid IS NULL
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="decision_audit_coverage",
            passed=missing_audit_count == 0,
            expected=0,
            observed=missing_audit_count,
        )

        missing_tag_count = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplication_decisions AS decision
                LEFT JOIN deduplication_project_tags AS tag
                    ON tag.run_id = decision.run_id
                   AND tag.project_uid = decision.project_uid
                WHERE decision.run_id = ?
                  AND tag.project_uid IS NULL
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="decision_tag_coverage",
            passed=missing_tag_count == 0,
            expected=0,
            observed=missing_tag_count,
        )

        my_core_excluded = int(
            scalar(
                connection,
                """
                SELECT COUNT(*)
                FROM deduplication_decisions
                WHERE run_id = ?
                  AND source_scope = 'MY_CORE'
                  AND decision =
                      'EXCLUDED_FROM_DEDUPLICATED_ANALYSIS'
                """,
                (expected_run["run_id"],),
            )
        )

        add_check(
            checks,
            name="my_core_duplicate_impact",
            passed=my_core_excluded == 0,
            expected=0,
            observed=my_core_excluded,
        )

        validate_drift_report(
            checks=checks,
            report_path=drift_report_path,
            required=require_drift_report,
            expected_run=expected_run,
        )

    finally:
        connection.close()

    return build_report(
        staging_database_path=staging_database_path,
        checks=checks,
    )
