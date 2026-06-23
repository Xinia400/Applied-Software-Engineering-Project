from src.classification.source_registry import (
    identify_base_data_provider,
    normalize_student_id,
    repair_metadata_url,
    split_base_data_locations,
)


def test_normalize_student_id_removes_excel_decimal():
    assert normalize_student_id("23071063.0") == "23071063"


def test_repair_malformed_raw_github_url():
    original = (
        "https://raw.githubusercontent.com/Xinia400/"
        "Applied-Software-Engineering-Project/blob/main/"
        "23071063-seeding.db"
    )

    repaired, changed = repair_metadata_url(original)

    assert changed is True
    assert repaired == (
        "https://raw.githubusercontent.com/Xinia400/"
        "Applied-Software-Engineering-Project/main/"
        "23071063-seeding.db"
    )


def test_repair_standard_github_blob_url():
    original = (
        "https://github.com/example/repository/blob/main/"
        "database.db"
    )

    repaired, changed = repair_metadata_url(original)

    assert changed is True
    assert repaired == (
        "https://raw.githubusercontent.com/example/repository/"
        "main/database.db"
    )


def test_split_multiple_base_data_locations():
    locations = split_base_data_locations(
        "https://one.example/data; https://two.example/data"
    )

    assert locations == [
        "https://one.example/data",
        "https://two.example/data",
    ]


def test_identify_base_data_providers():
    assert identify_base_data_provider(
        "https://faubox.rrze.uni-erlangen.de/getlink/example"
    ) == "FAUBOX"

    assert identify_base_data_provider(
        "https://drive.google.com/file/d/example/view"
    ) == "GOOGLE_DRIVE"

    assert identify_base_data_provider(
        "https://github.com/example/repository/tree/main/data"
    ) == "GITHUB"
