from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from src.classification.project_type_rules import (
    AMBIGUOUS_QDA_EXTENSIONS,
    HIGH_CONFIDENCE_QDA_EXTENSIONS,
    extension_from_filename,
    is_primary_data_extension,
    matched_qda_terms,
    normalize_context,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit project-type evidence without modifying staging."
    )
    parser.add_argument("--staging-db", required=True)
    parser.add_argument("--summary-output", required=True)
    parser.add_argument("--samples-output", required=True)
    args = parser.parse_args()

    connection = sqlite3.connect(Path(args.staging_db))

    project_evidence = defaultdict(
        lambda: {
            "has_file": False,
            "high_qda_extensions": set(),
            "ambiguous_extensions": set(),
            "ambiguous_filenames": [],
            "primary_extensions": set(),
        }
    )

    try:
        for project_uid, file_name in connection.execute(
            """
            SELECT project_uid, file_name
            FROM stg_files
            WHERE project_uid IS NOT NULL
            """
        ):
            evidence = project_evidence[project_uid]
            evidence["has_file"] = True

            suffix = extension_from_filename(file_name)

            if suffix in HIGH_CONFIDENCE_QDA_EXTENSIONS:
                evidence["high_qda_extensions"].add(suffix)

            if suffix in AMBIGUOUS_QDA_EXTENSIONS:
                evidence["ambiguous_extensions"].add(suffix)

                if len(evidence["ambiguous_filenames"]) < 5:
                    evidence["ambiguous_filenames"].append(
                        str(file_name or "")
                    )

            if is_primary_data_extension(suffix):
                evidence["primary_extensions"].add(suffix)

        ambiguous_project_ids = [
            project_uid
            for project_uid, evidence in project_evidence.items()
            if evidence["ambiguous_extensions"]
        ]

        project_metadata = {}

        for start in range(0, len(ambiguous_project_ids), 900):
            batch = ambiguous_project_ids[start:start + 900]
            placeholders = ",".join("?" for _ in batch)

            query = f"""
                SELECT
                    project_uid,
                    repository_id,
                    title,
                    description
                FROM stg_projects
                WHERE project_uid IN ({placeholders})
            """

            for row in connection.execute(query, batch):
                project_metadata[row[0]] = row[1:]

        strong_qda_projects = 0
        contextual_qda_projects = 0
        ambiguous_unconfirmed = 0
        qd_projects = 0
        other_file_projects = 0
        high_extension_counts = Counter()
        contextual_extension_counts = Counter()
        unconfirmed_extension_counts = Counter()
        sample_rows = []

        for project_uid, evidence in project_evidence.items():
            if evidence["high_qda_extensions"]:
                strong_qda_projects += 1

                for suffix in evidence["high_qda_extensions"]:
                    high_extension_counts[suffix] += 1

                continue

            if evidence["ambiguous_extensions"]:
                repository_id, title, description = project_metadata.get(
                    project_uid,
                    ("", "", ""),
                )

                context = normalize_context(
                    [
                        title,
                        description,
                        *evidence["ambiguous_filenames"],
                    ]
                )

                terms = matched_qda_terms(context)

                if terms:
                    contextual_qda_projects += 1

                    for suffix in evidence["ambiguous_extensions"]:
                        contextual_extension_counts[suffix] += 1

                    continue

                ambiguous_unconfirmed += 1

                for suffix in evidence["ambiguous_extensions"]:
                    unconfirmed_extension_counts[suffix] += 1

                if len(sample_rows) < 100:
                    sample_rows.append(
                        {
                            "project_uid": project_uid,
                            "repository_id": repository_id or "",
                            "title": title or "",
                            "ambiguous_extensions": sorted(
                                evidence["ambiguous_extensions"]
                            ),
                            "sample_filenames": evidence[
                                "ambiguous_filenames"
                            ],
                        }
                    )

            if evidence["primary_extensions"]:
                qd_projects += 1
            elif evidence["has_file"]:
                other_file_projects += 1

        total_projects = connection.execute(
            "SELECT COUNT(*) FROM stg_projects"
        ).fetchone()[0]

        no_file_projects = total_projects - len(project_evidence)

        summary = {
            "total_projects": total_projects,
            "projects_with_file_records": len(project_evidence),
            "no_file_projects": no_file_projects,
            "high_confidence_qda_projects": strong_qda_projects,
            "context_validated_ambiguous_qda_projects": (
                contextual_qda_projects
            ),
            "ambiguous_qda_without_context": ambiguous_unconfirmed,
            "primary_data_projects_without_qda_evidence": qd_projects,
            "projects_with_other_file_evidence": other_file_projects,
            "high_confidence_qda_extensions_by_project": dict(
                sorted(high_extension_counts.items())
            ),
            "context_validated_ambiguous_extensions_by_project": dict(
                sorted(contextual_extension_counts.items())
            ),
            "unconfirmed_ambiguous_extensions_by_project": dict(
                sorted(unconfirmed_extension_counts.items())
            ),
        }

        summary_path = Path(args.summary_output)
        samples_path = Path(args.samples_output)

        summary_path.parent.mkdir(parents=True, exist_ok=True)
        samples_path.parent.mkdir(parents=True, exist_ok=True)

        summary_path.write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )

        samples_path.write_text(
            json.dumps(sample_rows, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        print(json.dumps(summary, indent=2))
        print(f"\nSaved summary: {summary_path}")
        print(f"Saved ambiguous samples: {samples_path}")

    finally:
        connection.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
