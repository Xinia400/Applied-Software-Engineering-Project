from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.classification.deduplication import (
    canonical_doi,
    eligible_normalized_title,
)
from src.classification.staging_schema import connect_staging_database


RESOLUTION_VERSION = "deduplication-resolution-v2"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def stable_sha256(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def ensure_resolution_schema(
    connection: sqlite3.Connection,
) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS deduplication_runs (
            run_id TEXT PRIMARY KEY,
            resolution_version TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            raw_project_count INTEGER NOT NULL,
            candidate_cluster_count INTEGER NOT NULL,
            confirmed_cluster_count INTEGER NOT NULL,
            excluded_project_count INTEGER NOT NULL,
            included_project_count INTEGER NOT NULL,
            input_fingerprint TEXT NOT NULL,
            configuration_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS deduplication_decisions (
            decision_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            project_uid TEXT NOT NULL,
            canonical_project_uid TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            decision TEXT NOT NULL,
            evidence_rule TEXT NOT NULL,
            confidence REAL NOT NULL,
            canonical_score REAL NOT NULL,
            decision_reason TEXT NOT NULL,
            evidence_json TEXT NOT NULL,
            decided_at_utc TEXT NOT NULL,
            UNIQUE(run_id, project_uid),
            FOREIGN KEY(run_id)
                REFERENCES deduplication_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS deduplication_audit (
            audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL,
            project_uid TEXT NOT NULL,
            canonical_project_uid TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_payload_json TEXT NOT NULL,
            created_at_utc TEXT NOT NULL,
            FOREIGN KEY(run_id)
                REFERENCES deduplication_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS deduplicated_projects (
            run_id TEXT NOT NULL,
            project_uid TEXT NOT NULL,
            canonical_project_uid TEXT NOT NULL,
            source_scope TEXT NOT NULL,
            included_in_analysis INTEGER NOT NULL,
            decision TEXT NOT NULL,
            PRIMARY KEY(run_id, project_uid),
            FOREIGN KEY(run_id)
                REFERENCES deduplication_runs(run_id)
        );

        CREATE TABLE IF NOT EXISTS deduplication_project_tags (
            run_id TEXT NOT NULL,
            project_uid TEXT NOT NULL,
            tag TEXT NOT NULL,
            PRIMARY KEY(run_id, project_uid, tag),
            FOREIGN KEY(run_id)
                REFERENCES deduplication_runs(run_id)
        );

        CREATE INDEX IF NOT EXISTS
            idx_deduplication_decisions_run
        ON deduplication_decisions(run_id);

        CREATE INDEX IF NOT EXISTS
            idx_deduplication_decisions_scope
        ON deduplication_decisions(run_id, source_scope);

        CREATE INDEX IF NOT EXISTS
            idx_deduplicated_projects_analysis
        ON deduplicated_projects(run_id, included_in_analysis);

        CREATE INDEX IF NOT EXISTS
            idx_deduplication_tags_project
        ON deduplication_project_tags(project_uid);
        """
    )


def fetch_project_records(
    connection: sqlite3.Connection,
) -> dict[str, dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT
            p.project_uid,
            p.source_database_id,
            s.source_student_id,
            s.source_scope,
            p.repository_id,
            p.repository_url,
            p.project_url,
            p.title,
            p.description,
            p.doi,
            p.language,
            p.upload_date,
            COUNT(f.file_uid) AS file_count
        FROM stg_projects AS p
        JOIN source_databases AS s
            ON s.source_database_id = p.source_database_id
        LEFT JOIN stg_files AS f
            ON f.project_uid = p.project_uid
        GROUP BY
            p.project_uid,
            p.source_database_id,
            s.source_student_id,
            s.source_scope,
            p.repository_id,
            p.repository_url,
            p.project_url,
            p.title,
            p.description,
            p.doi,
            p.language,
            p.upload_date
        ORDER BY p.project_uid
        """
    ).fetchall()

    output: dict[str, dict[str, Any]] = {}

    for row in rows:
        (
            project_uid,
            source_database_id,
            source_student_id,
            source_scope,
            repository_id,
            repository_url,
            project_url,
            title,
            description,
            doi,
            language,
            upload_date,
            file_count,
        ) = row

        output[str(project_uid)] = {
            "project_uid": str(project_uid),
            "source_database_id": str(source_database_id),
            "source_student_id": str(source_student_id),
            "source_scope": str(source_scope),
            "repository_id": str(repository_id or ""),
            "repository_url": str(repository_url or ""),
            "project_url": str(project_url or ""),
            "title": str(title or ""),
            "description": str(description or ""),
            "doi": str(doi or ""),
            "language": str(language or ""),
            "upload_date": str(upload_date or ""),
            "file_count": int(file_count or 0),
        }

    return output


def fetch_source_profiles(
    connection: sqlite3.Connection,
) -> dict[str, str]:
    return {
        str(source_database_id): str(candidate_granularity)
        for source_database_id, candidate_granularity in connection.execute(
            """
            SELECT
                source_database_id,
                candidate_granularity
            FROM source_granularity_profiles
            """
        )
    }


def metadata_completeness_score(
    record: dict[str, Any],
) -> float:
    score = 0.0

    if canonical_doi(record["doi"]):
        score += 4.0

    if record["project_url"]:
        score += 3.0

    if record["repository_url"]:
        score += 1.0

    if record["description"]:
        score += 2.0

    if record["language"]:
        score += 0.5

    if record["upload_date"]:
        score += 0.5

    score += min(3.0, float(record["file_count"]) * 0.25)

    # MY_CORE receives a small deterministic tie-break preference only.
    # Metadata completeness remains the dominant canonical-selection factor.
    if record["source_scope"] == "MY_CORE":
        score += 0.25

    return round(score, 2)


def canonical_rank_key(
    record: dict[str, Any],
) -> tuple[float, int, str]:
    return (
        -metadata_completeness_score(record),
        -int(record["file_count"]),
        record["project_uid"],
    )


def confirmed_exact_cluster(
    *,
    cluster: dict[str, Any],
    members: list[dict[str, Any]],
    source_profiles: dict[str, str],
) -> tuple[bool, str]:
    if cluster["cluster_key_type"] != (
        "EXACT_DOI_AND_NORMALIZED_TITLE"
    ):
        return False, "Unsupported cluster key type."

    if cluster["candidate_strength"] != "HIGH_CONFIDENCE":
        return False, "Candidate strength is below HIGH_CONFIDENCE."

    if len(members) < 2:
        return False, "Cluster has fewer than two records."

    doi_values = {
        canonical_doi(member["doi"])
        for member in members
    }

    if len(doi_values) != 1 or "" in doi_values:
        return False, "Members do not share one valid canonical DOI."

    # Use the same punctuation-insensitive title normalization as
    # the candidate registry. This treats typographic quote variants,
    # apostrophe variants, whitespace differences, and case differences
    # as equivalent while still rejecting generic/file-like titles.
    titles = {
        eligible_normalized_title(member["title"])
        for member in members
    }

    if len(titles) != 1 or "" in titles:
        return False, "Members do not share the same eligible normalized title."

    source_categories = {
        source_profiles.get(
            member["source_database_id"],
            "MISSING_PROFILE",
        )
        for member in members
    }

    if source_categories != {"DATASET_LIKE"}:
        return (
            False,
            "At least one member is not from a DATASET_LIKE source.",
        )

    return (
        True,
        "Exact DOI and normalized-title evidence confirmed across "
        "dataset-like sources.",
    )


def fetch_cluster_members(
    connection: sqlite3.Connection,
    project_records: dict[str, dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    output: dict[str, list[dict[str, Any]]] = defaultdict(list)

    rows = connection.execute(
        """
        SELECT
            c.cluster_id,
            c.cluster_key_type,
            c.candidate_strength,
            c.canonical_key,
            c.raw_member_count,
            c.unique_title_count,
            c.evidence_json,
            m.project_uid
        FROM duplicate_clusters AS c
        JOIN duplicate_cluster_members AS m
            ON m.cluster_id = c.cluster_id
        ORDER BY c.cluster_id, m.member_rank
        """
    ).fetchall()

    for row in rows:
        (
            cluster_id,
            cluster_key_type,
            candidate_strength,
            canonical_key,
            raw_member_count,
            unique_title_count,
            evidence_json,
            project_uid,
        ) = row

        project_key = str(project_uid)

        if project_key not in project_records:
            continue

        output[str(cluster_id)].append(
            {
                "cluster_id": str(cluster_id),
                "cluster_key_type": str(cluster_key_type),
                "candidate_strength": str(candidate_strength),
                "canonical_key": str(canonical_key),
                "raw_member_count": int(raw_member_count),
                "unique_title_count": int(unique_title_count),
                "registry_evidence_json": str(evidence_json),
                "record": project_records[project_key],
            }
        )

    return output


def insert_decision(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    record: dict[str, Any],
    canonical_project_uid: str,
    decision: str,
    evidence_rule: str,
    confidence: float,
    canonical_score: float,
    decision_reason: str,
    evidence: dict[str, Any],
    tags: list[str],
) -> None:
    timestamp = utc_now_iso()
    evidence_json = json.dumps(
        evidence,
        ensure_ascii=False,
        sort_keys=True,
    )

    connection.execute(
        """
        INSERT INTO deduplication_decisions (
            run_id,
            project_uid,
            canonical_project_uid,
            source_scope,
            decision,
            evidence_rule,
            confidence,
            canonical_score,
            decision_reason,
            evidence_json,
            decided_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            record["project_uid"],
            canonical_project_uid,
            record["source_scope"],
            decision,
            evidence_rule,
            confidence,
            canonical_score,
            decision_reason,
            evidence_json,
            timestamp,
        ),
    )

    included_in_analysis = int(
        decision != "EXCLUDED_FROM_DEDUPLICATED_ANALYSIS"
    )

    connection.execute(
        """
        INSERT INTO deduplicated_projects (
            run_id,
            project_uid,
            canonical_project_uid,
            source_scope,
            included_in_analysis,
            decision
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            record["project_uid"],
            canonical_project_uid,
            record["source_scope"],
            included_in_analysis,
            decision,
        ),
    )

    connection.execute(
        """
        INSERT INTO deduplication_audit (
            run_id,
            project_uid,
            canonical_project_uid,
            event_type,
            event_payload_json,
            created_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            record["project_uid"],
            canonical_project_uid,
            decision,
            evidence_json,
            timestamp,
        ),
    )

    for tag in sorted(set(tags)):
        connection.execute(
            """
            INSERT INTO deduplication_project_tags (
                run_id,
                project_uid,
                tag
            )
            VALUES (?, ?, ?)
            """,
            (
                run_id,
                record["project_uid"],
                tag,
            ),
        )


def resolve_deduplicated_analysis(
    staging_database_path: Path,
) -> dict[str, Any]:
    connection = connect_staging_database(staging_database_path)

    try:
        ensure_resolution_schema(connection)

        project_records = fetch_project_records(connection)
        source_profiles = fetch_source_profiles(connection)
        cluster_members = fetch_cluster_members(
            connection,
            project_records,
        )

        fingerprint_input = {
            "projects": [
                {
                    key: value
                    for key, value in sorted(record.items())
                }
                for record in sorted(
                    project_records.values(),
                    key=lambda item: item["project_uid"],
                )
            ],
            "clusters": [
                {
                    "cluster_id": cluster_id,
                    "members": sorted(
                        item["record"]["project_uid"]
                        for item in members
                    ),
                }
                for cluster_id, members in sorted(
                    cluster_members.items()
                )
            ],
            "source_profiles": sorted(source_profiles.items()),
            "resolution_version": RESOLUTION_VERSION,
        }

        input_fingerprint = stable_sha256(fingerprint_input)
        run_id = (
            "dedup-run-"
            + uuid.uuid4().hex[:16]
        )

        confirmed_clusters = 0
        excluded_projects = 0
        decided_projects: set[str] = set()
        decisions_by_scope: Counter[str] = Counter()
        candidate_members_by_scope: Counter[str] = Counter()
        excluded_by_scope: Counter[str] = Counter()
        clusters_by_scope: Counter[str] = Counter()

        configuration = {
            "automatic_removal_policy": (
                "Only confirmed exact DOI plus normalized-title "
                "duplicates from DATASET_LIKE sources are excluded."
            ),
            "raw_staging_records_modified": False,
            "ambiguous_duplicates_retained": True,
            "scope_coverage": [
                "MY_CORE",
                "PEER_SHARED",
            ],
        }

        connection.execute("BEGIN")

        # Insert the parent run before child decision records because
        # SQLite foreign-key enforcement is enabled for the staging DB.
        connection.execute(
            """
            INSERT INTO deduplication_runs (
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
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                RESOLUTION_VERSION,
                utc_now_iso(),
                len(project_records),
                len(cluster_members),
                0,
                0,
                0,
                input_fingerprint,
                json.dumps(
                    configuration,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            ),
        )

        for cluster_id, items in sorted(cluster_members.items()):
            cluster = {
                "cluster_id": cluster_id,
                "cluster_key_type": items[0]["cluster_key_type"],
                "candidate_strength": items[0]["candidate_strength"],
                "canonical_key": items[0]["canonical_key"],
                "raw_member_count": items[0]["raw_member_count"],
                "unique_title_count": items[0]["unique_title_count"],
                "registry_evidence_json": (
                    items[0]["registry_evidence_json"]
                ),
            }

            members = [
                item["record"]
                for item in items
            ]

            confirmed, reason = confirmed_exact_cluster(
                cluster=cluster,
                members=members,
                source_profiles=source_profiles,
            )

            ranked_members = sorted(
                members,
                key=canonical_rank_key,
            )
            canonical = ranked_members[0]
            canonical_score = metadata_completeness_score(canonical)

            scopes_in_cluster = {
                member["source_scope"]
                for member in members
            }

            for scope in scopes_in_cluster:
                clusters_by_scope[scope] += 1

            cluster_evidence = {
                "cluster_id": cluster_id,
                "cluster_key_type": cluster["cluster_key_type"],
                "candidate_strength": cluster[
                    "candidate_strength"
                ],
                "canonical_key": cluster["canonical_key"],
                "registry_evidence_json": cluster[
                    "registry_evidence_json"
                ],
                "resolution_version": RESOLUTION_VERSION,
                "confirmed": confirmed,
                "reason": reason,
                "canonical_project_uid": canonical["project_uid"],
                "canonical_score": canonical_score,
                "member_scores": {
                    member["project_uid"]: metadata_completeness_score(
                        member
                    )
                    for member in ranked_members
                },
            }

            if confirmed:
                confirmed_clusters += 1

            for member in ranked_members:
                candidate_members_by_scope[
                    member["source_scope"]
                ] += 1

                is_canonical = (
                    member["project_uid"]
                    == canonical["project_uid"]
                )

                if confirmed and not is_canonical:
                    decision = (
                        "EXCLUDED_FROM_DEDUPLICATED_ANALYSIS"
                    )
                    confidence = 1.0
                    evidence_rule = (
                        "CONFIRMED_EXACT_DOI_AND_NORMALIZED_TITLE"
                    )
                    tags = [
                        "CONFIRMED_DUPLICATE",
                        "EXACT_IDENTIFIER_DUPLICATE",
                        "EXCLUDED_FROM_DEDUPLICATED_ANALYSIS",
                    ]
                    excluded_projects += 1
                    excluded_by_scope[
                        member["source_scope"]
                    ] += 1
                elif confirmed:
                    decision = "CANONICAL_RECORD"
                    confidence = 1.0
                    evidence_rule = (
                        "CONFIRMED_EXACT_DOI_AND_NORMALIZED_TITLE"
                    )
                    tags = [
                        "CONFIRMED_DUPLICATE",
                        "EXACT_IDENTIFIER_DUPLICATE",
                        "CANONICAL_RECORD",
                    ]
                else:
                    decision = "RETAINED_FOR_REVIEW"
                    confidence = 0.0
                    evidence_rule = "AMBIGUOUS_DUPLICATE_REVIEW"
                    tags = [
                        "AMBIGUOUS_DUPLICATE_REVIEW",
                        "RETAINED_IN_ANALYSIS",
                    ]

                insert_decision(
                    connection,
                    run_id=run_id,
                    record=member,
                    canonical_project_uid=canonical["project_uid"],
                    decision=decision,
                    evidence_rule=evidence_rule,
                    confidence=confidence,
                    canonical_score=metadata_completeness_score(
                        member
                    ),
                    decision_reason=reason,
                    evidence=cluster_evidence,
                    tags=tags,
                )

                decided_projects.add(member["project_uid"])
                decisions_by_scope[member["source_scope"]] += 1

        for project_uid, record in sorted(project_records.items()):
            if project_uid in decided_projects:
                continue

            unique_evidence = {
                "resolution_version": RESOLUTION_VERSION,
                "reason": (
                    "No confirmed duplicate cluster membership."
                ),
                "canonical_project_uid": project_uid,
            }

            insert_decision(
                connection,
                run_id=run_id,
                record=record,
                canonical_project_uid=project_uid,
                decision="UNIQUE_RECORD",
                evidence_rule="NO_CONFIRMED_DUPLICATE",
                confidence=1.0,
                canonical_score=metadata_completeness_score(record),
                decision_reason=(
                    "No confirmed duplicate cluster membership."
                ),
                evidence=unique_evidence,
                tags=[
                    "UNIQUE_RECORD",
                    "RETAINED_IN_ANALYSIS",
                ],
            )

            decisions_by_scope[record["source_scope"]] += 1

        included_projects = len(project_records) - excluded_projects

        connection.execute(
            """
            UPDATE deduplication_runs
            SET
                confirmed_cluster_count = ?,
                excluded_project_count = ?,
                included_project_count = ?
            WHERE run_id = ?
            """,
            (
                confirmed_clusters,
                excluded_projects,
                included_projects,
                run_id,
            ),
        )

        connection.commit()

        scope_summary: dict[str, dict[str, int]] = {}

        for scope in ("MY_CORE", "PEER_SHARED"):
            raw_count = sum(
                1
                for record in project_records.values()
                if record["source_scope"] == scope
            )

            scope_summary[scope] = {
                "raw_projects": raw_count,
                "candidate_cluster_members": (
                    candidate_members_by_scope[scope]
                ),
                "candidate_clusters_touching_scope": (
                    clusters_by_scope[scope]
                ),
                "decision_records": decisions_by_scope[scope],
                "excluded_duplicates": excluded_by_scope[scope],
                "deduplicated_projects": (
                    raw_count - excluded_by_scope[scope]
                ),
            }

        return {
            "run_id": run_id,
            "resolution_version": RESOLUTION_VERSION,
            "input_fingerprint": input_fingerprint,
            "raw_staging_records_modified": False,
            "raw_project_count": len(project_records),
            "candidate_cluster_count": len(cluster_members),
            "confirmed_cluster_count": confirmed_clusters,
            "excluded_duplicate_count": excluded_projects,
            "deduplicated_project_count": included_projects,
            "scope_summary": scope_summary,
            "automatic_removal_policy": configuration[
                "automatic_removal_policy"
            ],
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def latest_deduplication_run(
    connection: sqlite3.Connection,
) -> dict[str, Any] | None:
    row = connection.execute(
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

    if row is None:
        return None

    (
        run_id,
        resolution_version,
        created_at_utc,
        raw_project_count,
        candidate_cluster_count,
        confirmed_cluster_count,
        excluded_project_count,
        included_project_count,
        input_fingerprint,
        configuration_json,
    ) = row

    scope_rows = connection.execute(
        """
        SELECT
            source_scope,
            COUNT(*) AS raw_members,
            SUM(included_in_analysis) AS included_members,
            SUM(
                CASE
                    WHEN decision =
                    'EXCLUDED_FROM_DEDUPLICATED_ANALYSIS'
                    THEN 1
                    ELSE 0
                END
            ) AS excluded_members
        FROM deduplicated_projects
        WHERE run_id = ?
        GROUP BY source_scope
        ORDER BY source_scope
        """,
        (run_id,),
    ).fetchall()

    return {
        "run_id": str(run_id),
        "resolution_version": str(resolution_version),
        "created_at_utc": str(created_at_utc),
        "raw_project_count": int(raw_project_count),
        "candidate_cluster_count": int(candidate_cluster_count),
        "confirmed_cluster_count": int(confirmed_cluster_count),
        "excluded_project_count": int(excluded_project_count),
        "included_project_count": int(included_project_count),
        "input_fingerprint": str(input_fingerprint),
        "configuration": json.loads(configuration_json),
        "scope_summary": {
            str(source_scope): {
                "raw_projects": int(raw_members),
                "deduplicated_projects": int(included_members or 0),
                "excluded_duplicates": int(excluded_members or 0),
            }
            for (
                source_scope,
                raw_members,
                included_members,
                excluded_members,
            ) in scope_rows
        },
    }
