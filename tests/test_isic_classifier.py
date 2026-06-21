from __future__ import annotations

from src.classification.isic_classifier import (
    classify_context,
    classify_tier2_file_context,
)


def test_project_context_classifies_legal_corpus() -> None:
    result = classify_context(
        """
        International criminal law charging document.
        The defendant submitted an appeal to the ICC.
        """
    )

    assert result is not None
    assert result[0] == "N69"


def test_project_context_classifies_research_corpus() -> None:
    result = classify_context(
        """
        AiREAS citizen sensing examines environmental risk
        and responses survey data for risk governance.
        """
    )

    assert result is not None
    assert result[0] == "N72"


def test_tier2_file_classifies_from_one_legal_term() -> None:
    result = classify_tier2_file_context(
        "The prosecution submitted the brief."
    )

    assert result is not None
    assert result[0] == "N69"
    assert result[1] == "TIER2_FILE_CONTENT_SINGLE_TERM"
    assert result[2] == 0.80


def test_tier2_file_classifies_from_one_research_term() -> None:
    result = classify_tier2_file_context(
        "The AiREAS citizen sensing initiative collected observations."
    )

    assert result is not None
    assert result[0] == "N72"
    assert result[1] in {
        "TIER2_FILE_CONTENT_MULTI_TERM",
        "TIER2_FILE_CONTENT_SINGLE_TERM",
    }


def test_tier2_file_returns_none_without_domain_evidence() -> None:
    result = classify_tier2_file_context(
        "This document contains generic introductory text only."
    )

    assert result is None
