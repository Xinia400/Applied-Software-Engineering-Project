from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import requests


SQLITE_SIGNATURE = b"SQLite format 3\x00"

REQUIRED_REGISTRY_COLUMNS = {
    "source_student_id",
    "source_scope",
    "metadata_url_original",
    "metadata_url_canonical",
    "metadata_url_was_repaired",
}


@dataclass(frozen=True)
class MetadataLinkValidation:
    """Result of a small, non-destructive metadata-link probe."""

    source_student_id: str
    source_scope: str
    metadata_url_original: str
    metadata_url_canonical: str
    metadata_url_was_repaired: bool

    validated_at_utc: str
    access_status: str
    http_status: int | None
    final_url: str
    content_type: str
    reported_content_length: int | None

    bytes_sampled: int
    sqlite_signature_detected: bool
    error_message: str


def utc_now_iso() -> str:
    """Return a stable UTC timestamp for provenance records."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_optional_int(value: str | None) -> int | None:
    """Parse integer HTTP headers without raising on missing values."""
    if value is None:
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def create_http_session() -> requests.Session:
    """Create a polite, reusable HTTP session."""
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": (
                "QDArchive-X/0.1 "
                "(academic metadata validation; contact: local-project)"
            ),
            "Accept": "*/*",
        }
    )
    return session


def validate_metadata_url(
    session: requests.Session,
    *,
    source_student_id: str,
    source_scope: str,
    metadata_url_original: str,
    metadata_url_canonical: str,
    metadata_url_was_repaired: bool,
    timeout_seconds: float = 20.0,
    sample_bytes: int = 4096,
) -> MetadataLinkValidation:
    """
    Probe a metadata URL without downloading the entire database.

    A Range request is attempted, then only the first received chunk is read.
    The result is accepted as SQLite only when its bytes start with the
    official SQLite file signature.
    """
    timestamp = utc_now_iso()

    if not metadata_url_canonical.strip():
        return MetadataLinkValidation(
            source_student_id=source_student_id,
            source_scope=source_scope,
            metadata_url_original=metadata_url_original,
            metadata_url_canonical=metadata_url_canonical,
            metadata_url_was_repaired=metadata_url_was_repaired,
            validated_at_utc=timestamp,
            access_status="MISSING_URL",
            http_status=None,
            final_url="",
            content_type="",
            reported_content_length=None,
            bytes_sampled=0,
            sqlite_signature_detected=False,
            error_message="No canonical metadata URL was provided.",
        )

    response: requests.Response | None = None

    try:
        response = session.get(
            metadata_url_canonical,
            headers={"Range": f"bytes=0-{sample_bytes - 1}"},
            timeout=(8.0, timeout_seconds),
            allow_redirects=True,
            stream=True,
        )

        http_status = response.status_code
        final_url = response.url
        content_type = response.headers.get("Content-Type", "")
        content_length = as_optional_int(response.headers.get("Content-Length"))

        if not 200 <= http_status < 300:
            return MetadataLinkValidation(
                source_student_id=source_student_id,
                source_scope=source_scope,
                metadata_url_original=metadata_url_original,
                metadata_url_canonical=metadata_url_canonical,
                metadata_url_was_repaired=metadata_url_was_repaired,
                validated_at_utc=timestamp,
                access_status="HTTP_ERROR",
                http_status=http_status,
                final_url=final_url,
                content_type=content_type,
                reported_content_length=content_length,
                bytes_sampled=0,
                sqlite_signature_detected=False,
                error_message=f"Server returned HTTP {http_status}.",
            )

        sample = b""
        for chunk in response.iter_content(chunk_size=sample_bytes):
            if chunk:
                sample = chunk[:sample_bytes]
                break

        sqlite_signature_detected = sample.startswith(SQLITE_SIGNATURE)

        return MetadataLinkValidation(
            source_student_id=source_student_id,
            source_scope=source_scope,
            metadata_url_original=metadata_url_original,
            metadata_url_canonical=metadata_url_canonical,
            metadata_url_was_repaired=metadata_url_was_repaired,
            validated_at_utc=timestamp,
            access_status=(
                "ACCESSIBLE_SQLITE"
                if sqlite_signature_detected
                else "ACCESSIBLE_NON_SQLITE"
            ),
            http_status=http_status,
            final_url=final_url,
            content_type=content_type,
            reported_content_length=content_length,
            bytes_sampled=len(sample),
            sqlite_signature_detected=sqlite_signature_detected,
            error_message=(
                ""
                if sqlite_signature_detected
                else "Response did not start with the SQLite signature."
            ),
        )

    except requests.RequestException as error:
        return MetadataLinkValidation(
            source_student_id=source_student_id,
            source_scope=source_scope,
            metadata_url_original=metadata_url_original,
            metadata_url_canonical=metadata_url_canonical,
            metadata_url_was_repaired=metadata_url_was_repaired,
            validated_at_utc=timestamp,
            access_status="REQUEST_ERROR",
            http_status=None,
            final_url="",
            content_type="",
            reported_content_length=None,
            bytes_sampled=0,
            sqlite_signature_detected=False,
            error_message=f"{type(error).__name__}: {error}",
        )

    finally:
        if response is not None:
            response.close()


def load_registry_frame(registry_csv_path: Path) -> pd.DataFrame:
    """Load the private source registry and validate its required fields."""
    if not registry_csv_path.exists():
        raise FileNotFoundError(
            f"Private source registry was not found: {registry_csv_path}"
        )

    frame = pd.read_csv(
        registry_csv_path,
        dtype=str,
        keep_default_na=False,
    )

    missing_columns = REQUIRED_REGISTRY_COLUMNS.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            "Registry is missing required columns: "
            + ", ".join(sorted(missing_columns))
        )

    return frame


def validate_registry_links(
    registry_csv_path: Path,
    *,
    limit: int | None = None,
    timeout_seconds: float = 20.0,
    sample_bytes: int = 4096,
    sleep_seconds: float = 0.15,
) -> list[MetadataLinkValidation]:
    """Validate canonical metadata URLs from the private source registry."""
    frame = load_registry_frame(registry_csv_path)

    if limit is not None:
        if limit <= 0:
            raise ValueError("--limit must be greater than zero.")
        frame = frame.head(limit)

    results: list[MetadataLinkValidation] = []
    session = create_http_session()

    try:
        for _, row in frame.iterrows():
            result = validate_metadata_url(
                session,
                source_student_id=row["source_student_id"],
                source_scope=row["source_scope"],
                metadata_url_original=row["metadata_url_original"],
                metadata_url_canonical=row["metadata_url_canonical"],
                metadata_url_was_repaired=(
                    row["metadata_url_was_repaired"].strip().lower() == "true"
                ),
                timeout_seconds=timeout_seconds,
                sample_bytes=sample_bytes,
            )
            results.append(result)

            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
    finally:
        session.close()

    return results


def write_validation_outputs(
    validations: list[MetadataLinkValidation],
    *,
    private_csv_path: Path,
    summary_json_path: Path,
) -> dict[str, Any]:
    """Write detailed private validation data and a safe aggregate summary."""
    private_csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame([asdict(item) for item in validations])
    frame.to_csv(private_csv_path, index=False)

    status_counts = Counter(item.access_status for item in validations)
    core_status_counts = Counter(
        item.access_status
        for item in validations
        if item.source_scope == "MY_CORE"
    )
    peer_status_counts = Counter(
        item.access_status
        for item in validations
        if item.source_scope == "PEER_SHARED"
    )

    summary = {
        "total_links_checked": len(validations),
        "accessible_sqlite_links": status_counts["ACCESSIBLE_SQLITE"],
        "accessible_non_sqlite_links": status_counts["ACCESSIBLE_NON_SQLITE"],
        "http_error_links": status_counts["HTTP_ERROR"],
        "request_error_links": status_counts["REQUEST_ERROR"],
        "missing_url_links": status_counts["MISSING_URL"],
        "my_core_status_counts": dict(sorted(core_status_counts.items())),
        "peer_shared_status_counts": dict(sorted(peer_status_counts.items())),
        "status": "METADATA_LINK_VALIDATION_COMPLETED",
    }

    summary_json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return summary
