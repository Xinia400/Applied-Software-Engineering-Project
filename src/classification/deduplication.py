from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.classification.staging_schema import (
    connect_staging_database,
)

CLASSIFIER_VERSION = "deduplication-v1"

DOI_PATTERN = re.compile(
    r"10\.\d{4,9}/[-._;()/:a-z0-9]+",
    re.IGNORECASE,
)

FILE_LIKE_TITLE_PATTERN = re.compile(
    r"\.(pdf|txt|csv|tsv|tab|docx?|xlsx?|json|xml|"
    r"qdpx|nvpx|nvp|mx[0-9]+|zip|png|jpe?g|"
    r"wav|mp3|mp4|rtf|md)$",
    re.IGNORECASE,
)

GENERIC_TITLES = {
    "unknown",
    "dataset",
    "data set",
    "replication data for",
    "supplementary data",
    "supplementary files",
    "untitled",
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def canonical_doi(value: object) -> str:
    if value is None:
        return ""

    match = DOI_PATTERN.search(str(value).casefold())

    if not match:
        return ""

    return match.group(0).rstrip(".,;:)")


def is_file_like_title(value: object) -> bool:
    if value is None:
        return False

    return bool(
        FILE_LIKE_TITLE_PATTERN.search(str(value).strip())
    )


def eligible_normalized_title(value: object) -> str:
    if value is None or is_file_like_title(value):
        return ""

    text = str(value).casefold().strip()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^a-z0-9 ]+", "", text)
    text = text.strip()

    if len(text) < 20 or text in GENERIC_TITLES:
        return ""

    return text


def make_cluster_id(
    doi: str,
    normalized_title: str,
) -> str:
    raw_key = f"{doi}|{normalized_title}"
    digest = hashlib.sha256(
        raw_key.encode("utf-8")
    ).hexdigest()

    return f"dedup:{digest[:24]}"


def classify_source_granularity(
    *,
    projects: int,
    files: int,
    file_like_title_records: int,
    repeated_doi_records: int,
) -> str:
    if projects == 0:
        return "DATASET_LIKE"

    file_like_rate = file_like_title_records / projects
    repeated_doi_rate = repeated_doi_records / projects
    files_per_project = files / projects

    if (
        repeated_doi_rate >= 0.25
        and files_per_project <= 2.0
    ):
        return "FILE_LEVEL_LIKELY"

    if (
        file_like_rate >= 0.50
        and files_per_project <= 1.5
    ):
        return "FILE_LEVEL_LIKELY"

    if (
        repeated_doi_rate >= 0.05
        or file_like_rate >= 0.15
    ):
        return "MIXED_OR_REVIEW"

    return "DATASET_LIKE"


def profile_sources(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, Any]]:
    source_info = {
        str(source_database_id): {
            "student_id": str(student_id),
            "source_scope": str(source_scope),
        }
        for (
            source_database_id,
            student_id,
            source_scope,
        ) in connection.execute(
            """
            SELECT
                source_database_id,
                source_student_id,
                source_scope
            FROM source_databases
            """
        )
    }

    file_counts = {
        str(source_database_id): int(file_count)
        for source_database_id, file_count in connection.execute(
            """
            SELECT
                source_database_id,
                COUNT(*)
            FROM stg_files
            GROUP BY source_database_id
            """
        )
    }

    stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "projects": 0,
            "file_like_title_records": 0,
            "doi_counts": Counter(),
        }
    )

    for source_database_id, title, doi in connection.execute(
        """
        SELECT
            source_database_id,
            title,
            doi
        FROM stg_projects
        """
    ):
        source_key = str(source_database_id)
        item = stats[source_key]

        item["projects"] += 1

        if is_file_like_title(title):
            item["file_like_title_records"] += 1

        doi_key = canonical_doi(doi)

        if doi_key:
            item["doi_counts"][doi_key] += 1

    profiles: dict[str, dict[str, Any]] = {}

    for source_key, info in source_info.items():
        item = stats[source_key]
        projects = int(item["projects"])
        files = int(file_counts.get(source_key, 0))

        repeated_doi_records = sum(
            count
            for count in item["doi_counts"].values()
            if count > 1
        )

        category = classify_source_granularity(
            projects=projects,
            files=files,
            file_like_title_records=int(
                item["file_like_title_records"]
            ),
            repeated_doi_records=repeated_doi_records,
        )

        profiles[source_key] = {
            "source_database_id": source_key,
            "student_id": info["student_id"],
            "source_scope": info["source_scope"],
            "projects": projects,
            "files": files,
            "file_like_title_records": int(
                item["file_like_title_records"]
            ),
            "repeated_doi_records": repeated_doi_records,
            "candidate_granularity": category,
        }

    return profiles


