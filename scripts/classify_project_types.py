from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.classification.project_type_classifier import (
    classify_project_types,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Classify projects by QDA and primary-data evidence."
    )
    parser.add_argument("--staging-db", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Replace prior project-type classifications.",
    )
    args = parser.parse_args()

    summary = classify_project_types(
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
