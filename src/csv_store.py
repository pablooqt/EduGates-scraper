import os
import shutil
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
import pandas as pd
from src.models import CSV_SCHEMA_COLUMNS
from src.exporter import export_to_csv

logger = logging.getLogger("csv_store")


class CSVStore:
    """Canonical CSV Dataset Storage Manager with atomic updates, quality logging, and backups."""

    def __init__(
        self,
        file_path: str = "data/lowongan_magang.csv",
        encoding: str = "utf-8-sig",
        backup_enabled: bool = True,
        backup_retention: int = 3
    ):
        self.file_path = os.path.abspath(file_path)
        self.encoding = encoding
        self.backup_enabled = backup_enabled
        self.backup_retention = backup_retention
        self.tmp_path = self.file_path + ".tmp"
        self.backup_dir = os.path.join(os.path.dirname(self.file_path), "backups")

        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)
        if self.backup_enabled:
            os.makedirs(self.backup_dir, exist_ok=True)

    def load_existing(self) -> List[Dict[str, Any]]:
        """Load existing records from CSV file and sanitize malformed fields."""
        target_path = self.file_path if os.path.exists(self.file_path) else (self.tmp_path if os.path.exists(self.tmp_path) else None)

        if not target_path or not os.path.exists(target_path):
            logger.info(f"No existing CSV found at {self.file_path}. Starting fresh.")
            return []

        try:
            df = pd.read_csv(target_path, encoding=self.encoding, dtype=str)
            df = df.where(pd.notnull(df), None)
            records = df.to_dict(orient="records")

            cleaned_records = []
            for r in records:
                rec = {}
                for col in CSV_SCHEMA_COLUMNS:
                    val = r.get(col)
                    if val is not None and str(val).strip() != "" and str(val).strip().lower() != "none" and str(val).strip().lower() != "nan":
                        rec[col] = str(val).strip()
                    else:
                        rec[col] = None

                if not rec.get("source"):
                    rec["source"] = "maganghub"

                durasi_val = str(rec.get("durasi") or "")
                if "hari/minggu" in durasi_val.lower() or "hari kerja" in durasi_val.lower():
                    rec["durasi"] = None

                syarat_val = str(rec.get("syarat") or "")
                if "hari kerja per minggu" in syarat_val.lower():
                    clean_s = "\n".join([line.strip() for line in syarat_val.split("\n") if "hari kerja per minggu" not in line.lower()]).strip()
                    rec["syarat"] = clean_s if clean_s else None

                cleaned_records.append(rec)

            logger.info(f"Loaded {len(cleaned_records)} existing records from {target_path}")
            return cleaned_records

        except Exception as exc:
            logger.error(f"Error reading existing CSV {target_path}: {exc}")
            return []

    def save_dataset(self, records: List[Dict[str, Any]]) -> bool:
        """Atomically write dataset to canonical CSV file using exporter module."""
        if not records:
            logger.warning("Attempted to save empty record list. Operation cancelled to prevent data wipe.")
            return False

        existing_records = self.load_existing()
        existing_count = len(existing_records)
        new_count = len(records)

        if existing_count > 100 and new_count < (existing_count * 0.5):
            logger.warning(
                f"WARNING: Unexpected source record reduction detected! "
                f"Existing: {existing_count}, New: {new_count}. "
                f"Dataset will NOT be destructively overwritten."
            )
            return False

        # Create backup if file exists before exporting
        if self.backup_enabled and os.path.exists(self.file_path):
            self._create_backup()

        # Delegate export to clean exporter module
        return export_to_csv(records, filename=self.file_path, encoding=self.encoding)

    def _create_backup(self):
        """Create a timestamped backup of the canonical CSV and rotate old backups."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"lowongan_magang_{timestamp}.csv"
        backup_path = os.path.join(self.backup_dir, backup_filename)

        try:
            shutil.copy2(self.file_path, backup_path)
            logger.info(f"Created backup at {backup_path}")

            backups = sorted(
                [os.path.join(self.backup_dir, f) for f in os.listdir(self.backup_dir) if f.startswith("lowongan_magang_") and f.endswith(".csv")],
                key=os.path.getmtime
            )

            while len(backups) > self.backup_retention:
                oldest = backups.pop(0)
                try:
                    os.remove(oldest)
                    logger.info(f"Rotated old backup {oldest}")
                except Exception as e:
                    logger.warning(f"Failed to delete old backup {oldest}: {e}")

        except Exception as exc:
            logger.warning(f"Backup creation failed: {exc}")
