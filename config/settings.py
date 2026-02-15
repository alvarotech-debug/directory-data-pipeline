"""
Pipeline configuration.

All settings loaded from environment variables with sensible defaults.
"""

from dataclasses import dataclass, field
from pathlib import Path
import os


@dataclass
class SourceConfig:
    """Configuration for a single directory/registry source."""

    name: str
    base_url: str
    api_endpoint: str
    pagination_type: str  # "offset" | "cursor" | "page_number" | "link_header" | "none"
    page_size: int = 50
    rate_limit: float = 1.0
    max_concurrent: int = 5
    timeout: int = 30
    total_records: int | None = None
    headers: dict = field(default_factory=dict)
    auth_required: bool = False


@dataclass
class QualityThresholds:
    """Minimum quality standards for the pipeline."""

    min_completeness: float = 0.90
    min_uniqueness: float = 1.0
    min_format_compliance: float = 0.85
    max_duplicate_rate: float = 0.01


@dataclass
class Settings:
    """Application-wide settings."""

    # Data directories
    data_dir: Path = Path(os.getenv("DATA_DIR", "data"))
    bronze_dir: Path = field(init=False)
    silver_dir: Path = field(init=False)
    gold_dir: Path = field(init=False)

    # Database (optional — CSV by default)
    db_url: str | None = os.getenv("DATABASE_URL", None)

    # Extraction settings
    max_retries: int = 3
    backoff_factor: float = 2.0
    request_timeout: int = 30

    # Quality thresholds
    quality: QualityThresholds = field(default_factory=QualityThresholds)

    # Source configurations
    sources: list[SourceConfig] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.bronze_dir = self.data_dir / "bronze"
        self.silver_dir = self.data_dir / "silver"
        self.gold_dir = self.data_dir / "gold"

        for d in [self.bronze_dir, self.silver_dir, self.gold_dir]:
            d.mkdir(parents=True, exist_ok=True)

        if not self.sources:
            self.sources = [
                SourceConfig(
                    name="openlibrary_authors",
                    base_url="https://openlibrary.org",
                    api_endpoint="/search/authors.json",
                    pagination_type="offset",
                    page_size=100,
                    rate_limit=1.0,
                    max_concurrent=3,
                ),
                SourceConfig(
                    name="random_professionals",
                    base_url="https://randomuser.me",
                    api_endpoint="/api/",
                    pagination_type="page_number",
                    page_size=100,
                    rate_limit=0.5,
                    max_concurrent=5,
                    total_records=2000,
                ),
                SourceConfig(
                    name="countries_registry",
                    base_url="https://restcountries.com",
                    api_endpoint="/v3.1/all",
                    pagination_type="none",
                    rate_limit=0.5,
                ),
            ]
