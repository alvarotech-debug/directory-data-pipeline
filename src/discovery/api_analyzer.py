"""
API Discovery & Analysis Tool.

Automates the initial reconnaissance phase of API reverse engineering.
Given a base URL, this tool probes for common API patterns, analyzes
response formats, and identifies pagination schemes.

In real-world engagements, this supplements manual Chrome DevTools
analysis — automating the repetitive parts of API discovery.
"""

import logging
from dataclasses import dataclass, field
from enum import Enum

import httpx


class PaginationType(Enum):
    """Pagination schemes found in professional registries."""

    OFFSET = "offset"
    CURSOR = "cursor"
    PAGE_NUMBER = "page"
    LINK_HEADER = "link"
    NONE = "none"
    UNKNOWN = "unknown"


class ResponseFormat(Enum):
    """API response format classification."""

    JSON_ARRAY = "json_array"
    JSON_WRAPPED = "json_wrapped"
    HTML = "html"
    XML = "xml"
    UNKNOWN = "unknown"


@dataclass
class DiscoveryReport:
    """Results of API analysis for a given source."""

    base_url: str
    discovered_endpoints: list[dict] = field(default_factory=list)
    pagination_type: PaginationType = PaginationType.UNKNOWN
    response_format: ResponseFormat = ResponseFormat.UNKNOWN
    estimated_total_records: int | None = None
    auth_required: bool = False
    rate_limit_detected: bool = False
    headers_required: dict = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        """Printable summary of discovery findings."""
        lines = [
            f"=== API Discovery Report: {self.base_url} ===",
            f"Endpoints found: {len(self.discovered_endpoints)}",
        ]
        for ep in self.discovered_endpoints:
            status = ep.get("status", "?")
            fmt = ep.get("format", "?")
            lines.append(f"  {ep['path']}  [{status}] ({fmt})")
        lines.extend([
            f"Pagination: {self.pagination_type.value}",
            f"Response format: {self.response_format.value}",
            f"Estimated records: {self.estimated_total_records or 'N/A'}",
            f"Auth required: {self.auth_required}",
            f"Rate limiting: {self.rate_limit_detected}",
        ])
        if self.notes:
            lines.append("Notes:")
            for note in self.notes:
                lines.append(f"  - {note}")
        return "\n".join(lines)


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
        "/search/authors.json",
    ]

    def __init__(self, timeout: int = 15) -> None:
        self.timeout = timeout
        self.logger = logging.getLogger(self.__class__.__name__)

    async def analyze(self, base_url: str) -> DiscoveryReport:
        """
        Run full API discovery against a base URL.

        Probes common endpoints, detects pagination, analyzes
        response formats, and checks authentication requirements.

        Args:
            base_url: The target website base URL.

        Returns:
            DiscoveryReport with all findings.
        """
        report = DiscoveryReport(base_url=base_url)

        async with httpx.AsyncClient(
            timeout=self.timeout, follow_redirects=True
        ) as client:
            # Phase 1: Probe endpoints
            endpoints = await self._probe_endpoints(client, base_url)
            report.discovered_endpoints = endpoints

            if not endpoints:
                report.notes.append(
                    "No API endpoints discovered via common patterns."
                )
                return report

            # Use the first successful JSON endpoint for deeper analysis
            json_endpoints = [
                ep for ep in endpoints
                if ep.get("format") in ("json_array", "json_wrapped")
            ]

            if json_endpoints:
                target = json_endpoints[0]
                target_url = f"{base_url.rstrip('/')}{target['path']}"

                # Phase 2: Detect pagination
                report.pagination_type = await self._detect_pagination(
                    client, target_url
                )

                # Phase 3: Detect response format
                response = await client.get(target_url)
                report.response_format = await self._detect_response_format(
                    response
                )

                # Phase 4: Estimate total records
                report.estimated_total_records = (
                    await self._estimate_total(client, target_url)
                )

                # Phase 5: Check auth
                report.auth_required = await self._check_auth(
                    client, target_url
                )

                report.headers_required = {
                    "Accept": "application/json",
                    "User-Agent": "Mozilla/5.0",
                }
                report.notes.append(
                    f"Primary endpoint: {target['path']}"
                )

        return report

    async def _probe_endpoints(
        self, client: httpx.AsyncClient, base_url: str
    ) -> list[dict]:
        """Try common API paths and record which ones return data."""
        discovered = []
        all_paths = self.COMMON_PATHS + self.COMMON_SEARCH_PATTERNS
        base = base_url.rstrip("/")

        for path in all_paths:
            url = f"{base}{path}"
            try:
                response = await client.get(url)
                content_type = response.headers.get(
                    "content-type", ""
                )
                fmt = self._classify_content_type(content_type)

                if response.status_code < 400:
                    discovered.append({
                        "path": path,
                        "method": "GET",
                        "format": fmt,
                        "status": response.status_code,
                    })
                    self.logger.info(
                        "Found: %s [%d] (%s)",
                        path,
                        response.status_code,
                        fmt,
                    )
                elif response.status_code in (401, 403):
                    discovered.append({
                        "path": path,
                        "method": "GET",
                        "format": fmt,
                        "status": response.status_code,
                    })
                    self.logger.info(
                        "Auth-protected: %s [%d]",
                        path,
                        response.status_code,
                    )
            except (httpx.RequestError, httpx.TimeoutException):
                continue

        return discovered

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
        try:
            response = await client.get(endpoint_url)
            body = response.json()

            # Check Link header
            link = response.headers.get("Link", "")
            if 'rel="next"' in link:
                return PaginationType.LINK_HEADER

            if isinstance(body, list):
                return PaginationType.NONE

            # Check for cursor fields
            for key in ["next_cursor", "cursor", "nextCursor"]:
                if key in body:
                    return PaginationType.CURSOR

            # Check for offset/total pattern
            has_total = any(
                k in body
                for k in ["total", "numFound", "totalResults"]
            )
            if has_total:
                # Try with offset param to confirm
                test_resp = await client.get(
                    endpoint_url, params={"offset": 0, "limit": 1}
                )
                if test_resp.status_code == 200:
                    return PaginationType.OFFSET

            # Check for page-number pattern
            test_resp = await client.get(
                endpoint_url, params={"page": 1}
            )
            if test_resp.status_code == 200:
                return PaginationType.PAGE_NUMBER

        except (httpx.RequestError, ValueError):
            pass

        return PaginationType.UNKNOWN

    async def _detect_response_format(
        self, response: httpx.Response
    ) -> ResponseFormat:
        """Classify the response format based on Content-Type and body."""
        content_type = response.headers.get("content-type", "")
        classified = self._classify_content_type(content_type)

        if classified in ("json_array", "json_wrapped"):
            return ResponseFormat(classified)
        if classified == "html":
            return ResponseFormat.HTML
        if classified == "xml":
            return ResponseFormat.XML
        return ResponseFormat.UNKNOWN

    async def _check_auth(
        self, client: httpx.AsyncClient, url: str
    ) -> bool:
        """Check if endpoint requires authentication (401/403)."""
        try:
            response = await client.get(url)
            return response.status_code in (401, 403)
        except httpx.RequestError:
            return False

    async def _estimate_total(
        self, client: httpx.AsyncClient, endpoint_url: str
    ) -> int | None:
        """
        Try to determine total record count from API metadata.

        Looks for common metadata keys: total, count, totalResults,
        numFound, etc. Falls back to None if not detectable.
        """
        try:
            response = await client.get(
                endpoint_url, params={"limit": 1}
            )
            body = response.json()
            if isinstance(body, list):
                return None
            for key in [
                "total", "totalResults", "numFound",
                "count", "total_count",
            ]:
                if key in body:
                    return int(body[key])
        except (httpx.RequestError, ValueError, TypeError):
            pass
        return None

    def _classify_content_type(self, content_type: str) -> str:
        """Classify a Content-Type header string."""
        ct = content_type.lower()
        if "json" in ct:
            return "json_wrapped"
        if "html" in ct:
            return "html"
        if "xml" in ct:
            return "xml"
        return "unknown"
