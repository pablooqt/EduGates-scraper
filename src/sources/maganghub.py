import json
import re
import math
import random
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup
from src.sources.base import BaseSource
from src.sources.registry import SourceRegistry

SORT_OPTIONS = {
    "most_quota": "sort=most_quota",
    "latest": "sort=latest",
    "most_applicant": "sort=most_applicant",
    "default": "",
}


@SourceRegistry.register
class MagangHubSource(BaseSource):
    """MagangHub (Kemnaker) internship scraper source implementation."""

    SORT_PARAM = "sort=most_quota"

    @property
    def name(self) -> str:
        return "maganghub"

    @property
    def base_url(self) -> str:
        return "https://maganghub.kemnaker.go.id/magang-nasional"

    def resolve_sort_param(self, sort_name: Optional[str] = None) -> str:
        """Resolve sort parameter string based on sort choice."""
        if not sort_name:
            return self.SORT_PARAM
        sort_lower = sort_name.lower()
        if sort_lower == "random":
            return random.choice(list(SORT_OPTIONS.values()))
        return SORT_OPTIONS.get(sort_lower, f"sort={sort_name}")

    def discover_pagination(self, client: Any, sort_param: Optional[str] = None) -> Dict[str, Any]:
        """Fetch page 1 with sort parameter and extract total count and last page."""
        sp = sort_param if sort_param is not None else self.SORT_PARAM
        sep = "&" if sp else ""
        url = f"{self.base_url}/lowongan?{sp}{sep}page=1" if sp else f"{self.base_url}/lowongan?page=1"
        html = client.get(url)
        soup = BeautifulSoup(html, 'html.parser')

        # Check summary text: "Menampilkan 18 dari 28455 lowongan"
        total = None
        summary_el = soup.find(string=re.compile(r'Menampilkan\s+.*?dari\s+.*?lowongan', re.DOTALL))
        if summary_el:
            m = re.search(r'Menampilkan\s+.*?(\d+)\s+dari\s+([\d\.]+)\s+lowongan', summary_el.strip())
            if m:
                total = int(m.group(2).replace('.', ''))

        if total is None:
            nav = soup.find('nav', attrs={'aria-label': 'pagination'})
            if nav:
                page_links = nav.find_all('a', string=re.compile(r'^\d+$'))
                if page_links:
                    last_num = int(page_links[-1].get_text(strip=True))
                    total = last_num * 18

        if total is None:
            total = 0

        per_page = 18
        last_page = math.ceil(total / per_page) if total > 0 else 1

        return {
            "total": total,
            "per_page": per_page,
            "last_page": last_page,
            "sort_param": sp
        }

    def fetch_listing_page(self, client: Any, page: int, sort_param: Optional[str] = None) -> str:
        """Fetch raw HTML listing for given page number with sort parameter."""
        sp = sort_param if sort_param is not None else self.SORT_PARAM
        sep = "&" if sp else ""
        url = f"{self.base_url}/lowongan?{sp}{sep}page={page}" if sp else f"{self.base_url}/lowongan?page={page}"
        return client.get(url)

    def parse_listing(self, raw_content: str) -> List[Dict[str, Any]]:
        """Parse vacancy cards from listing page HTML."""
        soup = BeautifulSoup(raw_content, 'html.parser')
        cards = soup.find_all('a', href=re.compile(r'/magang-nasional/lowongan/[^?#]+'))

        parsed_items: List[Dict[str, Any]] = []
        seen_ids = set()

        for a in cards:
            href = a.get('href', '')
            uuid_match = re.search(r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$', href, re.I)
            if not uuid_match:
                continue

            source_id = uuid_match.group(1)
            if source_id in seen_ids:
                continue
            seen_ids.add(source_id)

            # Extract base slug from URL (not used in output, kept for URL parsing)
            card_div = a.find('div') or a

            # Judul
            title_el = card_div.find(['h3', 'h4', 'h2'])
            judul = title_el.get_text(strip=True) if title_el else None

            # Text lines inside card
            card_text = card_div.get_text("\n", strip=True)
            lines = [line.strip() for line in card_text.split("\n") if line.strip()]

            # Company name is line after title
            perusahaan_nama = None
            if len(lines) > 1:
                for line in lines[1:]:
                    if line != judul and len(line) > 2 and "Kuota:" not in line and "Pelamar:" not in line and "Peluang" not in line:
                        perusahaan_nama = line
                        break

            # Lokasi
            lokasi = None
            map_pin = card_div.find('svg', class_=re.compile(r'map-pin'))
            if map_pin and map_pin.parent:
                lokasi = map_pin.parent.get_text(strip=True)

            # Kuota
            kuota = None
            kuota_match = re.search(r'Kuota:\s*(\d+)', card_text)
            if kuota_match:
                kuota = int(kuota_match.group(1))

            full_url = f"https://maganghub.kemnaker.go.id{href}" if href.startswith('/') else href

            parsed_items.append({
                "source": "maganghub",
                "source_id": source_id,
                "source_url": full_url,
                "judul": judul,
                "perusahaan_nama": perusahaan_nama,
                "lokasi": lokasi,
                "kuota": kuota,
                "status": "Aktif"
            })

        return parsed_items

    def fetch_detail(self, client: Any, item: Dict[str, Any]) -> Optional[str]:
        """Fetch detail page HTML for a given card item."""
        source_url = item.get("source_url")
        if not source_url:
            return None
        return client.get(source_url)

    def parse_detail(self, raw_content: str) -> Dict[str, Any]:
        """Parse detail page HTML into authoritative fields."""
        soup = BeautifulSoup(raw_content, 'html.parser')

        # Layer 1: Extract RSC/Next.js script payload data
        rsc_text = self._extract_rsc_text(soup)

        tgl_buka = self._rsc_date(rsc_text, "participantRegistrationStartDate")
        if tgl_buka is None:
            tgl_buka = self._rsc_date(rsc_text, "registrationStartDate")

        tgl_tutup = self._rsc_date(rsc_text, "participantRegistrationEndDate")
        if tgl_tutup is None:
            tgl_tutup = self._rsc_date(rsc_text, "registrationEndDate")

        kontak_email = self._rsc_organizer_email(rsc_text)
        kuota_rsc = self._rsc_int(rsc_text, "quantityNeeded")
        lokasi_rsc = self._rsc_city(rsc_text)

        # Layer 2: HTML DOM extraction
        h1 = soup.find('h1')
        judul = h1.get_text(strip=True) if h1 else None

        deskripsi = self._parse_section_text(soup, 'Deskripsi Lowongan')
        syarat = self._parse_kualifikasi(soup)

        co_link = soup.find('a', href=re.compile(r'/magang-nasional/penyelenggara/'))
        perusahaan_source_id = None
        perusahaan_nama = None

        if co_link:
            href = co_link.get('href', '')
            uuid_match = re.search(
                r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$',
                href, re.I
            )
            if uuid_match:
                perusahaan_source_id = uuid_match.group(1)

            co_h3 = co_link.find(['h3', 'h4', 'h2'])
            if co_h3:
                perusahaan_nama = co_h3.get_text(strip=True)
            else:
                txt = co_link.get_text("\n", strip=True)
                lines = [l.strip() for l in txt.split("\n") if l.strip()]
                if lines:
                    perusahaan_nama = lines[0]

        if not perusahaan_nama:
            perusahaan_nama = self._rsc_str(rsc_text, "name", context="organizer")

        lokasi = lokasi_rsc or self._parse_lokasi_html(soup)

        return {
            "judul": judul,
            "deskripsi": deskripsi,
            "syarat": syarat,
            "lokasi": lokasi,
            "kuota": kuota_rsc,
            "perusahaan_source_id": perusahaan_source_id,
            "perusahaan_nama": perusahaan_nama,
            "tgl_buka": tgl_buka,
            "tgl_tutup": tgl_tutup,
            "kontak_email": kontak_email,
        }

    def _extract_rsc_text(self, soup: BeautifulSoup) -> str:
        parts = []
        for sc in soup.find_all('script'):
            content = sc.string or ''
            if 'self.__next_f.push' not in content:
                continue
            m = re.match(
                r'self\.__next_f\.push\(\[1,(".*")\]\s*\);?$',
                content.strip(), re.DOTALL
            )
            if m:
                try:
                    parts.append(json.loads(m.group(1)))
                except Exception:
                    pass
        return " ".join(parts)

    def _rsc_str(self, text: str, field: str, context: str = "") -> Optional[str]:
        if context:
            ctx_idx = text.find(f'"{context}"')
            if ctx_idx < 0:
                return None
            search_region = text[ctx_idx:ctx_idx + 2000]
        else:
            search_region = text
        m = re.search(rf'"{re.escape(field)}"\s*:\s*"([^"]*)"', search_region)
        return m.group(1) if m else None

    def _rsc_int(self, text: str, field: str) -> Optional[int]:
        m = re.search(rf'"{re.escape(field)}"\s*:\s*(\d+)', text)
        return int(m.group(1)) if m else None

    def _rsc_date(self, text: str, field: str) -> Optional[str]:
        m = re.search(rf'"{re.escape(field)}"\s*:\s*"(\d{{4}}-\d{{2}}-\d{{2}})', text)
        return m.group(1) if m else None

    def _rsc_organizer_email(self, text: str) -> Optional[str]:
        org_idx = text.find('"organizer"')
        if org_idx < 0:
            return None
        region = text[org_idx:org_idx + 1500]
        m = re.search(r'"email"\s*:\s*"([^"@\s]+@[^"]+)"', region)
        if m:
            email = m.group(1).strip()
            return email if email else None
        return None

    def _rsc_city(self, text: str) -> Optional[str]:
        m = re.search(r'"city"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]+)"', text)
        return m.group(1) if m else None

    def _parse_section_text(self, soup: BeautifulSoup, heading: str) -> Optional[str]:
        h2 = soup.find(lambda t: t.name == 'h2' and heading in t.get_text())
        if not h2:
            return None
        sec = h2.find_parent('section')
        if not sec:
            return None
        div = sec.find('div')
        raw = div.get_text("\n", strip=True) if div else sec.get_text("\n", strip=True)
        lines = [l.strip() for l in raw.split("\n") if l.strip() and heading not in l]
        return " | ".join(lines).strip() or None

    def _parse_kualifikasi(self, soup: BeautifulSoup) -> Optional[str]:
        qual_h2 = soup.find(lambda t: t.name == 'h2' and 'Kualifikasi' in t.get_text())
        if not qual_h2:
            return None
        sec = qual_h2.find_parent('section')
        if not sec:
            return None

        EXCLUDED_LABELS = frozenset({
            'hari kerja per minggu', 'hari/minggu', 'hari kerja',
            'durasi magang', 'working days',
        })

        parts = []
        for item_div in sec.find_all('div', class_=lambda c: c and 'flex' in c and 'items-start' in c):
            span = item_div.find('span', class_=lambda c: c and 'text-muted-foreground' in c)
            if not span:
                continue

            strong = span.find('strong')
            if strong:
                label_parts = [t.strip() for t in span.find_all(string=True, recursive=False)]
                label = ' '.join(label_parts).strip().rstrip(':').strip()
                value = strong.get_text(strip=True)

                if any(excl in label.lower() for excl in EXCLUDED_LABELS):
                    continue
                if any(excl in value.lower() for excl in EXCLUDED_LABELS):
                    continue
                if re.match(r'^\d+\s+hari', value.lower()):
                    continue

                if label and value:
                    parts.append(f"{label}: {value}")
            else:
                full_text = span.get_text(strip=True)
                if any(excl in full_text.lower() for excl in EXCLUDED_LABELS):
                    continue
                if re.search(r'\d+\s+hari\s+kerja', full_text, re.I):
                    continue
                if full_text:
                    parts.append(full_text)

        return " | ".join(parts) if parts else None

    def _parse_lokasi_html(self, soup: BeautifulSoup) -> Optional[str]:
        h2 = soup.find(lambda t: t.name == 'h2' and 'Lokasi Magang' in t.get_text())
        if not h2:
            return None
        sec = h2.find_parent('section')
        if not sec:
            return None
        divs = sec.find_all('div', class_=lambda c: c and 'text-sm' in c)
        for div in divs:
            txt = div.get_text(strip=True)
            if txt and 'Lokasi Magang' not in txt:
                return txt
        return None
