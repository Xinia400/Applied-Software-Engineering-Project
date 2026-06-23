from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests


CHUNK_SIZE_BYTES = 1024 * 1024


@dataclass(frozen=True)
class LfsObjectSpec:
    """Identity and integrity information for one Git LFS database object."""

    student_id: str
    owner: str
    repository: str
    filename: str
    sha256_oid: str
    expected_size_bytes: int


@dataclass(frozen=True)
class LfsDownloadResult:
    """Auditable outcome of one Git LFS object retrieval."""

    student_id: str
    filename: str
    destination_path: str
    downloaded_at_utc: str
    status: str
    expected_size_bytes: int
    actual_size_bytes: int
    expected_sha256: str
    actual_sha256: str
    error_message: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while chunk := file_handle.read(CHUNK_SIZE_BYTES):
            digest.update(chunk)

    return digest.hexdigest()


def create_lfs_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.git-lfs+json",
            "User-Agent": "QDArchive-X/0.1 academic-project",
        }
    )
    return session


def request_lfs_download_action(
    session: requests.Session,
    spec: LfsObjectSpec,
) -> tuple[str, dict[str, str]]:
    """Request GitHub's signed download URL for one LFS object."""
    endpoint = (
        f"https://github.com/{spec.owner}/"
        f"{spec.repository}.git/info/lfs/objects/batch"
    )

    response = session.post(
        endpoint,
        headers={
            "Accept": "application/vnd.git-lfs+json",
            "Content-Type": "application/vnd.git-lfs+json",
        },
        json={
            "operation": "download",
            "transfers": ["basic"],
            "objects": [
                {
                    "oid": spec.sha256_oid,
                    "size": spec.expected_size_bytes,
                }
            ],
        },
        timeout=30,
    )

    response.raise_for_status()

    payload = response.json()
    lfs_object = payload.get("objects", [{}])[0]

    if "error" in lfs_object:
        raise RuntimeError(f"Git LFS object error: {lfs_object['error']}")

    action = lfs_object.get("actions", {}).get("download")
    if not action:
        raise RuntimeError("Git LFS did not return a download action.")

    href = action.get("href")
    if not href:
        raise RuntimeError("Git LFS download action has no URL.")

    action_headers = {
        str(key): str(value)
        for key, value in action.get("header", {}).items()
    }

    return href, action_headers


def download_lfs_object(
    session: requests.Session,
    spec: LfsObjectSpec,
    output_directory: Path,
) -> LfsDownloadResult:
    """
    Download one LFS object privately and verify size plus SHA-256 integrity.

    The file is first written as a temporary .part file. It is renamed only
    after successful validation.
    """
    timestamp = utc_now_iso()
    output_directory.mkdir(parents=True, exist_ok=True)

    destination = output_directory / f"{spec.student_id}_{spec.filename}"
    temporary = destination.with_suffix(destination.suffix + ".part")

    if destination.exists():
        existing_size = destination.stat().st_size
        existing_hash = sha256_file(destination)

        if (
            existing_size == spec.expected_size_bytes
            and existing_hash == spec.sha256_oid
        ):
            return LfsDownloadResult(
                student_id=spec.student_id,
                filename=spec.filename,
                destination_path=str(destination),
                downloaded_at_utc=timestamp,
                status="ALREADY_VERIFIED",
                expected_size_bytes=spec.expected_size_bytes,
                actual_size_bytes=existing_size,
                expected_sha256=spec.sha256_oid,
                actual_sha256=existing_hash,
                error_message="",
            )

    temporary.unlink(missing_ok=True)

    try:
        download_url, action_headers = request_lfs_download_action(
            session,
            spec,
        )

        response = session.get(
            download_url,
            headers=action_headers,
            stream=True,
            timeout=(10, 180),
        )
        response.raise_for_status()

        digest = hashlib.sha256()
        bytes_written = 0

        with temporary.open("wb") as file_handle:
            for chunk in response.iter_content(chunk_size=CHUNK_SIZE_BYTES):
                if not chunk:
                    continue

                file_handle.write(chunk)
                digest.update(chunk)
                bytes_written += len(chunk)

        response.close()

        actual_hash = digest.hexdigest()

        if bytes_written != spec.expected_size_bytes:
            temporary.unlink(missing_ok=True)
            return LfsDownloadResult(
                student_id=spec.student_id,
                filename=spec.filename,
                destination_path=str(destination),
                downloaded_at_utc=timestamp,
                status="SIZE_MISMATCH",
                expected_size_bytes=spec.expected_size_bytes,
                actual_size_bytes=bytes_written,
                expected_sha256=spec.sha256_oid,
                actual_sha256=actual_hash,
                error_message="Downloaded bytes do not match Git LFS size.",
            )

        if actual_hash != spec.sha256_oid:
            temporary.unlink(missing_ok=True)
            return LfsDownloadResult(
                student_id=spec.student_id,
                filename=spec.filename,
                destination_path=str(destination),
                downloaded_at_utc=timestamp,
                status="SHA256_MISMATCH",
                expected_size_bytes=spec.expected_size_bytes,
                actual_size_bytes=bytes_written,
                expected_sha256=spec.sha256_oid,
                actual_sha256=actual_hash,
                error_message="SHA-256 does not match the Git LFS object ID.",
            )

        temporary.replace(destination)

        return LfsDownloadResult(
            student_id=spec.student_id,
            filename=spec.filename,
            destination_path=str(destination),
            downloaded_at_utc=timestamp,
            status="DOWNLOADED_VERIFIED",
            expected_size_bytes=spec.expected_size_bytes,
            actual_size_bytes=bytes_written,
            expected_sha256=spec.sha256_oid,
            actual_sha256=actual_hash,
            error_message="",
        )

    except (requests.RequestException, RuntimeError) as error:
        temporary.unlink(missing_ok=True)

        return LfsDownloadResult(
            student_id=spec.student_id,
            filename=spec.filename,
            destination_path=str(destination),
            downloaded_at_utc=timestamp,
            status="DOWNLOAD_ERROR",
            expected_size_bytes=spec.expected_size_bytes,
            actual_size_bytes=0,
            expected_sha256=spec.sha256_oid,
            actual_sha256="",
            error_message=f"{type(error).__name__}: {error}",
        )
