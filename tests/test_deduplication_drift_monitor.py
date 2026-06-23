from __future__ import annotations

from src.automation.deduplication_drift_monitor import (
    classify_deduplication_drift,
)


def test_deduplication_drift_is_unchanged_for_same_snapshot() -> None:
    snapshot = {
        "input_fingerprint": "same-input",
        "resolution_version": "deduplication-resolution-v2",
        "decision_fingerprint": "same-decisions",
    }

    result = classify_deduplication_drift(snapshot, snapshot)

    assert result["status"] == "UNCHANGED"
    assert result["rerun_required"] is False
    assert result["reasons"] == ["UNCHANGED"]


def test_deduplication_drift_requires_rerun_when_input_changes() -> None:
    previous = {
        "input_fingerprint": "old-input",
        "resolution_version": "deduplication-resolution-v2",
        "decision_fingerprint": "same-decisions",
    }

    current = {
        "input_fingerprint": "new-input",
        "resolution_version": "deduplication-resolution-v2",
        "decision_fingerprint": "same-decisions",
    }

    result = classify_deduplication_drift(current, previous)

    assert result["status"] == "DEDUPLICATION_RERUN_REQUIRED"
    assert result["rerun_required"] is True
    assert result["reasons"] == ["STAGING_INPUT_CHANGED"]
