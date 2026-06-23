from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.automation.deduplication_drift_monitor import (
    run_deduplication_drift_monitor,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Monitor staging-corpus and duplicate-resolution drift."
        )
    )
    parser.add_argument("--staging-db", required=True)
    parser.add_argument("--snapshot-dir", required=True)
    parser.add_argument("--report-output", required=True)
    args = parser.parse_args()

    report = run_deduplication_drift_monitor(
        staging_database_path=Path(args.staging_db),
        snapshot_dir=Path(args.snapshot_dir),
        report_path=Path(args.report_output),
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
