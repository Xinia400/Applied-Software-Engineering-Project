from __future__ import annotations

import json
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.classification.project_type_rules import (
    AMBIGUOUS_QDA_EXTENSIONS,
    HIGH_CONFIDENCE_QDA_EXTENSIONS,
    extension_from_filename,
    is_primary_data_extension,
    matched_qda_terms,
    normalize_context,
)
from src.classification.staging_schema import connect_staging_database


CLASSIFIER_VERSION = "project-type-v1"
PROJECT_TYPES = (
    "QDA_PROJECT",
    "QD_PROJECT",
    "OTHER_PROJECT",
    "NOT_A_PROJECT",
)
BATCH_SIZE = 1_000


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def ensure_project_type_schema(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS project_type_classifications (
            project_uid TEXT PRIMARY KEY,
            source_scope TEXT NOT NULL,
            repository_id TEXT,
            project_type TEXT NOT NULL
                CHECK (
                    project_type IN (
                        'QDA_PROJECT',
                        'QD_PROJECT',
                        'OTHER_PROJECT',
                        'NOT_A_PROJECT'
                    )
                ),
            classification_rule TEXT NOT NULL,
            file_record_count INTEGER NOT NULL,
            evidence_json TEXT NOT NULL,
            classifier_version TEXT NOT NULL,
            classified_at_utc TEXT NOT NULL,
            FOREIGN KEY (project_uid)
                REFERENCES stg_projects(project_uid)
        );

        CREATE INDEX IF NOT EXISTS
            idx_project_type_classifications_type
        ON project_type_classifications(project_type);

        CREATE INDEX IF NOT EXISTS
            idx_project_type_classifications_repository
        ON project_type_classifications(repository_id);
        """
    )


def new_evidence() -> dict[str, Any]:
    return {
        "file_record_count": 0,
        "high_confidence_qda_extensions": set(),
        "ambiguous_qda_extensions": set(),
        "ambiguous_filenames": [],
        "primary_data_extensions": set(),
    }


def classify_evidence(
    title: str | None,
    description: str | None,
    evidence: dict[str, Any],
) -> tuple[str, str, dict[str, Any]]:
    context = normalize_context(
        [
            title,
            description,
            *evidence["ambiguous_filenames"],
        ]
    )

    context_terms = matched_qda_terms(context)

    high_qda = sorted(
        evidence["high_confidence_qda_extensions"]
    )
    ambiguous_qda = sorted(
        evidence["ambiguous_qda_extensions"]
    )
    primary_data = sorted(
        evidence["primary_data_extensions"]
    )

    audit_evidence = {
        "file_record_count": evidence["file_record_count"],
        "high_confidence_qda_extensions": high_qda,
        "ambiguous_qda_extensions": ambiguous_qda,
        "matched_qda_context_terms": list(context_terms),
        "primary_data_extensions": primary_data,
    }

    if high_qda:
        return (
            "QDA_PROJECT",
            "HIGH_CONFIDENCE_QDA_EXTENSION",
            audit_evidence,
        )

    if ambiguous_qda and context_terms:
        return (
            "QDA_PROJECT",
            "CONTEXT_VALIDATED_AMBIGUOUS_QDA_EXTENSION",
            audit_evidence,
        )

    if primary_data:
        return (
            "QD_PROJECT",
            "PRIMARY_DATA_EXTENSION",
            audit_evidence,
        )

    if evidence["file_record_count"] > 0:
        return (
            "OTHER_PROJECT",
            "FILE_RECORD_WITHOUT_QDA_OR_PRIMARY_EVIDENCE",
            audit_evidence,
        )

    return (
        "NOT_A_PROJECT",
        "NO_FILE_RECORD",
        audit_evidence,
    )


def write_batch(
    connection: sqlite3.Connection,
    batch: list[tuple[Any, ...]],
) -> None:
    if not batch:
        return

    connection.executemany(
        """
        INSERT INTO project_type_classifications (
            project_uid,
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
        batch,
    )

    batch.clear()


def classify_project_types(
    staging_database_path: Path,
    *,
    reset: bool,
) -> dict[str, Any]:
    connection = connect_staging_database(
        staging_database_path
    )

    try:
        ensure_project_type_schema(connection)

        if reset:
            connection.execute(
                "DELETE FROM project_type_classifications"
            )
            connection.commit()

        cursor = connection.execute(
            """
            SELECT
                p.project_uid,
                s.source_scope,
                p.repository_id,
                p.title,
                p.description,
                f.file_uid,
                f.file_name
            FROM stg_projects AS p
            INNER JOIN source_databases AS s
                ON s.source_database_id = p.source_database_id
            LEFT JOIN stg_files AS f
                ON f.project_uid = p.project_uid
            ORDER BY p.project_uid
            """
        )

        current_project_uid: str | None = None
        current_scope = ""
        current_repository_id: str | None = None
        current_title: str | None = None
        current_description: str | None = None
        evidence = new_evidence()

        type_counts: Counter[str] = Counter()
        rule_counts: Counter[str] = Counter()
        batch: list[tuple[Any, ...]] = []

        def finalize_current_project() -> None:
            nonlocal evidence

            if current_project_uid is None:
                return

            project_type, rule, audit_evidence = classify_evidence(
                current_title,
                current_description,
                evidence,
            )

            type_counts[project_type] += 1
            rule_counts[rule] += 1

            batch.append(
                (
                    current_project_uid,
                    current_scope,
                    current_repository_id,
                    project_type,
                    rule,
                    evidence["file_record_count"],
                    json.dumps(
                        audit_evidence,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    CLASSIFIER_VERSION,
                    utc_now_iso(),
                )
            )

            if len(batch) >= BATCH_SIZE:
                write_batch(connection, batch)

        for (
            project_uid,
            source_scope,
            repository_id,
            title,
            description,
            file_uid,
            file_name,
        ) in cursor:
            if current_project_uid is None:
                current_project_uid = project_uid
                current_scope = source_scope
                current_repository_id = repository_id
                current_title = title
                current_description = description
                evidence = new_evidence()

            elif project_uid != current_project_uid:
                finalize_current_project()

                current_project_uid = project_uid
                current_scope = source_scope
                current_repository_id = repository_id
                current_title = title
                current_description = description
                evidence = new_evidence()

            if file_uid is None:
                continue

            evidence["file_record_count"] += 1
            suffix = extension_from_filename(file_name)

            if suffix in HIGH_CONFIDENCE_QDA_EXTENSIONS:
                evidence[
                    "high_confidence_qda_extensions"
                ].add(suffix)

            if suffix in AMBIGUOUS_QDA_EXTENSIONS:
                evidence["ambiguous_qda_extensions"].add(suffix)

                if len(evidence["ambiguous_filenames"]) < 5:
                    evidence["ambiguous_filenames"].append(
                        str(file_name or "")
                    )

            if is_primary_data_extension(suffix):
                evidence["primary_data_extensions"].add(suffix)

        finalize_current_project()
        write_batch(connection, batch)
        connection.commit()

        total_projects = connection.execute(
            "SELECT COUNT(*) FROM stg_projects"
        ).fetchone()[0]

        stored_results = connection.execute(
            """
            SELECT COUNT(*)
            FROM project_type_classifications
            """
        ).fetchone()[0]

        return {
            "classifier_version": CLASSIFIER_VERSION,
            "total_projects": total_projects,
            "classified_projects": stored_results,
            "counts_by_project_type": dict(
                sorted(type_counts.items())
            ),
            "counts_by_rule": dict(sorted(rule_counts.items())),
        }

    finally:
        connection.close()
