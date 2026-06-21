from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import requests


CHUNK_SIZE_BYTES = 1024 * 1024
SQLITE_SIGNATURE = b"SQLite format 3\x00"


@dataclass(frozen=True)
class DirectDatabaseTarget:
    """One directly downloadable peer SQLite metadata database."""

    student_id: str
    url: str
    url_source: str
    filename: str


@dataclass(frozen=True)
class DirectDownloadResult:
    """Auditable result of one direct metadata-database download."""

    student_id: str
    filename: str
    url: str
    url_source: str
    destination_path: str
    downloaded_at_utc: str
    status: str
    http_status: Optional[int]
    reported_content_length: Optional[int]
    actual_size_bytes: int
    sqlite_signature_detected: bool
    sqlite_quick_check: str
    sha256: str
    error_message: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def as_optional_int(value: str | None) -> Optional[int]:
    if not value:
        return None

    try:
        return int(value)
    except ValueError:
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file_handle:
        while chunk := file_handle.read(CHUNK_SIZE_BYTES):
            digest.update(chunk)

    return digest.hexdigest()


def sqlite_quick_check(path: Path) -> str:
    """Run a non-writing SQLite health check."""
    absolute_path = path.resolve()

    connection = sqlite3.connect(
        f"file:{absolute_path}?mode=ro&immutable=1",
        uri=True,
    )

    try:
        result = connection.execute("PRAGMA quick_check;").fetchone()
        return str(result[0]) if result else "NO_RESULT"
    finally:
        connection.close()


def safe_filename_from_url(url: str, fallback_name: str) -> str:
    filename = Path(urlsplit(url).path).name or fallback_name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", filename)


def create_download_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "QDArchive-X/0.1 academic-project",
            "Accept": "*/*",
        }
    )
    return session


