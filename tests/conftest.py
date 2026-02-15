"""Shared fixtures for pipeline tests."""

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import QualityThresholds, SourceConfig
from src.extractor.base import DirectoryRecord


@pytest.fixture
def sample_records() -> list[DirectoryRecord]:
    """Generate sample DirectoryRecord instances for testing."""
    return [
        DirectoryRecord(
            source="test_source",
            record_id="REC001",
            full_name="John Doe",
            title="Engineer",
            organization="Acme Corp",
            specialization="Software",
            location="New York",
            country="US",
            contact_email="john@example.com",
            contact_phone="+12125551234",
            website="https://johndoe.com",
            status="Active",
        ),
        DirectoryRecord(
            source="test_source",
            record_id="REC002",
            full_name="Jane Smith",
            title="Architect",
            organization="BuildCo",
            specialization="Residential",
            location="London",
            country="GB",
            contact_email="jane@example.com",
            contact_phone="+447700900123",
        ),
        DirectoryRecord(
            source="test_source",
            record_id="REC003",
            full_name="Carlos Garcia",
            location="Madrid",
            country="ES",
            contact_email="carlos@example.com",
        ),
    ]


@pytest.fixture
def sample_records_with_issues() -> list[DirectoryRecord]:
    """Records with quality issues for testing validation."""
    return [
        DirectoryRecord(
            source="test_source",
            record_id="REC001",
            full_name="  john DOE  ",
            contact_email="valid@example.com",
            contact_phone="(212) 555-1234",
            country="US",
        ),
        DirectoryRecord(
            source="test_source",
            record_id="REC002",
            full_name="jane   smith",
            contact_email="not-an-email",
            country="gb",
        ),
        DirectoryRecord(
            source="test_source",
            record_id="REC001",  # Duplicate ID
            full_name="John Doe Updated",
            country="US",
        ),
        DirectoryRecord(
            source="test_source",
            record_id="",
            full_name="",  # Invalid: empty required fields
        ),
    ]


@pytest.fixture
def offset_source_config() -> SourceConfig:
    """Config for offset-based pagination testing."""
    return SourceConfig(
        name="test_offset",
        base_url="https://example.com",
        api_endpoint="/api/search",
        pagination_type="offset",
        page_size=2,
        rate_limit=0.0,
        timeout=10,
    )


@pytest.fixture
def page_number_source_config() -> SourceConfig:
    """Config for page-number pagination testing."""
    return SourceConfig(
        name="test_page",
        base_url="https://example.com",
        api_endpoint="/api/data",
        pagination_type="page_number",
        page_size=2,
        rate_limit=0.0,
        timeout=10,
        total_records=5,
    )


@pytest.fixture
def cursor_source_config() -> SourceConfig:
    """Config for cursor-based pagination testing."""
    return SourceConfig(
        name="test_cursor",
        base_url="https://example.com",
        api_endpoint="/api/items",
        pagination_type="cursor",
        page_size=2,
        rate_limit=0.0,
        timeout=10,
    )


@pytest.fixture
def single_source_config() -> SourceConfig:
    """Config for single-response (no pagination) testing."""
    return SourceConfig(
        name="test_single",
        base_url="https://example.com",
        api_endpoint="/api/all",
        pagination_type="none",
        page_size=100,
        rate_limit=0.0,
        timeout=10,
    )


@pytest.fixture
def quality_thresholds() -> QualityThresholds:
    """Standard quality thresholds for testing."""
    return QualityThresholds(
        min_completeness=0.90,
        min_uniqueness=1.0,
        min_format_compliance=0.85,
        max_duplicate_rate=0.01,
    )


@pytest.fixture
def tmp_data_dir(tmp_path) -> dict:
    """Create temporary data directories."""
    bronze = tmp_path / "bronze"
    silver = tmp_path / "silver"
    gold = tmp_path / "gold"
    for d in [bronze, silver, gold]:
        d.mkdir()
    return {
        "bronze": bronze,
        "silver": silver,
        "gold": gold,
    }
