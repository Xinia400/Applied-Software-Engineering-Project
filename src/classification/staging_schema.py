from __future__ import annotations

import sqlite3
from pathlib import Path


STAGING_SCHEMA_VERSION = "1.0"


STAGING_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS staging_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_databases (
    source_database_id INTEGER PRIMARY KEY,
    source_student_id TEXT NOT NULL UNIQUE,
    source_scope TEXT NOT NULL,
    storage_kind TEXT NOT NULL,
    local_path TEXT NOT NULL,
    source_filename TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    source_file_size_bytes INTEGER NOT NULL,
    source_quick_check TEXT NOT NULL,
    source_schema_signature TEXT NOT NULL,
    registered_at_utc TEXT NOT NULL,
    source_notes TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS stg_projects (
    project_uid TEXT PRIMARY KEY,
    source_database_id INTEGER NOT NULL,
    source_table_name TEXT NOT NULL,
    source_project_id TEXT NOT NULL,

    repository_id TEXT,
    repository_url TEXT,
    project_url TEXT,
    query_string TEXT,
    version TEXT,
    title TEXT,
    description TEXT,
    language TEXT,
    doi TEXT,
    upload_date TEXT,
    download_date TEXT,
    download_repository_folder TEXT,
    download_project_folder TEXT,
    download_version_folder TEXT,
    download_method TEXT,

    upstream_project_type TEXT,
    upstream_isic_section TEXT,
    upstream_isic_division TEXT,
    upstream_class TEXT,

    raw_project_json TEXT NOT NULL,

    FOREIGN KEY (source_database_id)
        REFERENCES source_databases(source_database_id),
    UNIQUE (source_database_id, source_project_id)
);

CREATE TABLE IF NOT EXISTS stg_files (
    file_uid TEXT PRIMARY KEY,
    source_database_id INTEGER NOT NULL,
    source_table_name TEXT NOT NULL,
    source_file_id TEXT NOT NULL,
    project_uid TEXT,

    file_name TEXT,
    file_type TEXT,
    status TEXT,
    file_url TEXT,
    local_path TEXT,
    file_size_bytes INTEGER,

    upstream_isic_section TEXT,
    upstream_isic_division TEXT,
    upstream_class TEXT,

    raw_file_json TEXT NOT NULL,

    FOREIGN KEY (source_database_id)
        REFERENCES source_databases(source_database_id),
    FOREIGN KEY (project_uid)
        REFERENCES stg_projects(project_uid),
    UNIQUE (source_database_id, source_file_id)
);

CREATE TABLE IF NOT EXISTS stg_keywords (
    keyword_uid TEXT PRIMARY KEY,
    source_database_id INTEGER NOT NULL,
    source_table_name TEXT NOT NULL,
    source_keyword_id TEXT NOT NULL,
    project_uid TEXT,
    keyword TEXT,

    raw_keyword_json TEXT NOT NULL,

    FOREIGN KEY (source_database_id)
        REFERENCES source_databases(source_database_id),
    FOREIGN KEY (project_uid)
        REFERENCES stg_projects(project_uid),
    UNIQUE (source_database_id, source_keyword_id)
);

CREATE TABLE IF NOT EXISTS stg_licenses (
    license_uid TEXT PRIMARY KEY,
    source_database_id INTEGER NOT NULL,
    source_table_name TEXT NOT NULL,
    source_license_id TEXT NOT NULL,
    project_uid TEXT,
    license TEXT,

    raw_license_json TEXT NOT NULL,

    FOREIGN KEY (source_database_id)
        REFERENCES source_databases(source_database_id),
    FOREIGN KEY (project_uid)
        REFERENCES stg_projects(project_uid),
    UNIQUE (source_database_id, source_license_id)
);

CREATE TABLE IF NOT EXISTS stg_person_roles (
    person_role_uid TEXT PRIMARY KEY,
    source_database_id INTEGER NOT NULL,
    source_table_name TEXT NOT NULL,
    source_person_role_id TEXT NOT NULL,
    project_uid TEXT,
    name TEXT,
    role TEXT,
    email TEXT,

    raw_person_role_json TEXT NOT NULL,

    FOREIGN KEY (source_database_id)
        REFERENCES source_databases(source_database_id),
    FOREIGN KEY (project_uid)
        REFERENCES stg_projects(project_uid),
    UNIQUE (source_database_id, source_person_role_id)
);

CREATE TABLE IF NOT EXISTS import_audit (
    import_audit_id INTEGER PRIMARY KEY,
    source_database_id INTEGER NOT NULL,
    imported_at_utc TEXT NOT NULL,
    import_status TEXT NOT NULL,
    projects_imported INTEGER NOT NULL DEFAULT 0,
    files_imported INTEGER NOT NULL DEFAULT 0,
    keywords_imported INTEGER NOT NULL DEFAULT 0,
    licenses_imported INTEGER NOT NULL DEFAULT 0,
    person_roles_imported INTEGER NOT NULL DEFAULT 0,
    error_message TEXT NOT NULL DEFAULT '',

    FOREIGN KEY (source_database_id)
        REFERENCES source_databases(source_database_id)
);

CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id INTEGER PRIMARY KEY,
    source_database_id INTEGER,
    entity_type TEXT NOT NULL,
    entity_uid TEXT,
    issue_code TEXT NOT NULL,
    severity TEXT NOT NULL,
    details_json TEXT NOT NULL,
    detected_at_utc TEXT NOT NULL,

    FOREIGN KEY (source_database_id)
        REFERENCES source_databases(source_database_id)
);

CREATE INDEX IF NOT EXISTS idx_stg_projects_source
    ON stg_projects(source_database_id);

CREATE INDEX IF NOT EXISTS idx_stg_projects_repository
    ON stg_projects(repository_id);

CREATE INDEX IF NOT EXISTS idx_stg_files_project
    ON stg_files(project_uid);

CREATE INDEX IF NOT EXISTS idx_stg_files_type
    ON stg_files(file_type);

CREATE INDEX IF NOT EXISTS idx_stg_keywords_project
    ON stg_keywords(project_uid);

CREATE INDEX IF NOT EXISTS idx_stg_licenses_project
    ON stg_licenses(project_uid);

CREATE INDEX IF NOT EXISTS idx_stg_person_roles_project
    ON stg_person_roles(project_uid);

CREATE INDEX IF NOT EXISTS idx_quality_issues_source
    ON data_quality_issues(source_database_id);
"""


def connect_staging_database(database_path: Path) -> sqlite3.Connection:
    """Open the writable staging database with integrity safeguards."""
    database_path.parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON;")
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA synchronous = NORMAL;")

    return connection


def initialize_staging_database(database_path: Path) -> None:
    """Create the canonical staging schema safely and idempotently."""
    connection = connect_staging_database(database_path)

    try:
        connection.executescript(STAGING_SCHEMA_SQL)

        connection.execute(
            """
            INSERT INTO staging_meta (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            ("schema_version", STAGING_SCHEMA_VERSION),
        )

        connection.commit()

    finally:
        connection.close()


def list_user_tables(database_path: Path) -> list[str]:
    """Return non-system tables from the staging database."""
    connection = connect_staging_database(database_path)

    try:
        rows = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            ORDER BY name
            """
        ).fetchall()

        return [str(row[0]) for row in rows]

    finally:
        connection.close()