def download_direct_database(
    session: requests.Session,
    target: DirectDatabaseTarget,
    output_directory: Path,
) -> DirectDownloadResult:
    """
    Download one peer database atomically and verify its SQLite health.

    The destination file appears only after signature and quick-check success.
    """
    timestamp = utc_now_iso()
    output_directory.mkdir(parents=True, exist_ok=True)

    filename = safe_filename_from_url(
        target.url,
        fallback_name=target.filename,
    )

    destination = output_directory / f"{target.student_id}_{filename}"
    temporary = destination.with_suffix(destination.suffix + ".part")

    if destination.exists():
        try:
            existing_signature = destination.read_bytes()[:16].startswith(
                SQLITE_SIGNATURE
            )
            existing_check = (
                sqlite_quick_check(destination)
                if existing_signature
                else "NOT_SQLITE"
            )

            if existing_signature and existing_check == "ok":
                return DirectDownloadResult(
                    student_id=target.student_id,
                    filename=filename,
                    url=target.url,
                    url_source=target.url_source,
                    destination_path=str(destination),
                    downloaded_at_utc=timestamp,
                    status="ALREADY_VERIFIED",
                    http_status=None,
                    reported_content_length=destination.stat().st_size,
                    actual_size_bytes=destination.stat().st_size,
                    sqlite_signature_detected=True,
                    sqlite_quick_check=existing_check,
                    sha256=sha256_file(destination),
                    error_message="",
                )
        except (OSError, sqlite3.Error) as error:
            return DirectDownloadResult(
                student_id=target.student_id,
                filename=filename,
                url=target.url,
                url_source=target.url_source,
                destination_path=str(destination),
                downloaded_at_utc=timestamp,
                status="EXISTING_FILE_INVALID",
                http_status=None,
                reported_content_length=None,
                actual_size_bytes=0,
                sqlite_signature_detected=False,
                sqlite_quick_check="NOT_RUN",
                sha256="",
                error_message=f"{type(error).__name__}: {error}",
            )

    temporary.unlink(missing_ok=True)

    try:
        with session.get(
            target.url,
            stream=True,
            timeout=(10, 180),
            allow_redirects=True,
        ) as response:
            http_status = response.status_code
            reported_size = as_optional_int(
                response.headers.get("Content-Length")
            )

            if not 200 <= http_status < 300:
                return DirectDownloadResult(
                    student_id=target.student_id,
                    filename=filename,
                    url=target.url,
                    url_source=target.url_source,
                    destination_path=str(destination),
                    downloaded_at_utc=timestamp,
                    status="HTTP_ERROR",
                    http_status=http_status,
                    reported_content_length=reported_size,
                    actual_size_bytes=0,
                    sqlite_signature_detected=False,
                    sqlite_quick_check="NOT_RUN",
                    sha256="",
                    error_message=f"Server returned HTTP {http_status}.",
                )

            digest = hashlib.sha256()
            bytes_written = 0
            signature_sample = b""

            with temporary.open("wb") as file_handle:
                for chunk in response.iter_content(
                    chunk_size=CHUNK_SIZE_BYTES
                ):
                    if not chunk:
                        continue

                    file_handle.write(chunk)
                    digest.update(chunk)
                    bytes_written += len(chunk)

                    if len(signature_sample) < len(SQLITE_SIGNATURE):
                        signature_sample = (
                            signature_sample + chunk
                        )[: len(SQLITE_SIGNATURE)]

        signature_detected = signature_sample.startswith(SQLITE_SIGNATURE)
        file_hash = digest.hexdigest()

        if (
            reported_size is not None
            and bytes_written != reported_size
        ):
            temporary.unlink(missing_ok=True)

            return DirectDownloadResult(
                student_id=target.student_id,
                filename=filename,
                url=target.url,
                url_source=target.url_source,
                destination_path=str(destination),
                downloaded_at_utc=timestamp,
                status="SIZE_MISMATCH",
                http_status=http_status,
                reported_content_length=reported_size,
                actual_size_bytes=bytes_written,
                sqlite_signature_detected=signature_detected,
                sqlite_quick_check="NOT_RUN",
                sha256=file_hash,
                error_message=(
                    "Downloaded bytes do not match Content-Length."
                ),
            )

        if not signature_detected:
            temporary.unlink(missing_ok=True)

            return DirectDownloadResult(
                student_id=target.student_id,
                filename=filename,
                url=target.url,
                url_source=target.url_source,
                destination_path=str(destination),
                downloaded_at_utc=timestamp,
                status="NON_SQLITE_CONTENT",
                http_status=http_status,
                reported_content_length=reported_size,
                actual_size_bytes=bytes_written,
                sqlite_signature_detected=False,
                sqlite_quick_check="NOT_RUN",
                sha256=file_hash,
                error_message=(
                    "Downloaded content does not start with "
                    "the SQLite signature."
                ),
            )

        quick_check = sqlite_quick_check(temporary)

        if quick_check != "ok":
            temporary.unlink(missing_ok=True)

            return DirectDownloadResult(
                student_id=target.student_id,
                filename=filename,
                url=target.url,
                url_source=target.url_source,
                destination_path=str(destination),
                downloaded_at_utc=timestamp,
                status="SQLITE_CHECK_FAILED",
                http_status=http_status,
                reported_content_length=reported_size,
                actual_size_bytes=bytes_written,
                sqlite_signature_detected=True,
                sqlite_quick_check=quick_check,
                sha256=file_hash,
                error_message="SQLite quick_check did not return ok.",
            )

        temporary.replace(destination)

        return DirectDownloadResult(
            student_id=target.student_id,
            filename=filename,
            url=target.url,
            url_source=target.url_source,
            destination_path=str(destination),
            downloaded_at_utc=timestamp,
            status="DOWNLOADED_VERIFIED",
            http_status=http_status,
            reported_content_length=reported_size,
            actual_size_bytes=bytes_written,
            sqlite_signature_detected=True,
            sqlite_quick_check=quick_check,
            sha256=file_hash,
            error_message="",
        )

    except (requests.RequestException, OSError, sqlite3.Error) as error:
        temporary.unlink(missing_ok=True)

        return DirectDownloadResult(
            student_id=target.student_id,
            filename=filename,
            url=target.url,
            url_source=target.url_source,
            destination_path=str(destination),
            downloaded_at_utc=timestamp,
            status="DOWNLOAD_ERROR",
            http_status=None,
            reported_content_length=None,
            actual_size_bytes=0,
            sqlite_signature_detected=False,
            sqlite_quick_check="NOT_RUN",
            sha256="",
            error_message=f"{type(error).__name__}: {error}",
        )
