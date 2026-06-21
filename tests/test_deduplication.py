from src.classification.deduplication import (
    canonical_doi,
    eligible_normalized_title,
    is_file_like_title,
)


def test_canonical_doi_extracts_and_normalizes() -> None:
    assert canonical_doi(
        "doi:10.17026/DANS-ZCC-ZDHP."
    ) == "10.17026/dans-zcc-zdhp"


def test_non_generic_title_is_eligible() -> None:
    assert eligible_normalized_title(
        "International Criminal Law Charging Document Database"
    ) == "international criminal law charging document database"


def test_filename_title_is_not_eligible() -> None:
    assert is_file_like_title(
        "Interview_Transcript_001.pdf"
    )

    assert eligible_normalized_title(
        "Interview_Transcript_001.pdf"
    ) == ""


def test_generic_title_is_not_eligible() -> None:
    assert eligible_normalized_title("UNKNOWN") == ""
