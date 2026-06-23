from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.automation.drift_monitor import run_drift_monitor


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only provenance drift monitor for the "
            "SQ26 classification delivery."
        )
    )
    parser.add_argument(
        "--database",
        default="23071063-sq26-classification.db",
    )
    parser.add_argument(
        "--raw-data-root",
        default="data/raw",
    )
    parser.add_argument(
        "--snapshot-dir",
        default="data/private/drift_monitor",
    )
    parser.add_argument(
        "--report-output",
        default="reports/drift_report.json",
    )
    args = parser.parse_args()

    report = run_drift_monitor(
        database_path=Path(args.database),
        raw_data_root=Path(args.raw_data_root),
        snapshot_dir=Path(args.snapshot_dir),
        report_path=Path(args.report_output),
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))
    print()
    print(
        "Read-only monitor completed. "
        "No reclassification was performed."
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
