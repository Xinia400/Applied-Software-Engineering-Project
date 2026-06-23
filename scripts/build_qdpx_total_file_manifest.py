"""Build a reproducible manifest of total internal files in final DANS QDPX archives."""

from __future__ import annotations

import argparse
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


PROJECT_ARCHIVES = {
    "Sensing Risk (bertisum 2020-04-02).qdpx":
        "Sensing Risk (bertisum 2020-04-02).qdpx",
    "International Criminal Law Charging Document Database v7.qdpx":
        "International Criminal Law Charging Document Database v7.qdpx",
    "Prosecution_Appeals_Briefs_V1.qdpx":
        "Prosecution_Appeals_Briefs_V1.qdpx",
    "International_Criminal_Law_Charging_Document_Database_v6.qdpx":
        "International_Criminal_Law_Charging_Document_Database_v6.qdpx",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a manifest of total internal QDPX project files."
    )
    parser.add_argument(
        "--raw-root",
        type=Path,
        default=Path("data/raw/dans"),
        help="Root directory containing downloaded DANS QDPX folders.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("reports/qdpx_total_file_manifest.json"),
        help="Output JSON manifest path.",
    )
    return parser.parse_args()


def find_archive(raw_root: Path, archive_name: str) -> Path:
    matches = [
        path
        for path in raw_root.rglob("*.qdpx")
        if path.is_file() and path.name == archive_name
    ]

    if len(matches) != 1:
        raise RuntimeError(
            f"Expected exactly one archive named {archive_name!r}; "
            f"found {len(matches)}."
        )

    return matches[0]


def count_archive_files(archive_path: Path) -> dict[str, object]:
    with zipfile.ZipFile(archive_path) as archive:
        entries = [
            info
            for info in archive.infolist()
            if not info.is_dir()
            and not info.filename.startswith("__MACOSX/")
            and not Path(info.filename).name.startswith(".")
        ]

    extension_counts = Counter(
        Path(info.filename).suffix.lower() or "[no extension]"
        for info in entries
    )

    qde_count = extension_counts.get(".qde", 0)

    return {
        "archive_path": str(archive_path),
        "total_internal_files": len(entries),
        "non_classified_project_definition_files": qde_count,
        "extension_counts": dict(sorted(extension_counts.items())),
    }


def main() -> None:
    args = parse_args()

    projects = {
        title: count_archive_files(
            find_archive(args.raw_root, archive_name)
        )
        for title, archive_name in PROJECT_ARCHIVES.items()
    }

    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "counting_rule": (
            "Counts all non-directory, non-hidden internal QDPX archive "
            "entries, including QDE project-definition files."
        ),
        "classification_rule": (
            "QDE project-definition files are included in total project "
            "file counts but excluded from primary-file ISIC classification."
        ),
        "projects": projects,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    for title, info in projects.items():
        print(
            f"{title}: total={info['total_internal_files']}, "
            f"qde={info['non_classified_project_definition_files']}"
        )

    print(f"\nSaved: {args.output}")


if __name__ == "__main__":
    main()
