from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MONITOR_VERSION = "deduplication-drift-monitor-v1"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def latest_resolution_snapshot(
    staging_database_path: Path,
) -> dict[str, Any]:
    connection = sqlite3.connect(
        f"file:{staging_database_path}?mode=ro",
        uri=True,
    )
    connection.row_factory = sqlite3.Row

    try:
        run = connection.execute(
            """
            SELECT
                run_id,
                resolution_version,
                created_at_utc,
                raw_project_count,
                candidate_cluster_count,
                confirmed_cluster_count,
                excluded_project_count,
                included_project_count,
                input_fingerprint,
                configuration_json
            FROM deduplication_runs
            ORDER BY created_at_utc DESC, run_id DESC
            LIMIT 1
            """
        ).fetchone()

        if run is None:
            raise RuntimeError(
                "No deduplication run exists in the staging database."
            )

        run_id = str(run["run_id"])

        decision_counts = {
            str(row["decision"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT
                    decision,
                    COUNT(*) AS count
                FROM deduplication_decisions
                WHERE run_id = ?
                GROUP BY decision
                ORDER BY decision
                """,
                (run_id,),
            )
        }

        evidence_counts = {
            str(row["evidence_rule"]): int(row["count"])
            for row in connection.execute(
                """
                SELECT
                    evidence_rule,
                    COUNT(*) AS count
                FROM deduplication_decisions
                WHERE run_id = ?
                GROUP BY evidence_rule
                ORDER BY evidence_rule
                """,
                (run_id,),
            )
        }

        scope_summary = {
            str(row["source_scope"]): {
                "decision_records": int(row["decision_records"]),
                "included_projects": int(
                    row["included_projects"] or 0
                ),
                "excluded_projects": int(
                    row["excluded_projects"] or 0
                ),
            }
            for row in connection.execute(
                """
                SELECT
                    source_scope,
                    COUNT(*) AS decision_records,
                    SUM(included_in_analysis) AS included_projects,
                    SUM(
                        CASE
                            WHEN decision =
                            'EXCLUDED_FROM_DEDUPLICATED_ANALYSIS'
                            THEN 1
                            ELSE 0
                        END
                    ) AS excluded_projects
                FROM deduplicated_projects
                WHERE run_id = ?
                GROUP BY source_scope
                ORDER BY source_scope
                """,
                (run_id,),
            )
        }

        decision_rows = [
            {
                "project_uid": str(row["project_uid"]),
                "canonical_project_uid": str(
                    row["canonical_project_uid"]
                ),
                "source_scope": str(row["source_scope"]),
                "decision": str(row["decision"]),
                "evidence_rule": str(row["evidence_rule"]),
            }
            for row in connection.execute(
                """
                SELECT
                    project_uid,
                    canonical_project_uid,
                    source_scope,
                    decision,
                    evidence_rule
                FROM deduplication_decisions
                WHERE run_id = ?
                ORDER BY project_uid
                """,
                (run_id,),
            )
        ]

        decision_fingerprint = sha256_json(decision_rows)

        return {
            "run_id": run_id,
            "resolution_version": str(
                run["resolution_version"]
            ),
            "created_at_utc": str(run["created_at_utc"]),
            "raw_project_count": int(run["raw_project_count"]),
            "candidate_cluster_count": int(
                run["candidate_cluster_count"]
            ),
            "confirmed_cluster_count": int(
                run["confirmed_cluster_count"]
            ),
            "excluded_project_count": int(
                run["excluded_project_count"]
            ),
            "included_project_count": int(
                run["included_project_count"]
            ),
            "input_fingerprint": str(run["input_fingerprint"]),
            "configuration": json.loads(
                str(run["configuration_json"])
            ),
            "decision_counts": decision_counts,
            "evidence_counts": evidence_counts,
            "scope_summary": scope_summary,
            "decision_fingerprint": decision_fingerprint,
        }

    finally:
        connection.close()


def classify_deduplication_drift(
    current: dict[str, Any],
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    if previous is None:
        return {
            "status": "BASELINE_CREATED",
            "rerun_required": False,
            "reasons": [
                "No previous deduplication snapshot exists."
            ],
        }

    reasons: list[str] = []

    if (
        current["input_fingerprint"]
        != previous.get("input_fingerprint")
    ):
        reasons.append("STAGING_INPUT_CHANGED")

    if (
        current["resolution_version"]
        != previous.get("resolution_version")
    ):
        reasons.append("RESOLUTION_VERSION_CHANGED")

    if (
        current["decision_fingerprint"]
        != previous.get("decision_fingerprint")
    ):
        reasons.append("DEDUPLICATION_DECISIONS_CHANGED")

    if not reasons:
        return {
            "status": "UNCHANGED",
            "rerun_required": False,
            "reasons": ["UNCHANGED"],
        }

    return {
        "status": "DEDUPLICATION_RERUN_REQUIRED",
        "rerun_required": True,
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


def build_deduplication_drift_report(
    *,
    staging_database_path: Path,
    previous_snapshot: dict[str, Any] | None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    current = latest_resolution_snapshot(staging_database_path)

    previous_deduplication = (
        previous_snapshot.get("deduplication_snapshot")
        if previous_snapshot
        else None
    )

    drift = classify_deduplication_drift(
        current,
        previous_deduplication,
    )

    report = {
        "monitor_version": MONITOR_VERSION,
        "created_at_utc": utc_now_iso(),
        "staging_database_path": str(staging_database_path),
        "previous_snapshot_available": previous_snapshot
        is not None,
        "deduplication_run_id": current["run_id"],
        "deduplication_status": drift["status"],
        "deduplication_rerun_required": drift["rerun_required"],
        "deduplication_drift_reasons": drift["reasons"],
        "raw_project_count": current["raw_project_count"],
        "candidate_cluster_count": current[
            "candidate_cluster_count"
        ],
        "confirmed_cluster_count": current[
            "confirmed_cluster_count"
        ],
        "excluded_duplicate_count": current[
            "excluded_project_count"
        ],
        "deduplicated_project_count": current[
            "included_project_count"
        ],
        "scope_summary": current["scope_summary"],
        "input_fingerprint": current["input_fingerprint"],
        "decision_fingerprint": current[
            "decision_fingerprint"
        ],
        "raw_staging_records_modified": False,
        "automatic_raw_record_deletion_performed": False,
        "automatic_reclassification_performed": False,
    }

    snapshot = {
        "monitor_version": MONITOR_VERSION,
        "created_at_utc": report["created_at_utc"],
        "deduplication_snapshot": current,
    }

    return report, snapshot


def run_deduplication_drift_monitor(
    *,
    staging_database_path: Path,
    snapshot_dir: Path,
    report_path: Path,
) -> dict[str, Any]:
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)

    latest_snapshot_path = snapshot_dir / "latest.json"
    previous_snapshot = load_previous_snapshot(
        latest_snapshot_path
    )

    report, snapshot = build_deduplication_drift_report(
        staging_database_path=staging_database_path,
        previous_snapshot=previous_snapshot,
    )

    timestamp = report["created_at_utc"].replace(":", "-")

    history_path = snapshot_dir / f"snapshot_{timestamp}.json"

    serialized_snapshot = (
        json.dumps(snapshot, indent=2, ensure_ascii=False)
        + "\n"
    )

    history_path.write_text(
        serialized_snapshot,
        encoding="utf-8",
    )

    latest_snapshot_path.write_text(
        serialized_snapshot,
        encoding="utf-8",
    )

    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
        + "\n",
        encoding="utf-8",
    )

    return report
