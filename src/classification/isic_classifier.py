from __future__ import annotations

import hashlib
import json
import sqlite3
import zipfile

from src.classification.tier2_extractor import (
    extract_qdpx_primary_text,
)
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.classification.project_type_rules import (
    extension_from_filename,
)
from src.classification.staging_schema import (
    connect_staging_database,
)


CLASSIFIER_VERSION = "official-isic-v2-tier2"

OFFICIAL_REPOSITORIES = {"5", "15"}

ISIC_DIVISIONS = {
    "N69": {
        "section_code": "N",
        "division_code": "69",
        "title": "Legal and accounting activities",
    },
    "N72": {
        "section_code": "N",
        "division_code": "72",
        "title": "Scientific research and development",
    },
}

LEGAL_TERMS = (
    "international criminal law",
    "charging document",
    "prosecution",
    "appeals briefs",
    "appeal ground",
    "defendant",
    "international criminal court",
    "icc",
    "ictr",
    "scsl",
)

RESEARCH_TERMS = (
    "aireas",
    "safecast",
    "citizen sensing",
    "risk governance",
    "responses survey",
    "environmental risk",
)

PRIMARY_INTERNAL_EXTENSIONS = {
    "txt",
    "pdf",
    "rtf",
    "doc",
    "docx",
    "odt",
    "md",
    "csv",
    "tsv",
    "tab",
    "wav",
    "mp3",
    "m4a",
    "aac",
    "flac",
    "ogg",
    "mp4",
    "mov",
    "avi",
    "mkv",
    "srt",
    "vtt",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def make_file_classification_id(
    project_uid: str,
    file_origin: str,
    file_reference: str,
) -> str:
    value = f"{project_uid}|{file_origin}|{file_reference}"
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()

    return f"isic-file:{digest}"


def term_hits(
    context: str,
    terms: tuple[str, ...],
) -> list[str]:
    normalized = context.casefold()

    return [
        term
        for term in terms
        if term in normalized
    ]


def classify_context(
    context: str,
) -> tuple[str, str, float, list[str], list[str]] | None:
    legal_hits = term_hits(context, LEGAL_TERMS)
    research_hits = term_hits(context, RESEARCH_TERMS)

    legal_score = len(legal_hits)
    research_score = len(research_hits)

    if legal_score >= 2 and legal_score >= research_score:
        return (
            "N69",
            "LEGAL_CORPUS_METADATA_AND_QDPX_EVIDENCE",
            min(0.99, 0.80 + legal_score * 0.04),
            legal_hits,
            [
                "international-criminal-law",
                "legal-documents",
                "qualitative-coding",
            ],
        )

    if research_score >= 2 and research_score > legal_score:
        return (
            "N72",
            "RESEARCH_METADATA_AND_QDPX_EVIDENCE",
            min(0.99, 0.80 + research_score * 0.04),
            research_hits,
            [
                "citizen-sensing",
                "environmental-risk",
                "survey-research",
            ],
        )

    return None


def build_qdpx_index(raw_root: Path) -> dict[str, Path]:
    index: dict[str, Path] = {}

    for path in raw_root.rglob("*.qdpx"):
        if path.is_file():
            index.setdefault(path.name.casefold(), path)

    return index


def inspect_qdpx(
    archive_path: Path,
) -> tuple[str, list[tuple[str, str]]]:
    """Read QDPX project metadata and enumerate primary files only."""
    with zipfile.ZipFile(archive_path) as archive:
        qde_names = [
            name
            for name in archive.namelist()
            if name.casefold().endswith(".qde")
        ]

        qde_text_parts = [
            archive.read(name).decode(
                "utf-8",
                errors="replace",
            )
            for name in qde_names
        ]

        primary_files: list[tuple[str, str]] = []

        for item in archive.infolist():
            if item.is_dir():
                continue

            internal_path = item.filename
            suffix = extension_from_filename(internal_path)

            if not internal_path.casefold().startswith("sources/"):
                continue

            if suffix in PRIMARY_INTERNAL_EXTENSIONS:
                primary_files.append((internal_path, suffix))

    return "\n".join(qde_text_parts), primary_files


def ensure_isic_schema(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS isic_project_classifications (
            project_uid TEXT PRIMARY KEY,
            source_scope TEXT NOT NULL,
            repository_id TEXT,
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
            FOREIGN KEY (project_uid)
                REFERENCES stg_projects(project_uid)
        );

        CREATE TABLE IF NOT EXISTS isic_file_classifications (
            file_classification_id TEXT PRIMARY KEY,
            project_uid TEXT NOT NULL,
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
            FOREIGN KEY (project_uid)
                REFERENCES isic_project_classifications(project_uid)
        );

        CREATE TABLE IF NOT EXISTS isic_project_tags (
            project_uid TEXT NOT NULL,
            tag TEXT NOT NULL,
            classifier_version TEXT NOT NULL,
            PRIMARY KEY (project_uid, tag, classifier_version),
            FOREIGN KEY (project_uid)
                REFERENCES isic_project_classifications(project_uid)
        );

        CREATE INDEX IF NOT EXISTS
            idx_isic_project_classifications_repository
        ON isic_project_classifications(repository_id);

        CREATE INDEX IF NOT EXISTS
            idx_isic_project_classifications_division
        ON isic_project_classifications(primary_division_code);
        """
    )


def reset_isic_classifications(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("DELETE FROM isic_project_tags")
    connection.execute("DELETE FROM isic_file_classifications")
    connection.execute("DELETE FROM isic_project_classifications")
    connection.commit()


def classify_official_isic(
    staging_database_path: Path,
    raw_data_root: Path,
    *,
    reset: bool,
) -> dict[str, Any]:
    connection = connect_staging_database(
        staging_database_path
    )

    try:
        ensure_isic_schema(connection)

        if reset:
            reset_isic_classifications(connection)

        qdpx_index = build_qdpx_index(raw_data_root)

        projects = connection.execute(
            """
            SELECT
                c.project_uid,
                c.source_scope,
                c.repository_id,
                c.project_type,
                p.title,
                p.description
            FROM project_type_classifications AS c
            JOIN stg_projects AS p
                ON p.project_uid = c.project_uid
            WHERE c.source_scope = 'MY_CORE'
              AND c.repository_id IN ('5', '15')
              AND c.project_type IN (
                  'QDA_PROJECT',
                  'QD_PROJECT'
              )
            ORDER BY c.repository_id, p.title
            """
        ).fetchall()

        summary_counts: Counter[str] = Counter()
        files_classified = 0
        errors: list[dict[str, str]] = []
        unclassified_projects: list[str] = []

        for (
            project_uid,
            source_scope,
            repository_id,
            project_type,
            title,
            description,
        ) in projects:
            project_files = connection.execute(
                """
                SELECT file_uid, file_name
                FROM stg_files
                WHERE project_uid = ?
                ORDER BY file_name
                """,
                (project_uid,),
            ).fetchall()

            context_parts = [
                title or "",
                description or "",
            ]
            primary_file_records: list[
                tuple[str, str, str, str]
            ] = []
            evidence_source = "METADATA_ONLY"

            if project_type == "QDA_PROJECT":
                qdpx_names = [
                    str(file_name)
                    for _, file_name in project_files
                    if extension_from_filename(file_name) == "qdpx"
                ]

                if not qdpx_names:
                    errors.append(
                        {
                            "project_uid": project_uid,
                            "error": "No QDPX file record found.",
                        }
                    )
                    continue

                archive_path = qdpx_index.get(
                    qdpx_names[0].casefold()
                )

                if archive_path is None:
                    errors.append(
                        {
                            "project_uid": project_uid,
                            "error": (
                                "Downloaded QDPX archive was not found: "
                                f"{qdpx_names[0]}"
                            ),
                        }
                    )
                    continue

                try:
                    qde_text, internal_files = inspect_qdpx(
                        archive_path
                    )
                    extracted_files, tier2_summary = (
                        extract_qdpx_primary_text(archive_path)
                    )
                except (
                    OSError,
                    zipfile.BadZipFile,
                ) as error:
                    errors.append(
                        {
                            "project_uid": project_uid,
                            "error": (
                                f"Could not inspect QDPX: {error}"
                            ),
                        }
                    )
                    continue

                context_parts.append(qde_text)

                tier2_text_by_path = {
                    item.internal_path: item.text
                    for item in extracted_files
                    if item.extraction_status == "EXTRACTED"
                }

                context_parts.extend(
                    tier2_text_by_path[path]
                    for path in sorted(tier2_text_by_path)
                )

                evidence_source = (
                    "METADATA_QDE_AND_TIER2_PRIMARY_CONTENT"
                )

                for internal_path, suffix in internal_files:
                    primary_file_records.append(
                        (
                            "QDPX_INTERNAL",
                            internal_path,
                            Path(internal_path).name,
                            suffix,
                        )
                    )

            else:
                evidence_source = "STAGING_METADATA"

                for file_uid, file_name in project_files:
                    suffix = extension_from_filename(file_name)

                    if suffix in PRIMARY_INTERNAL_EXTENSIONS:
                        primary_file_records.append(
                            (
                                "STAGING_FILE",
                                str(file_uid),
                                str(file_name or ""),
                                suffix,
                            )
                        )

            classification = classify_context(
                "\n".join(context_parts)
            )

            if classification is None:
                unclassified_projects.append(project_uid)
                continue

            (
                isic_code,
                rule,
                confidence,
                matched_terms,
                tags,
            ) = classification

            label = ISIC_DIVISIONS[isic_code]

            evidence = {
                "evidence_source": evidence_source,
                "matched_terms": matched_terms,
                "primary_file_count": len(primary_file_records),
                "isic_taxonomy": "ISIC Rev. 5",
            }

            if project_type == "QDA_PROJECT":
                evidence["tier2_extraction"] = tier2_summary

            connection.execute(
                """
                INSERT INTO isic_project_classifications (
                    project_uid,
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
                    project_uid,
                    source_scope,
                    repository_id,
                    project_type,
                    label["section_code"],
                    label["division_code"],
                    label["title"],
                    None,
                    None,
                    None,
                    rule,
                    confidence,
                    json.dumps(
                        evidence,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    CLASSIFIER_VERSION,
                    utc_now_iso(),
                ),
            )

            for tag in tags:
                connection.execute(
                    """
                    INSERT OR IGNORE INTO isic_project_tags (
                        project_uid,
                        tag,
                        classifier_version
                    )
                    VALUES (?, ?, ?)
                    """,
                    (
                        project_uid,
                        tag,
                        CLASSIFIER_VERSION,
                    ),
                )

            for (
                file_origin,
                file_reference,
                file_name,
                file_extension,
            ) in primary_file_records:
                file_classification = None

                if file_origin == "QDPX_INTERNAL":
                    file_text = tier2_text_by_path.get(
                        file_reference,
                        "",
                    )
                    file_classification = (
                        classify_tier2_file_context(file_text)
                        if file_text
                        else None
                    )

                if file_classification is None:
                    file_label = label
                    file_rule = (
                        "TIER2_PROJECT_CONTEXT_FALLBACK"
                        if file_origin == "QDPX_INTERNAL"
                        else rule
                    )
                    file_confidence = (
                        min(confidence, 0.78)
                        if file_origin == "QDPX_INTERNAL"
                        else confidence
                    )
                else:
                    (
                        file_isic_code,
                        file_rule,
                        file_confidence,
                        _file_matched_terms,
                        _file_tags,
                    ) = file_classification
                    file_label = ISIC_DIVISIONS[file_isic_code]

                connection.execute(
                    """
                    INSERT INTO isic_file_classifications (
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
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        make_file_classification_id(
                            project_uid,
                            file_origin,
                            file_reference,
                        ),
                        project_uid,
                        file_origin,
                        file_reference,
                        file_name,
                        file_extension,
                        file_label["section_code"],
                        file_label["division_code"],
                        file_label["title"],
                        file_rule,
                        file_confidence,
                        CLASSIFIER_VERSION,
                        utc_now_iso(),
                    ),
                )

                files_classified += 1

            summary_counts[
                f"{label['section_code']}{label['division_code']}"
            ] += 1

        connection.commit()

        return {
            "classifier_version": CLASSIFIER_VERSION,
            "official_eligible_projects": len(projects),
            "classified_projects": sum(summary_counts.values()),
            "unclassified_projects": (
                len(unclassified_projects) + len(errors)
            ),
            "primary_files_classified": files_classified,
            "projects_by_isic_division": dict(
                sorted(summary_counts.items())
            ),
            "errors": errors,
        }

    finally:
        connection.close()


def classify_tier2_file_context(
    context: str,
) -> tuple[str, str, float, list[str], list[str]] | None:
    """Classify one primary file from its own extracted Tier 2 text.

    First apply the normal two-term project rule. If that is inconclusive,
    accept one unambiguous domain term with lower confidence. This makes
    file-level evidence useful without overriding conflicting evidence.
    """
    strict_result = classify_context(context)

    if strict_result is not None:
        (
            isic_code,
            _rule,
            confidence,
            matched_terms,
            tags,
        ) = strict_result

        return (
            isic_code,
            "TIER2_FILE_CONTENT_MULTI_TERM",
            confidence,
            matched_terms,
            tags,
        )

    legal_hits = term_hits(context, LEGAL_TERMS)
    research_hits = term_hits(context, RESEARCH_TERMS)

    if legal_hits and not research_hits:
        return (
            "N69",
            "TIER2_FILE_CONTENT_SINGLE_TERM",
            0.80,
            legal_hits,
            [
                "international-criminal-law",
                "legal-documents",
                "qualitative-coding",
            ],
        )

    if research_hits and not legal_hits:
        return (
            "N72",
            "TIER2_FILE_CONTENT_SINGLE_TERM",
            0.80,
            research_hits,
            [
                "citizen-sensing",
                "environmental-risk",
                "survey-research",
            ],
        )

    return None
