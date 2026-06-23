from src.classification.staging_schema import (
    STAGING_SCHEMA_VERSION,
    initialize_staging_database,
    list_user_tables,
)


def test_initialize_staging_database_creates_expected_tables(tmp_path):
    database_path = tmp_path / "staging.db"

    initialize_staging_database(database_path)

    expected_tables = {
        "staging_meta",
        "source_databases",
        "stg_projects",
        "stg_files",
        "stg_keywords",
        "stg_licenses",
        "stg_person_roles",
        "import_audit",
        "data_quality_issues",
    }

    assert expected_tables.issubset(set(list_user_tables(database_path)))


def test_initialize_staging_database_is_idempotent(tmp_path):
    database_path = tmp_path / "staging.db"

    initialize_staging_database(database_path)
    initialize_staging_database(database_path)

    import sqlite3

    connection = sqlite3.connect(database_path)
    try:
        version = connection.execute(
            "SELECT value FROM staging_meta WHERE key = ?",
            ("schema_version",),
        ).fetchone()[0]
    finally:
        connection.close()

    assert version == STAGING_SCHEMA_VERSION
