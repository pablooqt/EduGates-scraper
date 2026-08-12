"""
Data models for internship vacancy records.
Inspired by ScrapingPython dataclass patterns for strong typing,
predictable schema, and strict CSV column ordering.
"""

from dataclasses import dataclass, field, asdict
from typing import Dict, Any, Optional

CSV_SCHEMA_COLUMNS = [
    "source",
    "source_id",
    "source_url",
    "perusahaan_source_id",
    "perusahaan_nama",
    "perusahaan_id",
    "judul",
    "deskripsi",
    "lokasi",
    "kuota",
    "status",
    "tgl_buka",
    "tgl_tutup",
    "syarat",
    "kontak_email",
    "scraped_at"
]


@dataclass
class VacancyRecord:
    source: str = "maganghub"
    source_id: str = ""
    source_url: str = ""
    perusahaan_source_id: Optional[str] = None
    perusahaan_nama: Optional[str] = None
    perusahaan_id: Optional[str] = None
    judul: Optional[str] = None
    deskripsi: Optional[str] = None
    lokasi: Optional[str] = None
    kuota: Optional[int] = None
    status: str = "Aktif"
    tgl_buka: Optional[str] = None
    tgl_tutup: Optional[str] = None
    syarat: Optional[str] = None
    kontak_email: Optional[str] = None
    scraped_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert record to a dictionary matching CSV_SCHEMA_COLUMNS ordering exactly."""
        raw_dict = asdict(self)
        return {col: raw_dict.get(col, None) for col in CSV_SCHEMA_COLUMNS}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "VacancyRecord":
        """Construct VacancyRecord instance safely from a raw dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)
