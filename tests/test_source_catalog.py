import hashlib

from src.classification.source_catalog import (
    build_source_catalog,
    extract_student_id,
)


def test_extract_student_id_supports_hyphen_and_underscore_names(tmp_path):
    assert extract_student_id(
        tmp_path / "23071063-seeding.db"
    ) == "23071063"

    assert extract_student_id(
        tmp_path / "23025313_23025313-seeding.db"
    ) == "23025313"


def test_build_source_catalog_discovers_databases_and_ignores_sidecars(tmp_path):
    own_database = tmp_path / "23071063-seeding.db"
    direct_directory = tmp_path / "direct"
    lfs_directory = tmp_path / "lfs"

    direct_directory.mkdir()
    lfs_directory.mkdir()

    own_database.write_bytes(b"own database")
    (direct_directory / "23025313_peer.db").write_bytes(
        b"direct database"
    )
    (direct_directory / "23025328_peer.sqlite").write_bytes(
        b"second direct database"
    )

    (lfs_directory / "23726011_large.db").write_bytes(
        b"lfs database"
    )
    (lfs_directory / "23726011_large.db-wal").write_bytes(
        b"ignored sidecar"
    )
    (lfs_directory / "23726011_large.db-shm").write_bytes(
        b"ignored sidecar"
    )

    records = build_source_catalog(
        own_database=own_database,
        direct_directory=direct_directory,
        lfs_directory=lfs_directory,
    )

    assert [record.source_student_id for record in records] == [
        "23025313",
        "23025328",
        "23071063",
        "23726011",
    ]

    by_id = {
        record.source_student_id: record
        for record in records
    }

    assert by_id["23071063"].source_scope == "MY_CORE"
    assert by_id["23071063"].storage_kind == "MY_CORE_ROOT"

    assert by_id["23025313"].storage_kind == "PEER_DIRECT"
    assert by_id["23726011"].storage_kind == "PEER_LFS"

    expected_hash = hashlib.sha256(b"own database").hexdigest()
    assert by_id["23071063"].source_sha256 == expected_hash
