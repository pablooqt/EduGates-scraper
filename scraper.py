#!/usr/bin/env python3
"""
MagangHub & Multi-Source Internship Vacancy Scraper
Structured after ScrapingPython configuration, Playwright browser automation,
and entrypoint design.
"""

import sys
import os
import argparse
import logging
from typing import Dict, Any, List, Set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.client import ScraperHTTPClient, ScraperPlaywrightClient
from src.sources.registry import SourceRegistry
from src.sources.maganghub import MagangHubSource
from src.deduplicator import VacancyDeduplicator
from src.csv_store import CSVStore
from src.exporter import export_to_csv, build_dataframe
from src.models import CSV_SCHEMA_COLUMNS, VacancyRecord
from src.checkpoint import CheckpointManager

# ======================================
# SCRAPER CONFIGURATION
# ======================================

DEFAULT_SOURCE = "maganghub"
DEFAULT_MODE = "full"          # 'full' or 'incremental'
DEFAULT_LIMIT = 0              # 0 = unlimited / full crawl, set e.g. 100 for testing
DEFAULT_ENGINE = "playwright"  # 'playwright' or 'httpx'
HEADLESS = True                # True = background browser, False = visible browser UI
DEFAULT_REQUEST_DELAY = 0.5    # Request delay in seconds
DEFAULT_BATCH_SIZE = 100       # Batch size for CSV persistence
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


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-Source Internship Vacancy Scraper")
    parser.add_argument(
        "--source",
        type=str,
        default=DEFAULT_SOURCE,
        help=f"Target scraper source (default: {DEFAULT_SOURCE})"
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["full", "incremental"],
        default=DEFAULT_MODE,
        help=f"Scraping mode: full or incremental (default: {DEFAULT_MODE})"
    )
    parser.add_argument(
        "--engine",
        type=str,
        choices=["playwright", "httpx"],
        default=DEFAULT_ENGINE,
        help=f"Scraping engine: playwright or httpx (default: {DEFAULT_ENGINE})"
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=HEADLESS,
        help=f"Run Playwright browser in headless mode (default: {HEADLESS})"
    )
    parser.add_argument(
        "--no-headless",
        action="store_false",
        dest="headless",
        help="Run Playwright browser with visible UI window"
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume scraping from latest saved checkpoint"
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Ignore checkpoint and start crawl from page 1"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help=f"Limit total vacancies to process (0 = unlimited, default: {DEFAULT_LIMIT})"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_REQUEST_DELAY,
        help=f"Request delay in seconds (default: {DEFAULT_REQUEST_DELAY})"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Batch size for CSV persistence (default: {DEFAULT_BATCH_SIZE})"
    )
    parser.add_argument(
        "--output",
        type=str,
        default=OUTPUT_FILE,
        help=f"Output CSV path (default: {OUTPUT_FILE})"
    )
    return parser.parse_args()


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

        durasi_val = str(rec.get("durasi") or "")
        if "hari/minggu" in durasi_val or "hari kerja" in durasi_val:
            suspicious_durations += 1

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

    if suspicious_durations > 0:
        print(f" WARNING: {suspicious_durations} records contain working schedule text in 'durasi'!")
    else:
        print(" PASSED: 'durasi' contains zero working schedule noise.")

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
    args = parse_args()
    source_name = args.source.lower()
    output_path = args.output

    try:
        source = SourceRegistry.get_source(source_name)
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)

    logger.info("==================================================")
    logger.info(f"Starting Multi-Source Internship Vacancy Scraper")
    logger.info(f"Target Source: {source.name}")
    logger.info(f"Engine: {args.engine.upper()} (Headless={args.headless})")
    logger.info(f"Mode: {args.mode}")
    logger.info(f"Limit: {args.limit if args.limit > 0 else 'Unlimited'}")
    logger.info(f"Request Delay: {args.delay}s")
    logger.info(f"Batch Size: {args.batch_size}")
    logger.info(f"Output File: {output_path}")
    
    sort_param = getattr(source, "SORT_PARAM", None)
    if sort_param:
        logger.info(f"Sorting Parameter: {sort_param} (Kuota Terbanyak)")
    logger.info("==================================================")

    csv_store = CSVStore(file_path=output_path)
    existing_records = [] if args.restart else csv_store.load_existing()
    deduplicator = VacancyDeduplicator(existing_records)
    checkpoint_mgr = CheckpointManager()

    start_page = 1
    processed_source_ids: Set[str] = set()
    stats = {"inserted": 0, "updated": 0, "unchanged": 0, "errors": 0}

    checkpoint = checkpoint_mgr.load() if (args.resume and not args.restart) else None
    if checkpoint and checkpoint.get("source") == source.name:
        start_page = checkpoint.get("last_page", 1) + 1
        stats = checkpoint.get("stats", stats)
        processed_source_ids = set(checkpoint.get("processed_source_ids", []))
        logger.info(f"Resuming from page {start_page}. Previously processed {len(processed_source_ids)} vacancies.")

    with get_client(engine=args.engine, request_delay=args.delay, headless=args.headless) as client:
        logger.info("Discovering pagination boundaries...")
        try:
            pag_info = source.discover_pagination(client)
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

        for current_page in range(start_page, total_pages + 1):
            logger.info(f"--- Fetching Page {current_page} / {total_pages} (Params: sort=most_quota) ---")

            try:
                raw_listing = source.fetch_listing_page(client, current_page)
                items = source.parse_listing(raw_listing)
            except Exception as exc:
                logger.error(f"Error fetching/parsing page {current_page}: {exc}")
                stats["errors"] += 1
                continue

            if not items:
                logger.info(f"Page {current_page} returned no vacancy cards. Reached end of available data.")
                break

            # Validate Sorting on Page 1
            if current_page == 1 and items:
                quotas = [it.get("kuota") for it in items if it.get("kuota") is not None]
                if quotas:
                    logger.info(f"Verified sort order on Page 1 (Top Quotas): {quotas[:5]}")
                    is_desc = all(quotas[i] >= quotas[i+1] for i in range(len(quotas)-1))
                    if is_desc:
                        logger.info("PASSED: First page quotas are strictly descending (Kuota Terbanyak).")
                    else:
                        logger.warning("WARNING: First page quotas are not strictly descending. Verify sorting.")

            # Pagination Loop Protection
            first_id = items[0].get("source_id") if items else None
            if first_id and first_id == prev_page_first_id:
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

                if args.mode == "incremental" and sid in deduplicator.records_by_id:
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

                if args.limit > 0 and total_processed >= args.limit:
                    logger.info(f"Reached development limit (--limit {args.limit}). Stopping crawl.")
                    break

            # Periodically save dataset
            if current_page % max(1, args.batch_size // per_page) == 0 or current_page == total_pages or (args.limit > 0 and total_processed >= args.limit):
                csv_store.save_dataset(deduplicator.get_all_records())
                checkpoint_mgr.save(
                    source=source.name,
                    mode=args.mode,
                    last_page=current_page,
                    total_pages=total_pages,
                    records_processed=total_processed,
                    stats=stats,
                    processed_ids=processed_source_ids
                )
                logger.info(f"Checkpoint saved at page {current_page}. Total dataset: {len(deduplicator.get_all_records()):,} records.")

            if args.limit > 0 and total_processed >= args.limit:
                break

        csv_store.save_dataset(deduplicator.get_all_records())

        if args.limit == 0 or total_processed >= total_records:
            checkpoint_mgr.clear()

        print_summary(source.name, current_page, total_pages, total_records, total_processed, stats, csv_store.file_path)
        generate_validation_report(deduplicator.get_all_records(), source.name)


if __name__ == "__main__":
    main()
