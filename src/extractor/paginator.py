"""
Generic pagination handler for API data extraction.

Supports multiple pagination patterns commonly found in
professional registries and public directories:

- Offset-based:    ?offset=0&limit=50 -> ?offset=50&limit=50
- Page number:     ?page=1&size=50 -> ?page=2&size=50
- Cursor-based:    ?cursor=abc123 (cursor from previous response)
- Link header:     Link: <url>; rel="next"
- Single response: All data returned in one call (no pagination)
"""

import asyncio
import logging
import random
from dataclasses import dataclass
from typing import AsyncGenerator

import httpx

from config.settings import SourceConfig
from src.utils.rate_limiter import AdaptiveRateLimiter


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
            return (
                f"{self.records_fetched}/{self.total_records}"
                f" ({pct:.1f}%)"
            )
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
        config: SourceConfig,
        client: httpx.AsyncClient,
        rate_limiter: AdaptiveRateLimiter | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
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

    async def _paginate_offset(
        self,
    ) -> AsyncGenerator[list[dict], None]:
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
                "q": "a",
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

            if self.state.total_records is None:
                self.state.total_records = self._extract_total(response)

            self.logger.info(
                "Page %d: %s",
                self.state.current_page,
                self.state.progress,
            )
            yield data

            if len(data) < self.config.page_size:
                self.state.is_complete = True
                break

            offset += self.config.page_size

    async def _paginate_page_number(
        self,
    ) -> AsyncGenerator[list[dict], None]:
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
                "seed": "portfolio_demo",
            }
            response = await self._fetch(params)
            data = self._extract_results(response)

            if not data:
                self.state.is_complete = True
                break

            self.state.records_fetched += len(data)
            self.state.current_page = page
            self.state.total_records = max_records

            self.logger.info(
                "Page %d: %s", page, self.state.progress
            )
            yield data

            page += 1

        self.state.is_complete = True

    async def _paginate_cursor(
        self,
    ) -> AsyncGenerator[list[dict], None]:
        """
        Cursor-based pagination.

        Sends: GET {endpoint}?cursor=TOKEN&limit=M
        Stops: When response contains no next cursor
        """
        cursor: str | None = None
        while True:
            if self.rate_limiter:
                await self.rate_limiter.wait()

            params: dict = {"limit": self.config.page_size}
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

            self.logger.info(
                "Page %d: %s",
                self.state.current_page,
                self.state.progress,
            )
            yield data

            if not cursor:
                self.state.is_complete = True
                break

    async def _paginate_link_header(
        self,
    ) -> AsyncGenerator[list[dict], None]:
        """
        Link-header pagination (RFC 5988).

        Reads: Link: <https://api.example.com/items?page=2>; rel="next"
        Stops: When no 'next' link in response headers
        """
        url = self._build_url({})
        while url:
            if self.rate_limiter:
                await self.rate_limiter.wait()

            response = await self.client.get(
                url, timeout=self.config.timeout
            )
            response.raise_for_status()

            body = response.json()
            results = (
                body
                if isinstance(body, list)
                else self._extract_results(body)
            )

            if not results:
                self.state.is_complete = True
                break

            self.state.records_fetched += len(results)
            self.state.current_page += 1

            self.logger.info(
                "Page %d: %s",
                self.state.current_page,
                self.state.progress,
            )
            yield results

            url = self._parse_link_header(
                response.headers.get("Link", "")
            )

        self.state.is_complete = True

    async def _paginate_single(
        self,
    ) -> AsyncGenerator[list[dict], None]:
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
                        "Rate limited (attempt %d). Waiting %.1fs",
                        attempt + 1,
                        wait,
                    )
                    await asyncio.sleep(wait)
                else:
                    raise
            except httpx.TimeoutException:
                self.logger.warning(
                    "Timeout (attempt %d)", attempt + 1
                )
                if attempt == 2:
                    raise
        return []

    def _build_url(self, params: dict) -> str:
        """Construct full URL from base + endpoint."""
        base = self.config.base_url.rstrip("/")
        endpoint = self.config.api_endpoint
        if not endpoint.startswith("/"):
            endpoint = f"/{endpoint}"
        return f"{base}{endpoint}"

    def _extract_results(self, response: dict | list) -> list[dict]:
        """
        Extract the results array from various API response formats.

        Handles: {results: [...]}, {docs: [...]}, {data: [...]}, [...]
        """
        if isinstance(response, list):
            return response
        for key in [
            "results", "docs", "data", "items", "records", "entries",
        ]:
            if key in response:
                return response[key]
        return []

    def _extract_total(self, response: dict | list) -> int | None:
        """Extract total record count from response metadata."""
        if isinstance(response, list):
            return len(response)
        for key in [
            "total", "totalResults", "numFound", "count", "total_count",
        ]:
            if key in response:
                return int(response[key])
        return None

    def _extract_cursor(self, response: dict) -> str | None:
        """Extract next cursor from response."""
        for key in [
            "next_cursor", "cursor", "nextCursor", "next",
        ]:
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
