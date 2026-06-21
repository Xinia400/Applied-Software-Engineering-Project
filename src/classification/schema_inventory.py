from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class TableProfile:
    table_name: str
    normalized_table_name: str
    row_count: int
    columns: list[str]
    primary_key_columns: list[str]


@dataclass(frozen=True)
class DatabaseProfile:
    source_student_id: str
    source_scope: str
    database_path: str
    quick_check: str
    tables: list[TableProfile]
    error_message: str


def quote_identifier(identifier: str) -> str:
    """Safely quote a SQLite identifier."""
    return '"' + identifier.replace('"', '""') + '"'


def infer_student_id(database_path: Path) -> str:
    """Extract the student ID from the beginning of a database filename."""
    prefix = database_path.name.split("_", maxsplit=1)[0]
    prefix = prefix.split("-", maxsplit=1)[0]

    if prefix.isdigit():
        return prefix

    raise ValueError(
        f"Could not infer student ID from filename: {database_path.name}"
    )


def open_read_only_database(database_path: Path) -> sqlite3.Connection:
    """Open a database in immutable read-only mode."""
    absolute_path = database_path.resolve()

    return sqlite3.connect(
        f"file:{absolute_path}?mode=ro&immutable=1",
        uri=True,
    )


def profile_database(
    database_path: Path,
    *,
    source_student_id: str,
    source_scope: str,
) -> DatabaseProfile:
    """Create a structural profile without modifying the source database."""
    try:
        connection = open_read_only_database(database_path)

        try:
            quick_check_row = connection.execute(
                "PRAGMA quick_check;"
            ).fetchone()
            quick_check = (
                str(quick_check_row[0])
                if quick_check_row
                else "NO_RESULT"
            )

            table_rows = connection.execute(
                """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                  AND name NOT LIKE 'sqlite_%'
                ORDER BY lower(name), name;
                """
            ).fetchall()

            tables: list[TableProfile] = []

            for (table_name,) in table_rows:
                safe_name = quote_identifier(table_name)

                column_rows = connection.execute(
                    f"PRAGMA table_info({safe_name});"
                ).fetchall()

                columns = [str(row[1]) for row in column_rows]
                primary_key_columns = [
                    str(row[1])
                    for row in column_rows
                    if int(row[5]) > 0
                ]

                row_count = connection.execute(
                    f"SELECT COUNT(*) FROM {safe_name};"
                ).fetchone()[0]

                tables.append(
                    TableProfile(
                        table_name=table_name,
                        normalized_table_name=table_name.lower(),
                        row_count=int(row_count),
                        columns=columns,
                        primary_key_columns=primary_key_columns,
                    )
                )

            return DatabaseProfile(
                source_student_id=source_student_id,
                source_scope=source_scope,
                database_path=str(database_path),
                quick_check=quick_check,
                tables=tables,
                error_message="",
            )

        finally:
            connection.close()

    except (sqlite3.Error, OSError, ValueError) as error:
        return DatabaseProfile(
            source_student_id=source_student_id,
            source_scope=source_scope,
            database_path=str(database_path),
            quick_check="NOT_AVAILABLE",
            tables=[],
            error_message=f"{type(error).__name__}: {error}",
        )


def profile_many_databases(
    database_sources: list[tuple[Path, str, str]],
) -> list[dict]:
    """Profile all source databases and return JSON-ready dictionaries."""
    profiles = []

    for database_path, student_id, scope in database_sources:
        profile = profile_database(
            database_path,
            source_student_id=student_id,
            source_scope=scope,
        )
        profiles.append(asdict(profile))

    return profiles
