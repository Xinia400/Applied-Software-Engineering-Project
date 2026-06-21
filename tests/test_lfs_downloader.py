import hashlib

from src.classification.lfs_downloader import (
    LfsObjectSpec,
    download_lfs_object,
    sha256_file,
)


def test_sha256_file_returns_expected_hash(tmp_path):
    file_path = tmp_path / "sample.db"
    file_path.write_bytes(b"SQLite format 3\x00example")

    expected = hashlib.sha256(file_path.read_bytes()).hexdigest()

    assert sha256_file(file_path) == expected


def test_existing_valid_lfs_file_is_not_downloaded_again(tmp_path):
    student_id = "99999999"
    filename = "example-seeding.db"
    payload = b"SQLite format 3\x00already verified database"

    destination = tmp_path / f"{student_id}_{filename}"
    destination.write_bytes(payload)

    spec = LfsObjectSpec(
        student_id=student_id,
        owner="example-owner",
        repository="example-repository",
        filename=filename,
        sha256_oid=hashlib.sha256(payload).hexdigest(),
        expected_size_bytes=len(payload),
    )

    result = download_lfs_object(
        session=None,
        spec=spec,
        output_directory=tmp_path,
    )

    assert result.status == "ALREADY_VERIFIED"
    assert result.actual_size_bytes == len(payload)
    assert result.actual_sha256 == spec.sha256_oid
