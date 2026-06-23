from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.classification.source_catalog import (
    SourceDatabaseFile,
    sha256_file,
)
from src.classification.staging_schema import (
    connect_staging_database,
)


FETCH_BATCH_SIZE = 1_000

CORE_TABLES = {
    "projects",
    "files",
    "keywords",
    "licenses",
    "person_role",
}


@dataclass(frozen=True)
class ImportResult:
    source_student_id: str
    source_database_id: int | None
    import_status: str
    projects_imported: int
    files_imported: int
    keywords_imported: int
    licenses_imported: int
    person_roles_imported: int
    error_message: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(
        microsecond=0
    ).isoformat()


def quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def as_text(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, bytes):
        return value.decode(
            "utf-8",
            errors="replace",
        ).strip() or None

    text = str(value).strip()
    return text or None


def canonical_id(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    text = as_text(value)

    if text is None:
        return None

    if re.fullmatch(r"\d+\.0", text):
        return text[:-2]

    return text


def as_optional_int(value: Any) -> int | None:
    if value is None:
        return None

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def first_present(
    row: dict[str, Any],
    candidates: tuple[str, ...],
) -> Any:
    for column in candidates:
        value = row.get(column)

        if value is not None and str(value).strip() != "":
            return value

    return None


def json_default(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}

    return str(value)


def raw_json(row: dict[str, Any]) -> str:
    return json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        default=json_default,
    )


def project_uid(student_id: str, source_id: str) -> str:
    return f"{student_id}:project:{source_id}"


def entity_uid(
    student_id: str,
    entity_type: str,
    source_id: str,
) -> str:
    return f"{student_id}:{entity_type}:{source_id}"


def open_source_database(path: Path) -> sqlite3.Connection:
    absolute_path = path.resolve()

    return sqlite3.connect(
        f"file:{absolute_path}?mode=ro&immutable=1",
        uri=True,
    )


def source_table_map(connection: sqlite3.Connection) -> dict[str, str]:
    rows = connection.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
          AND name NOT LIKE 'sqlite_%'
        """
    ).fetchall()

    return {
        str(name).lower(): str(name)
        for (name,) in rows
    }


def quick_check(connection: sqlite3.Connection) -> str:
    row = connection.execute("PRAGMA quick_check;").fetchone()
    return str(row[0]) if row else "NO_RESULT"


def source_schema_signature(connection: sqlite3.Connection) -> str:
    return "|".join(sorted(source_table_map(connection)))


def iter_source_rows(
    connection: sqlite3.Connection,
    table_name: str,
) -> Iterator[dict[str, Any]]:
    cursor = connection.execute(
        f"SELECT * FROM {quote_identifier(table_name)}"
    )

    columns = [
        str(description[0]).lower()
        for description in cursor.description
    ]

    try:
        while rows := cursor.fetchmany(FETCH_BATCH_SIZE):
            for values in rows:
                yield dict(zip(columns, values))
    finally:
        cursor.close()


def verify_catalog_source(source: SourceDatabaseFile) -> None:
    path = Path(source.local_path)

    if not path.exists():
        raise FileNotFoundError(f"Missing source database: {path}")

    if path.stat().st_size != source.source_file_size_bytes:
        raise ValueError(
            f"Size mismatch for {source.source_student_id}."
        )

    if sha256_file(path) != source.source_sha256:
        raise ValueError(
            f"SHA-256 mismatch for {source.source_student_id}."
        )


def register_source_database(
    connection: sqlite3.Connection,
    source: SourceDatabaseFile,
    source_quick_check: str,
    schema_signature: str,
) -> int:
    existing = connection.execute(
        """
        SELECT source_database_id
        FROM source_databases
        WHERE source_student_id = ?
        """,
        (source.source_student_id,),
    ).fetchone()

    if existing:
        raise ValueError(
            f"Student {source.source_student_id} already imported. "
            "Use --reset before importing again."
        )

    cursor = connection.execute(
        """
        INSERT INTO source_databases (
            source_student_id,
            source_scope,
            storage_kind,
            local_path,
            source_filename,
            source_sha256,
            source_file_size_bytes,
            source_quick_check,
            source_schema_signature,
            registered_at_utc,
            source_notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source.source_student_id,
            source.source_scope,
            source.storage_kind,
            source.local_path,
            source.source_filename,
            source.source_sha256,
            source.source_file_size_bytes,
            source_quick_check,
            schema_signature,
            utc_now_iso(),
            "",
        ),
    )

    return int(cursor.lastrowid)


