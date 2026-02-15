"""
Concrete extractors for demo directory sources.

Each extractor maps a specific API's response format into
the standardized DirectoryRecord schema.
"""

import logging

import httpx

from config.settings import SourceConfig
from src.extractor.base import BaseDirectoryExtractor, DirectoryRecord
from src.extractor.paginator import Paginator
from src.utils.rate_limiter import AdaptiveRateLimiter


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

    def __init__(
        self,
        config: SourceConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if config is None:
            config = SourceConfig(
                name="openlibrary_authors",
                base_url="https://openlibrary.org",
                api_endpoint="/search/authors.json",
                pagination_type="offset",
                page_size=100,
                rate_limit=1.0,
                max_concurrent=3,
            )
        super().__init__(config, logger)

    async def extract_all(self) -> list[DirectoryRecord]:
        """
        Extract author records using offset pagination.
        Uses broad search query to retrieve large dataset.
        """
        records: list[DirectoryRecord] = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=self.config,
                client=client,
                rate_limiter=AdaptiveRateLimiter(
                    requests_per_second=1.0 / self.config.rate_limit
                ),
                logger=self.logger,
            )
            async for page in paginator.paginate():
                for raw in page:
                    record = self._map_to_record(raw)
                    if record:
                        records.append(record)

        self._records_extracted = len(records)
        self.logger.info(
            "Extracted %d records from %s",
            self._records_extracted,
            self.config.name,
        )
        return records

    def _map_to_record(self, raw: dict) -> DirectoryRecord | None:
        """
        Map Open Library author to DirectoryRecord.

        Mapping:
        - key -> record_id (e.g., "OL1234A")
        - name -> full_name
        - top_work -> organization (treating primary work as affiliation)
        - top_subjects[0] -> specialization
        - birth_date -> title (using as metadata)
        - work_count -> stored in raw_data for enrichment
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
                profile_url=(
                    "https://openlibrary.org/authors/"
                    f"{raw.get('key', '')}"
                ),
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

    def __init__(
        self,
        config: SourceConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if config is None:
            config = SourceConfig(
                name="random_professionals",
                base_url="https://randomuser.me",
                api_endpoint="/api/",
                pagination_type="page_number",
                page_size=100,
                rate_limit=0.5,
                max_concurrent=5,
                total_records=2000,
            )
        super().__init__(config, logger)

    async def extract_all(self) -> list[DirectoryRecord]:
        """Extract professional profiles using page-number pagination."""
        records: list[DirectoryRecord] = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=self.config,
                client=client,
                rate_limiter=AdaptiveRateLimiter(
                    requests_per_second=1.0 / self.config.rate_limit
                ),
                logger=self.logger,
            )
            async for page in paginator.paginate():
                for raw in page:
                    record = self._map_to_record(raw)
                    if record:
                        records.append(record)

        self._records_extracted = len(records)
        self.logger.info(
            "Extracted %d records from %s",
            self._records_extracted,
            self.config.name,
        )
        return records

    def _map_to_record(self, raw: dict) -> DirectoryRecord | None:
        """
        Map RandomUser response to DirectoryRecord.

        Mapping:
        - login.uuid -> record_id
        - name.first + name.last -> full_name
        - name.title -> title
        - location.city + location.country -> location
        - nat -> country
        - email -> contact_email
        - phone -> contact_phone
        """
        try:
            name = raw.get("name", {})
            location = raw.get("location", {})
            login = raw.get("login", {})

            city = location.get("city", "")
            country_name = location.get("country", "")
            loc = f"{city}, {country_name}" if city else country_name

            return DirectoryRecord(
                source=self.config.name,
                record_id=login.get("uuid", ""),
                full_name=f"{name.get('first', '')} {name.get('last', '')}",
                title=name.get("title"),
                location=loc or None,
                country=raw.get("nat"),
                contact_email=raw.get("email"),
                contact_phone=raw.get("phone"),
                status="Active",
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning("Failed to map record: %s", e)
            return None


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

    def __init__(
        self,
        config: SourceConfig | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        if config is None:
            config = SourceConfig(
                name="countries_registry",
                base_url="https://restcountries.com",
                api_endpoint="/v3.1/all",
                pagination_type="none",
                rate_limit=0.5,
            )
        super().__init__(config, logger)

    async def extract_all(self) -> list[DirectoryRecord]:
        """Extract all country records in a single API call."""
        records: list[DirectoryRecord] = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=self.config,
                client=client,
                rate_limiter=AdaptiveRateLimiter(
                    requests_per_second=1.0 / self.config.rate_limit
                ),
                logger=self.logger,
            )
            async for page in paginator.paginate():
                for raw in page:
                    record = self._map_to_record(raw)
                    if record:
                        records.append(record)

        self._records_extracted = len(records)
        self.logger.info(
            "Extracted %d records from %s",
            self._records_extracted,
            self.config.name,
        )
        return records

    def _map_to_record(self, raw: dict) -> DirectoryRecord | None:
        """
        Map country to DirectoryRecord.

        Mapping:
        - cca2 -> record_id (ISO 3166 alpha-2)
        - name.common -> full_name
        - region -> specialization
        - subregion -> organization
        - capital[0] -> location
        """
        try:
            name_data = raw.get("name", {})
            capitals = raw.get("capital", [])

            return DirectoryRecord(
                source=self.config.name,
                record_id=raw.get("cca2", ""),
                full_name=name_data.get("common", ""),
                specialization=raw.get("region"),
                organization=raw.get("subregion"),
                location=capitals[0] if capitals else None,
                country=raw.get("cca2"),
                raw_data=raw,
            )
        except Exception as e:
            self.logger.warning("Failed to map record: %s", e)
            return None
