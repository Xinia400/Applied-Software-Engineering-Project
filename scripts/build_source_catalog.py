from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.classification.source_catalog import (
    build_source_catalog,
    records_to_dicts,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the local metadata-database source catalog."
    )
    parser.add_argument("--own-db", required=True)
    parser.add_argument("--direct-dir", required=True)
    parser.add_argument("--lfs-dir", required=True)
    parser.add_argument("--private-output", required=True)
    parser.add_argument("--summary-output", required=True)
    args = parser.parse_args()

    records = build_source_catalog(
        own_database=Path(args.own_db),
        direct_directory=Path(args.direct_dir),
        lfs_directory=Path(args.lfs_dir),
    )

    private_output = Path(args.private_output)
    summary_output = Path(args.summary_output)

    private_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)

    private_output.write_text(
        json.dumps(records_to_dicts(records), indent=2) + "\n",
        encoding="utf-8",
    )

    storage_counts = Counter(record.storage_kind for record in records)
    scope_counts = Counter(record.source_scope for record in records)

    summary = {
        "total_source_databases": len(records),
        "source_scope_counts": dict(sorted(scope_counts.items())),
        "storage_kind_counts": dict(sorted(storage_counts.items())),
        "total_source_bytes": sum(
            record.source_file_size_bytes for record in records
        ),
        "total_source_mib": round(
            sum(record.source_file_size_bytes for record in records)
            / 1024
            / 1024,
            2,
        ),
        "status": "SOURCE_CATALOG_CREATED",
    }

    summary_output.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
