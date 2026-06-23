from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.classification.source_registry import (
    load_source_registry,
    write_registry_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build a provenance-aware student source registry."
    )
    parser.add_argument("--input", required=True)
    parser.add_argument("--own-student-id", required=True)
    parser.add_argument("--private-output", required=True)
    parser.add_argument("--summary-output", required=True)
    args = parser.parse_args()

    records = load_source_registry(
        input_xlsx=Path(args.input),
        own_student_id=args.own_student_id,
    )

    summary = write_registry_outputs(
        records=records,
        private_csv_path=Path(args.private_output),
        summary_json_path=Path(args.summary_output),
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
