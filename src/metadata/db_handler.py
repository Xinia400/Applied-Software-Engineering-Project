from __future__ import annotations
import sqlite3
from pathlib import Path
from typing import Any, Dict, Optional

def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.row_factory = sqlite3.Row
    return con

def init_db(con: sqlite3.Connection, schema_sql_path: Path) -> None:
    schema = schema_sql_path.read_text(encoding="utf-8")
    con.executescript(schema)
    con.commit()

def normalize_url(url: str) -> str:
    # minimal normalization: trim + remove trailing slash
    u = (url or "").strip()
    while u.endswith("/"):
        u = u[:-1]
    return u.lower()

def exists_by_url(con: sqlite3.Connection, qda_url: str) -> bool:
    q = "SELECT 1 FROM qda_files WHERE qda_url_norm = ? LIMIT 1"
    cur = con.execute(q, (normalize_url(qda_url),))
    return cur.fetchone() is not None

def insert_qda_record(con: sqlite3.Connection, record: Dict[str, Any]) -> bool:
    """
    Returns True if inserted, False if skipped due to duplicates.
    Dedup is enforced by UNIQUE constraints (qda_url_norm) and (sha256).
    """
    record = dict(record)
    record["qda_url_norm"] = normalize_url(record.get("qda_url", ""))

    cols = [
        "qda_url","download_timestamp","local_directory","local_qda_filename",
        "repository","dataset_url","license","uploader_name","uploader_email",
        "title","doi","year","description","file_type",
        "qda_url_norm","sha256","file_size_bytes","download_status","error_message"
    ]
    values = [record.get(c) for c in cols]

    placeholders = ",".join(["?"] * len(cols))
    sql = f"INSERT OR IGNORE INTO qda_files ({','.join(cols)}) VALUES ({placeholders})"

    cur = con.execute(sql, values)
    con.commit()
    return cur.rowcount == 1