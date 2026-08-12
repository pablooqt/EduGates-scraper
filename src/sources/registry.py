from typing import Dict, Type, List
from src.sources.base import BaseSource


class SourceRegistry:
    """Registry and factory for scraper sources."""

    _registry: Dict[str, Type[BaseSource]] = {}

    @classmethod
    def register(cls, source_class: Type[BaseSource]) -> Type[BaseSource]:
        """Decorator or function to register a source class."""
        instance = source_class()
        cls._registry[instance.name.lower()] = source_class
        return source_class

    @classmethod
    def get_source(cls, name: str) -> BaseSource:
        """Instantiate and return source by name."""
        name_lower = name.lower()
        if name_lower not in cls._registry:
            valid_sources = list(cls._registry.keys())
            raise ValueError(f"Unknown source '{name}'. Available sources: {valid_sources}")
        return cls._registry[name_lower]()

    @classmethod
    def list_sources(cls) -> List[str]:
        """List registered source names."""
        return list(cls._registry.keys())
