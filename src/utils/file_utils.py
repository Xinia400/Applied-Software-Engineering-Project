from __future__ import annotations
import hashlib
from pathlib import Path

def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

def safe_slug(text: str, max_len: int = 80) -> str:
    # filesystem-friendly folder name
    cleaned = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in text.strip())
    cleaned = "-".join(filter(None, cleaned.split("-")))
    return cleaned[:max_len] if cleaned else "dataset"