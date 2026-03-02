-- src/metadata/schema.sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS qda_files (
  id INTEGER PRIMARY KEY AUTOINCREMENT,

  -- Required by Output Format v1
  qda_url TEXT NOT NULL,
  download_timestamp TEXT NOT NULL,         -- ISO 8601 UTC
  local_directory TEXT NOT NULL,
  local_qda_filename TEXT NOT NULL,

  -- Optional / recommended
  repository TEXT,
  dataset_url TEXT,
  license TEXT,
  uploader_name TEXT,
  uploader_email TEXT,
  title TEXT,
  doi TEXT,
  year INTEGER,
  description TEXT,
  file_type TEXT,

  -- Dedupe helpers
  qda_url_norm TEXT NOT NULL,               -- normalized url for stable uniqueness
  sha256 TEXT,                              -- fingerprint of downloaded QDA file (optional if download fails)
  file_size_bytes INTEGER,
  download_status TEXT NOT NULL DEFAULT 'OK',  -- OK / FAILED / SKIPPED
  error_message TEXT,

  -- Dedup rules:
  -- 1) If we already have this QDA URL, do not insert again.
  CONSTRAINT uq_qda_url UNIQUE (qda_url_norm),

  -- 2) If sha256 is available, don’t store duplicates by file hash either.
  CONSTRAINT uq_sha256 UNIQUE (sha256)
);

CREATE INDEX IF NOT EXISTS idx_repo ON qda_files(repository);
CREATE INDEX IF NOT EXISTS idx_timestamp ON qda_files(download_timestamp);