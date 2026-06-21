from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from src.classification.lfs_downloader import (
    LfsObjectSpec,
    create_lfs_session,
    download_lfs_object,
)


def load_specs(targets_path: Path) -> list[LfsObjectSpec]:
    if not targets_path.exists():
        raise FileNotFoundError(f"LFS target manifest not found: {targets_path}")

    payload = json.loads(targets_path.read_text(encoding="utf-8"))

    if not isinstance(payload, list):
        raise ValueError("LFS target manifest must contain a JSON list.")

    required_fields = {
        "student_id",
        "owner",
        "repository",
        "filename",
        "sha256_oid",
        "expected_size_bytes",
    }

    specs: list[LfsObjectSpec] = []

    for item in payload:
        missing = required_fields.difference(item)
        if missing:
            raise ValueError(
                "LFS target is missing fields: "
                + ", ".join(sorted(missing))
            )

        specs.append(
            LfsObjectSpec(
                student_id=str(item["student_id"]),
                owner=str(item["owner"]),
                repository=str(item["repository"]),
                filename=str(item["filename"]),
                sha256_oid=str(item["sha256_oid"]),
                expected_size_bytes=int(item["expected_size_bytes"]),
            )
        )

    return specs


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Download and verify Git LFS-backed peer metadata databases."
    )
    parser.add_argument("--targets", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--private-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument(
        "--student-id",
        action="append",
        default=[],
        help="Download only this student ID. May be supplied multiple times.",
    )
    args = parser.parse_args()

    specs = load_specs(Path(args.targets))

    if args.student_id:
        requested_ids = set(args.student_id)
        specs = [
            spec for spec in specs
            if spec.student_id in requested_ids
        ]

        if not specs:
            raise ValueError("No LFS targets match the requested student ID(s).")

    output_dir = Path(args.output_dir)
    results = []

    with create_lfs_session() as session:
        for spec in specs:
            expected_mib = spec.expected_size_bytes / 1024 / 1024

            print(
                f"Downloading student {spec.student_id}: "
                f"{spec.filename} ({expected_mib:.2f} MiB)"
            )

            result = download_lfs_object(
                session=session,
                spec=spec,
                output_directory=output_dir,
            )
            results.append(result)

            print(
                f"Result: {result.status} | "
                f"{result.actual_size_bytes} bytes"
            )

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
        "lfs_objects_attempted": len(results),
        "downloaded_verified": status_counts["DOWNLOADED_VERIFIED"],
        "already_verified": status_counts["ALREADY_VERIFIED"],
        "size_mismatch": status_counts["SIZE_MISMATCH"],
        "sha256_mismatch": status_counts["SHA256_MISMATCH"],
        "download_error": status_counts["DOWNLOAD_ERROR"],
        "total_expected_bytes": sum(
            result.expected_size_bytes for result in results
        ),
        "total_actual_bytes": sum(
            result.actual_size_bytes for result in results
        ),
        "status": "LFS_DOWNLOAD_COMPLETED",
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
