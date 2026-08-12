from abc import ABC, abstractmethod
from typing import Dict, List, Any, Tuple, Optional


class BaseSource(ABC):
    """
    Abstract Base Class for Scraper Sources.
    Allows easy addition of new internship platform sources.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for the source (e.g. 'maganghub')."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Base URL of the source platform."""
        pass

    @abstractmethod
    def discover_pagination(self, client: Any) -> Dict[str, Any]:
        """
        Discover pagination details (total records, per page, last page).
        Returns dict with keys: 'total', 'per_page', 'last_page'
        """
        pass

    @abstractmethod
    def fetch_listing_page(self, client: Any, page: int) -> str:
        """Fetch raw listing page content (HTML or JSON) for given page number."""
        pass

    @abstractmethod
    def parse_listing(self, raw_content: str) -> List[Dict[str, Any]]:
        """Parse raw listing content into a list of card item dicts."""
        pass

    @abstractmethod
    def fetch_detail(self, client: Any, item: Dict[str, Any]) -> Optional[str]:
        """Fetch detail page content for a specific item if needed."""
        pass

    @abstractmethod
    def parse_detail(self, raw_content: str) -> Dict[str, Any]:
        """Parse detail page content into additional fields dict."""
        pass
