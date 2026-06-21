from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from src.classification.direct_metadata_downloader import (
    DirectDatabaseTarget,
    create_download_session,
    download_direct_database,
    safe_filename_from_url,
)


def load_recovery_overrides(path: Path) -> dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"Override file not found: {path}")

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)

    required = {
        "source_student_id",
        "recovered_metadata_url",
        "recovery_status",
    }
    missing = required.difference(frame.columns)

    if missing:
        raise ValueError(
            "Override file is missing columns: "
            + ", ".join(sorted(missing))
        )

    return {
        row["source_student_id"]: row["recovered_metadata_url"]
        for _, row in frame.iterrows()
        if row["recovery_status"] == "CONFIRMED_SQLITE"
        and row["recovered_metadata_url"].strip()
    }


def build_targets(
    validation_path: Path,
    overrides_path: Path,
) -> list[DirectDatabaseTarget]:
    validation = pd.read_csv(
        validation_path,
        dtype=str,
        keep_default_na=False,
    )

    overrides = load_recovery_overrides(overrides_path)

    targets: list[DirectDatabaseTarget] = []
    seen_ids: set[str] = set()

    for _, row in validation.iterrows():
        student_id = row["source_student_id"]

        if student_id in seen_ids:
            continue

        if row["source_scope"] != "PEER_SHARED":
            continue

        if student_id in overrides:
            url = overrides[student_id]
            url_source = "RECOVERY_OVERRIDE"
        elif row["access_status"] == "ACCESSIBLE_SQLITE":
            url = row["metadata_url_canonical"]
            url_source = "REGISTRY"
        else:
            continue

        targets.append(
            DirectDatabaseTarget(
                student_id=student_id,
                url=url,
                url_source=url_source,
                filename=safe_filename_from_url(
                    url,
                    fallback_name=f"{student_id}-metadata.db",
                ),
            )
        )
        seen_ids.add(student_id)

    return targets


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Download direct peer metadata databases with SQLite validation."
        )
    )
    parser.add_argument("--validation", required=True)
    parser.add_argument("--overrides", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--private-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sleep-seconds", type=float, default=0.10)
    args = parser.parse_args()

    targets = build_targets(
        validation_path=Path(args.validation),
        overrides_path=Path(args.overrides),
    )

    if args.limit is not None:
        if args.limit <= 0:
            raise ValueError("--limit must be greater than zero.")
        targets = targets[: args.limit]

    print(f"Direct peer targets selected: {len(targets)}")

    results = []

    with create_download_session() as session:
        for index, target in enumerate(targets, start=1):
            print(
                f"[{index}/{len(targets)}] Downloading "
                f"{target.student_id} ({target.url_source})"
            )

            result = download_direct_database(
                session=session,
                target=target,
                output_directory=Path(args.output_dir),
            )
            results.append(result)

            print(
                f"  -> {result.status} | "
                f"{result.actual_size_bytes} bytes | "
                f"quick_check={result.sqlite_quick_check}"
            )

            if args.sleep_seconds > 0:
                time.sleep(args.sleep_seconds)

    private_output = Path(args.private_output)
    summary_output = Path(args.summary_output)

    private_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)

    private_output.write_text(
        json.dumps(
            [asdict(result) for result in results],
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )

    status_counts = Counter(result.status for result in results)

    summary = {
        "direct_peer_targets_attempted": len(results),
        "downloaded_verified": status_counts["DOWNLOADED_VERIFIED"],
        "already_verified": status_counts["ALREADY_VERIFIED"],
        "http_error": status_counts["HTTP_ERROR"],
        "size_mismatch": status_counts["SIZE_MISMATCH"],
        "non_sqlite_content": status_counts["NON_SQLITE_CONTENT"],
        "sqlite_check_failed": status_counts["SQLITE_CHECK_FAILED"],
        "download_error": status_counts["DOWNLOAD_ERROR"],
        "total_verified_bytes": sum(
            result.actual_size_bytes
            for result in results
            if result.status in {
                "DOWNLOADED_VERIFIED",
                "ALREADY_VERIFIED",
            }
        ),
        "recovery_override_targets": sum(
            result.url_source == "RECOVERY_OVERRIDE"
            for result in results
        ),
        "status": "DIRECT_METADATA_DOWNLOAD_COMPLETED",
    }

    summary_output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print("\nSummary:")
    print(json.dumps(summary, indent=2, ensure_ascii=False))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
