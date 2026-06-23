from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.automation.deduplication_quality_gate import (
    run_deduplication_quality_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate duplicate-resolution integrity, auditability, "
            "and drift-monitor consistency."
        )
    )
    parser.add_argument("--staging-db", required=True)
    parser.add_argument("--report-output", required=True)
    parser.add_argument("--drift-report")
    parser.add_argument(
        "--require-drift-report",
        action="store_true",
    )
    args = parser.parse_args()

    report = run_deduplication_quality_gate(
        staging_database_path=Path(args.staging_db),
        drift_report_path=(
            Path(args.drift_report)
            if args.drift_report
            else None
        ),
        require_drift_report=args.require_drift_report,
    )

    output_path = Path(args.report_output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(report, indent=2, ensure_ascii=False))

    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
