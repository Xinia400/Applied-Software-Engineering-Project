from __future__ import annotations

import argparse
from pathlib import Path
import yaml

from src.utils.logger import setup_logger
from src.utils.file_utils import safe_slug
from src.metadata.db_handler import connect, init_db, exists_by_url, insert_qda_record
from src.acquisition.search import search_from_config
from src.acquisition.downloader import download_file, utc_now_iso


def guess_filename_from_url(url: str) -> str:
    name = url.split("?")[0].rstrip("/").split("/")[-1]
    return name if name else "main.qda"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/queries.yaml")
    parser.add_argument("--db", default="database/metadata.db")
    parser.add_argument("--data-dir", default="data/raw")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of downloads")
    args = parser.parse_args()

    logger = setup_logger()

    cfg_path = Path(args.config)
    db_path = Path(args.db)
    data_dir = Path(args.data_dir)

    if not cfg_path.exists():
        logger.error(f"Config not found: {cfg_path}")
        return 2

    cfg = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}

    con = connect(db_path)
    init_db(con, Path("src/metadata/schema.sql"))

    found = search_from_config(cfg)
    total_found = len(found)
    logger.info(f"Total candidate QDA files found: {total_found}")

    if args.limit is not None:
        found = found[:args.limit]
        logger.info(f"Limiting downloads to first {len(found)} items")

    inserted = 0
    skipped = 0
    failed = 0

    for idx, item in enumerate(found, start=1):
        logger.info(f"[{idx}/{len(found)}] Processing: {item.qda_url}")

        # Skip if already stored
        if exists_by_url(con, item.qda_url):
            skipped += 1
            logger.info(f"[{idx}/{len(found)}] SKIPPED (duplicate URL)")
            continue

        base_name = item.title or guess_filename_from_url(item.qda_url)
        folder = safe_slug(base_name)
        repo_folder = safe_slug(item.repository)
        dataset_dir = data_dir / repo_folder / folder

        filename = item.filename or guess_filename_from_url(item.qda_url)

        # ----------------------------------------
        # METADATA-ONLY MODE
        # ----------------------------------------
        if getattr(item, "metadata_only", False):
            record = {
                "qda_url": item.qda_url,
                "download_timestamp": utc_now_iso(),
                "local_directory": str(dataset_dir),
                "local_qda_filename": filename,
                "repository": item.repository,
                "dataset_url": item.dataset_url,
                "license": item.license,
                "uploader_name": item.uploader_name,
                "uploader_email": item.uploader_email,
                "title": item.title,
                "doi": item.doi,
                "year": item.year,
                "description": item.description,
                "file_type": None,
                "sha256": None,
                "file_size_bytes": None,
                "download_status": item.status_hint or "NO_PUBLIC_FILE_FOUND",
                "error_message": item.description,
            }

            ok_insert = insert_qda_record(con, record)

            if ok_insert:
                inserted += 1
                logger.info(f"[{idx}/{len(found)}] METADATA-ONLY STORED: {filename}")
            else:
                skipped += 1
                logger.info(f"[{idx}/{len(found)}] SKIPPED (duplicate metadata-only URL)")

            continue

        # ----------------------------------------
        # DIRECT DOWNLOAD MODE
        # ----------------------------------------
        out_path = dataset_dir / filename
        res = download_file(item.qda_url, out_path)

        record = {
            "qda_url": item.qda_url,
            "download_timestamp": utc_now_iso(),
            "local_directory": str(dataset_dir),
            "local_qda_filename": filename,
            "repository": item.repository,
            "dataset_url": item.dataset_url,
            "license": item.license,
            "uploader_name": item.uploader_name,
            "uploader_email": item.uploader_email,
            "title": item.title,
            "doi": item.doi,
            "year": item.year,
            "description": item.description,
            "file_type": Path(filename).suffix.lower().lstrip(".") if "." in filename else None,
            "sha256": res.sha256,
            "file_size_bytes": res.size_bytes,
            "download_status": res.status,
            "error_message": res.error,
        }

        ok_insert = insert_qda_record(con, record)

        if res.ok and ok_insert:
            inserted += 1
            logger.info(f"[{idx}/{len(found)}] DOWNLOADED: {filename}")
        elif res.ok and not ok_insert:
            skipped += 1
            logger.info(f"[{idx}/{len(found)}] SKIPPED (duplicate content or URL)")
        else:
            failed += 1
            logger.error(f"[{idx}/{len(found)}] FAILED: {res.error}")

    logger.info(f"Done. inserted={inserted}, skipped={skipped}, failed={failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())