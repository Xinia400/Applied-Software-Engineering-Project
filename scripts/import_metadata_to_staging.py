from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from src.classification.source_catalog import SourceDatabaseFile
from src.classification.staging_importer import (
    import_source_database,
    reset_staging_import_data,
)
from src.classification.staging_schema import (
    initialize_staging_database,
)


def load_catalog(path: Path) -> list[SourceDatabaseFile]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    return [
        SourceDatabaseFile(
            source_student_id=str(item["source_student_id"]),
            source_scope=str(item["source_scope"]),
            storage_kind=str(item["storage_kind"]),
            local_path=str(item["local_path"]),
            source_filename=str(item["source_filename"]),
            source_file_size_bytes=int(
                item["source_file_size_bytes"]
            ),
            source_sha256=str(item["source_sha256"]),
        )
        for item in payload
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import verified databases into QDArchive-X staging."
    )
    parser.add_argument("--catalog", required=True)
    parser.add_argument("--staging-db", required=True)
    parser.add_argument("--private-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument(
        "--student-id",
        action="append",
        default=[],
    )
    parser.add_argument(
        "--reset",
        action="store_true",
    )
    args = parser.parse_args()

    staging_path = Path(args.staging_db)
    initialize_staging_database(staging_path)

    if args.reset:
        reset_staging_import_data(staging_path)

    sources = load_catalog(Path(args.catalog))

    if args.student_id:
        requested = set(args.student_id)
        sources = [
            source
            for source in sources
            if source.source_student_id in requested
        ]

    if not sources:
        raise ValueError("No source databases selected.")

    results = []

    for index, source in enumerate(sources, start=1):
        print(
            f"[{index}/{len(sources)}] "
            f"Importing {source.source_student_id}"
        )

        result = import_source_database(staging_path, source)
        results.append(result)

        print(
            f"  -> {result.import_status} | "
            f"projects={result.projects_imported} | "
            f"files={result.files_imported}"
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

    counts = Counter(
        result.import_status
        for result in results
    )

    summary = {
        "sources_attempted": len(results),
        "completed": counts["COMPLETED"],
        "failed": counts["FAILED"],
        "projects_imported": sum(
            result.projects_imported
            for result in results
        ),
        "files_imported": sum(
            result.files_imported
            for result in results
        ),
        "keywords_imported": sum(
            result.keywords_imported
            for result in results
        ),
        "licenses_imported": sum(
            result.licenses_imported
            for result in results
        ),
        "person_roles_imported": sum(
            result.person_roles_imported
            for result in results
        ),
        "status": "STAGING_IMPORT_COMPLETED",
    }

    summary_output.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print("\nSummary:")
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
