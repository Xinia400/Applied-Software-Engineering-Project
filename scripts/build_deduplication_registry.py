from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.classification.deduplication import (
    build_deduplication_registry,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Create a non-destructive duplicate-cluster registry."
        )
    )
    parser.add_argument("--staging-db", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument(
        "--reset",
        action="store_true",
    )
    args = parser.parse_args()

    summary = build_deduplication_registry(
        Path(args.staging_db),
        reset=args.reset,
    )

    output_path = Path(args.summary_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2))
    print(f"\nSaved: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
