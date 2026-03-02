from __future__ import annotations
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple
import requests

from src.utils.file_utils import sha256_file

@dataclass
class DownloadResult:
    ok: bool
    status: str            # OK / FAILED / SKIPPED
    path: Optional[Path]
    sha256: Optional[str]
    size_bytes: Optional[int]
    error: Optional[str]

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

def download_file(url: str, out_path: Path, timeout: int = 60) -> DownloadResult:
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with requests.get(url, stream=True, timeout=timeout, headers={"User-Agent":"QDArchiveSeeder/1.0"}) as r:
            r.raise_for_status()
            with out_path.open("wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)

        size = out_path.stat().st_size
        digest = sha256_file(out_path)
        return DownloadResult(True, "OK", out_path, digest, size, None)

    except Exception as e:
        return DownloadResult(False, "FAILED", None, None, None, str(e))