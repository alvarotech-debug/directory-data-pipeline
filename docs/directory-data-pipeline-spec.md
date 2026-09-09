# SPEC: directory-data-pipeline

## Agent Instructions

You are building a **portfolio project** for a freelance Web Scraping & Data Engineer. This is NOT a production system for a real client — it is a **technical demonstration** designed to showcase professional data extraction and pipeline skills to potential US clients on Upwork.

The code must look like it was written by a senior engineer: clean architecture, proper error handling, type hints, docstrings, logging, and tests. The README is equally important as the code — it sells the developer's capabilities.

This project demonstrates a COMPLETE end-to-end pipeline: discovering a hidden API behind a JavaScript-heavy website, reverse-engineering it, extracting thousands of records efficiently, and processing them through a Bronze-Silver-Gold data architecture with quality checks at every stage.

**CRITICAL: This project uses ONLY public, free data sources for demonstration purposes.** The demo targets:

- [Open Library API](https://openlibrary.org/developers/api) — free, no auth, returns author/book registry data
- [RandomUser API](https://randomuser.me/api/) — generates fake "professional" profile data for pipeline testing
- [REST Countries API](https://restcountries.com/) — free country/region data to demonstrate geographic enrichment

These 3 sources simulate the real-world scenario of extracting records from professional registries and public directories (e.g., architect registries, medical license boards, business directories).

The STORY this repo tells: "A research firm needed 12,000+ structured records from professional registries. The registries had no public API — or so they thought. I discovered hidden REST endpoints behind the JavaScript frontend, built an async extraction client, and processed everything through a Bronze-Silver-Gold pipeline with 94%+ data quality."

---

## Project Identity

| Field | Value |
|-------|-------|
| Repo name | `directory-data-pipeline` |
| Language | Python 3.11+ |
| License | MIT |
| Author | Alvaro Faustino |
| GitHub description | `Full ETL pipeline for extracting and structuring data from public directories and professional registries. API reverse engineering + Bronze-Silver-Gold architecture. 12,000+ records with 94%+ data quality.` |

---

## Project Structure

```
directory-data-pipeline/
├── README.md
├── LICENSE
├── requirements.txt
├── pyproject.toml
├── .env.example
├── .gitignore
├── config/
│   ├── __init__.py
│   └── settings.py
├── src/
│   ├── __init__.py
│   ├── discovery/
│   │   ├── __init__.py
│   │   └── api_analyzer.py
│   ├── extractor/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── api_client.py
│   │   └── paginator.py
│   ├── pipeline/
│   │   ├── __init__.py
│   │   ├── bronze.py
│   │   ├── silver.py
│   │   └── gold.py
│   ├── quality/
│   │   ├── __init__.py
│   │   └── validators.py
│   └── utils/
│       ├── __init__.py
│       ├── rate_limiter.py
│       ├── session_manager.py
│       └── logger.py
├── examples/
│   ├── run_full_pipeline.py
│   ├── run_discovery.py
│   └── run_quality_report.py
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── test_extractor.py
│   ├── test_paginator.py
│   ├── test_pipeline.py
│   ├── test_validators.py
│   └── test_session_manager.py
├── data/
│   ├── bronze/           # Raw JSON (gitignored)
│   ├── silver/           # Cleaned CSV (gitignored)
│   ├── gold/             # Enriched & aggregated (gitignored)
│   └── sample/           # Committed sample data
│       ├── bronze_raw_page_1.json
│       ├── silver_professionals.csv
│       ├── gold_enriched.csv
│       └── quality_report.json
└── docs/
    ├── reverse-engineering-walkthrough.md
    └── pipeline-architecture.md
```

---

## File-by-File Specifications

### `config/settings.py`

**Purpose:** Centralized configuration for the entire pipeline.

```python
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
    api_endpoint: str          # Discovered API path
    pagination_type: str       # "offset" | "cursor" | "page_number"
    page_size: int = 50
    rate_limit: float = 1.0    # seconds between requests
    max_concurrent: int = 5
    timeout: int = 30
    total_records: int | None = None  # If known from API metadata
    headers: dict = field(default_factory=dict)
    auth_required: bool = False


@dataclass
class QualityThresholds:
    """Minimum quality standards for the pipeline."""
    min_completeness: float = 0.90      # 90% required fields non-null
    min_uniqueness: float = 1.0         # 100% unique IDs
    min_format_compliance: float = 0.85  # 85% format match
    max_duplicate_rate: float = 0.01     # Max 1% duplicates


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

    def __post_init__(self):
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
```

**Requirements:**
- `dataclass` (not pydantic)
- `SourceConfig` with pagination_type field — key differentiator
- `QualityThresholds` as separate config for the quality layer
- Type hints everywhere
- Defaults that work out of the box

---

### `src/discovery/api_analyzer.py`

**Purpose:** Simulates the API discovery process. This module exists to TELL THE STORY of reverse engineering — it shows the developer's methodology in code, not just in a README.

**Behavior:**
1. Takes a base URL
2. Probes common API endpoint patterns
3. Analyzes response format (JSON vs HTML)
4. Detects pagination scheme
5. Reports discovery findings

```python
"""
API Discovery & Analysis Tool.

Automates the initial reconnaissance phase of API reverse engineering.
Given a base URL, this tool probes for common API patterns, analyzes
response formats, and identifies pagination schemes.

In real-world engagements, this supplements manual Chrome DevTools
analysis — automating the repetitive parts of API discovery.
"""
from dataclasses import dataclass
from enum import Enum


class PaginationType(Enum):
    OFFSET = "offset"        # ?offset=0&limit=50
    CURSOR = "cursor"        # ?cursor=abc123
    PAGE_NUMBER = "page"     # ?page=1&size=50
    LINK_HEADER = "link"     # Link: <url>; rel="next"
    NONE = "none"            # All data in single response
    UNKNOWN = "unknown"


class ResponseFormat(Enum):
    JSON_ARRAY = "json_array"          # [item, item, ...]
    JSON_WRAPPED = "json_wrapped"      # {results: [...], total: N}
    HTML = "html"
    XML = "xml"
    UNKNOWN = "unknown"


@dataclass
class DiscoveryReport:
    """Results of API analysis for a given source."""
    base_url: str
    discovered_endpoints: list[dict]   # [{path, method, format, status}]
    pagination_type: PaginationType
    response_format: ResponseFormat
    estimated_total_records: int | None
    auth_required: bool
    rate_limit_detected: bool
    headers_required: dict             # Minimum headers for success
    notes: list[str]                   # Human-readable observations

    def summary(self) -> str:
        """Printable summary of discovery findings."""
        ...


class APIAnalyzer:
    """
    Probes a website for hidden API endpoints.

    Methodology:
    1. Try common API path patterns (/api/, /v1/, /search.json, etc.)
    2. Analyze response Content-Type and structure
    3. Detect pagination by comparing responses with different params
    4. Check for auth requirements (401/403 responses)
    5. Estimate total records from pagination metadata
    """

    # Common API patterns found in professional registries
    COMMON_PATHS = [
        "/api/v1/",
        "/api/v2/",
        "/api/",
        "/search.json",
        "/data.json",
        "/rest/",
        "/graphql",
        "/_api/",
        "/wp-json/wp/v2/",
    ]

    COMMON_SEARCH_PATTERNS = [
        "/api/search",
        "/api/professionals",
        "/api/members",
        "/api/registry",
        "/api/directory",
        "/search/authors.json",  # Open Library specific
    ]

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    async def analyze(self, base_url: str) -> DiscoveryReport:
        """
        Run full API discovery against a base URL.
        Returns a DiscoveryReport with findings.
        """
        ...

    async def _probe_endpoints(
        self, client: httpx.AsyncClient, base_url: str
    ) -> list[dict]:
        """Try common API paths and record which ones return data."""
        ...

    async def _detect_pagination(
        self, client: httpx.AsyncClient, endpoint_url: str
    ) -> PaginationType:
        """
        Determine pagination scheme by analyzing response metadata.

        Strategy:
        - Check for 'total', 'count', 'totalResults' in JSON response
        - Check for 'next', 'offset', 'cursor' fields
        - Check for Link header with rel="next"
        - Compare responses with different page/offset params
        """
        ...

    async def _detect_response_format(
        self, response: httpx.Response
    ) -> ResponseFormat:
        """Classify the response format based on Content-Type and body."""
        ...

    async def _check_auth(
        self, client: httpx.AsyncClient, url: str
    ) -> bool:
        """Check if endpoint requires authentication (401/403)."""
        ...

    async def _estimate_total(
        self, client: httpx.AsyncClient, endpoint_url: str
    ) -> int | None:
        """
        Try to determine total record count from API metadata.
        Look for: total, count, totalResults, numFound, etc.
        """
        ...
```

**Requirements:**
- Enum types for PaginationType and ResponseFormat
- DiscoveryReport dataclass with summary() method
- Probes common patterns — shows the developer knows what to look for
- All async with httpx
- Extensive docstrings explaining the WHY of each method
- This module is more about SHOWING METHODOLOGY than being a production tool

---

### `src/extractor/base.py`

**Purpose:** Abstract base class and standardized record schema.

```python
"""
Base extractor and record schema for directory data extraction.
All directory sources map their data into DirectoryRecord format.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


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
    source: str                        # Source identifier
    record_id: str                     # Unique ID within source
    full_name: str                     # Primary name field
    title: str | None = None           # Professional title / role
    organization: str | None = None    # Firm / company / publisher
    specialization: str | None = None  # Area of expertise / genre
    location: str | None = None        # City, region, or country
    country: str | None = None         # ISO country code
    contact_email: str | None = None   # Public contact email
    contact_phone: str | None = None   # Public phone
    website: str | None = None         # Professional website
    registration_id: str | None = None # License / reg number
    status: str | None = None          # Active, inactive, etc.
    profile_url: str | None = None     # Source profile page URL
    raw_data: dict | None = None       # Original API response
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

    def __init__(self, config: "SourceConfig", logger=None):
        self.config = config
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self._records_extracted = 0

    @abstractmethod
    async def extract_all(self) -> list[DirectoryRecord]:
        """Extract all records from this directory source."""
        ...

    @abstractmethod
    def _map_to_record(self, raw: dict) -> DirectoryRecord:
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
```

**Requirements:**
- `DirectoryRecord` with enough fields to represent any professional registry
- `raw_data` field preserved for debugging but excluded from exports
- `to_dict()` with datetime serialization
- Abstract `_map_to_record()` — forces each extractor to define its mapping
- Stats property for pipeline reporting

---

### `src/extractor/paginator.py`

**Purpose:** Generic pagination handler that supports multiple pagination schemes. This is a KEY component — it shows the developer has encountered and solved pagination in many forms.

```python
"""
Generic pagination handler for API data extraction.

Supports multiple pagination patterns commonly found in
professional registries and public directories:

- Offset-based:    ?offset=0&limit=50 → ?offset=50&limit=50
- Page number:     ?page=1&size=50 → ?page=2&size=50
- Cursor-based:    ?cursor=abc123 (cursor from previous response)
- Link header:     Link: <url>; rel="next"
- Single response: All data returned in one call (no pagination)
"""
from dataclasses import dataclass
from enum import Enum
from typing import AsyncGenerator


@dataclass
class PaginationState:
    """Tracks current position in paginated extraction."""
    current_page: int = 0
    total_pages: int | None = None
    total_records: int | None = None
    records_fetched: int = 0
    next_cursor: str | None = None
    next_url: str | None = None
    is_complete: bool = False

    @property
    def progress(self) -> str:
        """Human-readable progress string."""
        if self.total_records:
            pct = (self.records_fetched / self.total_records) * 100
            return f"{self.records_fetched}/{self.total_records} ({pct:.1f}%)"
        return f"{self.records_fetched} records (total unknown)"


class Paginator:
    """
    Generic paginator that yields pages of results from any API.

    Usage:
        paginator = Paginator(config, client)
        async for page_data in paginator.paginate():
            records.extend(page_data)
    """

    def __init__(
        self,
        config: "SourceConfig",
        client: httpx.AsyncClient,
        rate_limiter: "RateLimiter | None" = None,
        logger: logging.Logger | None = None,
    ):
        self.config = config
        self.client = client
        self.rate_limiter = rate_limiter
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.state = PaginationState()

    async def paginate(self) -> AsyncGenerator[list[dict], None]:
        """
        Async generator yielding pages of raw records.

        Automatically handles the configured pagination scheme.
        Stops when: no more data, empty page, or max pages reached.
        """
        handler = self._get_handler()
        async for page in handler():
            yield page

    def _get_handler(self):
        """Route to the correct pagination handler."""
        handlers = {
            "offset": self._paginate_offset,
            "page_number": self._paginate_page_number,
            "cursor": self._paginate_cursor,
            "link_header": self._paginate_link_header,
            "none": self._paginate_single,
        }
        handler = handlers.get(self.config.pagination_type)
        if not handler:
            raise ValueError(
                f"Unknown pagination type: {self.config.pagination_type}"
            )
        return handler

    async def _paginate_offset(self) -> AsyncGenerator[list[dict], None]:
        """
        Offset-based pagination.
        Used by: Open Library (?offset=0&limit=100)

        Sends: GET {endpoint}?q={query}&offset=N&limit=M
        Stops: When len(results) < page_size or offset >= total
        """
        offset = 0
        while True:
            if self.rate_limiter:
                await self.rate_limiter.wait()

            params = {
                "q": "a",  # Broad search to get many results
                "offset": offset,
                "limit": self.config.page_size,
            }
            response = await self._fetch(params)
            data = self._extract_results(response)

            if not data:
                self.state.is_complete = True
                break

            self.state.records_fetched += len(data)
            self.state.current_page += 1

            # Try to get total from response metadata
            if self.state.total_records is None:
                self.state.total_records = self._extract_total(response)

            self.logger.info("Page %d: %s", self.state.current_page, self.state.progress)
            yield data

            if len(data) < self.config.page_size:
                self.state.is_complete = True
                break

            offset += self.config.page_size

    async def _paginate_page_number(self) -> AsyncGenerator[list[dict], None]:
        """
        Page-number pagination.
        Used by: RandomUser API (?page=1&results=100)

        Sends: GET {endpoint}?page=N&results=M
        Stops: When records_fetched >= total_records (configured)
        """
        page = 1
        max_records = self.config.total_records or 2000

        while self.state.records_fetched < max_records:
            if self.rate_limiter:
                await self.rate_limiter.wait()

            remaining = max_records - self.state.records_fetched
            batch_size = min(self.config.page_size, remaining)

            params = {
                "page": page,
                "results": batch_size,
                "seed": "portfolio_demo",  # Reproducible results
            }
            response = await self._fetch(params)
            data = self._extract_results(response)

            if not data:
                self.state.is_complete = True
                break

            self.state.records_fetched += len(data)
            self.state.current_page = page
            self.state.total_records = max_records

            self.logger.info("Page %d: %s", page, self.state.progress)
            yield data

            page += 1

        self.state.is_complete = True

    async def _paginate_cursor(self) -> AsyncGenerator[list[dict], None]:
        """
        Cursor-based pagination.

        Sends: GET {endpoint}?cursor=TOKEN&limit=M
        Stops: When response contains no next cursor
        """
        cursor = None
        while True:
            if self.rate_limiter:
                await self.rate_limiter.wait()

            params = {"limit": self.config.page_size}
            if cursor:
                params["cursor"] = cursor

            response = await self._fetch(params)
            data = self._extract_results(response)

            if not data:
                self.state.is_complete = True
                break

            self.state.records_fetched += len(data)
            self.state.current_page += 1

            cursor = self._extract_cursor(response)
            self.state.next_cursor = cursor

            self.logger.info("Page %d: %s", self.state.current_page, self.state.progress)
            yield data

            if not cursor:
                self.state.is_complete = True
                break

    async def _paginate_link_header(self) -> AsyncGenerator[list[dict], None]:
        """
        Link-header pagination (RFC 5988).

        Reads: Link: <https://api.example.com/items?page=2>; rel="next"
        Stops: When no 'next' link in response headers
        """
        url = self._build_url({})
        while url:
            if self.rate_limiter:
                await self.rate_limiter.wait()

            response = await self.client.get(url, timeout=self.config.timeout)
            response.raise_for_status()

            data = response.json()
            results = data if isinstance(data, list) else self._extract_results(data)

            if not results:
                self.state.is_complete = True
                break

            self.state.records_fetched += len(results)
            self.state.current_page += 1

            self.logger.info("Page %d: %s", self.state.current_page, self.state.progress)
            yield results

            # Parse Link header for next URL
            url = self._parse_link_header(response.headers.get("Link", ""))

        self.state.is_complete = True

    async def _paginate_single(self) -> AsyncGenerator[list[dict], None]:
        """
        No pagination — all data in single response.
        Used by: REST Countries API
        """
        if self.rate_limiter:
            await self.rate_limiter.wait()

        response = await self._fetch({})
        data = self._extract_results(response)
        self.state.records_fetched = len(data)
        self.state.is_complete = True

        self.logger.info("Single response: %d records", len(data))
        yield data

    async def _fetch(self, params: dict) -> dict | list:
        """Execute HTTP request with retry logic."""
        url = self._build_url(params)
        for attempt in range(3):
            try:
                response = await self.client.get(
                    url,
                    params=params,
                    timeout=self.config.timeout,
                    headers=self.config.headers,
                )
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    wait = (2 ** attempt) + random.uniform(0, 1)
                    self.logger.warning(
                        "Rate limited (attempt %d). Waiting %.1fs", attempt + 1, wait
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
            except httpx.TimeoutException:
                self.logger.warning("Timeout (attempt %d)", attempt + 1)
                if attempt == 2:
                    raise
        return []

    def _build_url(self, params: dict) -> str:
        """Construct full URL from base + endpoint."""
        ...

    def _extract_results(self, response: dict | list) -> list[dict]:
        """
        Extract the results array from various API response formats.
        Handles: {results: [...]}, {docs: [...]}, {data: [...]}, [...]
        """
        if isinstance(response, list):
            return response
        # Try common wrapper keys
        for key in ["results", "docs", "data", "items", "records", "entries"]:
            if key in response:
                return response[key]
        return []

    def _extract_total(self, response: dict | list) -> int | None:
        """Extract total record count from response metadata."""
        if isinstance(response, list):
            return len(response)
        for key in ["total", "totalResults", "numFound", "count", "total_count"]:
            if key in response:
                return int(response[key])
        return None

    def _extract_cursor(self, response: dict) -> str | None:
        """Extract next cursor from response."""
        for key in ["next_cursor", "cursor", "nextCursor", "next"]:
            if key in response and response[key]:
                return str(response[key])
        return None

    def _parse_link_header(self, link_header: str) -> str | None:
        """Parse RFC 5988 Link header for 'next' URL."""
        if not link_header:
            return None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                return url
        return None
```

**Requirements:**
- AsyncGenerator yielding pages (not returning full list)
- PaginationState tracking with progress reporting
- All 5 pagination types implemented (offset, page_number, cursor, link_header, none)
- `_extract_results()` handles multiple JSON wrapper formats
- `_extract_total()` probes common metadata keys
- Retry with exponential backoff on 429
- Rate limiter integration
- Extensive docstrings on each pagination type explaining when it's used

---

### `src/extractor/api_client.py`

**Purpose:** Concrete extractors for each demo data source.

```python
"""
Concrete extractors for demo directory sources.

Each extractor maps a specific API's response format into
the standardized DirectoryRecord schema.
"""


class OpenLibraryExtractor(BaseDirectoryExtractor):
    """
    Extracts author records from Open Library's search API.

    API: https://openlibrary.org/search/authors.json?q=a&offset=0&limit=100
    Pagination: offset-based
    Auth: none
    Rate limit: ~1 req/sec (be respectful)

    Simulates: Professional registry extraction (e.g., architect
    license board, medical registry) where the "directory" is
    searchable and paginatable.
    """

    async def extract_all(self) -> list[DirectoryRecord]:
        """
        Extract author records using offset pagination.
        Uses broad search query to retrieve large dataset.
        """
        records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=self.config,
                client=client,
                rate_limiter=RateLimiter(requests_per_second=1.0),
                logger=self.logger,
            )
            async for page in paginator.paginate():
                for raw in page:
                    record = self._map_to_record(raw)
                    if record:
                        records.append(record)

        self._records_extracted = len(records)
        return records

    def _map_to_record(self, raw: dict) -> DirectoryRecord | None:
        """
        Map Open Library author to DirectoryRecord.

        Mapping:
        - key → record_id (e.g., "OL1234A")
        - name → full_name
        - top_work → organization (treating primary work as "affiliation")
        - top_subjects[0] → specialization
        - birth_date → title (using as metadata)
        - work_count → stored in raw_data for enrichment
        """
        try:
            return DirectoryRecord(
                source=self.config.name,
                record_id=raw.get("key", ""),
                full_name=raw.get("name", ""),
                title=raw.get("birth_date"),
                organization=raw.get("top_work"),
                specialization=(
                    raw.get("top_subjects", [None])[0]
                    if raw.get("top_subjects")
                    else None
                ),
                profile_url=f"https://openlibrary.org/authors/{raw.get('key', '')}",
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning("Failed to map record: %s", e)
            return None


class RandomProfessionalsExtractor(BaseDirectoryExtractor):
    """
    Generates professional profile data using RandomUser API.

    API: https://randomuser.me/api/?results=100&page=1&seed=demo
    Pagination: page-number based
    Auth: none

    Simulates: Business directory / professional contact database
    with name, location, email, phone, and profile photo.

    Using seed="portfolio_demo" for reproducible results.
    """

    async def extract_all(self) -> list[DirectoryRecord]:
        ...

    def _map_to_record(self, raw: dict) -> DirectoryRecord | None:
        """
        Map RandomUser response to DirectoryRecord.

        Mapping:
        - login.uuid → record_id
        - name.first + name.last → full_name
        - name.title → title
        - location.city + location.country → location
        - nat → country
        - email → contact_email
        - phone → contact_phone
        """
        ...


class CountriesRegistryExtractor(BaseDirectoryExtractor):
    """
    Extracts country data from REST Countries API.

    API: https://restcountries.com/v3.1/all
    Pagination: none (single response)
    Auth: none

    Simulates: Geographic reference data used to ENRICH
    records from other sources (e.g., mapping country codes
    to regions, adding population data).
    """

    async def extract_all(self) -> list[DirectoryRecord]:
        ...

    def _map_to_record(self, raw: dict) -> DirectoryRecord | None:
        """
        Map country to DirectoryRecord.

        Mapping:
        - cca2 → record_id (ISO 3166 alpha-2)
        - name.common → full_name
        - region → specialization
        - subregion → organization
        - capital[0] → location
        """
        ...
```

**Requirements:**
- Each extractor has docstrings explaining what it simulates in real-world terms
- `_map_to_record()` has explicit mapping comments
- All use Paginator for pagination (except Countries which uses "none")
- Error handling in mapping (try/except with logging, return None on failure)
- OpenLibrary uses seed/broad query to get reproducible, large dataset
- RandomUser uses `seed=portfolio_demo` for reproducible results

---

### `src/utils/session_manager.py`

**Purpose:** Manages HTTP sessions, cookies, and authentication tokens. Demonstrates handling of auth flows — even though demo APIs don't require auth.

```python
"""
HTTP session management with cookie and token persistence.

In production scraping of professional registries, many sites
require session cookies or authentication tokens. This manager
handles:
- Session cookie persistence across requests
- Token refresh for authenticated APIs
- Header management (User-Agent rotation, Accept headers)
"""


@dataclass
class SessionState:
    """Current session state."""
    cookies: dict = field(default_factory=dict)
    auth_token: str | None = None
    token_expires_at: datetime | None = None
    user_agent: str = ""
    request_count: int = 0

    @property
    def is_token_valid(self) -> bool:
        """Check if auth token is still valid."""
        if not self.auth_token or not self.token_expires_at:
            return False
        return datetime.utcnow() < self.token_expires_at


class SessionManager:
    """
    Manages HTTP session state for scraping operations.

    Features:
    - User-Agent rotation from realistic browser strings
    - Cookie jar persistence across requests
    - Auth token refresh when expired
    - Request counting for rate limit awareness
    """

    USER_AGENTS = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 ...",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 ...",
        # 5-7 realistic user agent strings
    ]

    def __init__(self):
        self.state = SessionState()
        self._rotate_user_agent()

    def get_headers(self) -> dict:
        """Build request headers with current session state."""
        headers = {
            "User-Agent": self.state.user_agent,
            "Accept": "application/json, text/html;q=0.9",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        if self.state.auth_token:
            headers["Authorization"] = f"Bearer {self.state.auth_token}"
        return headers

    def _rotate_user_agent(self) -> None:
        """Select a random User-Agent string."""
        ...

    async def refresh_token(self, auth_url: str, credentials: dict) -> None:
        """
        Refresh authentication token.
        Placeholder for registry-specific auth flows.
        """
        ...

    def update_cookies(self, response_cookies: dict) -> None:
        """Merge response cookies into session state."""
        ...

    def create_client(self) -> httpx.AsyncClient:
        """Create a configured httpx client with session state."""
        return httpx.AsyncClient(
            headers=self.get_headers(),
            cookies=self.state.cookies,
            follow_redirects=True,
            timeout=30,
        )
```

**Requirements:**
- Realistic User-Agent strings (not placeholder text — use real browser UAs)
- Cookie persistence
- Token refresh placeholder (shows awareness of auth flows)
- `create_client()` factory method
- Docstrings explaining real-world usage even though demo doesn't need auth

---

### `src/utils/rate_limiter.py`

**Purpose:** Same concept as REPO 1 but can be slightly different implementation.

```python
"""
Adaptive rate limiter with jitter and backoff awareness.
"""


class AdaptiveRateLimiter:
    """
    Rate limiter that adjusts speed based on server responses.

    Starts at configured rate, slows down on 429 responses,
    and gradually speeds back up after successful requests.
    """

    def __init__(
        self,
        requests_per_second: float = 1.0,
        jitter: float = 0.3,
        backoff_factor: float = 2.0,
        recovery_factor: float = 0.95,
    ):
        self.base_interval = 1.0 / requests_per_second
        self.current_interval = self.base_interval
        self.jitter = jitter
        self.backoff_factor = backoff_factor
        self.recovery_factor = recovery_factor
        self._last_request = 0.0
        self._lock = asyncio.Lock()
        self._consecutive_success = 0

    async def wait(self) -> None:
        """Wait the appropriate interval before next request."""
        ...

    def report_success(self) -> None:
        """Report a successful request — may speed up."""
        self._consecutive_success += 1
        if self._consecutive_success > 10:
            # Gradually recover toward base rate
            self.current_interval = max(
                self.base_interval,
                self.current_interval * self.recovery_factor
            )

    def report_rate_limit(self) -> None:
        """Report a 429 response — slow down."""
        self._consecutive_success = 0
        self.current_interval *= self.backoff_factor
        self.logger.warning(
            "Rate limit hit. Interval increased to %.2fs",
            self.current_interval
        )
```

**Key difference from REPO 1:** This is an ADAPTIVE rate limiter — it speeds up/slows down based on server feedback. Shows evolution of the concept.

---

### `src/pipeline/bronze.py`

**Purpose:** Bronze layer — raw data ingestion with no transformation.

```python
"""
Bronze Layer — Raw Data Ingestion.

Stores raw API responses exactly as received. No cleaning,
no transformation, no deduplication. This is the immutable
source of truth that all downstream processing references.

Design principle: If the API changes or we discover a mapping
error, we can always reprocess from Bronze without re-extracting.
"""


class BronzeLayer:
    """
    Manages Bronze (raw) data storage.

    Storage format: JSON files, one per extraction batch.
    Naming: {source}_{timestamp}.json
    Policy: Append-only, never modify or delete.
    """

    def __init__(self, bronze_dir: Path, logger=None):
        ...

    def ingest(
        self,
        records: list[DirectoryRecord],
        source: str,
    ) -> Path:
        """
        Save raw records to Bronze layer.

        Returns the path to the created file.
        Each record's raw_data field is preserved if available.
        """
        ...

    def load_latest(self, source: str) -> list[dict] | None:
        """Load the most recent Bronze file for a given source."""
        ...

    def list_files(self, source: str | None = None) -> list[Path]:
        """List all Bronze files, optionally filtered by source."""
        ...

    @property
    def stats(self) -> dict:
        """Storage statistics: file count, total size, date range."""
        ...
```

---

### `src/pipeline/silver.py`

**Purpose:** Silver layer — cleaning, deduplication, validation, and standardization.

```python
"""
Silver Layer — Data Cleaning & Standardization.

Transforms raw Bronze data into clean, validated records:
- Deduplication by record_id
- Field standardization (names, phones, emails)
- Null handling and default values
- Schema validation
- Type conversion

Output is a clean, analysis-ready dataset.
"""


class SilverLayer:
    """
    Cleans and standardizes raw directory records.

    Processing steps (in order):
    1. Deduplicate by record_id (keep latest)
    2. Standardize names (title case, trim whitespace)
    3. Standardize phone numbers (E.164 format attempt)
    4. Validate email format
    5. Normalize country codes (ISO 3166 alpha-2)
    6. Remove records failing validation
    7. Export to CSV
    """

    def __init__(self, silver_dir: Path, logger=None):
        ...

    def process(
        self,
        records: list[DirectoryRecord],
    ) -> "SilverResult":
        """
        Run full Silver processing pipeline.
        Returns SilverResult with clean records and processing stats.
        """
        df = pd.DataFrame([r.to_dict() for r in records])

        # Step 1: Deduplicate
        before_dedup = len(df)
        df = self._deduplicate(df)

        # Step 2: Standardize fields
        df = self._standardize_names(df)
        df = self._standardize_phones(df)
        df = self._validate_emails(df)
        df = self._normalize_countries(df)

        # Step 3: Remove invalid
        df, rejected = self._remove_invalid(df)

        # Step 4: Export
        output_path = self._export(df)

        return SilverResult(
            clean_records=len(df),
            duplicates_removed=before_dedup - len(df),
            invalid_removed=len(rejected),
            output_path=output_path,
            rejection_reasons=rejected,
        )

    def _deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate record_ids, keeping the latest extraction."""
        ...

    def _standardize_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize name fields:
        - Strip whitespace
        - Title case
        - Remove extra spaces
        """
        ...

    def _standardize_phones(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Attempt to standardize phone numbers.
        Best-effort — not all formats will parse cleanly.
        """
        ...

    def _validate_emails(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate email format using regex.
        Marks invalid emails as None rather than removing records.
        """
        ...

    def _normalize_countries(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Normalize country fields to ISO 3166 alpha-2 codes.
        """
        ...

    def _remove_invalid(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[dict]]:
        """
        Remove records that fail minimum requirements:
        - record_id is required
        - full_name is required and non-empty
        Returns (valid_df, list of rejected records with reasons)
        """
        ...

    def _export(self, df: pd.DataFrame) -> Path:
        """Save to Silver directory as CSV."""
        ...

    def load_latest(self, source: str | None = None) -> pd.DataFrame | None:
        """Load the latest Silver dataset."""
        ...


@dataclass
class SilverResult:
    clean_records: int
    duplicates_removed: int
    invalid_removed: int
    output_path: Path
    rejection_reasons: list[dict]

    def summary(self) -> str:
        """Human-readable processing summary."""
        ...
```

---

### `src/pipeline/gold.py`

**Purpose:** Gold layer — enrichment, aggregation, and analytics-ready output.

```python
"""
Gold Layer — Enrichment & Analytics.

Transforms Silver data into business-ready datasets:
- Geographic enrichment (country → region, population)
- Aggregations (records per country, per specialization)
- Derived fields (completeness scores, data quality flags)
- Cross-source linking (match records across directories)
"""


class GoldLayer:
    """
    Enriches and aggregates clean directory data.

    Outputs:
    - gold/enriched_{source}_{date}.csv — Full enriched dataset
    - gold/summary_{date}.json — Aggregation summary
    - gold/quality_{date}.json — Quality report
    """

    def __init__(self, gold_dir: Path, logger=None):
        ...

    def process(
        self,
        silver_df: pd.DataFrame,
        enrichment_data: pd.DataFrame | None = None,
    ) -> "GoldResult":
        """
        Run Gold layer processing.

        Args:
            silver_df: Cleaned data from Silver layer
            enrichment_data: Optional reference data for enrichment
                           (e.g., country details from REST Countries)
        """
        # Step 1: Enrich with external data
        if enrichment_data is not None:
            df = self._enrich_geographic(silver_df, enrichment_data)
        else:
            df = silver_df.copy()

        # Step 2: Add derived fields
        df = self._add_completeness_score(df)

        # Step 3: Generate aggregations
        summary = self._aggregate(df)

        # Step 4: Generate quality report
        quality = self._quality_report(df)

        # Step 5: Export
        enriched_path = self._export_enriched(df)
        summary_path = self._export_summary(summary)
        quality_path = self._export_quality(quality)

        return GoldResult(
            total_records=len(df),
            enriched_path=enriched_path,
            summary_path=summary_path,
            quality_path=quality_path,
            summary=summary,
            quality=quality,
        )

    def _enrich_geographic(
        self, df: pd.DataFrame, countries: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Enrich records with geographic data.
        Joins on country code to add: region, subregion, population.
        """
        ...

    def _add_completeness_score(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate per-record completeness score.
        Score = (non-null optional fields) / (total optional fields)
        """
        optional_fields = [
            "title", "organization", "specialization", "location",
            "country", "contact_email", "contact_phone", "website",
        ]
        ...

    def _aggregate(self, df: pd.DataFrame) -> dict:
        """
        Generate summary aggregations:
        - Records per source
        - Records per country/region
        - Records per specialization
        - Average completeness by source
        """
        ...

    def _quality_report(self, df: pd.DataFrame) -> dict:
        """
        Generate data quality report:
        - Completeness: % of non-null values per field
        - Uniqueness: % unique record_ids
        - Format compliance: % valid emails, phones
        """
        ...

    def _export_enriched(self, df: pd.DataFrame) -> Path:
        ...

    def _export_summary(self, summary: dict) -> Path:
        ...

    def _export_quality(self, quality: dict) -> Path:
        ...


@dataclass
class GoldResult:
    total_records: int
    enriched_path: Path
    summary_path: Path
    quality_path: Path
    summary: dict
    quality: dict

    def print_summary(self) -> None:
        """Print formatted summary to console."""
        ...
```

---

### `src/quality/validators.py`

**Purpose:** Data quality validation with configurable rules. This is a SELLING POINT — most scrapers don't validate data.

```python
"""
Data Quality Validation Framework.

Implements quality checks at multiple levels:
- Record-level: individual record validation
- Field-level: specific field format/content checks
- Dataset-level: aggregate quality metrics

Quality checks are inspired by Great Expectations patterns
but implemented without the dependency for simplicity.
"""


@dataclass
class QualityCheck:
    """Result of a single quality check."""
    check_name: str
    field: str | None
    passed: bool
    expected: str
    actual: str
    severity: str = "error"  # "error" | "warning"


@dataclass
class QualityReport:
    """Complete quality report for a dataset."""
    source: str
    total_records: int
    checks: list[QualityCheck]
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def pass_rate(self) -> float:
        """Overall check pass rate."""
        if not self.checks:
            return 1.0
        passed = sum(1 for c in self.checks if c.passed)
        return passed / len(self.checks)

    @property
    def errors(self) -> list[QualityCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    @property
    def warnings(self) -> list[QualityCheck]:
        return [c for c in self.checks if not c.passed and c.severity == "warning"]

    def summary(self) -> str:
        """Human-readable quality summary."""
        ...

    def to_dict(self) -> dict:
        """Serialize for JSON export."""
        ...


class DataQualityValidator:
    """
    Validates dataset quality against configurable thresholds.

    Checks performed:
    1. Completeness — required fields must be non-null
    2. Uniqueness — record_ids must be unique
    3. Format compliance — emails, phones match expected patterns
    4. Consistency — cross-field logical checks
    5. Freshness — extracted_at within expected window
    """

    def __init__(self, thresholds: "QualityThresholds"):
        self.thresholds = thresholds

    def validate(self, df: pd.DataFrame, source: str) -> QualityReport:
        """Run all quality checks and return report."""
        checks = []
        checks.extend(self._check_completeness(df))
        checks.extend(self._check_uniqueness(df))
        checks.extend(self._check_format_compliance(df))
        checks.extend(self._check_consistency(df))
        checks.extend(self._check_freshness(df))

        return QualityReport(
            source=source,
            total_records=len(df),
            checks=checks,
        )

    def _check_completeness(self, df: pd.DataFrame) -> list[QualityCheck]:
        """
        Check that required fields have sufficient non-null values.

        Required fields: record_id, full_name, source
        Important fields (warning): location, country, specialization
        """
        ...

    def _check_uniqueness(self, df: pd.DataFrame) -> list[QualityCheck]:
        """Check for duplicate record_ids."""
        ...

    def _check_format_compliance(self, df: pd.DataFrame) -> list[QualityCheck]:
        """
        Validate field formats:
        - contact_email: basic email regex
        - contact_phone: contains digits, reasonable length
        - country: 2-letter ISO code
        """
        ...

    def _check_consistency(self, df: pd.DataFrame) -> list[QualityCheck]:
        """
        Cross-field logical checks:
        - If country is set, it should be a valid ISO code
        - If contact_email is set, it should contain @
        """
        ...

    def _check_freshness(self, df: pd.DataFrame) -> list[QualityCheck]:
        """Check that extracted_at is within last 24 hours."""
        ...
```

**Requirements:**
- QualityCheck and QualityReport as dataclasses
- 5 categories of checks (completeness, uniqueness, format, consistency, freshness)
- Severity levels (error vs warning)
- `pass_rate` property
- `to_dict()` for JSON export
- Configurable thresholds from Settings

---

### `examples/run_full_pipeline.py`

```python
#!/usr/bin/env python3
"""
Full directory extraction pipeline demo.

Extracts records from 3 demo sources, processes through
Bronze → Silver → Gold layers, and generates a quality report.

Usage:
    python examples/run_full_pipeline.py

No configuration needed — uses public APIs only.
Expected runtime: ~2-3 minutes (depending on rate limits).
Expected output: ~2,500+ records across all sources.
"""
```

**Behavior:**
1. Run API discovery on Open Library (shows methodology)
2. Extract from all 3 sources
3. Save raw data to Bronze
4. Clean and standardize in Silver
5. Enrich with country data in Gold
6. Run quality validation
7. Print comprehensive summary with metrics

**Must show a final output like:**

```
=== Directory Data Pipeline — Complete ===

Sources processed: 3
Total records extracted: 2,547
Pipeline duration: 2m 34s

Bronze Layer:
  Files created: 3
  Raw records: 2,547

Silver Layer:
  Clean records: 2,401
  Duplicates removed: 89
  Invalid removed: 57
  Pass rate: 94.3%

Gold Layer:
  Enriched records: 2,401
  Geographic coverage: 42 countries
  Avg completeness score: 0.72

Quality Report:
  Checks passed: 18/20 (90.0%)
  Errors: 0
  Warnings: 2
    - contact_phone format compliance: 87.2% (threshold: 85.0%)
    - specialization completeness: 68.4% (threshold: n/a, warning only)

Output files:
  data/bronze/openlibrary_authors_20241215_083000.json
  data/bronze/random_professionals_20241215_083045.json
  data/bronze/countries_registry_20241215_083100.json
  data/silver/all_professionals_latest.csv
  data/gold/enriched_professionals_20241215.csv
  data/gold/summary_20241215.json
  data/gold/quality_20241215.json
```

---

### `examples/run_discovery.py`

```python
#!/usr/bin/env python3
"""
API Discovery demo — analyze a website for hidden API endpoints.

Usage:
    python examples/run_discovery.py [url]
    python examples/run_discovery.py  # defaults to openlibrary.org

Demonstrates the reverse engineering methodology:
1. Probe common API path patterns
2. Analyze response formats
3. Detect pagination schemes
4. Report findings
"""
```

---

### `examples/run_quality_report.py`

```python
#!/usr/bin/env python3
"""
Generate a standalone quality report from existing Silver data.

Usage:
    python examples/run_quality_report.py

Reads the latest Silver layer CSV and runs all quality checks.
Useful for monitoring data quality over time.
"""
```

---

## Test Specifications

### `tests/test_extractor.py`

| Test | Description |
|------|-------------|
| `test_openlibrary_mapping` | Mock API response, verify DirectoryRecord field mapping |
| `test_randomuser_mapping` | Mock API response, verify name/email/phone mapping |
| `test_countries_mapping` | Mock API response, verify country code mapping |
| `test_null_handling` | Records with missing fields map to None, not crash |
| `test_invalid_record_skipped` | Malformed records return None and log warning |

### `tests/test_paginator.py`

| Test | Description |
|------|-------------|
| `test_offset_pagination` | Mock 3 pages, verify all records collected |
| `test_offset_stops_on_empty` | Empty page stops pagination |
| `test_page_number_pagination` | Mock pages, verify page increment |
| `test_page_number_respects_max` | Stops at total_records limit |
| `test_cursor_pagination` | Mock cursor chain, verify follows cursors |
| `test_cursor_stops_on_null` | Null cursor stops pagination |
| `test_single_response` | All data in one call, no pagination |
| `test_retry_on_429` | Mock 429 response, verify retry with backoff |
| `test_progress_tracking` | Verify PaginationState updates correctly |
| `test_extract_results_various_formats` | Test JSON wrapper detection (results, docs, data, items) |
| `test_extract_total_various_keys` | Test total detection (total, numFound, count) |

### `tests/test_pipeline.py`

| Test | Description |
|------|-------------|
| `test_bronze_creates_json` | Verify JSON file with correct naming |
| `test_bronze_preserves_raw` | All fields including raw_data saved |
| `test_silver_deduplicates` | Duplicate record_ids → keep latest |
| `test_silver_standardizes_names` | "  john DOE  " → "John Doe" |
| `test_silver_validates_emails` | Invalid emails set to None |
| `test_silver_rejects_invalid` | Missing required fields → rejected |
| `test_gold_enriches_countries` | Country code joined with region data |
| `test_gold_completeness_score` | Score calculated correctly |
| `test_gold_aggregation` | Records per country/source counted |

### `tests/test_validators.py`

| Test | Description |
|------|-------------|
| `test_completeness_pass` | All required fields present → pass |
| `test_completeness_fail` | Missing full_name → fail |
| `test_uniqueness_pass` | All unique IDs → pass |
| `test_uniqueness_fail` | Duplicate IDs → fail with count |
| `test_email_format_valid` | "user@example.com" → pass |
| `test_email_format_invalid` | "not-an-email" → fail |
| `test_quality_report_summary` | Report generates readable summary |
| `test_quality_report_pass_rate` | Pass rate calculated correctly |
| `test_freshness_check` | Old timestamps flagged |

### `tests/test_session_manager.py`

| Test | Description |
|------|-------------|
| `test_headers_include_user_agent` | get_headers returns User-Agent |
| `test_user_agent_rotation` | Multiple calls return different UAs |
| `test_cookie_persistence` | Cookies stored and included in headers |
| `test_token_validity_check` | Expired token returns False |
| `test_create_client_configured` | Client has headers and cookies |

---

## README.md Structure

Follow this EXACT structure. Written as a case study.

1. **Title + one-line description**
2. **The Problem** (3 sentences — research firm scenario)
3. **Results** (table: records extracted, completeness, time, approach)
4. **Approach** (3 subsections)
   - Step 1: Reconnaissance (API discovery)
   - Step 2: API Replication (httpx async)
   - Step 3: Data Pipeline (Bronze-Silver-Gold)
5. **Architecture** (Mermaid diagram — full pipeline flow)
6. **Data Quality** (table with check name, rule, pass rate)
7. **Tech Stack** (table with Layer, Technology)
8. **Key Technical Decisions** (3 subsections with code)
   - Generic Pagination Handler
   - Adaptive Rate Limiting
   - Data Quality Framework
9. **Quick Start** (3 commands)
10. **Sample Output** (pipeline execution log)
11. **Project Structure** (tree)
12. **Pipeline Layers** (Bronze/Silver/Gold table with purpose, format, policy)
13. **License**

---

## docs/reverse-engineering-walkthrough.md

```markdown
# Reverse Engineering Walkthrough

## Real-World Scenario

A client needs 12,000+ records from a professional registry.
The website has a search interface but no documented API.
Here's exactly how I approach this.

## Step 1: Open DevTools

[Explain: Network tab, filter XHR/Fetch, search on the site]

## Step 2: Identify the API Call

[Explain: Look for JSON responses, note URL pattern, headers]

## Step 3: Analyze Pagination

[Explain: Change page on site, watch how URL params change]
[Show: offset vs cursor vs page number patterns]

## Step 4: Replicate in Python

[Code example: minimal httpx script reproducing the call]

## Step 5: Handle Edge Cases

- Rate limiting (429 responses)
- Session cookies
- Dynamic tokens in headers
- CORS headers (not needed for server-side requests)

## Step 6: Verify Data Completeness

[Explain: Compare total from API metadata vs records extracted]

## The Payoff

| Method | Time for 12K records | Reliability | Resources |
|--------|---------------------|-------------|-----------|
| Browser automation | ~10 hours | Fragile | High (headless browser) |
| API reverse engineering | ~45 minutes | Stable | Minimal (HTTP only) |

**93% faster. More reliable. Fewer resources.**
```

---

## docs/pipeline-architecture.md

```markdown
# Pipeline Architecture — Bronze-Silver-Gold

## Why This Pattern?

The Bronze-Silver-Gold (medallion) architecture separates
concerns in data processing:

| Layer | Purpose | Mutability | Format |
|-------|---------|------------|--------|
| Bronze | Raw preservation | Append-only, immutable | JSON |
| Silver | Clean & standardize | Overwrite latest, keep history | CSV |
| Gold | Enrich & aggregate | Regenerated from Silver | CSV + JSON |

## Key Benefits

1. **Reprocessing** — If a bug is found in Silver logic,
   reprocess from Bronze without re-extracting
2. **Auditability** — Raw data always available for verification
3. **Separation** — Extraction team and analysis team work independently
4. **Incremental** — New extractions append to Bronze, Silver
   merges and deduplicates

## Data Flow

[Mermaid diagram of full flow]

## Quality Gates

Data must pass quality checks between Silver and Gold:
- Minimum 90% completeness on required fields
- 100% unique record IDs
- Minimum 85% format compliance on validated fields

If quality drops below thresholds, the pipeline logs warnings
but continues processing — allowing human review.
```

---

## Sample Data Files

### `data/sample/bronze_raw_page_1.json`

```json
{
  "source": "openlibrary_authors",
  "extracted_at": "2024-12-15T08:30:00Z",
  "page": 1,
  "records": [
    {
      "key": "OL1234A",
      "name": "Margaret Atwood",
      "top_work": "The Handmaid's Tale",
      "work_count": 127,
      "top_subjects": ["fiction", "dystopian"],
      "birth_date": "18 November 1939"
    },
    {
      "key": "OL5678A",
      "name": "Haruki Murakami",
      "top_work": "Norwegian Wood",
      "work_count": 98,
      "top_subjects": ["fiction", "japanese literature"],
      "birth_date": "12 January 1949"
    }
  ]
}
```

### `data/sample/silver_professionals.csv`

```csv
source,record_id,full_name,title,organization,specialization,location,country,contact_email,contact_phone,website,profile_url,status,completeness_score,extracted_at
openlibrary_authors,OL1234A,Margaret Atwood,18 November 1939,The Handmaid's Tale,Fiction,,,,,,https://openlibrary.org/authors/OL1234A,,0.38,2024-12-15T08:30:00
random_professionals,abc-123-def,Emily Richardson,Ms,,,London,GB,emily.r@example.com,+44-7700-900123,,,Active,0.62,2024-12-15T08:31:00
countries_registry,US,United States,,,North America,Washington D.C.,US,,,,,,0.50,2024-12-15T08:32:00
```

### `data/sample/quality_report.json`

```json
{
  "source": "all_sources",
  "total_records": 2547,
  "generated_at": "2024-12-15T08:35:00Z",
  "overall_pass_rate": 0.90,
  "checks": [
    {
      "check_name": "completeness_record_id",
      "field": "record_id",
      "passed": true,
      "expected": ">= 100.0% non-null",
      "actual": "100.0%",
      "severity": "error"
    },
    {
      "check_name": "completeness_full_name",
      "field": "full_name",
      "passed": true,
      "expected": ">= 90.0% non-null",
      "actual": "99.8%",
      "severity": "error"
    },
    {
      "check_name": "uniqueness_record_id",
      "field": "record_id",
      "passed": true,
      "expected": "100% unique",
      "actual": "100.0%",
      "severity": "error"
    },
    {
      "check_name": "format_contact_email",
      "field": "contact_email",
      "passed": true,
      "expected": ">= 85.0% valid format",
      "actual": "91.8%",
      "severity": "error"
    },
    {
      "check_name": "format_contact_phone",
      "field": "contact_phone",
      "passed": true,
      "expected": ">= 85.0% valid format",
      "actual": "87.2%",
      "severity": "warning"
    },
    {
      "check_name": "completeness_specialization",
      "field": "specialization",
      "passed": false,
      "expected": ">= 90.0% non-null",
      "actual": "68.4%",
      "severity": "warning"
    }
  ]
}
```

---

## requirements.txt

```
httpx>=0.27.0
pandas>=2.2.0
python-dotenv>=1.0.0
```

**Dev dependencies:**
```
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-httpx>=0.30.0
```

---

## .env.example

```env
# Directory Data Pipeline — Configuration

# Data storage directory
DATA_DIR=data

# Database (optional — CSV by default)
# DATABASE_URL=postgresql://user:pass@localhost:5432/directory

# Extraction limits (for demo, keep low to respect free APIs)
MAX_RECORDS_PER_SOURCE=500

# Logging
LOG_LEVEL=INFO
```

---

## .gitignore

```
# Data (except samples)
data/bronze/
data/silver/
data/gold/
!data/sample/

# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/
*.egg-info/
dist/
build/

# Environment
.env

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
```

---

## Code Quality Standards

Same as REPO 1 — the agent MUST follow these across ALL files:

1. **Type hints** on every function parameter and return value
2. **Docstrings** on every class and public method (Google style)
3. **Logging** instead of print (except in examples output)
4. **Error handling** — never let exceptions crash silently
5. **Async/await** — all I/O operations must be async
6. **Constants** — no magic numbers or hardcoded strings
7. **DRY** — shared logic in base classes or utils
8. **Import order** — stdlib → third party → local
9. **Line length** — max 88 characters
10. **Naming** — snake_case for functions, PascalCase for classes

---

## Commit Strategy

Create commits in this order:

1. `Initial project structure and configuration`
2. `Add base extractor and directory record schema`
3. `Implement generic pagination handler with 5 strategies`
4. `Add API discovery and analysis tool`
5. `Implement Open Library author extractor`
6. `Implement RandomUser professional extractor`
7. `Implement REST Countries registry extractor`
8. `Add session manager with UA rotation`
9. `Add adaptive rate limiter`
10. `Implement Bronze layer — raw data ingestion`
11. `Implement Silver layer — cleaning and standardization`
12. `Implement Gold layer — enrichment and aggregation`
13. `Add data quality validation framework`
14. `Add full pipeline example with summary output`
15. `Add discovery and quality report examples`
16. `Add unit tests`
17. `Add README, docs, and sample data`

---

## Key Differences from REPO 1

This repo differentiates from ecommerce-price-monitor by showcasing:

| Aspect | REPO 1 (Price Monitor) | REPO 2 (Directory Pipeline) |
|--------|----------------------|---------------------------|
| Focus | Change detection & alerting | Full ETL pipeline with quality |
| Extraction | Multiple retailers, async | Multiple registries, paginated |
| Unique feature | Change detection engine | Generic pagination handler (5 types) |
| Pipeline depth | Basic Bronze-Silver-Gold | Full Bronze-Silver-Gold with quality gates |
| Added value | API discovery/analysis tool | Data quality framework |
| Story | "I monitor prices at scale" | "I extract and clean directory data" |
| Record type | ProductRecord (simple) | DirectoryRecord (complex, many fields) |
| Quality | Basic validation | Full quality report with metrics |

The two repos together tell a complete story:
- REPO 1: "I can build monitoring systems"
- REPO 2: "I can build data pipelines with quality guarantees"
