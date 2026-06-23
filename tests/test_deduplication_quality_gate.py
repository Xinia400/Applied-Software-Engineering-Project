from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.automation.deduplication_quality_gate import (
    run_deduplication_quality_gate,
)


def create_quality_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)

    try:
        connection.execute("PRAGMA foreign_keys = ON;")

        connection.executescript(
            """
            CREATE TABLE stg_projects (
                project_uid TEXT PRIMARY KEY
            );

            CREATE TABLE duplicate_clusters (
                cluster_id TEXT PRIMARY KEY
            );

            CREATE TABLE duplicate_cluster_members (
                cluster_id TEXT,
                project_uid TEXT
            );

            CREATE TABLE deduplication_runs (
                run_id TEXT PRIMARY KEY,
                created_at_utc TEXT NOT NULL,
                raw_project_count INTEGER NOT NULL,
                candidate_cluster_count INTEGER NOT NULL,
                confirmed_cluster_count INTEGER NOT NULL,
                excluded_project_count INTEGER NOT NULL,
                included_project_count INTEGER NOT NULL
            );

            CREATE TABLE deduplication_decisions (
                run_id TEXT NOT NULL,
                project_uid TEXT NOT NULL,
                canonical_project_uid TEXT NOT NULL,
                source_scope TEXT NOT NULL,
                decision TEXT NOT NULL
            );

            CREATE TABLE deduplication_audit (
                run_id TEXT NOT NULL,
                project_uid TEXT NOT NULL
            );

            CREATE TABLE deduplicated_projects (
                run_id TEXT NOT NULL,
                project_uid TEXT NOT NULL,
                included_in_analysis INTEGER NOT NULL,
                decision TEXT NOT NULL
            );

            CREATE TABLE deduplication_project_tags (
                run_id TEXT NOT NULL,
                project_uid TEXT NOT NULL,
                tag TEXT NOT NULL
            );
            """
        )

        connection.executemany(
            "INSERT INTO stg_projects VALUES (?)",
            [("peer:1",), ("peer:2",), ("core:1",)],
        )

        connection.execute(
            """
            INSERT INTO deduplication_runs VALUES (
                'run-1',
                '2026-01-01T00:00:00+00:00',
                3,
                1,
                1,
                1,
                2
            )
            """
        )

        connection.executemany(
            """
            INSERT INTO deduplication_decisions VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "run-1",
                    "peer:1",
                    "peer:1",
                    "PEER_SHARED",
                    "CANONICAL_RECORD",
                ),
                (
                    "run-1",
                    "peer:2",
                    "peer:1",
                    "PEER_SHARED",
                    "EXCLUDED_FROM_DEDUPLICATED_ANALYSIS",
                ),
                (
                    "run-1",
                    "core:1",
                    "core:1",
                    "MY_CORE",
                    "UNIQUE_RECORD",
                ),
            ],
        )

        connection.executemany(
            """
            INSERT INTO deduplicated_projects VALUES (?, ?, ?, ?)
            """,
            [
                ("run-1", "peer:1", 1, "CANONICAL_RECORD"),
                (
                    "run-1",
                    "peer:2",
                    0,
                    "EXCLUDED_FROM_DEDUPLICATED_ANALYSIS",
                ),
                ("run-1", "core:1", 1, "UNIQUE_RECORD"),
            ],
        )

        connection.executemany(
            "INSERT INTO deduplication_audit VALUES (?, ?)",
            [
                ("run-1", "peer:1"),
                ("run-1", "peer:2"),
                ("run-1", "core:1"),
            ],
        )

        connection.executemany(
            "INSERT INTO deduplication_project_tags VALUES (?, ?, ?)",
            [
                ("run-1", "peer:1", "CANONICAL_RECORD"),
                (
                    "run-1",
                    "peer:2",
                    "EXCLUDED_FROM_DEDUPLICATED_ANALYSIS",
                ),
                ("run-1", "core:1", "UNIQUE_RECORD"),
            ],
        )

        connection.commit()

    finally:
        connection.close()


def write_drift_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "deduplication_run_id": "run-1",
                "deduplication_status": "UNCHANGED",
                "deduplication_rerun_required": False,
                "raw_project_count": 3,
                "candidate_cluster_count": 1,
                "confirmed_cluster_count": 1,
                "excluded_duplicate_count": 1,
                "deduplicated_project_count": 2,
                "raw_staging_records_modified": False,
                "automatic_raw_record_deletion_performed": False,
                "automatic_reclassification_performed": False,
            }
        ),
        encoding="utf-8",
    )


def test_deduplication_quality_gate_passes(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "staging.db"
    drift_path = tmp_path / "drift.json"

    create_quality_test_db(database_path)
    write_drift_report(drift_path)

    report = run_deduplication_quality_gate(
        staging_database_path=database_path,
        drift_report_path=drift_path,
        require_drift_report=True,
    )

    assert report["passed"] is True
    assert report["failed_check_count"] == 0


def test_deduplication_quality_gate_detects_missing_canonical(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "broken.db"

    create_quality_test_db(database_path)

    connection = sqlite3.connect(database_path)
    connection.execute(
        """
        DELETE FROM deduplication_decisions
        WHERE project_uid = 'peer:1'
        """
    )
    connection.commit()
    connection.close()

    report = run_deduplication_quality_gate(
        staging_database_path=database_path
    )

    assert report["passed"] is False

    failed_names = {
        check["name"]
        for check in report["checks"]
        if not check["passed"]
    }

    assert "excluded_records_have_canonical_replacement" in failed_names
