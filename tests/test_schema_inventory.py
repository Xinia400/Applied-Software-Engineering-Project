import sqlite3

from src.classification.schema_inventory import (
    profile_database,
    quote_identifier,
)


def create_sample_database(path):
    connection = sqlite3.connect(path)

    try:
        connection.execute(
            """
            CREATE TABLE PROJECTS (
                id INTEGER PRIMARY KEY,
                title TEXT,
                description TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE files (
                id INTEGER PRIMARY KEY,
                project_id INTEGER,
                file_name TEXT,
                file_type TEXT,
                status TEXT
            )
            """
        )

        connection.execute(
            "INSERT INTO PROJECTS (title, description) VALUES (?, ?)",
            ("Example", "Example project"),
        )
        connection.execute(
            """
            INSERT INTO files
            (project_id, file_name, file_type, status)
            VALUES (?, ?, ?, ?)
            """,
            (1, "interview.txt", "txt", "DOWNLOADED"),
        )

        connection.commit()

    finally:
        connection.close()


def test_quote_identifier_escapes_quotes():
    assert quote_identifier('a"b') == '"a""b"'


def test_profile_database_reads_tables_columns_and_counts(tmp_path):
    database_path = tmp_path / "23071063-sample.db"
    create_sample_database(database_path)

    profile = profile_database(
        database_path,
        source_student_id="23071063",
        source_scope="MY_CORE",
    )

    assert profile.quick_check == "ok"
    assert profile.error_message == ""

    tables = {table.normalized_table_name: table for table in profile.tables}

    assert set(tables) == {"projects", "files"}
    assert tables["projects"].row_count == 1
    assert tables["projects"].primary_key_columns == ["id"]
    assert tables["files"].columns == [
        "id",
        "project_id",
        "file_name",
        "file_type",
        "status",
    ]
