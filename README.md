# MagangHub & Multi-Source Internship Scraper

A robust, large-scale, resumable web scraping system for collecting internship vacancy data from **MagangHub (Kemnaker RI)** and future multi-source internship platforms into a clean, deduplicated CSV dataset.

Primary Target URL:
`https://maganghub.kemnaker.go.id/magang-nasional/lowongan`

---

## Output Dataset

- **Primary File**: `data/lowongan_magang.csv`
- **Format**: UTF-8 with BOM (`utf-8-sig`) for Excel compatibility
- **Columns**:
  1. `source_id`: Unique vacancy ID from source (UUID)
  2. `source_url`: Canonical vacancy URL
  3. `perusahaan_source_id`: Unique company ID from source (UUID)
  4. `perusahaan_nama`: Normalized company name
  5. `perusahaan_id`: Deterministic company identifier
  6. `judul`: Vacancy title
  7. `slug`: Deterministic URL slug
  8. `deskripsi`: Authoritative vacancy description
  9. `lokasi`: Work location
  10. `durasi`: Work duration (e.g. `6 hari/minggu`)
  11. `kuota`: Integer quota (e.g. `1`)
  12. `status`: Vacancy status (`Aktif` / `Tutup`)
  13. `tgl_buka`: Opening date (`YYYY-MM-DD` or `null`)
  14. `tgl_tutup`: Closing date (`YYYY-MM-DD` or `null`)
  15. `syarat`: Qualification requirements
  16. `kontak_email`: Contact email or `null`
  17. `scraped_at`: ISO timestamp of latest scrape (`YYYY-MM-DDTHH:MM:SSZ`)

---

## Installation

1. Clone or navigate to the repository directory:
   ```bash
   cd EduGates-scraper
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. (Optional) Copy `.env.example` to `.env` to customize settings:
   ```bash
   cp .env.example .env
   ```

---

## Usage Guide

### 1. Test Crawl (Development Limit)
Test the scraper pipeline on a small batch (e.g. 10 or 100 vacancies):
```bash
python scraper.py --mode full --limit 100
```

### 2. Full Crawl
Crawl all available vacancies dynamically across all pagination pages:
```bash
python scraper.py --mode full
```

### 3. Incremental Crawl
Efficiently check for new or updated vacancies:
```bash
python scraper.py --mode incremental
```

### 4. Resume Interrupted Crawl
If a crawl is interrupted (e.g. network failure, Ctrl+C), resume from the latest checkpoint:
```bash
python scraper.py --resume
```

### 5. Force Restart
Ignore previous checkpoints and start fresh from page 1:
```bash
python scraper.py --mode full --restart
```

### 6. Specifying Source
By default, `--source maganghub` is used. Specify a source explicitly:
```bash
python scraper.py --source maganghub --mode full --limit 100
```

---

## Multi-Source Architecture

This system uses an **Adapter/Strategy Pattern** (`src/sources/base.py` & `src/sources/registry.py`).

Adding a new platform source (e.g. `karirhub`) requires only creating a new class extending `BaseSource` inside `src/sources/`:

```python
from src.sources.base import BaseSource
from src.sources.registry import SourceRegistry

@SourceRegistry.register
class KarirHubSource(BaseSource):
    @property
    def name(self) -> str:
        return "karirhub"

    ...
```

The core CLI, HTTP client, deduplication system, checkpointing, and atomic CSV writer work seamlessly across all sources.

---

## Running Unit Tests

Run the full offline unit test suite:
```bash
python -m unittest discover tests
```

---

## Key Features

- **Dynamic Pagination**: Discovers total record count (`~28,455`) and page boundaries dynamically without hard-coded page limits.
- **Deduplication & Upserts**: Idempotent processing using identity priority (`source_id` -> `source_url` -> `slug`).
- **Atomic CSV Persistence**: Writes to `.tmp.csv` before atomic rename, ensuring dataset integrity even during crashes.
- **Source Change Protection**: Prevents accidental data wipes if a source temporarily returns fewer records.
- **Checkpoint Recovery**: Saves state to `data/scraper_state.json` allowing seamless `--resume`.
- **Automatic Backups**: Keeps rolling backups in `data/backups/`.
