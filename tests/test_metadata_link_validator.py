from src.classification.metadata_link_validator import (
    SQLITE_SIGNATURE,
    as_optional_int,
    validate_metadata_url,
)


class FakeResponse:
    def __init__(
        self,
        *,
        status_code: int,
        content: bytes,
        content_type: str = "application/octet-stream",
        content_length: str | None = None,
        url: str = "https://example.org/final.db",
    ) -> None:
        self.status_code = status_code
        self._content = content
        self.url = url
        self.headers = {
            "Content-Type": content_type,
        }

        if content_length is not None:
            self.headers["Content-Length"] = content_length

    def iter_content(self, chunk_size: int):
        yield self._content[:chunk_size]

    def close(self) -> None:
        pass


class FakeSession:
    def __init__(self, response: FakeResponse) -> None:
        self.response = response

    def get(self, *args, **kwargs) -> FakeResponse:
        return self.response


def test_as_optional_int():
    assert as_optional_int("123") == 123
    assert as_optional_int(None) is None
    assert as_optional_int("not-a-number") is None


def test_valid_sqlite_signature_is_detected():
    session = FakeSession(
        FakeResponse(
            status_code=206,
            content=SQLITE_SIGNATURE + b"example database bytes",
            content_length="4096",
        )
    )

    result = validate_metadata_url(
        session,
        source_student_id="23071063",
        source_scope="MY_CORE",
        metadata_url_original="https://example.org/original.db",
        metadata_url_canonical="https://example.org/final.db",
        metadata_url_was_repaired=False,
    )

    assert result.access_status == "ACCESSIBLE_SQLITE"
    assert result.sqlite_signature_detected is True
    assert result.bytes_sampled > 0


def test_lfs_pointer_is_not_mistaken_for_sqlite():
    lfs_pointer = (
        b"version https://git-lfs.github.com/spec/v1\n"
        b"oid sha256:abc123\n"
        b"size 204767232\n"
    )

    session = FakeSession(
        FakeResponse(
            status_code=206,
            content=lfs_pointer,
            content_type="text/plain; charset=utf-8",
        )
    )

    result = validate_metadata_url(
        session,
        source_student_id="23692652",
        source_scope="PEER_SHARED",
        metadata_url_original="https://example.org/original.db",
        metadata_url_canonical="https://example.org/final.db",
        metadata_url_was_repaired=True,
    )

    assert result.access_status == "ACCESSIBLE_NON_SQLITE"
    assert result.sqlite_signature_detected is False


def test_http_error_is_recorded():
    session = FakeSession(
        FakeResponse(
            status_code=404,
            content=b"404: Not Found",
            content_type="text/plain; charset=utf-8",
        )
    )

    result = validate_metadata_url(
        session,
        source_student_id="23542421",
        source_scope="PEER_SHARED",
        metadata_url_original="https://example.org/original.db",
        metadata_url_canonical="https://example.org/missing.db",
        metadata_url_was_repaired=True,
    )

    assert result.access_status == "HTTP_ERROR"
    assert result.http_status == 404
