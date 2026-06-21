from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from src.classification.schema_inventory import profile_many_databases


DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}


def direct_database_sources(
    directory: Path,
) -> list[tuple[Path, str, str]]:
    """Return only actual SQLite database files, excluding WAL/SHM sidecars."""
    sources = []

    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue

        if path.suffix.lower() not in DATABASE_SUFFIXES:
            continue

        student_id = path.name.split("_", maxsplit=1)[0]

        if student_id.isdigit():
            sources.append((path, student_id, "PEER_SHARED"))

    return sources


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a read-only schema inventory of metadata databases."
    )
    parser.add_argument("--own-db", required=True)
    parser.add_argument("--direct-dir", required=True)
    parser.add_argument("--lfs-dir", required=True)
    parser.add_argument("--private-output", required=True)
    parser.add_argument("--summary-output", required=True)
    args = parser.parse_args()

    own_db = Path(args.own_db)
    direct_dir = Path(args.direct_dir)
    lfs_dir = Path(args.lfs_dir)

    if not own_db.exists():
        raise FileNotFoundError(f"Own database not found: {own_db}")

    if not direct_dir.exists():
        raise FileNotFoundError(f"Direct peer folder not found: {direct_dir}")

    if not lfs_dir.exists():
        raise FileNotFoundError(f"LFS peer folder not found: {lfs_dir}")

    sources = [
        (own_db, "23071063", "MY_CORE"),
        *direct_database_sources(direct_dir),
        *direct_database_sources(lfs_dir),
    ]

    student_ids = [student_id for _, student_id, _ in sources]

    if len(student_ids) != len(set(student_ids)):
        raise ValueError(
            "Duplicate student IDs detected across database source folders."
        )

    profiles = profile_many_databases(sources)

    private_output = Path(args.private_output)
    summary_output = Path(args.summary_output)

    private_output.parent.mkdir(parents=True, exist_ok=True)
    summary_output.parent.mkdir(parents=True, exist_ok=True)

    private_output.write_text(
        json.dumps(profiles, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    profile_count = len(profiles)
    healthy_count = sum(
        profile["quick_check"] == "ok"
        and not profile["error_message"]
        for profile in profiles
    )

    table_signature_counts = Counter(
        tuple(
            sorted(
                table["normalized_table_name"]
                for table in profile["tables"]
            )
        )
        for profile in profiles
        if profile["tables"]
    )

    summary = {
        "databases_profiled": profile_count,
        "healthy_sqlite_databases": healthy_count,
        "database_profiles_with_errors": profile_count - healthy_count,
        "schema_signature_counts": {
            " | ".join(signature): count
            for signature, count in sorted(
                table_signature_counts.items(),
                key=lambda item: (-item[1], item[0]),
            )
        },
        "status": "SCHEMA_INVENTORY_COMPLETED",
    }

    summary_output.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
