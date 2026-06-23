from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.classification.deduplication_resolution import (
    resolve_deduplicated_analysis,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a provenance-preserving deduplicated "
            "analysis corpus from the staging database."
        )
    )
    parser.add_argument(
        "--staging-db",
        required=True,
        help="Path to the writable staging SQLite database.",
    )
    parser.add_argument(
        "--summary-output",
        required=True,
        help="Path for the JSON deduplication summary.",
    )
    args = parser.parse_args()

    summary = resolve_deduplicated_analysis(
        Path(args.staging_db)
    )

    output_path = Path(args.summary_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
