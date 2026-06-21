from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from src.automation.release_quality_gate import run_quality_gate


def create_minimal_delivery_db(path: Path) -> None:
    connection = sqlite3.connect(path)

    try:
        connection.executescript(
            """
            CREATE TABLE PROJECTS (
                id INTEGER PRIMARY KEY,
                repository_id INTEGER,
                type TEXT,
                primary_division_code TEXT,
                class TEXT
            );

            CREATE TABLE FILES (
                id INTEGER PRIMARY KEY,
                project_id INTEGER,
                primary_division_code TEXT,
                class TEXT
            );

            CREATE TABLE KEYWORDS (id INTEGER PRIMARY KEY);
            CREATE TABLE LICENSES (id INTEGER PRIMARY KEY);
            CREATE TABLE PERSON_ROLE (id INTEGER PRIMARY KEY);
            CREATE TABLE PROJECT_TYPE_CLASSIFICATIONS (id INTEGER PRIMARY KEY);
            CREATE TABLE ISIC_PROJECT_CLASSIFICATIONS (id INTEGER PRIMARY KEY);
            CREATE TABLE ISIC_FILE_CLASSIFICATIONS (id INTEGER PRIMARY KEY);
            CREATE TABLE delivery_metadata (id INTEGER PRIMARY KEY);
            """
        )

        for project_id in range(1, 5):
            division = "72" if project_id == 1 else "69"
            name = (
                "Scientific research and development"
                if project_id == 1
                else "Legal and accounting activities"
            )

            connection.execute(
                """
                INSERT INTO PROJECTS (
                    id,
                    repository_id,
                    type,
                    primary_division_code,
                    class
                )
                VALUES (?, 5, 'QDA_PROJECT', ?, ?)
                """,
                (project_id, division, name),
            )

        for project_id in range(5, 10):
            connection.execute(
                """
                INSERT INTO PROJECTS (
                    id,
                    repository_id,
                    type
                )
                VALUES (?, 15, 'OTHER_PROJECT')
                """,
                (project_id,),
            )

        file_id = 1

        for _ in range(499):
            connection.execute(
                """
                INSERT INTO FILES (
                    id,
                    project_id,
                    primary_division_code,
                    class
                )
                VALUES (?, 2, '69', 'Legal and accounting activities')
                """,
                (file_id,),
            )
            file_id += 1

        for _ in range(8):
            connection.execute(
                """
                INSERT INTO FILES (
                    id,
                    project_id,
                    primary_division_code,
                    class
                )
                VALUES (
                    ?,
                    1,
                    '72',
                    'Scientific research and development'
                )
                """,
                (file_id,),
            )
            file_id += 1

        connection.commit()

    finally:
        connection.close()


def write_valid_drift_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "official_qdpx_archive_count": 4,
                "reclassification_required_count": 0,
                "automatic_database_modification_performed": False,
            }
        ),
        encoding="utf-8",
    )


def test_quality_gate_passes_for_expected_delivery(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "23071063-sq26-classification.db"
    drift_report_path = tmp_path / "drift_report.json"

    create_minimal_delivery_db(database_path)
    write_valid_drift_report(drift_report_path)

    report = run_quality_gate(
        database_path=database_path,
        drift_report_path=drift_report_path,
        require_drift_report=True,
    )

    assert report["passed"] is True
    assert report["failed_check_count"] == 0
    assert report["database_modified"] is False


def test_quality_gate_fails_when_project_count_is_wrong(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "broken.db"

    create_minimal_delivery_db(database_path)

    connection = sqlite3.connect(database_path)
    connection.execute("DELETE FROM PROJECTS WHERE id = 9")
    connection.commit()
    connection.close()

    report = run_quality_gate(database_path=database_path)

    assert report["passed"] is False

    failed_names = {
        check["name"]
        for check in report["checks"]
        if not check["passed"]
    }

    assert "official_project_count" in failed_names


def test_quality_gate_requires_drift_report_when_requested(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "delivery.db"

    create_minimal_delivery_db(database_path)

    report = run_quality_gate(
        database_path=database_path,
        drift_report_path=tmp_path / "missing_drift.json",
        require_drift_report=True,
    )

    assert report["passed"] is False

    drift_check = next(
        check
        for check in report["checks"]
        if check["name"] == "drift_monitor_report"
    )

    assert drift_check["passed"] is False
