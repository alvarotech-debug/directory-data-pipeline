"""Tests for the generic pagination handler."""

import pytest
import httpx

from src.extractor.paginator import Paginator, PaginationState


class TestPaginationState:
    """Tests for PaginationState tracking."""

    def test_progress_with_total(self):
        """Progress shows percentage when total is known."""
        state = PaginationState(
            records_fetched=50, total_records=200
        )
        assert "50/200" in state.progress
        assert "25.0%" in state.progress

    def test_progress_without_total(self):
        """Progress shows count when total is unknown."""
        state = PaginationState(records_fetched=50)
        assert "50 records" in state.progress
        assert "unknown" in state.progress


class TestOffsetPagination:
    """Tests for offset-based pagination."""

    @pytest.mark.asyncio
    async def test_offset_pagination(
        self, offset_source_config, httpx_mock
    ):
        """Mock 3 pages, verify all records collected."""
        base = "https://example.com/api/search"

        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "q": "a", "offset": "0", "limit": "2",
            }),
            json={"docs": [{"id": 1}, {"id": 2}], "numFound": 5},
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "q": "a", "offset": "2", "limit": "2",
            }),
            json={"docs": [{"id": 3}, {"id": 4}], "numFound": 5},
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "q": "a", "offset": "4", "limit": "2",
            }),
            json={"docs": [{"id": 5}], "numFound": 5},
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=offset_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 5
        assert paginator.state.is_complete

    @pytest.mark.asyncio
    async def test_offset_stops_on_empty(
        self, offset_source_config, httpx_mock
    ):
        """Empty page stops pagination."""
        base = "https://example.com/api/search"

        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "q": "a", "offset": "0", "limit": "2",
            }),
            json={"docs": [{"id": 1}, {"id": 2}], "numFound": 10},
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "q": "a", "offset": "2", "limit": "2",
            }),
            json={"docs": []},
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=offset_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 2
        assert paginator.state.is_complete


class TestPageNumberPagination:
    """Tests for page-number pagination."""

    @pytest.mark.asyncio
    async def test_page_number_pagination(
        self, page_number_source_config, httpx_mock
    ):
        """Mock pages, verify page increment."""
        base = "https://example.com/api/data"

        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "page": "1", "results": "2", "seed": "portfolio_demo",
            }),
            json={"results": [{"id": 1}, {"id": 2}]},
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "page": "2", "results": "2", "seed": "portfolio_demo",
            }),
            json={"results": [{"id": 3}, {"id": 4}]},
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "page": "3", "results": "1", "seed": "portfolio_demo",
            }),
            json={"results": [{"id": 5}]},
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=page_number_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 5
        assert paginator.state.is_complete

    @pytest.mark.asyncio
    async def test_page_number_respects_max(
        self, page_number_source_config, httpx_mock
    ):
        """Stops at total_records limit."""
        base = "https://example.com/api/data"
        page_number_source_config.total_records = 3

        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "page": "1", "results": "2", "seed": "portfolio_demo",
            }),
            json={"results": [{"id": 1}, {"id": 2}]},
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "page": "2", "results": "1", "seed": "portfolio_demo",
            }),
            json={"results": [{"id": 3}]},
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=page_number_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 3


class TestCursorPagination:
    """Tests for cursor-based pagination."""

    @pytest.mark.asyncio
    async def test_cursor_pagination(
        self, cursor_source_config, httpx_mock
    ):
        """Mock cursor chain, verify follows cursors."""
        base = "https://example.com/api/items"

        httpx_mock.add_response(
            url=httpx.URL(base, params={"limit": "2"}),
            json={
                "data": [{"id": 1}, {"id": 2}],
                "next_cursor": "abc123",
            },
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "limit": "2", "cursor": "abc123",
            }),
            json={
                "data": [{"id": 3}, {"id": 4}],
                "next_cursor": "def456",
            },
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "limit": "2", "cursor": "def456",
            }),
            json={"data": [{"id": 5}]},
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=cursor_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 5
        assert paginator.state.is_complete

    @pytest.mark.asyncio
    async def test_cursor_stops_on_null(
        self, cursor_source_config, httpx_mock
    ):
        """Null cursor stops pagination."""
        base = "https://example.com/api/items"

        httpx_mock.add_response(
            url=httpx.URL(base, params={"limit": "2"}),
            json={"data": [{"id": 1}], "next_cursor": None},
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=cursor_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 1
        assert paginator.state.is_complete


class TestSingleResponse:
    """Tests for single-response (no pagination) mode."""

    @pytest.mark.asyncio
    async def test_single_response(
        self, single_source_config, httpx_mock
    ):
        """All data in one call, no pagination."""
        base = "https://example.com/api/all"

        httpx_mock.add_response(
            json=[{"id": 1}, {"id": 2}, {"id": 3}],
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=single_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 3
        assert paginator.state.is_complete


class TestRetryLogic:
    """Tests for HTTP retry behavior."""

    @pytest.mark.asyncio
    async def test_retry_on_429(
        self, offset_source_config, httpx_mock
    ):
        """Mock 429 response, verify retry with backoff."""
        base = "https://example.com/api/search"

        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "q": "a", "offset": "0", "limit": "2",
            }),
            status_code=429,
        )
        httpx_mock.add_response(
            url=httpx.URL(base, params={
                "q": "a", "offset": "0", "limit": "2",
            }),
            json={"docs": [{"id": 1}]},
        )

        all_records = []
        async with httpx.AsyncClient() as client:
            paginator = Paginator(
                config=offset_source_config, client=client
            )
            async for page in paginator.paginate():
                all_records.extend(page)

        assert len(all_records) == 1


class TestExtractHelpers:
    """Tests for result/total extraction helpers."""

    def test_extract_results_various_formats(
        self, offset_source_config
    ):
        """Test JSON wrapper detection (results, docs, data, items)."""
        import httpx as _httpx

        paginator = Paginator(
            config=offset_source_config,
            client=_httpx.AsyncClient(),
        )

        assert paginator._extract_results(
            {"results": [1, 2]}
        ) == [1, 2]
        assert paginator._extract_results(
            {"docs": [3, 4]}
        ) == [3, 4]
        assert paginator._extract_results(
            {"data": [5, 6]}
        ) == [5, 6]
        assert paginator._extract_results(
            {"items": [7, 8]}
        ) == [7, 8]
        assert paginator._extract_results([9, 10]) == [9, 10]
        assert paginator._extract_results({"other": 1}) == []

    def test_extract_total_various_keys(
        self, offset_source_config
    ):
        """Test total detection (total, numFound, count)."""
        import httpx as _httpx

        paginator = Paginator(
            config=offset_source_config,
            client=_httpx.AsyncClient(),
        )

        assert paginator._extract_total({"total": 100}) == 100
        assert paginator._extract_total(
            {"numFound": 200}
        ) == 200
        assert paginator._extract_total({"count": 50}) == 50
        assert paginator._extract_total([1, 2, 3]) == 3
        assert paginator._extract_total({"other": 1}) is None

    def test_progress_tracking(self, offset_source_config):
        """Verify PaginationState updates correctly."""
        state = PaginationState()
        assert state.records_fetched == 0
        assert not state.is_complete

        state.records_fetched = 100
        state.total_records = 500
        assert "100/500" in state.progress
        assert "20.0%" in state.progress
