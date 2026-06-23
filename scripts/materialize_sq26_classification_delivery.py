#!/usr/bin/env python3
"""
Materialize the official SQ26 Part 2 classification delivery database.

Source:
    data/staging/qdarchive_x_staging.db

Output:
    23071063-sq26-classification.db

Official scope:
    - MY_CORE only
    - repository 5 (DANS): 4 QDA_PROJECT
    - repository 15 (ICPSR): 5 OTHER_PROJECT
    - 9 projects total
    - 4 ISIC-classified DANS QDA projects
    - 507 QDPX_INTERNAL primary files
    - N69: 3 projects / 499 files
    - N72: 1 project / 8 files
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter
from pathlib import Path


SOURCE_DB = Path("data/staging/qdarchive_x_staging.db")
OUTPUT_DB = Path("23071063-sq26-classification.db")
REPORT_PATH = Path("reports/delivery_validation.json")

EXPECTED_PROJECT_TOTAL = 9
EXPECTED_PROJECT_TYPES = {
    (5, "QDA_PROJECT"): 4,
    (15, "OTHER_PROJECT"): 5,
}
EXPECTED_PROJECT_DIVISIONS = {
    "N69": 3,
    "N72": 1,
}
EXPECTED_FILE_TOTAL = 507
EXPECTED_FILE_DIVISIONS = {
    "N69": 499,
    "N72": 8,
}


class DeliveryError(RuntimeError):
    pass


def fail_if(condition: bool, message: str) -> None:
    if condition:
        raise DeliveryError(message)


def create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        PRAGMA foreign_keys = ON;

        CREATE TABLE delivery_metadata (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );

        CREATE TABLE PROJECTS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            source_project_uid TEXT NOT NULL UNIQUE,
            source_database_id INTEGER,
            source_table_name TEXT,
            source_project_id TEXT,

            query_string TEXT,
            repository_id INTEGER NOT NULL,
            repository_url TEXT,
            project_url TEXT,
            version TEXT,

            title TEXT NOT NULL,
            description TEXT,
            language TEXT,
            doi TEXT,
            upload_date TEXT,
            download_date TEXT,
            download_repository_folder TEXT,
            download_project_folder TEXT,
            download_version_folder TEXT,
            download_method TEXT,

            type TEXT NOT NULL CHECK (
                type IN (
                    'QDA_PROJECT',
                    'QD_PROJECT',
                    'OTHER_PROJECT',
                    'NOT_A_PROJECT'
                )
            ),

            primary_section_code TEXT,
            primary_division_code TEXT,
            class TEXT,

            secondary_section_code TEXT,
            secondary_division_code TEXT,
            secondary_class TEXT,

            classification_rule TEXT,
            confidence REAL,
            classifier_version TEXT,
            classified_at_utc TEXT
        );

        CREATE TABLE FILES (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            project_id INTEGER NOT NULL,
            source_file_classification_id TEXT NOT NULL UNIQUE,

            file_origin TEXT NOT NULL,
            file_reference TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_type TEXT,

            status TEXT NOT NULL DEFAULT 'QDPX_INTERNAL',
            file_url TEXT,
            local_path TEXT,
            file_size_bytes INTEGER,

            primary_section_code TEXT NOT NULL,
            primary_division_code TEXT NOT NULL,
            class TEXT NOT NULL,

            classification_rule TEXT NOT NULL,
            confidence REAL NOT NULL,
            classifier_version TEXT NOT NULL,
            classified_at_utc TEXT NOT NULL,

            FOREIGN KEY(project_id) REFERENCES PROJECTS(id)
        );

        CREATE TABLE KEYWORDS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            keyword TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES PROJECTS(id)
        );

        CREATE TABLE PERSON_ROLE (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES PROJECTS(id)
        );

        CREATE TABLE LICENSES (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            license TEXT NOT NULL,
            FOREIGN KEY(project_id) REFERENCES PROJECTS(id)
        );


        CREATE TABLE PROJECT_TYPE_CLASSIFICATIONS (
            project_id INTEGER PRIMARY KEY,
            source_scope TEXT NOT NULL,
            repository_id INTEGER NOT NULL,
            project_type TEXT NOT NULL,
            classification_rule TEXT NOT NULL,
            file_record_count INTEGER NOT NULL,
            evidence_json TEXT NOT NULL,
            classifier_version TEXT NOT NULL,
            classified_at_utc TEXT NOT NULL,

            FOREIGN KEY(project_id) REFERENCES PROJECTS(id)
        );

        CREATE TABLE ISIC_PROJECT_CLASSIFICATIONS (
            project_id INTEGER PRIMARY KEY,

            source_scope TEXT NOT NULL,
            repository_id INTEGER NOT NULL,
            project_type TEXT NOT NULL,

            primary_section_code TEXT NOT NULL,
            primary_division_code TEXT NOT NULL,
            primary_class TEXT NOT NULL,

            secondary_section_code TEXT,
            secondary_division_code TEXT,
            secondary_class TEXT,

            classification_rule TEXT NOT NULL,
            confidence REAL NOT NULL,
            evidence_json TEXT NOT NULL,
            classifier_version TEXT NOT NULL,
            classified_at_utc TEXT NOT NULL,

            FOREIGN KEY(project_id) REFERENCES PROJECTS(id)
        );

        CREATE TABLE ISIC_FILE_CLASSIFICATIONS (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,

            source_file_classification_id TEXT NOT NULL UNIQUE,
            file_origin TEXT NOT NULL,
            file_reference TEXT NOT NULL,
            file_name TEXT NOT NULL,
            file_extension TEXT,

            primary_section_code TEXT NOT NULL,
            primary_division_code TEXT NOT NULL,
            primary_class TEXT NOT NULL,

            classification_rule TEXT NOT NULL,
            confidence REAL NOT NULL,
            classifier_version TEXT NOT NULL,
            classified_at_utc TEXT NOT NULL,

            FOREIGN KEY(project_id) REFERENCES PROJECTS(id)
        );

        CREATE INDEX idx_projects_repository_type
            ON PROJECTS(repository_id, type);

        CREATE INDEX idx_projects_division
            ON PROJECTS(primary_division_code);

        CREATE INDEX idx_files_project
            ON FILES(project_id);

        CREATE INDEX idx_files_division
            ON FILES(primary_division_code);
        """
    )


