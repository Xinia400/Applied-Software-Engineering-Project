from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import pandas as pd


REQUIRED_COLUMNS = {"id", "meta data", "base data"}

MY_CORE = "MY_CORE"
PEER_SHARED = "PEER_SHARED"
PENDING_VALIDATION = "PENDING_VALIDATION"


@dataclass(frozen=True)
class SourceRegistryRecord:
    """One student-provided acquisition source from Students_repo.xlsx."""

    registry_row: int
    source_student_id: str
    source_scope: str

    metadata_url_original: str
    metadata_url_canonical: str
    metadata_url_was_repaired: bool
    metadata_access_status: str

    base_data_locations: str
    base_data_location_count: int
    base_data_providers: str
    base_data_access_status: str


def clean_text(value: Any) -> str:
    """Convert spreadsheet values into safe stripped strings."""
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def normalize_student_id(value: Any) -> str:
    """Normalize IDs read by Excel, including values such as 23071063.0."""
    student_id = clean_text(value)

    if re.fullmatch(r"\d+\.0", student_id):
        student_id = student_id[:-2]

    if not re.fullmatch(r"\d{6,}", student_id):
        raise ValueError(f"Invalid or missing student ID: {student_id!r}")

    return student_id


def repair_metadata_url(url: str) -> tuple[str, bool]:
    """
    Repair malformed GitHub raw URLs such as:

    https://raw.githubusercontent.com/user/repo/blob/main/file.db

    into:

    https://raw.githubusercontent.com/user/repo/main/file.db
    """
    raw_pattern = re.compile(
        r"^https://raw\.githubusercontent\.com/"
        r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/"
        r"(?P<ref>[^/]+)/(?P<path>.+)$",
        flags=re.IGNORECASE,
    )

    github_blob_pattern = re.compile(
        r"^https://github\.com/"
        r"(?P<owner>[^/]+)/(?P<repo>[^/]+)/blob/"
        r"(?P<ref>[^/]+)/(?P<path>.+)$",
        flags=re.IGNORECASE,
    )

    match = raw_pattern.match(url)
    if match:
        repaired = (
            "https://raw.githubusercontent.com/"
            f"{match.group('owner')}/"
            f"{match.group('repo')}/"
            f"{match.group('ref')}/"
            f"{match.group('path')}"
        )
        return repaired, True

    match = github_blob_pattern.match(url)
    if match:
        repaired = (
            "https://raw.githubusercontent.com/"
            f"{match.group('owner')}/"
            f"{match.group('repo')}/"
            f"{match.group('ref')}/"
            f"{match.group('path')}"
        )
        return repaired, True

    return url, False


def split_base_data_locations(value: str) -> list[str]:
    """Split multiple base-data locations written in one Excel cell."""
    return [item.strip() for item in value.split(";") if item.strip()]


def identify_base_data_provider(location: str) -> str:
    """Identify the provider hosting a base-data location."""
    normalized = location.lower()

    if "faubox.rrze.uni-erlangen.de" in normalized:
        return "FAUBOX"
    if "drive.google.com" in normalized:
        return "GOOGLE_DRIVE"
    if "github.com" in normalized or "raw.githubusercontent.com" in normalized:
        return "GITHUB"
    if normalized.startswith(("https://", "http://")):
        return "WEB"
    if "/" in location or "\\" in location:
        return "LOCAL_OR_RELATIVE_PATH"

    return "UNKNOWN"


def load_source_registry(
    input_xlsx: Path,
    own_student_id: str,
) -> list[SourceRegistryRecord]:
    """Load the student spreadsheet into provenance-aware records."""
    if not input_xlsx.exists():
        raise FileNotFoundError(f"Registry spreadsheet not found: {input_xlsx}")

    frame = pd.read_excel(input_xlsx, dtype=object)
    frame.columns = [str(column).strip().lower() for column in frame.columns]

    missing_columns = REQUIRED_COLUMNS.difference(frame.columns)
    if missing_columns:
        raise ValueError(
            "Missing required spreadsheet columns: "
            + ", ".join(sorted(missing_columns))
        )

    records: list[SourceRegistryRecord] = []
    seen_student_ids: set[str] = set()

    for index, row in frame.iterrows():
        student_id = normalize_student_id(row["id"])

        if student_id in seen_student_ids:
            raise ValueError(f"Duplicate student ID found: {student_id}")
        seen_student_ids.add(student_id)

        original_metadata_url = clean_text(row["meta data"])
        canonical_metadata_url, repaired = repair_metadata_url(
            original_metadata_url
        )

        base_locations = split_base_data_locations(clean_text(row["base data"]))
        providers = sorted(
            {
                identify_base_data_provider(location)
                for location in base_locations
            }
        )

        records.append(
            SourceRegistryRecord(
                registry_row=index + 2,
                source_student_id=student_id,
                source_scope=(
                    MY_CORE if student_id == own_student_id else PEER_SHARED
                ),
                metadata_url_original=original_metadata_url,
                metadata_url_canonical=canonical_metadata_url,
                metadata_url_was_repaired=repaired,
                metadata_access_status=PENDING_VALIDATION,
                base_data_locations=json.dumps(
                    base_locations,
                    ensure_ascii=False,
                ),
                base_data_location_count=len(base_locations),
                base_data_providers=json.dumps(
                    providers,
                    ensure_ascii=False,
                ),
                base_data_access_status=PENDING_VALIDATION,
            )
        )

    core_count = sum(
        record.source_scope == MY_CORE for record in records
    )
    if core_count != 1:
        raise ValueError(
            f"Expected exactly one MY_CORE record for {own_student_id}; "
            f"found {core_count}."
        )

    return records


def write_registry_outputs(
    records: list[SourceRegistryRecord],
    private_csv_path: Path,
    summary_json_path: Path,
) -> dict[str, Any]:
    """Write private detailed registry and safe aggregate summary."""
    private_csv_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)

    frame = pd.DataFrame([asdict(record) for record in records])
    frame.to_csv(private_csv_path, index=False)

    provider_counts: Counter[str] = Counter()
    for record in records:
        provider_counts.update(json.loads(record.base_data_providers))

    summary = {
        "total_registry_entries": len(records),
        "my_core_entries": sum(
            record.source_scope == MY_CORE for record in records
        ),
        "peer_shared_entries": sum(
            record.source_scope == PEER_SHARED for record in records
        ),
        "metadata_urls_repaired": sum(
            record.metadata_url_was_repaired for record in records
        ),
        "records_with_multiple_base_locations": sum(
            record.base_data_location_count > 1 for record in records
        ),
        "base_data_provider_counts": dict(sorted(provider_counts.items())),
        "status": "REGISTRY_CREATED_PENDING_VALIDATION",
    }

    summary_json_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return summary
