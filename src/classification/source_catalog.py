from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from pathlib import Path


DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
CHUNK_SIZE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class SourceDatabaseFile:
    """A locally available metadata database ready for staging import."""

    source_student_id: str
    source_scope: str
    storage_kind: str
    local_path: str
    source_filename: str
    source_file_size_bytes: int
    source_sha256: str


def sha256_file(path: Path) -> str:
    """Return the SHA-256 checksum of a file without loading it into memory."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        while chunk := handle.read(CHUNK_SIZE_BYTES):
            digest.update(chunk)

    return digest.hexdigest()


def extract_student_id(path: Path) -> str:
    """Extract the leading numeric student ID from a downloaded database name."""
    prefix = path.name.split("_", maxsplit=1)[0]
    prefix = prefix.split("-", maxsplit=1)[0]

    if not prefix.isdigit():
        raise ValueError(
            f"Could not determine student ID from filename: {path.name}"
        )

    return prefix


def discover_database_files(
    directory: Path,
    *,
    source_scope: str,
    storage_kind: str,
) -> list[SourceDatabaseFile]:
    """Discover real database files while ignoring SQLite WAL/SHM sidecars."""
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")

    records: list[SourceDatabaseFile] = []

    for path in sorted(directory.iterdir()):
        if not path.is_file():
            continue

        if path.suffix.lower() not in DATABASE_SUFFIXES:
            continue

        student_id = extract_student_id(path)

        records.append(
            SourceDatabaseFile(
                source_student_id=student_id,
                source_scope=source_scope,
                storage_kind=storage_kind,
                local_path=str(path),
                source_filename=path.name,
                source_file_size_bytes=path.stat().st_size,
                source_sha256=sha256_file(path),
            )
        )

    return records


def build_source_catalog(
    *,
    own_database: Path,
    direct_directory: Path,
    lfs_directory: Path,
) -> list[SourceDatabaseFile]:
    """Build the complete 44-database catalog with unique student IDs."""
    if not own_database.exists():
        raise FileNotFoundError(f"Own database not found: {own_database}")

    own_student_id = extract_student_id(own_database)

    records = [
        SourceDatabaseFile(
            source_student_id=own_student_id,
            source_scope="MY_CORE",
            storage_kind="MY_CORE_ROOT",
            local_path=str(own_database),
            source_filename=own_database.name,
            source_file_size_bytes=own_database.stat().st_size,
            source_sha256=sha256_file(own_database),
        ),
        *discover_database_files(
            direct_directory,
            source_scope="PEER_SHARED",
            storage_kind="PEER_DIRECT",
        ),
        *discover_database_files(
            lfs_directory,
            source_scope="PEER_SHARED",
            storage_kind="PEER_LFS",
        ),
    ]

    student_ids = [record.source_student_id for record in records]

    if len(student_ids) != len(set(student_ids)):
        duplicates = sorted(
            {
                student_id
                for student_id in student_ids
                if student_ids.count(student_id) > 1
            }
        )
        raise ValueError(
            "Duplicate student IDs found in source catalog: "
            + ", ".join(duplicates)
        )

    return sorted(records, key=lambda record: int(record.source_student_id))


def records_to_dicts(
    records: list[SourceDatabaseFile],
) -> list[dict[str, object]]:
    return [asdict(record) for record in records]