def fetch_core_projects(source: sqlite3.Connection) -> list[sqlite3.Row]:
    rows = source.execute(
        """
        SELECT
            p.*,
            pt.project_type,
            pt.classification_rule AS type_classification_rule,
            pt.file_record_count,
            pt.evidence_json AS type_evidence_json,
            pt.classifier_version AS type_classifier_version,
            pt.classified_at_utc AS type_classified_at_utc,

            ipc.primary_section_code,
            ipc.primary_division_code,
            ipc.primary_class,
            ipc.secondary_section_code,
            ipc.secondary_division_code,
            ipc.secondary_class,
            ipc.classification_rule AS isic_classification_rule,
            ipc.confidence AS isic_confidence,
            ipc.evidence_json AS isic_evidence_json,
            ipc.classifier_version AS isic_classifier_version,
            ipc.classified_at_utc AS isic_classified_at_utc

        FROM stg_projects AS p
        INNER JOIN project_type_classifications AS pt
            ON pt.project_uid = p.project_uid
        LEFT JOIN isic_project_classifications AS ipc
            ON ipc.project_uid = p.project_uid
           AND ipc.source_scope = 'MY_CORE'

        WHERE pt.source_scope = 'MY_CORE'
          AND CAST(pt.repository_id AS INTEGER) IN (5, 15)

        ORDER BY
            CAST(p.repository_id AS INTEGER),
            p.project_uid
        """
    ).fetchall()

    return rows


