#!/usr/bin/env python3
"""
Main entry point for Multi-Source Internship Scraper (MagangHub & Glints).
Modeled directly after ScrapingPython architecture:
Run `python main.py` to start scraping immediately using configuration constants defined below.
Supports random page sampling, sorting options, source selection, and auto-incrementing filenames.
"""

import sys
import os
import random
import logging
from typing import Dict, Any, List, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.client import ScraperHTTPClient, ScraperPlaywrightClient
from src.sources.registry import SourceRegistry
from src.sources.maganghub import MagangHubSource
from src.sources.glints import GlintsSource
from src.deduplicator import VacancyDeduplicator
from src.csv_store import CSVStore
from src.exporter import export_to_csv, build_dataframe, resolve_unique_filename
from src.models import CSV_SCHEMA_COLUMNS, VacancyRecord
from src.checkpoint import CheckpointManager

# ======================================
# SCRAPER CONFIGURATION
# ======================================

# SOURCE: Pilih source yang ingin di-scrape
#   "maganghub" → MagangHub (Kemnaker) — lowongan magang resmi pemerintah
#   "glints"    → Glints Indonesia — lowongan internship
SOURCE = "glints"

MODE = "full"                   # 'full' or 'incremental'
LIMIT = 25                      # Total vacancies limit (0 = unlimited)
SORT = "most_quota"             # Hanya berlaku untuk maganghub. Glints: diabaikan.
RANDOM_PAGES = False            # True = acak halaman, False = berurutan
AUTO_INCREMENT_FILENAME = True  # True = auto-increment filename jika file sudah ada
ENGINE = "playwright"           # 'playwright' or 'httpx'
HEADLESS = False                # False = browser tampil, True = background
REQUEST_DELAY = 1.0             # Delay antar request (detik). Glints: gunakan >= 1.0
BATCH_SIZE = 100                # Batch save CSV setiap N records
OUTPUT_FILE = "data/lowongan_magang.csv"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main")


def generate_validation_report(records: List[Dict[str, Any]], source_name: str):
    """Generate field-by-field validation report."""
    total = len(records)
    if total == 0:
        print("\n[VALIDATION REPORT] No records to validate.")
        return

    field_counts = {col: 0 for col in CSV_SCHEMA_COLUMNS}
    suspicious_durations = 0
    suspicious_syarat = 0

    for rec in records:
        for col in CSV_SCHEMA_COLUMNS:
            val = rec.get(col)
            if val is not None and str(val).strip() != "":
                field_counts[col] += 1

        syarat_val = str(rec.get("syarat") or "")
        if "hari kerja per minggu" in syarat_val:
            suspicious_syarat += 1

    print("\n" + "=" * 50)
    print(f" FIELD VALIDATION REPORT ({source_name.upper()})")
    print("=" * 50)
    print(f" Total Records Audited : {total:,}")
    print("-" * 50)
    for col in CSV_SCHEMA_COLUMNS:
        cnt = field_counts[col]
        pct = (cnt / total) * 100
        print(f" {col:<22} : {cnt:>6,} / {total:<6,} ({pct:>5.1f}%)")
    print("-" * 50)

    if suspicious_syarat > 0:
        print(f" WARNING: {suspicious_syarat} records contain working schedule noise in 'syarat'!")
    else:
        print(" PASSED: 'syarat' is clean of working schedule noise.")

    print("=" * 50 + "\n")


def print_summary(
    source_name: str,
    pages_processed: int,
    total_pages: int,
    discovered: int,
    processed: int,
    stats: Dict[str, int],
    csv_file: str
):
    print("\n" + "=" * 50)
    print(f" SCRAPING SUMMARY ({source_name.upper()})")
    print("=" * 50)
    print(f" Pages processed       : {pages_processed:,} / {total_pages:,}")
    print(f" Vacancies discovered  : {discovered:,}")
    print(f" Vacancies processed   : {processed:,}")
    print(f"   - New vacancies     : {stats.get('inserted', 0):,}")
    print(f"   - Updated vacancies : {stats.get('updated', 0):,}")
    print(f"   - Unchanged         : {stats.get('unchanged', 0):,}")
    print(f"   - Errors            : {stats.get('errors', 0):,}")
    print("-" * 50)
    print(f" Output Dataset CSV    : {csv_file}")
    print("=" * 50)


