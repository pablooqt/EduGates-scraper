"""
Glints Source — scrapes internship vacancies specifically from Glints Indonesia (glints.com/id).
Filters exclusively for INTERNSHIP employment type.
Uses Glints internal v2-alc GraphQL API (/api/v2-alc/graphql?op=searchJobsV3) and Next.js __NEXT_DATA__ payload.
"""

import json
import re
import math
import logging
import httpx
from typing import Dict, List, Any, Optional
from bs4 import BeautifulSoup

from src.sources.base import BaseSource
from src.sources.registry import SourceRegistry

logger = logging.getLogger("glints")

GLINTS_GRAPHQL_ENDPOINT = "https://glints.com/api/v2-alc/graphql?op=searchJobsV3"
GLINTS_EXPLORE_URL = "https://glints.com/id/opportunities/jobs/explore?country=ID&jobTypes=INTERNSHIP"
GLINTS_JOB_BASE_URL = "https://glints.com/id/opportunities/jobs"

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "application/json, text/html, */*",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Origin": "https://glints.com",
    "Referer": GLINTS_EXPLORE_URL,
    "x-glints-country-code": "ID",
}

GRAPHQL_QUERY = """query searchJobsV3($data: JobSearchConditionInput!) {
  searchJobsV3(data: $data) {
    jobsInPage {
      id
      title
      workArrangementOption
      status
      createdAt
      updatedAt
      educationLevel
      type
      minYearsOfExperience
      company {
        id
        name
        brandName
        logo
      }
      citySubDivision {
        name
      }
      city {
        id
        name
      }
      country {
        code
        name
      }
      location {
        formattedName
        slug
      }
      links {
        slug
      }
    }
    expInfo
    hasMore
  }
}"""