def validate_source_projects(projects: list[sqlite3.Row]) -> None:
    fail_if(
        len(projects) != EXPECTED_PROJECT_TOTAL,
        f"Expected {EXPECTED_PROJECT_TOTAL} MY_CORE projects, found {len(projects)}.",
    )

    type_counts = Counter(
        (int(row["repository_id"]), row["project_type"])
        for row in projects
    )

    fail_if(
        dict(type_counts) != EXPECTED_PROJECT_TYPES,
        "Unexpected official project-type distribution: "
        f"{dict(type_counts)}; expected {EXPECTED_PROJECT_TYPES}.",
    )

    isic_rows = [
        row
        for row in projects
        if row["primary_division_code"] is not None
    ]

    fail_if(
        len(isic_rows) != 4,
        f"Expected 4 ISIC-classified DANS projects, found {len(isic_rows)}.",
    )

    divisions = Counter(
        f"{row['primary_section_code']}{row['primary_division_code']}"
        for row in isic_rows
    )

    fail_if(
        dict(divisions) != EXPECTED_PROJECT_DIVISIONS,
        "Unexpected ISIC project distribution: "
        f"{dict(divisions)}; expected {EXPECTED_PROJECT_DIVISIONS}.",
    )


def insert_projects(
    target: sqlite3.Connection,
    projects: list[sqlite3.Row],
) -> dict[str, int]:
    project_id_map: dict[str, int] = {}

    for row in projects:
        cursor = target.execute(
            """
            INSERT INTO PROJECTS (
                source_project_uid,
                source_database_id,
                source_table_name,
                source_project_id,
                query_string,
                repository_id,
                repository_url,
                project_url,
                version,
                title,
                description,
                language,
                doi,
                upload_date,
                download_date,
                download_repository_folder,
                download_project_folder,
                download_version_folder,
                download_method,
                type,
                primary_section_code,
                primary_division_code,
                class,
                secondary_section_code,
                secondary_division_code,
                secondary_class,
                classification_rule,
                confidence,
                classifier_version,
                classified_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["project_uid"],
                row["source_database_id"],
                row["source_table_name"],
                row["source_project_id"],
                row["query_string"],
                int(row["repository_id"]),
                row["repository_url"],
                row["project_url"],
                row["version"],
                row["title"] or "Untitled project",
                row["description"],
                row["language"],
                row["doi"],
                row["upload_date"],
                row["download_date"],
                row["download_repository_folder"],
                row["download_project_folder"],
                row["download_version_folder"],
                row["download_method"],
                row["project_type"],
                row["primary_section_code"],
                row["primary_division_code"],
                row["primary_class"],
                row["secondary_section_code"],
                row["secondary_division_code"],
                row["secondary_class"],
                row["isic_classification_rule"],
                row["isic_confidence"],
                row["isic_classifier_version"],
                row["isic_classified_at_utc"],
            ),
        )

        project_id = int(cursor.lastrowid)
        project_id_map[row["project_uid"]] = project_id

        target.execute(
            """
            INSERT INTO PROJECT_TYPE_CLASSIFICATIONS (
                project_id,
                source_scope,
                repository_id,
                project_type,
                classification_rule,
                file_record_count,
                evidence_json,
                classifier_version,
                classified_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                "MY_CORE",
                int(row["repository_id"]),
                row["project_type"],
                row["type_classification_rule"],
                row["file_record_count"],
                row["type_evidence_json"],
                row["type_classifier_version"],
                row["type_classified_at_utc"],
            ),
        )

        if row["primary_division_code"] is not None:
            target.execute(
                """
                INSERT INTO ISIC_PROJECT_CLASSIFICATIONS (
                    project_id,
                    source_scope,
                    repository_id,
                    project_type,
                    primary_section_code,
                    primary_division_code,
                    primary_class,
                    secondary_section_code,
                    secondary_division_code,
                    secondary_class,
                    classification_rule,
                    confidence,
                    evidence_json,
                    classifier_version,
                    classified_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    "MY_CORE",
                    int(row["repository_id"]),
                    row["project_type"],
                    row["primary_section_code"],
                    row["primary_division_code"],
                    row["primary_class"],
                    row["secondary_section_code"],
                    row["secondary_division_code"],
                    row["secondary_class"],
                    row["isic_classification_rule"],
                    row["isic_confidence"],
                    row["isic_evidence_json"],
                    row["isic_classifier_version"],
                    row["isic_classified_at_utc"],
                ),
            )

    return project_id_map


def fetch_internal_files(
    source: sqlite3.Connection,
    project_uids: list[str],
) -> list[sqlite3.Row]:
    placeholders = ",".join("?" for _ in project_uids)

    rows = source.execute(
        f"""
        SELECT
            file_classification_id,
            project_uid,
            file_origin,
            file_reference,
            file_name,
            file_extension,
            primary_section_code,
            primary_division_code,
            primary_class,
            classification_rule,
            confidence,
            classifier_version,
            classified_at_utc
        FROM isic_file_classifications
        WHERE project_uid IN ({placeholders})
          AND file_origin = 'QDPX_INTERNAL'
        ORDER BY project_uid, file_reference
        """,
        project_uids,
    ).fetchall()

    return rows


def insert_internal_files(
    target: sqlite3.Connection,
    files: list[sqlite3.Row],
    project_id_map: dict[str, int],
) -> None:
    for row in files:
        project_id = project_id_map[row["project_uid"]]

        target.execute(
            """
            INSERT INTO FILES (
                project_id,
                source_file_classification_id,
                file_origin,
                file_reference,
                file_name,
                file_type,
                status,
                file_url,
                local_path,
                file_size_bytes,
                primary_section_code,
                primary_division_code,
                class,
                classification_rule,
                confidence,
                classifier_version,
                classified_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                row["file_classification_id"],
                row["file_origin"],
                row["file_reference"],
                row["file_name"],
                row["file_extension"],
                "QDPX_INTERNAL",
                None,
                row["file_reference"],
                None,
                row["primary_section_code"],
                row["primary_division_code"],
                row["primary_class"],
                row["classification_rule"],
                row["confidence"],
                row["classifier_version"],
                row["classified_at_utc"],
            ),
        )

        target.execute(
            """
            INSERT INTO ISIC_FILE_CLASSIFICATIONS (
                project_id,
                source_file_classification_id,
                file_origin,
                file_reference,
                file_name,
                file_extension,
                primary_section_code,
                primary_division_code,
                primary_class,
                classification_rule,
                confidence,
                classifier_version,
                classified_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                row["file_classification_id"],
                row["file_origin"],
                row["file_reference"],
                row["file_name"],
                row["file_extension"],
                row["primary_section_code"],
                row["primary_division_code"],
                row["primary_class"],
                row["classification_rule"],
                row["confidence"],
                row["classifier_version"],
                row["classified_at_utc"],
            ),
        )


def validate_target(target: sqlite3.Connection) -> dict:
    project_total = target.execute(
        "SELECT COUNT(*) FROM PROJECTS"
    ).fetchone()[0]

    project_types = {
        (int(repository_id), project_type): count
        for repository_id, project_type, count in target.execute(
            """
            SELECT repository_id, type, COUNT(*)
            FROM PROJECTS
            GROUP BY repository_id, type
            ORDER BY repository_id, type
            """
        )
    }

    project_divisions = {
        f"{section}{division}": count
        for section, division, count in target.execute(
            """
            SELECT
                primary_section_code,
                primary_division_code,
                COUNT(*)
            FROM ISIC_PROJECT_CLASSIFICATIONS
            GROUP BY primary_section_code, primary_division_code
            ORDER BY primary_section_code, primary_division_code
            """
        )
    }

    file_total = target.execute(
        """
        SELECT COUNT(*)
        FROM FILES
        WHERE file_origin = 'QDPX_INTERNAL'
        """
    ).fetchone()[0]

    file_divisions = {
        f"{section}{division}": count
        for section, division, count in target.execute(
            """
            SELECT
                primary_section_code,
                primary_division_code,
                COUNT(*)
            FROM ISIC_FILE_CLASSIFICATIONS
            GROUP BY primary_section_code, primary_division_code
            ORDER BY primary_section_code, primary_division_code
            """
        )
    }

    foreign_key_errors = target.execute(
        "PRAGMA foreign_key_check"
    ).fetchall()

    fail_if(
        project_total != EXPECTED_PROJECT_TOTAL,
        f"Target has {project_total} projects; expected {EXPECTED_PROJECT_TOTAL}.",
    )

    fail_if(
        project_types != EXPECTED_PROJECT_TYPES,
        f"Target project types {project_types}; expected {EXPECTED_PROJECT_TYPES}.",
    )

    fail_if(
        project_divisions != EXPECTED_PROJECT_DIVISIONS,
        f"Target project ISIC divisions {project_divisions}; "
        f"expected {EXPECTED_PROJECT_DIVISIONS}.",
    )

    fail_if(
        file_total != EXPECTED_FILE_TOTAL,
        f"Target has {file_total} QDPX internal files; expected {EXPECTED_FILE_TOTAL}.",
    )

    fail_if(
        file_divisions != EXPECTED_FILE_DIVISIONS,
        f"Target file ISIC divisions {file_divisions}; "
        f"expected {EXPECTED_FILE_DIVISIONS}.",
    )

    fail_if(
        bool(foreign_key_errors),
        f"Foreign-key errors found: {foreign_key_errors}",
    )

    return {
        "source_database": str(SOURCE_DB),
        "output_database": str(OUTPUT_DB),
        "project_total": project_total,
        "repository_project_type_counts": {
            f"{repo_id}|{project_type}": count
            for (repo_id, project_type), count in project_types.items()
        },
        "project_isic_division_counts": project_divisions,
        "qdpX_internal_primary_file_total": file_total,
        "primary_file_isic_division_counts": file_divisions,
        "foreign_key_check": "passed",
    }


def main() -> int:
    fail_if(
        not SOURCE_DB.exists(),
        f"Source database does not exist: {SOURCE_DB}",
    )

    OUTPUT_DB.unlink(missing_ok=True)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)

    source = sqlite3.connect(SOURCE_DB)
    source.row_factory = sqlite3.Row

    target = sqlite3.connect(OUTPUT_DB)

    try:
        create_schema(target)

        projects = fetch_core_projects(source)
        validate_source_projects(projects)

        project_id_map = insert_projects(target, projects)

        eligible_dans_qda_project_uids = [
            row["project_uid"]
            for row in projects
            if int(row["repository_id"]) == 5
            and row["project_type"] == "QDA_PROJECT"
        ]

        files = fetch_internal_files(
            source,
            eligible_dans_qda_project_uids,
        )

        insert_internal_files(target, files, project_id_map)

        target.execute(
            """
            INSERT INTO delivery_metadata (key, value)
            VALUES (?, ?)
            """,
            ("materializer", "sq26-classification-delivery-v1"),
        )

        target.execute(
            """
            INSERT INTO delivery_metadata (key, value)
            VALUES (?, ?)
            """,
            ("scope", "MY_CORE repositories 5 and 15 only"),
        )

        statistics = validate_target(target)

        target.commit()
        target.execute("VACUUM")

        REPORT_PATH.write_text(
            json.dumps(statistics, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        print("\nSUCCESS: official delivery database created.\n")
        print(json.dumps(statistics, indent=2, sort_keys=True))
        print(f"\nDatabase: {OUTPUT_DB.resolve()}")
        print(f"Report:   {REPORT_PATH.resolve()}")

        return 0

    except Exception as error:
        target.rollback()
        OUTPUT_DB.unlink(missing_ok=True)

        print(f"\nFAILED: {error}\n", file=sys.stderr)
        return 1

    finally:
        source.close()
        target.close()


if __name__ == "__main__":
    raise SystemExit(main())