def get_client(engine: str, request_delay: float, headless: bool):
    """Instantiate scraper client based on engine choice ('playwright' or 'httpx')."""
    if engine.lower() == "playwright":
        return ScraperPlaywrightClient(headless=headless, request_delay=request_delay)
    else:
        return ScraperHTTPClient(request_delay=request_delay)


def main():
    source_name = SOURCE.lower()
    
    # Determine source-specific base filename (e.g. lowongan_magang_glints.csv or lowongan_magang.csv)
    base_file = OUTPUT_FILE
    if source_name == "glints":
        base_file = "data/lowongan_magang_glints.csv"
    elif source_name == "maganghub" and base_file == "data/lowongan_magang.csv":
        base_file = "data/lowongan_magang.csv"

    # Auto-increment filename if configured and file already exists
    output_path = base_file
    if AUTO_INCREMENT_FILENAME:
        output_path = resolve_unique_filename(base_file)
        if output_path != base_file:
            logger.info(f"File '{base_file}' already exists. Output dataset will be saved as '{output_path}'.")

    try:
        source = SourceRegistry.get_source(source_name)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    sort_param = source.resolve_sort_param(SORT) if hasattr(source, "resolve_sort_param") else None

    logger.info("==================================================")
    logger.info(f"Starting Multi-Source Internship Vacancy Scraper")
    logger.info(f"Target Source: {source.name}")
    logger.info(f"Engine: {ENGINE.upper()} (Headless={HEADLESS})")
    logger.info(f"Mode: {MODE}")
    logger.info(f"Sorting Choice: '{SORT}' (Parameter: '{sort_param}')")
    logger.info(f"Random Page Sampling: {RANDOM_PAGES}")
    logger.info(f"Auto-Increment Filename: {AUTO_INCREMENT_FILENAME}")
    logger.info(f"Limit: {LIMIT if LIMIT > 0 else 'Unlimited'}")
    logger.info(f"Request Delay: {REQUEST_DELAY}s")
    logger.info(f"Batch Size: {BATCH_SIZE}")
    logger.info(f"Output File: {output_path}")
    logger.info("==================================================")

    csv_store = CSVStore(file_path=output_path)
    existing_records = csv_store.load_existing()
    deduplicator = VacancyDeduplicator(existing_records)
    checkpoint_mgr = CheckpointManager()

    start_page = 1
    processed_source_ids: Set[str] = set()
    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}

    checkpoint = checkpoint_mgr.load() if MODE == "incremental" else None
    if checkpoint and checkpoint.get("source") == source.name:
        start_page = checkpoint.get("last_page", 1) + 1
        stats = checkpoint.get("stats", stats)
        processed_source_ids = set(checkpoint.get("processed_source_ids", []))
        logger.info(f"Resuming from page {start_page}. Previously processed {len(processed_source_ids)} vacancies.")

    with get_client(engine=ENGINE, request_delay=REQUEST_DELAY, headless=HEADLESS) as client:
        logger.info("Discovering pagination boundaries...")
        try:
            pag_info = source.discover_pagination(client, sort_param=sort_param)
        except Exception as exc:
            logger.error(f"Failed to discover pagination for {source.name}: {exc}")
            sys.exit(1)

        total_records = pag_info.get("total", 0)
        total_pages = pag_info.get("last_page", 1)
        per_page = pag_info.get("per_page", 18)

        logger.info(f"Discovered: {total_records:,} total vacancies across {total_pages:,} pages ({per_page} per page)")

        if start_page > total_pages:
            logger.info("Start page exceeds total pages. Crawl is already complete.")
            print_summary(source.name, total_pages, total_pages, total_records, len(processed_source_ids), stats, csv_store.file_path)
            generate_validation_report(deduplicator.get_all_records(), source.name)
            return

        total_processed = len(processed_source_ids)
        prev_page_first_id = None
        consecutive_identical_pages = 0

        # Construct page sequence
        page_sequence = list(range(start_page, total_pages + 1))
        if RANDOM_PAGES:
            random.shuffle(page_sequence)
            logger.info(f"Random page sampling ENABLED. Shuffled {len(page_sequence):,} pages across dataset.")

        pages_crawled_count = 0

        for current_page in page_sequence:
            pages_crawled_count += 1
            logger.info(f"--- Fetching Page {current_page} / {total_pages} (Progress: {pages_crawled_count}/{len(page_sequence)}, Sort: {SORT}) ---")

            try:
                raw_listing = source.fetch_listing_page(client, current_page, sort_param=sort_param)
                items = source.parse_listing(raw_listing)
            except Exception as exc:
                logger.error(f"Error fetching/parsing page {current_page}: {exc}")
                stats["errors"] += 1
                continue

            if not items:
                logger.info(f"Page {current_page} returned no vacancy cards.")
                continue

            # Pagination Loop Protection
            first_id = items[0].get("source_id") if items else None
            if first_id and first_id == prev_page_first_id and not RANDOM_PAGES:
                consecutive_identical_pages += 1
                if consecutive_identical_pages >= 2:
                    logger.error(f"PAGINATION LOOP DETECTED: Page {current_page} returned identical data as previous page. Stopping crawl.")
                    break
            else:
                consecutive_identical_pages = 0
                prev_page_first_id = first_id

            # Process items
            for item in items:
                sid = item.get("source_id")

                if MODE == "incremental" and sid in deduplicator.records_by_id:
                    action, norm_rec = deduplicator.process_record(item)
                    if action == "unchanged":
                        stats["unchanged"] += 1
                        total_processed += 1
                        processed_source_ids.add(sid)
                        continue

                # Fetch detail page via Playwright / HTTP client
                detail_fields = {}
                try:
                    raw_detail = source.fetch_detail(client, item)
                    if raw_detail:
                        detail_fields = source.parse_detail(raw_detail)
                except Exception as exc:
                    logger.warning(f"Error fetching detail for {sid} ({item.get('judul')}): {exc}")
                    stats["errors"] += 1

                combined = dict(item)
                combined.update({k: v for k, v in detail_fields.items() if v is not None})

                action, norm_rec = deduplicator.process_record(combined)
                stats[action] += 1
                total_processed += 1
                if sid:
                    processed_source_ids.add(sid)

                if LIMIT > 0 and total_processed >= LIMIT:
                    logger.info(f"Reached limit ({LIMIT}). Stopping crawl.")
                    break

            # Periodically save dataset
            if pages_crawled_count % max(1, BATCH_SIZE // per_page) == 0 or pages_crawled_count == len(page_sequence) or (LIMIT > 0 and total_processed >= LIMIT):
                csv_store.save_dataset(deduplicator.get_all_records())
                checkpoint_mgr.save(
                    source=source.name,
                    mode=MODE,
                    last_page=current_page,
                    total_pages=total_pages,
                    records_processed=total_processed,
                    stats=stats,
                    processed_ids=processed_source_ids
                )
                logger.info(f"Checkpoint saved at page {current_page}. Total dataset: {len(deduplicator.get_all_records()):,} records.")

            if LIMIT > 0 and total_processed >= LIMIT:
                break

        csv_store.save_dataset(deduplicator.get_all_records())

        if LIMIT == 0 or total_processed >= total_records:
            checkpoint_mgr.clear()

        print_summary(source.name, pages_crawled_count, total_pages, total_records, total_processed, stats, csv_store.file_path)
        generate_validation_report(deduplicator.get_all_records(), source.name)


if __name__ == "__main__":
    main()
