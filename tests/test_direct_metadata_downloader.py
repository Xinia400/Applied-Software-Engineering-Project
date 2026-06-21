import sqlite3

from src.classification.direct_metadata_downloader import (
    DirectDatabaseTarget,
    download_direct_database,
    safe_filename_from_url,
    sqlite_quick_check,
)


def create_small_sqlite_database(path):
    connection = sqlite3.connect(path)
    try:
        connection.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY, title TEXT)"
        )
        connection.execute(
            "INSERT INTO projects (title) VALUES ('Test project')"
        )
        connection.commit()
    finally:
        connection.close()


def test_safe_filename_from_url_removes_query_string():
    filename = safe_filename_from_url(
        "https://example.org/files/metadata.sqlite?download=1",
        fallback_name="fallback.db",
    )

    assert filename == "metadata.sqlite"


def test_sqlite_quick_check_returns_ok(tmp_path):
    database_path = tmp_path / "test.db"
    create_small_sqlite_database(database_path)

    assert sqlite_quick_check(database_path) == "ok"


def test_existing_valid_database_is_reused(tmp_path):
    student_id = "99999999"
    url = "https://example.org/peer-seeding.db"

    output_directory = tmp_path / "downloads"
    output_directory.mkdir()

    database_path = output_directory / f"{student_id}_peer-seeding.db"
    create_small_sqlite_database(database_path)

    target = DirectDatabaseTarget(
        student_id=student_id,
        url=url,
        url_source="REGISTRY",
        filename="peer-seeding.db",
    )

    result = download_direct_database(
        session=None,
        target=target,
        output_directory=output_directory,
    )

    assert result.status == "ALREADY_VERIFIED"
    assert result.sqlite_signature_detected is True
    assert result.sqlite_quick_check == "ok"
    assert result.actual_size_bytes > 0
