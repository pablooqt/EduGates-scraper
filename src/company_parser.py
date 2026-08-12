import re
import uuid


def normalize_company_name(nama: str) -> str:
    """Normalize legal entity formatting in company names."""
    if not nama:
        return ""
    clean = nama.strip()
    clean = re.sub(r'\bPT\.?\b', 'PT', clean, flags=re.I)
    clean = re.sub(r'\bCV\.?\b', 'CV', clean, flags=re.I)
    clean = re.sub(r'\bUD\.?\b', 'UD', clean, flags=re.I)
    clean = re.sub(r'\s+', ' ', clean).strip()
    return clean


def derive_perusahaan_id(perusahaan_source_id: str, perusahaan_nama: str, source: str = "maganghub") -> str:
    """
    Derive deterministic internal perusahaan_id with source prefix.
    Prefers perusahaan_source_id.
    Fallbacks to deterministic UUID v5 from normalized company name.
    """
    if perusahaan_source_id and len(perusahaan_source_id.strip()) > 0:
        return f"{source}-{perusahaan_source_id.strip()}"

    clean_name = normalize_company_name(perusahaan_nama).lower()
    if clean_name:
        comp_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{source}:perusahaan:{clean_name}"))
        return f"{source}-company-{comp_uuid[:8]}"

    return f"{source}-company-unknown"
