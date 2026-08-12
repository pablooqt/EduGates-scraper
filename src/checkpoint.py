import os
import json
import logging
from typing import Dict, Any, Optional, Set
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CheckpointManager:
    """Manages scraper progress state for crash recovery and resume capability."""

    def __init__(self, file_path: str = "data/scraper_state.json"):
        self.file_path = os.path.abspath(file_path)
        os.makedirs(os.path.dirname(self.file_path), exist_ok=True)

    def load(self) -> Optional[Dict[str, Any]]:
        """Load state checkpoint if exists and valid."""
        if not os.path.exists(self.file_path):
            return None
        try:
            with open(self.file_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            logger.info(f"Loaded checkpoint from {self.file_path} (Last Page: {state.get('last_page')})")
            return state
        except Exception as exc:
            logger.error(f"Failed to read checkpoint file {self.file_path}: {exc}")
            return None

    def save(
        self,
        source: str,
        mode: str,
        last_page: int,
        total_pages: int,
        records_processed: int,
        stats: Dict[str, int],
        processed_ids: Set[str],
        started_at: Optional[str] = None
    ):
        """Save current progress state."""
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        state = {
            "source": source,
            "mode": mode,
            "last_page": last_page,
            "total_pages": total_pages,
            "records_processed": records_processed,
            "stats": stats,
            "processed_source_ids": list(processed_ids),
            "started_at": started_at or now_iso,
            "updated_at": now_iso
        }

        try:
            tmp_path = self.file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2)
            if os.path.exists(self.file_path):
                os.remove(self.file_path)
            os.rename(tmp_path, self.file_path)
        except Exception as exc:
            logger.error(f"Failed to save checkpoint: {exc}")

    def clear(self):
        """Remove checkpoint file."""
        if os.path.exists(self.file_path):
            try:
                os.remove(self.file_path)
                logger.info(f"Cleared checkpoint at {self.file_path}")
            except Exception as exc:
                logger.warning(f"Could not clear checkpoint file: {exc}")
