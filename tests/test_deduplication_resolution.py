from __future__ import annotations

import sqlite3
from pathlib import Path

from src.classification.deduplication_resolution import (
    latest_deduplication_run,
    resolve_deduplicated_analysis,
)


def create_resolution_test_db(path: Path) -> None:
    connection = sqlite3.connect(path)

    try:
        connection.execute("PRAGMA foreign_keys = ON;")

        connection.executescript(
            """
            CREATE TABLE source_databases (
                source_database_id INTEGER PRIMARY KEY,
                source_student_id TEXT NOT NULL,
                source_scope TEXT NOT NULL
            );

            CREATE TABLE stg_projects (
                project_uid TEXT PRIMARY KEY,
                source_database_id INTEGER NOT NULL,
                repository_id TEXT,
                repository_url TEXT,
                project_url TEXT,
                title TEXT,
                description TEXT,
                doi TEXT,
                language TEXT,
                upload_date TEXT,
                FOREIGN KEY(source_database_id)
                    REFERENCES source_databases(source_database_id)
            );

            CREATE TABLE stg_files (
                file_uid TEXT PRIMARY KEY,
                project_uid TEXT,
                FOREIGN KEY(project_uid)
                    REFERENCES stg_projects(project_uid)
            );

            CREATE TABLE source_granularity_profiles (
                source_database_id TEXT PRIMARY KEY,
                candidate_granularity TEXT NOT NULL
            );

            CREATE TABLE duplicate_clusters (
                cluster_id TEXT PRIMARY KEY,
                cluster_key_type TEXT NOT NULL,
                candidate_strength TEXT NOT NULL,
                canonical_key TEXT NOT NULL,
                raw_member_count INTEGER NOT NULL,
                unique_title_count INTEGER NOT NULL,
                evidence_json TEXT NOT NULL
            );

            CREATE TABLE duplicate_cluster_members (
                cluster_id TEXT NOT NULL,
                project_uid TEXT NOT NULL,
                member_rank INTEGER NOT NULL,
                PRIMARY KEY(cluster_id, project_uid),
                FOREIGN KEY(cluster_id)
                    REFERENCES duplicate_clusters(cluster_id),
                FOREIGN KEY(project_uid)
                    REFERENCES stg_projects(project_uid)
            );
            """
        )

        connection.executemany(
            """
            INSERT INTO source_databases (
                source_database_id,
                source_student_id,
                source_scope
            )
            VALUES (?, ?, ?)
            """,
            [
                (1, "peer-a", "PEER_SHARED"),
                (2, "peer-b", "PEER_SHARED"),
                (3, "23071063", "MY_CORE"),
            ],
        )

        connection.executemany(
            """
            INSERT INTO stg_projects (
                project_uid,
                source_database_id,
                repository_id,
                repository_url,
                project_url,
                title,
                description,
                doi,
                language,
                upload_date
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    "peer-a:project:1",
                    1,
                    "2",
                    "https://example.org/repository",
                    "https://example.org/a",
                    "Researcher’s Qualitative Study",
                    "Complete metadata record.",
                    "https://doi.org/10.1234/example.1",
                    "en",
                    "2026-01-01",
                ),
                (
                    "peer-b:project:1",
                    2,
                    "2",
                    "https://example.org/repository",
                    "https://example.org/b",
                    "Researcher's Qualitative Study",
                    "",
                    "doi:10.1234/example.1",
                    "en",
                    "",
                ),
                (
                    "core:project:1",
                    3,
                    "5",
                    "https://dans.example",
                    "https://dans.example/project",
                    "Independent MY_CORE Project",
                    "MY_CORE record with no duplicate.",
                    "10.9999/core.1",
                    "en",
                    "2026-02-01",
                ),
            ],
        )

        connection.executemany(
            """
            INSERT INTO stg_files (
                file_uid,
                project_uid
            )
            VALUES (?, ?)
            """,
            [
                ("file-a", "peer-a:project:1"),
                ("file-core", "core:project:1"),
            ],
        )

        connection.executemany(
            """
            INSERT INTO source_granularity_profiles (
                source_database_id,
                candidate_granularity
            )
            VALUES (?, 'DATASET_LIKE')
            """,
            [("1",), ("2",), ("3",)],
        )

        connection.execute(
            """
            INSERT INTO duplicate_clusters (
                cluster_id,
                cluster_key_type,
                candidate_strength,
                canonical_key,
                raw_member_count,
                unique_title_count,
                evidence_json
            )
            VALUES (
                'dedup:test-1',
                'EXACT_DOI_AND_NORMALIZED_TITLE',
                'HIGH_CONFIDENCE',
                '10.1234/example.1|researchers qualitative study',
                2,
                1,
                '{}'
            )
            """
        )

        connection.executemany(
            """
            INSERT INTO duplicate_cluster_members (
                cluster_id,
                project_uid,
                member_rank
            )
            VALUES ('dedup:test-1', ?, ?)
            """,
            [
                ("peer-a:project:1", 1),
                ("peer-b:project:1", 2),
            ],
        )

        connection.commit()

    finally:
        connection.close()


def test_resolution_excludes_confirmed_peer_duplicate(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "staging.db"
    create_resolution_test_db(database_path)

    summary = resolve_deduplicated_analysis(database_path)

    assert summary["raw_project_count"] == 3
    assert summary["confirmed_cluster_count"] == 1
    assert summary["excluded_duplicate_count"] == 1
    assert summary["deduplicated_project_count"] == 2

    assert summary["scope_summary"]["MY_CORE"] == {
        "raw_projects": 1,
        "candidate_cluster_members": 0,
        "candidate_clusters_touching_scope": 0,
        "decision_records": 1,
        "excluded_duplicates": 0,
        "deduplicated_projects": 1,
    }

    assert summary["scope_summary"]["PEER_SHARED"] == {
        "raw_projects": 2,
        "candidate_cluster_members": 2,
        "candidate_clusters_touching_scope": 1,
        "decision_records": 2,
        "excluded_duplicates": 1,
        "deduplicated_projects": 1,
    }

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row

    try:
        raw_project_count = connection.execute(
            "SELECT COUNT(*) FROM stg_projects"
        ).fetchone()[0]

        assert raw_project_count == 3

        excluded = connection.execute(
            """
            SELECT project_uid, canonical_project_uid
            FROM deduplication_decisions
            WHERE decision =
                'EXCLUDED_FROM_DEDUPLICATED_ANALYSIS'
            """
        ).fetchone()

        assert excluded["project_uid"] == "peer-b:project:1"
        assert excluded["canonical_project_uid"] == "peer-a:project:1"

        tags = {
            row[0]
            for row in connection.execute(
                """
                SELECT tag
                FROM deduplication_project_tags
                WHERE project_uid = 'peer-b:project:1'
                """
            )
        }

        assert "CONFIRMED_DUPLICATE" in tags
        assert "EXCLUDED_FROM_DEDUPLICATED_ANALYSIS" in tags

        latest = latest_deduplication_run(connection)

        assert latest is not None
        assert latest["excluded_project_count"] == 1

    finally:
        connection.close()
