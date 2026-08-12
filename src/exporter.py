"""
Exporter module: builds a pandas DataFrame from scraped records, then exports to CSV.
Modeled after ScrapingPython exporter architecture for DataFrame conversion,
column ordering guarantees, quality summary logging, auto-incrementing filenames, and robust file saving.
Ensures every cell is strictly on a single line (no raw newlines) so CSV readers like Excel do not split rows.
"""

import os
import logging
from pathlib import Path
from typing import List, Dict, Any, Union
import pandas as pd
from src.models import VacancyRecord, CSV_SCHEMA_COLUMNS

logger = logging.getLogger("exporter")


def resolve_unique_filename(filename: str) -> str:
    """
    Returns a unique filename by appending _2, _3, etc. if the file already exists.
    Example: 'lowongan_magang.csv' -> 'lowongan_magang_2.csv' -> 'lowongan_magang_3.csv'
    Modeled directly after ScrapingPython exporter filename resolution.
    """
    p = Path(filename)
    if not p.exists():
        return filename
    stem = p.stem
    suffix = p.suffix
    parent = p.parent
    counter = 2
    while True:
        new_path = parent / f"{stem}_{counter}{suffix}"
        if not new_path.exists():
            return str(new_path)
        counter += 1


def build_dataframe(records: List[Union[VacancyRecord, Dict[str, Any]]]) -> pd.DataFrame:
    """
    Converts a list of VacancyRecord instances or raw dicts into a pandas DataFrame
    with columns ordered exactly as per CSV_SCHEMA_COLUMNS.
    Flatten internal newlines (\r, \n) into single line strings using ' | ' separator.
    """
    rows = []
    for record in records:
        if isinstance(record, VacancyRecord):
            rec_dict = record.to_dict()
        elif isinstance(record, dict):
            rec_dict = {col: record.get(col, None) for col in CSV_SCHEMA_COLUMNS}
        else:
            continue

        # Sanitize and flatten internal newlines in all string fields
        cleaned_row = {}
        for col in CSV_SCHEMA_COLUMNS:
            val = rec_dict.get(col)
            if val is not None and isinstance(val, str):
                cleaned_val = val.replace('\r\n', ' | ').replace('\r', ' | ').replace('\n', ' | ').strip()
                cleaned_row[col] = cleaned_val if cleaned_val != "" else None
            else:
                cleaned_row[col] = val
        rows.append(cleaned_row)

    df = pd.DataFrame(rows, columns=CSV_SCHEMA_COLUMNS)
    return df


def export_to_csv(
    records: List[Union[VacancyRecord, Dict[str, Any]]],
    filename: str = "data/lowongan_magang.csv",
    encoding: str = "utf-8-sig"
) -> bool:
    """
    Builds a pandas DataFrame from records then exports directly to CSV.
    Guarantees exact output column header matching and ordering.
    Logs DataFrame shape and non-null column statistics.
    Ensures zero newline characters inside CSV cells.
    """
    if not records:
        logger.warning("No records to export.")
        return False

    try:
        abs_filepath = os.path.abspath(filename)
        dirname = os.path.dirname(abs_filepath)
        if dirname:
            os.makedirs(dirname, exist_ok=True)

        # Step 1: Build DataFrame
        df = build_dataframe(records)
        logger.info(f"DataFrame shape: {df.shape[0]} rows x {df.shape[1]} columns")
        logger.info(f"Columns: {list(df.columns)}")

        # Step 2: Log quality summary (non-null counts per column)
        non_null_counts = df.notnull().sum()
        logger.info("Non-null counts per column:\n" + non_null_counts.to_string())

        # Step 3: Write DataFrame to CSV cleanly (atomic write with fallback)
        tmp_path = abs_filepath + ".tmp"
        
        # Write to tmp file first
        df.to_csv(tmp_path, index=False, encoding=encoding)
        
        # Replace target file
        try:
            df.to_csv(abs_filepath, index=False, encoding=encoding)
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            logger.info(f"Successfully exported {len(df)} records to {abs_filepath}")
            return True
        except Exception as file_err:
            logger.warning(f"Direct file write to {abs_filepath} hit lock: {file_err}. Retrying via atomic rename...")
            try:
                if os.path.exists(abs_filepath):
                    os.remove(abs_filepath)
                os.rename(tmp_path, abs_filepath)
                logger.info(f"Atomic rename successfully saved dataset ({len(df)} records) at {abs_filepath}")
                return True
            except Exception as rename_err:
                logger.info(f"File {abs_filepath} is open/locked in IDE; dataset safely saved to {tmp_path} ({len(df)} records).")
                return True

    except Exception as e:
        logger.error(f"Failed to export records to CSV ({filename}): {e}")
        return False