def ensure_deduplication_schema(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS source_granularity_profiles (
            source_database_id TEXT PRIMARY KEY,
            source_student_id TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            project_count INTEGER NOT NULL,
            file_count INTEGER NOT NULL,
            file_like_title_records INTEGER NOT NULL,
            repeated_doi_records INTEGER NOT NULL,
            candidate_granularity TEXT NOT NULL,
            classifier_version TEXT NOT NULL,
            profiled_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS duplicate_clusters (
            cluster_id TEXT PRIMARY KEY,
            cluster_key_type TEXT NOT NULL,
            canonical_key TEXT NOT NULL,
            candidate_strength TEXT NOT NULL,
            review_status TEXT NOT NULL,
            auto_merge_allowed INTEGER NOT NULL,
            raw_member_count INTEGER NOT NULL,
            unique_source_count INTEGER NOT NULL,
            unique_student_count INTEGER NOT NULL,
            unique_repository_count INTEGER NOT NULL,
            unique_title_count INTEGER NOT NULL,
            canonical_project_uid TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            classifier_version TEXT NOT NULL,
            created_at_utc TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS duplicate_cluster_members (
            cluster_id TEXT NOT NULL,
            project_uid TEXT NOT NULL,
            source_database_id TEXT NOT NULL,
            source_student_id TEXT NOT NULL,
            repository_id TEXT,
            member_rank INTEGER NOT NULL,
            is_canonical INTEGER NOT NULL,
            PRIMARY KEY (cluster_id, project_uid),
            FOREIGN KEY (cluster_id)
                REFERENCES duplicate_clusters(cluster_id),
            FOREIGN KEY (project_uid)
                REFERENCES stg_projects(project_uid)
        );

        CREATE INDEX IF NOT EXISTS
            idx_duplicate_cluster_members_project
        ON duplicate_cluster_members(project_uid);

        CREATE INDEX IF NOT EXISTS
            idx_duplicate_clusters_strength
        ON duplicate_clusters(candidate_strength);
        """
    )


def reset_deduplication_registry(
    connection: sqlite3.Connection,
) -> None:
    connection.execute("DELETE FROM duplicate_cluster_members")
    connection.execute("DELETE FROM duplicate_clusters")
    connection.execute("DELETE FROM source_granularity_profiles")
    connection.commit()


def persist_source_profiles(
    connection: sqlite3.Connection,
    profiles: dict[str, dict[str, Any]],
) -> None:
    timestamp = utc_now_iso()

    for profile in profiles.values():
        connection.execute(
            """
            INSERT INTO source_granularity_profiles (
                source_database_id,
                source_student_id,
                source_scope,
                project_count,
                file_count,
                file_like_title_records,
                repeated_doi_records,
                candidate_granularity,
                classifier_version,
                profiled_at_utc
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile["source_database_id"],
                profile["student_id"],
                profile["source_scope"],
                profile["projects"],
                profile["files"],
                profile["file_like_title_records"],
                profile["repeated_doi_records"],
                profile["candidate_granularity"],
                CLASSIFIER_VERSION,
                timestamp,
            ),
        )


def canonical_sort_key(
    record: dict[str, Any],
    file_counts: dict[str, int],
) -> tuple[Any, ...]:
    scope_priority = (
        0
        if record["source_scope"] == "MY_CORE"
        else 1
    )

    metadata_score = (
        int(bool(record["description"]))
        + int(bool(record["project_url"]))
        + int(bool(record["doi"]))
        + min(3, file_counts.get(record["project_uid"], 0))
    )

    return (
        scope_priority,
        -metadata_score,
        record["project_uid"],
    )


def build_deduplication_registry(
    staging_database_path: Path,
    *,
    reset: bool,
) -> dict[str, Any]:
    connection = connect_staging_database(
        staging_database_path
    )

    try:
        ensure_deduplication_schema(connection)

        if reset:
            reset_deduplication_registry(connection)

        profiles = profile_sources(connection)
        persist_source_profiles(connection, profiles)

        file_counts = {
            str(project_uid): int(file_count)
            for project_uid, file_count in connection.execute(
                """
                SELECT
                    project_uid,
                    COUNT(*)
                FROM stg_files
                GROUP BY project_uid
                """
            )
        }

        groups: dict[
            tuple[str, str],
            list[dict[str, Any]],
        ] = defaultdict(list)

        rows = connection.execute(
            """
            SELECT
                p.project_uid,
                p.source_database_id,
                s.source_student_id,
                s.source_scope,
                p.repository_id,
                p.title,
                p.description,
                p.doi,
                p.project_url
            FROM stg_projects AS p
            JOIN source_databases AS s
                ON s.source_database_id = p.source_database_id
            """
        ).fetchall()

        for row in rows:
            (
                project_uid,
                source_database_id,
                student_id,
                source_scope,
                repository_id,
                title,
                description,
                doi,
                project_url,
            ) = row

            source_key = str(source_database_id)
            profile = profiles[source_key]

            if (
                profile["candidate_granularity"]
                != "DATASET_LIKE"
            ):
                continue

            doi_key = canonical_doi(doi)
            title_key = eligible_normalized_title(title)

            if not doi_key or not title_key:
                continue

            groups[(doi_key, title_key)].append(
                {
                    "project_uid": str(project_uid),
                    "source_database_id": source_key,
                    "student_id": str(student_id),
                    "source_scope": str(source_scope),
                    "repository_id": str(repository_id or ""),
                    "title": str(title or ""),
                    "description": str(description or ""),
                    "doi": str(doi or ""),
                    "project_url": str(project_url or ""),
                }
            )

        cluster_count = 0
        raw_member_count = 0
        cluster_size_counter: Counter[int] = Counter()

        for (doi_key, title_key), members in sorted(
            groups.items()
        ):
            unique_students = {
                item["student_id"]
                for item in members
            }

            if len(unique_students) < 2:
                continue

            cluster_id = make_cluster_id(
                doi_key,
                title_key,
            )

            ordered_members = sorted(
                members,
                key=lambda item: canonical_sort_key(
                    item,
                    file_counts,
                ),
            )

            canonical = ordered_members[0]

            evidence = {
                "doi": doi_key,
                "normalized_title": title_key,
                "cluster_rule": (
                    "EXACT_DOI_AND_NON_GENERIC_NORMALIZED_TITLE"
                ),
                "raw_records_preserved": True,
                "raw_merge_performed": False,
                "canonicalization_scope": (
                    "analytics_and_reporting_only"
                ),
            }

            connection.execute(
                """
                INSERT INTO duplicate_clusters (
                    cluster_id,
                    cluster_key_type,
                    canonical_key,
                    candidate_strength,
                    review_status,
                    auto_merge_allowed,
                    raw_member_count,
                    unique_source_count,
                    unique_student_count,
                    unique_repository_count,
                    unique_title_count,
                    canonical_project_uid,
                    evidence_json,
                    classifier_version,
                    created_at_utc
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cluster_id,
                    "EXACT_DOI_AND_NORMALIZED_TITLE",
                    f"{doi_key}|{title_key}",
                    "HIGH_CONFIDENCE",
                    "CANONICAL_LINK_CREATED_NO_RAW_MERGE",
                    0,
                    len(ordered_members),
                    len(
                        {
                            item["source_database_id"]
                            for item in ordered_members
                        }
                    ),
                    len(unique_students),
                    len(
                        {
                            item["repository_id"]
                            for item in ordered_members
                        }
                    ),
                    len(
                        {
                            eligible_normalized_title(
                                item["title"]
                            )
                            for item in ordered_members
                        }
                    ),
                    canonical["project_uid"],
                    json.dumps(
                        evidence,
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    CLASSIFIER_VERSION,
                    utc_now_iso(),
                ),
            )

            for rank, member in enumerate(
                ordered_members,
                start=1,
            ):
                connection.execute(
                    """
                    INSERT INTO duplicate_cluster_members (
                        cluster_id,
                        project_uid,
                        source_database_id,
                        source_student_id,
                        repository_id,
                        member_rank,
                        is_canonical
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        cluster_id,
                        member["project_uid"],
                        member["source_database_id"],
                        member["student_id"],
                        member["repository_id"],
                        rank,
                        int(
                            member["project_uid"]
                            == canonical["project_uid"]
                        ),
                    ),
                )

            cluster_count += 1
            raw_member_count += len(ordered_members)
            cluster_size_counter[len(ordered_members)] += 1

        connection.commit()

        profile_counts = Counter(
            profile["candidate_granularity"]
            for profile in profiles.values()
        )

        return {
            "classifier_version": CLASSIFIER_VERSION,
            "raw_staging_projects_preserved": len(rows),
            "source_profile_counts": dict(
                sorted(profile_counts.items())
            ),
            "eligible_dataset_like_sources": sum(
                1
                for profile in profiles.values()
                if (
                    profile["candidate_granularity"]
                    == "DATASET_LIKE"
                )
            ),
            "duplicate_clusters_created": cluster_count,
            "raw_records_linked_to_clusters": raw_member_count,
            "canonical_analytics_records": cluster_count,
            "cluster_sizes": dict(
                sorted(cluster_size_counter.items())
            ),
            "raw_merge_performed": False,
        }

    finally:
        connection.close()
