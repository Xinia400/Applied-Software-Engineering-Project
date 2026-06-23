from __future__ import annotations

import argparse
from pathlib import Path

from src.classification.staging_schema import (
    initialize_staging_database,
    list_user_tables,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Initialize the QDArchive-X canonical staging database."
    )
    parser.add_argument("--database", required=True)
    args = parser.parse_args()

    database_path = Path(args.database)

    initialize_staging_database(database_path)

    print(f"Staging database created: {database_path}")
    print("\nTables:")
    for table_name in list_user_tables(database_path):
        print(f"- {table_name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
