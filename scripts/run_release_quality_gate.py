from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.automation.release_quality_gate import (
    run_quality_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Read-only release quality gate for the "
            "SQ26 classification delivery."
        )
    )
    parser.add_argument(
        "--database",
        default="23071063-sq26-classification.db",
    )
    parser.add_argument(
        "--drift-report",
        default="reports/drift_report.json",
    )
    parser.add_argument(
        "--require-drift-report",
        action="store_true",
    )
    parser.add_argument(
        "--report-output",
        default="reports/release_quality_gate.json",
    )
    args = parser.parse_args()

    report = run_quality_gate(
        database_path=Path(args.database),
        drift_report_path=Path(args.drift_report),
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
