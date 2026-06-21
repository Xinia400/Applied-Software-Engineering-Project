from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.classification.metadata_link_validator import (
    validate_registry_links,
    write_validation_outputs,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate metadata database links from the private registry."
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--private-output", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--sample-bytes", type=int, default=4096)
    parser.add_argument("--sleep-seconds", type=float, default=0.15)
    args = parser.parse_args()

    validations = validate_registry_links(
        registry_csv_path=Path(args.registry),
        limit=args.limit,
        timeout_seconds=args.timeout_seconds,
        sample_bytes=args.sample_bytes,
        sleep_seconds=args.sleep_seconds,
    )

    summary = write_validation_outputs(
        validations,
        private_csv_path=Path(args.private_output),
        summary_json_path=Path(args.summary_output),
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