@SourceRegistry.register
class GlintsSource(BaseSource):
    """Glints internship scraper source implementation."""

    @property
    def name(self) -> str:
        return "glints"

    @property
    def base_url(self) -> str:
        return "https://glints.com/id"

    def discover_pagination(self, client: Any, sort_param: Optional[str] = None) -> Dict[str, Any]:
        """Fetch Page 1 internships to discover total count and boundaries."""
        logger.info("[Glints] Discovering internship vacancies on Glints Indonesia...")

        jobs = self._fetch_graphql_jobs(client, page=1)
        if not jobs:
            jobs = self._fetch_nextdata_jobs(client, page=1)

        total = len(jobs)
        per_page = 30
        last_page = math.ceil(total / per_page) if total > 0 else 1

        logger.info(f"[Glints] Discovered {total} active internship vacancies.")
        return {
            "total": total,
            "per_page": per_page,
            "last_page": last_page,
            "sort_param": ""
        }

    def fetch_listing_page(self, client: Any, page: int, sort_param: Optional[str] = None) -> str:
        """Fetch raw JSON listing string for given page number."""
        jobs = self._fetch_graphql_jobs(client, page=page)
        if not jobs and page == 1:
            jobs = self._fetch_nextdata_jobs(client, page=1)
        return json.dumps(jobs)

    def parse_listing(self, raw_content: str) -> List[Dict[str, Any]]:
        """Parse list of Glints internship cards from raw JSON string."""
        try:
            jobs = json.loads(raw_content)
        except Exception:
            return []

        if not isinstance(jobs, list):
            return []

        parsed_items: List[Dict[str, Any]] = []

        for job in jobs:
            if not isinstance(job, dict):
                continue

            job_id = job.get("id")
            if not job_id:
                continue

            # Ensure filter: only INTERNSHIP
            job_type = str(job.get("type") or "").upper()
            if job_type and "INTERNSHIP" not in job_type and "MAGANG" not in job_type:
                continue

            # Extract slug
            slug = None
            links = job.get("links")
            if isinstance(links, list) and links:
                slug = links[0].get("slug") if isinstance(links[0], dict) else None
            elif isinstance(links, dict):
                slug = links.get("slug")

            loc_obj = job.get("location") or {}
            loc_slug = loc_obj.get("slug") if isinstance(loc_obj, dict) else None

            title_slug = self._slugify(job.get("title") or "internship")
            final_slug = slug or loc_slug or title_slug

            source_url = f"{GLINTS_JOB_BASE_URL}/{final_slug}/{job_id}"

            # Company
            company = job.get("company") or {}
            perusahaan_nama = company.get("name") if isinstance(company, dict) else None
            perusahaan_source_id = company.get("id") if isinstance(company, dict) else None

            # Location
            lokasi = None
            if isinstance(loc_obj, dict) and loc_obj.get("formattedName"):
                lokasi = loc_obj.get("formattedName")
            else:
                city = job.get("city") or {}
                if isinstance(city, dict):
                    lokasi = city.get("name")

            # Dates
            created_at = job.get("createdAt")
            tgl_buka = str(created_at)[:10] if created_at else None

            # Status
            raw_status = str(job.get("status") or "OPEN").upper()
            status = "Aktif" if raw_status in ("OPEN", "ACTIVE") else "Tutup"

            parsed_items.append({
                "source": "glints",
                "source_id": str(job_id),
                "source_url": source_url,
                "judul": job.get("title"),
                "perusahaan_nama": perusahaan_nama,
                "perusahaan_source_id": perusahaan_source_id,
                "lokasi": lokasi,
                "status": status,
                "tgl_buka": tgl_buka,
                "tgl_tutup": None,
                "kuota": None,
            })

        return parsed_items

    def fetch_detail(self, client: Any, item: Dict[str, Any]) -> Optional[str]:
        """Fetch detail page HTML for a given Glints internship item."""
        source_url = item.get("source_url")
        if not source_url:
            return None
        try:
            return client.get(source_url)
        except Exception as exc:
            logger.warning(f"[Glints] Error fetching detail page for {source_url}: {exc}")
            return None

    def parse_detail(self, raw_content: str) -> Dict[str, Any]:
        """Parse detail page HTML into authoritative fields (deskripsi, syarat, dates, company)."""
        if not raw_content:
            return {}

        soup = BeautifulSoup(raw_content, "html.parser")
        detail_fields: Dict[str, Any] = {}

        # Strategy 1: Extract from __NEXT_DATA__ script tag
        next_data_el = soup.find("script", id="__NEXT_DATA__")
        if next_data_el and next_data_el.string:
            try:
                data = json.loads(next_data_el.string)
                page_props = data.get("props", {}).get("pageProps", {})
                initial_data = page_props.get("initialData", {})
                job = initial_data.get("data", {}) if isinstance(initial_data, dict) else {}

                if isinstance(job, dict) and job:
                    # Deskripsi from descriptionJsonString
                    desc_str = None
                    desc_json_str = job.get("descriptionJsonString")
                    if desc_json_str:
                        try:
                            desc_obj = json.loads(desc_json_str)
                            blocks = desc_obj.get("blocks", [])
                            lines = [b.get("text", "").strip() for b in blocks if isinstance(b, dict) and b.get("text", "").strip()]
                            desc_str = " | ".join(lines) if lines else None
                        except Exception:
                            desc_str = str(desc_json_str)

                    # Syarat / Skills / Education
                    syarat_parts = []
                    edu = job.get("educationLevel")
                    if edu:
                        syarat_parts.append(f"Tingkat Pendidikan: {edu}")

                    exp = job.get("minYearsOfExperience")
                    if exp is not None:
                        syarat_parts.append(f"Pengalaman Minimal: {exp} tahun")

                    skills = job.get("skills", [])
                    if isinstance(skills, list):
                        skill_names = [s.get("skill", {}).get("name") for s in skills if isinstance(s, dict) and s.get("skill", {}).get("name")]
                        if skill_names:
                            syarat_parts.append(f"Keahlian: {', '.join(skill_names)}")

                    syarat_str = " | ".join(syarat_parts) if syarat_parts else None

                    # Company
                    comp = job.get("company") or {}
                    if isinstance(comp, dict):
                        if comp.get("name"):
                            detail_fields["perusahaan_nama"] = comp.get("name")
                        if comp.get("id"):
                            detail_fields["perusahaan_source_id"] = comp.get("id")

                    # Dates
                    if job.get("createdAt"):
                        detail_fields["tgl_buka"] = str(job.get("createdAt"))[:10]
                    if job.get("expiryDate"):
                        detail_fields["tgl_tutup"] = str(job.get("expiryDate"))[:10]

                    if desc_str:
                        detail_fields["deskripsi"] = desc_str
                    if syarat_str:
                        detail_fields["syarat"] = syarat_str
            except Exception as exc:
                logger.warning(f"[Glints] Error parsing __NEXT_DATA__ detail: {exc}")

        # Strategy 2: Fallback to HTML DOM parsing if deskripsi or syarat is missing
        if not detail_fields.get("deskripsi") or not detail_fields.get("syarat"):
            dom_desc, dom_syarat = self._parse_detail_dom(soup)
            if not detail_fields.get("deskripsi") and dom_desc:
                detail_fields["deskripsi"] = dom_desc
            if not detail_fields.get("syarat") and dom_syarat:
                detail_fields["syarat"] = dom_syarat

        return detail_fields

    def _fetch_graphql_jobs(self, client: Any, page: int = 1) -> List[Dict[str, Any]]:
        """Fetch Glints internship jobs via GraphQL API POST."""
        payload = {
            "operationName": "searchJobsV3",
            "variables": {
                "data": {
                    "CountryCode": "ID",
                    "type": ["INTERNSHIP"],
                    "includeExternalJobs": True,
                    "pageSize": 30,
                    "page": page
                }
            },
            "query": GRAPHQL_QUERY
        }

        try:
            if hasattr(client, "post"):
                res = client.post(GLINTS_GRAPHQL_ENDPOINT, json=payload, headers=DEFAULT_HEADERS)
            else:
                r = httpx.post(GLINTS_GRAPHQL_ENDPOINT, json=payload, headers=DEFAULT_HEADERS, timeout=30.0, verify=False)
                res = r.json() if r.status_code == 200 else {}

            if isinstance(res, dict):
                search_res = res.get("data", {}).get("searchJobsV3", {})
                jobs = search_res.get("jobsInPage", [])
                if isinstance(jobs, list):
                    return jobs
        except Exception as exc:
            logger.warning(f"[Glints] GraphQL fetch error for page {page}: {exc}")

        return []

    def _fetch_nextdata_jobs(self, client: Any, page: int = 1) -> List[Dict[str, Any]]:
        """Fallback: fetch Glints explore HTML page and parse __NEXT_DATA__."""
        url = f"https://glints.com/id/opportunities/jobs/explore?country=ID&jobTypes=INTERNSHIP&page={page}"
        try:
            html = client.get(url)
            soup = BeautifulSoup(html, "html.parser")
            next_data_el = soup.find("script", id="__NEXT_DATA__")
            if next_data_el and next_data_el.string:
                data = json.loads(next_data_el.string)
                page_props = data.get("props", {}).get("pageProps", {})
                initial_jobs = page_props.get("initialJobs", {})
                jobs = initial_jobs.get("jobsInPage", [])
                if isinstance(jobs, list):
                    return jobs
        except Exception as exc:
            logger.warning(f"[Glints] __NEXT_DATA__ fetch error for page {page}: {exc}")

        return []

    def _parse_detail_dom(self, soup: BeautifulSoup) -> tuple[Optional[str], Optional[str]]:
        """Fallback DOM text parsing for detail page."""
        main_el = soup.find("main") or soup.find("body")
        if not main_el:
            return None, None

        raw_text = main_el.get_text("\n", strip=True)
        lines = [l.strip() for l in raw_text.split("\n") if l.strip()]

        if not lines:
            return None, None

        full_str = " | ".join(lines)
        return full_str[:1500], None

    def _slugify(self, text: str) -> str:
        """Convert text to URL slug."""
        text = text.lower()
        text = re.sub(r'[^a-z0-9\s-]', '', text)
        text = re.sub(r'[\s-]+', '-', text).strip('-')
        return text or "internship"
