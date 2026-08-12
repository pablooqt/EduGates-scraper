import re

INDONESIAN_MONTHS = {
    "januari": "01", "jan": "01",
    "februari": "02", "feb": "02",
    "maret": "03", "mar": "03",
    "april": "04", "apr": "04",
    "mei": "05",
    "juni": "06", "jun": "06",
    "juli": "07", "jul": "07",
    "agustus": "08", "agu": "08", "agt": "08",
    "september": "09", "sep": "09",
    "oktober": "10", "okt": "10",
    "november": "11", "nov": "11",
    "desember": "12", "des": "12",
}


def normalize_text(text: str, join_delimiter: str = " | ") -> str:
    """Clean whitespace and flatten multi-line text into a single line string to prevent CSV line splits."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    result = join_delimiter.join(lines).strip()
    return result


def normalize_quota(val: any) -> any:
    """Convert quota string or number into integer or None."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    val_str = str(val).strip()
    match = re.search(r'(\d+)', val_str)
    if match:
        return int(match.group(1))
    return None


def normalize_status(val: str) -> str:
    """Normalize status to 'Aktif' or 'Tutup'."""
    if not val:
        return "Aktif"
    val_lower = str(val).lower()
    if any(term in val_lower for term in ["tutup", "closed", "berakhir", "expired", "ditutup"]):
        return "Tutup"
    return "Aktif"


def normalize_date(val: str) -> any:
    """Parse Indonesian dates (e.g. '15 Agustus 2026') to 'YYYY-MM-DD'."""
    if not val or not isinstance(val, str):
        return None
    val_clean = val.strip().lower()
    m = re.search(r'(\d{1,2})\s+([a-z]+)\s+(\d{4})', val_clean)
    if m:
        day = int(m.group(1))
        month_str = m.group(2)
        year = int(m.group(3))
        if month_str in INDONESIAN_MONTHS:
            month = INDONESIAN_MONTHS[month_str]
            return f"{year:04d}-{month}-{day:02d}"
    m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', val_clean)
    if m_iso:
        return m_iso.group(0)
    return None


def normalize_slug(judul: str, source_id: str, slug: str = None) -> str:
    """Generate a clean, unique, and deterministic slug."""
    raw_slug = slug or judul or f"vacancy-{source_id}"
    base_slug = raw_slug.strip().lower()
    # Strip any trailing uuid if already attached
    base_slug = re.sub(r'-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', '', base_slug, flags=re.I)
    base_slug = re.sub(r'[^a-z0-9\-]+', '-', base_slug)
    base_slug = re.sub(r'-+', '-', base_slug).strip('-')
    
    if not base_slug:
        base_slug = "vacancy"
        
    return f"{base_slug}-{source_id}"


def sanitize_csv_cell(val: any) -> any:
    """Sanitize string values starting with formula characters to prevent CSV injection and remove inline newlines."""
    if isinstance(val, str) and val:
        cleaned = val.replace('\r\n', ' | ').replace('\r', ' | ').replace('\n', ' | ').strip()
        if cleaned and cleaned[0] in ('=', '+', '-', '@'):
            return "'" + cleaned
        return cleaned
    return val
