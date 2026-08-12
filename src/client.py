import time
import logging
import httpx
from typing import Dict, Any, Optional
from playwright.sync_api import sync_playwright, Browser, Page, Playwright

logger = logging.getLogger(__name__)

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,id;q=0.8",
}


class ScraperHTTPClient:
    """Robust HTTP Client wrapper with retries, exponential backoff, and rate limiting."""

    def __init__(
        self,
        timeout: float = 30.0,
        max_retries: int = 3,
        request_delay: float = 0.5,
        headers: Optional[Dict[str, str]] = None
    ):
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.headers = headers or DEFAULT_HEADERS
        self.session = httpx.Client(
            headers=self.headers,
            timeout=self.timeout,
            follow_redirects=True,
            verify=False
        )

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Perform GET request with retries and backoff."""
        attempt = 0
        backoff = 1.0

        while attempt <= self.max_retries:
            try:
                if self.request_delay > 0:
                    time.sleep(self.request_delay)

                response = self.session.get(url, params=params)

                if response.status_code == 200:
                    return response.text
                elif response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = float(retry_after) if retry_after and retry_after.isdigit() else backoff * 2
                    logger.warning(f"HTTP 429 Rate limited at {url}. Backing off for {sleep_time}s...")
                    time.sleep(sleep_time)
                elif response.status_code in (500, 502, 503, 504):
                    logger.warning(f"HTTP {response.status_code} at {url} (Attempt {attempt+1}/{self.max_retries+1})")
                else:
                    response.raise_for_status()

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning(f"Request error at {url}: {exc} (Attempt {attempt+1}/{self.max_retries+1})")

            attempt += 1
            if attempt <= self.max_retries:
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"Failed to fetch {url} after {self.max_retries + 1} attempts.")

    def post(self, url: str, json: Optional[Dict[str, Any]] = None, headers: Optional[Dict[str, str]] = None) -> Any:
        """Perform POST request with JSON body, retries and backoff. Returns parsed JSON."""
        import json as json_lib
        attempt = 0
        backoff = 1.0
        merged_headers = {**self.headers, **(headers or {})}

        while attempt <= self.max_retries:
            try:
                if self.request_delay > 0:
                    time.sleep(self.request_delay)

                response = self.session.post(url, json=json, headers=merged_headers)

                if response.status_code == 200:
                    return response.json()
                elif response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    sleep_time = float(retry_after) if retry_after and retry_after.isdigit() else backoff * 2
                    logger.warning(f"HTTP 429 Rate limited at {url}. Backing off for {sleep_time}s...")
                    time.sleep(sleep_time)
                elif response.status_code in (500, 502, 503, 504):
                    logger.warning(f"HTTP {response.status_code} at {url} (Attempt {attempt+1}/{self.max_retries+1})")
                else:
                    logger.warning(f"HTTP {response.status_code} at {url}")
                    response.raise_for_status()

            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                logger.warning(f"POST request error at {url}: {exc} (Attempt {attempt+1}/{self.max_retries+1})")

            attempt += 1
            if attempt <= self.max_retries:
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"Failed to POST {url} after {self.max_retries + 1} attempts.")

    def close(self):
        """Close the HTTP session."""
        self.session.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


class ScraperPlaywrightClient:
    """
    Playwright Browser Automation Client wrapper.
    Modeled after ScrapingPython browser navigation flow.
    Launches a single Playwright Chromium browser instance, navigates to target URLs,
    and returns page.content() HTML for parsing.
    """

    def __init__(
        self,
        headless: bool = True,
        timeout: float = 30.0,
        max_retries: int = 3,
        request_delay: float = 0.5,
        user_agent: Optional[str] = None
    ):
        self.headless = headless
        self.timeout = timeout
        self.max_retries = max_retries
        self.request_delay = request_delay
        self.user_agent = user_agent or DEFAULT_HEADERS["User-Agent"]

        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None
        self._page: Optional[Page] = None

    def start(self):
        """Initialize Playwright browser and context page."""
        logger.info(f"Launching Playwright Chromium Browser (Headless={self.headless})...")
        self._playwright = sync_playwright().start()
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context = self._browser.new_context(
            user_agent=self.user_agent,
            viewport={"width": 1280, "height": 800}
        )
        self._page = context.new_page()
        self._page.set_default_timeout(int(self.timeout * 1000))

    def get(self, url: str, params: Optional[Dict[str, Any]] = None) -> str:
        """Navigate to URL via Playwright page.goto() and return page.content() HTML."""
        if self._page is None:
            self.start()

        full_url = url
        if params:
            import urllib.parse
            query_str = urllib.parse.urlencode(params)
            full_url = f"{url}?{query_str}" if "?" not in url else f"{url}&{query_str}"

        attempt = 0
        backoff = 1.0

        while attempt <= self.max_retries:
            try:
                if self.request_delay > 0:
                    time.sleep(self.request_delay)

                logger.info(f"[Playwright] Navigating to: {full_url}")
                self._page.goto(full_url, wait_until="domcontentloaded", timeout=int(self.timeout * 1000))
                self._page.wait_for_timeout(1000)

                html_content = self._page.content()
                if html_content:
                    return html_content

            except Exception as exc:
                logger.warning(f"[Playwright] Navigation error at {full_url}: {exc} (Attempt {attempt+1}/{self.max_retries+1})")

            attempt += 1
            if attempt <= self.max_retries:
                time.sleep(backoff)
                backoff *= 2

        raise RuntimeError(f"Playwright failed to load {full_url} after {self.max_retries + 1} attempts.")

    def close(self):
        """Close browser and stop Playwright."""
        if self._browser:
            try:
                self._browser.close()
            except Exception:
                pass
            self._browser = None
        if self._playwright:
            try:
                self._playwright.stop()
            except Exception:
                pass
            self._playwright = None
        self._page = None
        logger.info("[Playwright] Browser closed.")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
