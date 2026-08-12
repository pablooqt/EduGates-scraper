import logging
from typing import Dict, List, Any, Tuple, Optional
from datetime import datetime, timezone
from src.normalizer import (
    normalize_text,
    normalize_quota,
    normalize_status,
    normalize_slug,
    sanitize_csv_cell
)
from src.company_parser import normalize_company_name, derive_perusahaan_id

logger = logging.getLogger(__name__)

COMPARE_FIELDS = [
    "judul",
    "deskripsi",
    "lokasi",
    "durasi",
    "kuota",
    "status",
    "tgl_buka",
    "tgl_tutup",
    "syarat",
    "kontak_email",
    "perusahaan_nama"
]


class VacancyDeduplicator:
    """Handles deduplication, identity resolution, and upsert classification."""

    def __init__(self, existing_records: List[Dict[str, Any]] = None):
        self.records_by_id: Dict[str, Dict[str, Any]] = {}
        self.records_by_url: Dict[str, str] = {}  # url -> source_id
        self.records_by_slug: Dict[str, str] = {}  # slug -> source_id

        if existing_records:
            self._index_existing(existing_records)

    def _index_existing(self, records: List[Dict[str, Any]]):
        for rec in records:
            sid = rec.get("source_id")
            surl = rec.get("source_url")
            slug = rec.get("slug")

            if sid:
                self.records_by_id[sid] = rec
                if surl:
                    self.records_by_url[surl] = sid
                if slug:
                    self.records_by_slug[slug] = sid

    def find_existing(self, record: Dict[str, Any]) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """Find existing record by identity priority: source_id -> source_url -> slug."""
        sid = record.get("source_id")
        surl = record.get("source_url")
        slug = record.get("slug")

        # 1. By source_id
        if sid and sid in self.records_by_id:
            return sid, self.records_by_id[sid]

        # 2. By canonical source_url
        if surl and surl in self.records_by_url:
            matched_id = self.records_by_url[surl]
            return matched_id, self.records_by_id[matched_id]

        # 3. By slug
        if slug and slug in self.records_by_slug:
            matched_id = self.records_by_slug[slug]
            return matched_id, self.records_by_id[matched_id]

        return None, None

    def process_record(self, raw_record: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
        """
        Normalize and upsert a record.
        Returns tuple of (action, normalized_record) where action is 'inserted', 'updated', or 'unchanged'.
        """
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        source = str(raw_record.get("source", "maganghub")).strip()
        sid = str(raw_record.get("source_id", "")).strip()
        surl = str(raw_record.get("source_url", "")).strip()
        co_sid = str(raw_record.get("perusahaan_source_id", "")).strip() or None
        co_nama = normalize_company_name(raw_record.get("perusahaan_nama", ""))
        co_id = derive_perusahaan_id(co_sid, co_nama, source=source)
        judul = normalize_text(raw_record.get("judul", ""))
        slug = normalize_slug(judul, sid, raw_record.get("slug"))
        deskripsi = normalize_text(raw_record.get("deskripsi", "")) or None
        lokasi = normalize_text(raw_record.get("lokasi", "")) or None
        
        # Valid duration check
        durasi_raw = raw_record.get("durasi")
        durasi = None
        if durasi_raw and "hari/minggu" not in str(durasi_raw).lower() and "hari kerja" not in str(durasi_raw).lower():
            durasi = normalize_text(str(durasi_raw))

        kuota = normalize_quota(raw_record.get("kuota"))
        status = normalize_status(raw_record.get("status"))
        tgl_buka = raw_record.get("tgl_buka") or None
        tgl_tutup = raw_record.get("tgl_tutup") or None
        syarat = normalize_text(raw_record.get("syarat", "")) or None
        kontak_email = raw_record.get("kontak_email") or None

        normalized = {
            "source": source,
            "source_id": sid,
            "source_url": surl,
            "perusahaan_source_id": co_sid,
            "perusahaan_nama": sanitize_csv_cell(co_nama),
            "perusahaan_id": co_id,
            "judul": sanitize_csv_cell(judul),
            "slug": slug,
            "deskripsi": sanitize_csv_cell(deskripsi) if deskripsi else None,
            "lokasi": sanitize_csv_cell(lokasi) if lokasi else None,
            "durasi": sanitize_csv_cell(durasi) if durasi else None,
            "kuota": kuota,
            "status": status,
            "tgl_buka": tgl_buka,
            "tgl_tutup": tgl_tutup,
            "syarat": sanitize_csv_cell(syarat) if syarat else None,
            "kontak_email": kontak_email,
            "scraped_at": now_iso
        }

        existing_id, existing_rec = self.find_existing(normalized)

        if not existing_rec:
            # INSERT
            self.records_by_id[sid] = normalized
            if surl:
                self.records_by_url[surl] = sid
            if slug:
                self.records_by_slug[slug] = sid
            return "inserted", normalized

        # Compare fields to determine if updated or unchanged
        changed = False
        for field in COMPARE_FIELDS:
            new_val = normalized.get(field)
            old_val = existing_rec.get(field)
            if new_val != old_val and new_val is not None:
                changed = True
                break

        if changed:
            # UPDATE
            merged = dict(existing_rec)
            merged.update({k: v for k, v in normalized.items() if v is not None})
            merged["scraped_at"] = now_iso
            self.records_by_id[existing_id] = merged
            return "updated", merged
        else:
            # UNCHANGED
            return "unchanged", existing_rec

    def get_all_records(self) -> List[Dict[str, Any]]:
        """Return all deduplicated records."""
        return list(self.records_by_id.values())
