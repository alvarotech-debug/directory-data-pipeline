"""
Base extractor and record schema for directory data extraction.

All directory sources map their data into DirectoryRecord format,
providing a unified interface for downstream processing regardless
of the source API's native response structure.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
import logging

from config.settings import SourceConfig


@dataclass
class DirectoryRecord:
    """
    Standardized record from any professional directory.

    Designed to be flexible enough to represent:
    - Professional licenses (architects, doctors, lawyers)
    - Business directory entries
    - Author/creator registries
    - Any entity with name + details + location
    """

    source: str
    record_id: str
    full_name: str
    title: str | None = None
    organization: str | None = None
    specialization: str | None = None
    location: str | None = None
    country: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    website: str | None = None
    registration_id: str | None = None
    status: str | None = None
    profile_url: str | None = None
    raw_data: dict | None = None
    extracted_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Serialize to dictionary, excluding raw_data."""
        d = {k: v for k, v in self.__dict__.items() if k != "raw_data"}
        d["extracted_at"] = self.extracted_at.isoformat()
        return d


class BaseDirectoryExtractor(ABC):
    """
    Abstract extractor for directory/registry data sources.

    Subclasses implement source-specific extraction logic and
    mapping from raw API responses to DirectoryRecord.
    """

    def __init__(
        self,
        config: SourceConfig,
        logger: logging.Logger | None = None,
    ) -> None:
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._records_extracted: int = 0

    @abstractmethod
    async def extract_all(self) -> list[DirectoryRecord]:
        """Extract all records from this directory source."""
        ...

    @abstractmethod
    def _map_to_record(self, raw: dict) -> DirectoryRecord | None:
        """Map a single raw API response to DirectoryRecord."""
        ...

    @property
    def stats(self) -> dict:
        """Extraction statistics."""
        return {
            "source": self.config.name,
            "records_extracted": self._records_extracted,
            "api_endpoint": self.config.api_endpoint,
        }