def add_quality_issue(
    connection: sqlite3.Connection,
    source_database_id: int,
    entity_type: str,
    entity_uid_value: str | None,
    issue_code: str,
    severity: str,
    details: dict[str, Any],
) -> None:
    connection.execute(
        """
        INSERT INTO data_quality_issues (
            source_database_id,
            entity_type,
            entity_uid,
            issue_code,
            severity,
            details_json,
            detected_at_utc
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            source_database_id,
            entity_type,
            entity_uid_value,
            issue_code,
            severity,
            json.dumps(
                details,
                ensure_ascii=False,
                sort_keys=True,
                default=json_default,
            ),
            utc_now_iso(),
        ),
    )


def project_reference(
    connection: sqlite3.Connection,
    source_database_id: int,
    source_student_id: str,
    valid_project_ids: set[str],
    source_project_id: Any,
    entity_type: str,
    current_uid: str,
) -> str | None:
    normalized_id = canonical_id(source_project_id)

    if normalized_id is None:
        add_quality_issue(
            connection,
            source_database_id,
            entity_type,
            current_uid,
            "MISSING_PROJECT_REFERENCE",
            "WARNING",
            {},
        )
        return None

    if normalized_id not in valid_project_ids:
        add_quality_issue(
            connection,
            source_database_id,
            entity_type,
            current_uid,
            "ORPHAN_PROJECT_REFERENCE",
            "WARNING",
            {"source_project_id": normalized_id},
        )
        return None

    return project_uid(source_student_id, normalized_id)


def import_projects(
    connection: sqlite3.Connection,
    source_connection: sqlite3.Connection,
    source_table_name: str,
    source_database_id: int,
    source_student_id: str,
) -> tuple[int, set[str]]:
    sql = """
        INSERT INTO stg_projects (
            project_uid,
            source_database_id,
            source_table_name,
            source_project_id,
            repository_id,
            repository_url,
            project_url,
            query_string,
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
            upstream_project_type,
            upstream_isic_section,
            upstream_isic_division,
            upstream_class,
            raw_project_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    batch: list[tuple[Any, ...]] = []
    imported = 0
    project_ids: set[str] = set()

    for row in iter_source_rows(
        source_connection,
        source_table_name,
    ):
        source_id = canonical_id(row.get("id"))

        if source_id is None:
            add_quality_issue(
                connection,
                source_database_id,
                "PROJECT",
                None,
                "MISSING_SOURCE_ID",
                "ERROR",
                {},
            )
            continue

        project_ids.add(source_id)

        batch.append(
            (
                project_uid(source_student_id, source_id),
                source_database_id,
                source_table_name,
                source_id,
                as_text(row.get("repository_id")),
                as_text(row.get("repository_url")),
                as_text(row.get("project_url")),
                as_text(row.get("query_string")),
                as_text(row.get("version")),
                as_text(row.get("title")),
                as_text(row.get("description")),
                as_text(row.get("language")),
                as_text(row.get("doi")),
                as_text(row.get("upload_date")),
                as_text(row.get("download_date")),
                as_text(row.get("download_repository_folder")),
                as_text(row.get("download_project_folder")),
                as_text(row.get("download_version_folder")),
                as_text(row.get("download_method")),
                as_text(
                    first_present(row, ("project_type", "type"))
                ),
                as_text(
                    first_present(
                        row,
                        ("isic_section", "isic_section_code"),
                    )
                ),
                as_text(
                    first_present(
                        row,
                        ("isic_division", "isic_division_code"),
                    )
                ),
                as_text(row.get("class")),
                raw_json(row),
            )
        )

        if len(batch) >= FETCH_BATCH_SIZE:
            connection.executemany(sql, batch)
            imported += len(batch)
            batch.clear()

    if batch:
        connection.executemany(sql, batch)
        imported += len(batch)

    return imported, project_ids


def import_files(
    connection: sqlite3.Connection,
    source_connection: sqlite3.Connection,
    source_table_name: str,
    source_database_id: int,
    source_student_id: str,
    valid_project_ids: set[str],
) -> int:
    sql = """
        INSERT INTO stg_files (
            file_uid,
            source_database_id,
            source_table_name,
            source_file_id,
            project_uid,
            file_name,
            file_type,
            status,
            file_url,
            local_path,
            file_size_bytes,
            upstream_isic_section,
            upstream_isic_division,
            upstream_class,
            raw_file_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    batch: list[tuple[Any, ...]] = []
    imported = 0

    for row in iter_source_rows(
        source_connection,
        source_table_name,
    ):
        source_id = canonical_id(row.get("id"))

        if source_id is None:
            add_quality_issue(
                connection,
                source_database_id,
                "FILE",
                None,
                "MISSING_SOURCE_ID",
                "ERROR",
                {},
            )
            continue

        current_uid = entity_uid(
            source_student_id,
            "file",
            source_id,
        )

        batch.append(
            (
                current_uid,
                source_database_id,
                source_table_name,
                source_id,
                project_reference(
                    connection,
                    source_database_id,
                    source_student_id,
                    valid_project_ids,
                    row.get("project_id"),
                    "FILE",
                    current_uid,
                ),
                as_text(row.get("file_name")),
                as_text(row.get("file_type")),
                as_text(row.get("status")),
                as_text(
                    first_present(
                        row,
                        ("file_url", "download_url", "gdrive_url"),
                    )
                ),
                as_text(
                    first_present(row, ("local_path", "zip_path"))
                ),
                as_optional_int(
                    first_present(
                        row,
                        (
                            "file_size_bytes",
                            "size_bytes",
                            "file_size",
                            "size",
                        ),
                    )
                ),
                as_text(row.get("isic_section")),
                as_text(row.get("isic_division")),
                as_text(row.get("class")),
                raw_json(row),
            )
        )

        if len(batch) >= FETCH_BATCH_SIZE:
            connection.executemany(sql, batch)
            imported += len(batch)
            batch.clear()

    if batch:
        connection.executemany(sql, batch)
        imported += len(batch)

    return imported


def import_simple_project_table(
    connection: sqlite3.Connection,
    source_connection: sqlite3.Connection,
    source_table_name: str,
    source_database_id: int,
    source_student_id: str,
    valid_project_ids: set[str],
    entity_name: str,
) -> int:
    configurations = {
        "KEYWORD": (
            "stg_keywords",
            "keyword_uid",
            "source_keyword_id",
            "keyword",
            "raw_keyword_json",
            "keyword",
        ),
        "LICENSE": (
            "stg_licenses",
            "license_uid",
            "source_license_id",
            "license",
            "raw_license_json",
            "license",
        ),
        "PERSON_ROLE": (
            "stg_person_roles",
            "person_role_uid",
            "source_person_role_id",
            None,
            "raw_person_role_json",
            "person_role",
        ),
    }

    (
        destination_table,
        uid_column,
        source_id_column,
        value_column,
        raw_column,
        uid_label,
    ) = configurations[entity_name]

    if entity_name == "PERSON_ROLE":
        sql = """
            INSERT INTO stg_person_roles (
                person_role_uid,
                source_database_id,
                source_table_name,
                source_person_role_id,
                project_uid,
                name,
                role,
                email,
                raw_person_role_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
    else:
        sql = f"""
            INSERT INTO {destination_table} (
                {uid_column},
                source_database_id,
                source_table_name,
                {source_id_column},
                project_uid,
                {value_column},
                {raw_column}
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """

    batch: list[tuple[Any, ...]] = []
    imported = 0

    for row in iter_source_rows(
        source_connection,
        source_table_name,
    ):
        source_id = canonical_id(row.get("id"))

        if source_id is None:
            add_quality_issue(
                connection,
                source_database_id,
                entity_name,
                None,
                "MISSING_SOURCE_ID",
                "ERROR",
                {},
            )
            continue

        current_uid = entity_uid(
            source_student_id,
            uid_label,
            source_id,
        )

        linked_project_uid = project_reference(
            connection,
            source_database_id,
            source_student_id,
            valid_project_ids,
            row.get("project_id"),
            entity_name,
            current_uid,
        )

        if entity_name == "PERSON_ROLE":
            batch.append(
                (
                    current_uid,
                    source_database_id,
                    source_table_name,
                    source_id,
                    linked_project_uid,
                    as_text(row.get("name")),
                    as_text(row.get("role")),
                    as_text(row.get("email")),
                    raw_json(row),
                )
            )
        else:
            batch.append(
                (
                    current_uid,
                    source_database_id,
                    source_table_name,
                    source_id,
                    linked_project_uid,
                    as_text(row.get(value_column)),
                    raw_json(row),
                )
            )

        if len(batch) >= FETCH_BATCH_SIZE:
            connection.executemany(sql, batch)
            imported += len(batch)
            batch.clear()

    if batch:
        connection.executemany(sql, batch)
        imported += len(batch)

    return imported


def reset_staging_import_data(database_path: Path) -> None:
    connection = connect_staging_database(database_path)

    try:
        for table_name in (
            "data_quality_issues",
            "import_audit",
            "stg_person_roles",
            "stg_licenses",
            "stg_keywords",
            "stg_files",
            "stg_projects",
            "source_databases",
        ):
            connection.execute(
                f"DELETE FROM {quote_identifier(table_name)}"
            )

        connection.commit()
    finally:
        connection.close()


def import_source_database(
    staging_database_path: Path,
    source: SourceDatabaseFile,
) -> ImportResult:
    destination = connect_staging_database(staging_database_path)
    source_connection: sqlite3.Connection | None = None
    source_database_id: int | None = None

    try:
        verify_catalog_source(source)

        source_connection = open_source_database(
            Path(source.local_path)
        )

        source_check = quick_check(source_connection)

        if source_check != "ok":
            raise ValueError(
                f"Source quick_check failed: {source_check}"
            )

        table_map = source_table_map(source_connection)
        missing = CORE_TABLES.difference(table_map)

        if missing:
            raise ValueError(
                "Missing core tables: "
                + ", ".join(sorted(missing))
            )

        source_database_id = register_source_database(
            destination,
            source,
            source_check,
            source_schema_signature(source_connection),
        )

        destination.commit()
        destination.execute("BEGIN")

        projects, valid_project_ids = import_projects(
            destination,
            source_connection,
            table_map["projects"],
            source_database_id,
            source.source_student_id,
        )

        files = import_files(
            destination,
            source_connection,
            table_map["files"],
            source_database_id,
            source.source_student_id,
            valid_project_ids,
        )

        keywords = import_simple_project_table(
            destination,
            source_connection,
            table_map["keywords"],
            source_database_id,
            source.source_student_id,
            valid_project_ids,
            "KEYWORD",
        )

        licenses = import_simple_project_table(
            destination,
            source_connection,
            table_map["licenses"],
            source_database_id,
            source.source_student_id,
            valid_project_ids,
            "LICENSE",
        )

        persons = import_simple_project_table(
            destination,
            source_connection,
            table_map["person_role"],
            source_database_id,
            source.source_student_id,
            valid_project_ids,
            "PERSON_ROLE",
        )

        destination.execute(
            """
            INSERT INTO import_audit (
                source_database_id,
                imported_at_utc,
                import_status,
                projects_imported,
                files_imported,
                keywords_imported,
                licenses_imported,
                person_roles_imported,
                error_message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                source_database_id,
                utc_now_iso(),
                "COMPLETED",
                projects,
                files,
                keywords,
                licenses,
                persons,
                "",
            ),
        )

        destination.commit()

        return ImportResult(
            source_student_id=source.source_student_id,
            source_database_id=source_database_id,
            import_status="COMPLETED",
            projects_imported=projects,
            files_imported=files,
            keywords_imported=keywords,
            licenses_imported=licenses,
            person_roles_imported=persons,
            error_message="",
        )

    except (sqlite3.Error, OSError, ValueError) as error:
        if destination.in_transaction:
            destination.rollback()

        return ImportResult(
            source_student_id=source.source_student_id,
            source_database_id=source_database_id,
            import_status="FAILED",
            projects_imported=0,
            files_imported=0,
            keywords_imported=0,
            licenses_imported=0,
            person_roles_imported=0,
            error_message=f"{type(error).__name__}: {error}",
        )

    finally:
        if source_connection is not None:
            source_connection.close()

        destination.close()
