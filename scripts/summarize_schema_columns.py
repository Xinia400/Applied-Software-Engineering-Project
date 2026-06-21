from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


CORE_TABLES = {
    "projects",
    "files",
    "keywords",
    "licenses",
    "person_role",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Summarize column compatibility across profiled SQLite databases."
    )
    parser.add_argument("--inventory", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    inventory_path = Path(args.inventory)
    output_path = Path(args.output)

    profiles = json.loads(inventory_path.read_text(encoding="utf-8"))

    table_database_counts: Counter[str] = Counter()
    column_counts: dict[str, Counter[str]] = defaultdict(Counter)
    schema_signatures: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)
    primary_key_signatures: dict[str, Counter[tuple[str, ...]]] = defaultdict(Counter)

    for profile in profiles:
        for table in profile.get("tables", []):
            table_name = table["normalized_table_name"]

            if table_name not in CORE_TABLES:
                continue

            table_database_counts[table_name] += 1

            normalized_columns = tuple(
                column.strip().lower()
                for column in table.get("columns", [])
            )

            normalized_primary_keys = tuple(
                column.strip().lower()
                for column in table.get("primary_key_columns", [])
            )

            schema_signatures[table_name][normalized_columns] += 1
            primary_key_signatures[table_name][normalized_primary_keys] += 1

            for column in normalized_columns:
                column_counts[table_name][column] += 1

    summary = {
        "databases_profiled": len(profiles),
        "core_tables": {},
        "status": "COLUMN_COMPATIBILITY_SUMMARY_COMPLETED",
    }

    for table_name in sorted(CORE_TABLES):
        present_in = table_database_counts[table_name]

        summary["core_tables"][table_name] = {
            "present_in_databases": present_in,
            "missing_from_databases": len(profiles) - present_in,
            "column_frequency": dict(
                sorted(
                    column_counts[table_name].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ),
            "distinct_column_layouts": [
                {
                    "count": count,
                    "columns": list(columns),
                }
                for columns, count in sorted(
                    schema_signatures[table_name].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
            "primary_key_layouts": [
                {
                    "count": count,
                    "primary_key_columns": list(columns),
                }
                for columns, count in sorted(
                    primary_key_signatures[table_name].items(),
                    key=lambda item: (-item[1], item[0]),
                )
            ],
        }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
