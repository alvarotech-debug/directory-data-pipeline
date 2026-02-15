"""Tests for concrete extractors and record mapping."""

import pytest

from src.extractor.api_client import (
    CountriesRegistryExtractor,
    OpenLibraryExtractor,
    RandomProfessionalsExtractor,
)
from src.extractor.base import DirectoryRecord


class TestOpenLibraryMapping:
    """Tests for OpenLibrary author -> DirectoryRecord mapping."""

    def setup_method(self):
        self.extractor = OpenLibraryExtractor()

    def test_openlibrary_mapping(self):
        """Mock API response, verify DirectoryRecord field mapping."""
        raw = {
            "key": "OL1234A",
            "name": "Margaret Atwood",
            "top_work": "The Handmaid's Tale",
            "work_count": 127,
            "top_subjects": ["fiction", "dystopian"],
            "birth_date": "18 November 1939",
        }
        record = self.extractor._map_to_record(raw)

        assert record is not None
        assert record.record_id == "OL1234A"
        assert record.full_name == "Margaret Atwood"
        assert record.organization == "The Handmaid's Tale"
        assert record.specialization == "fiction"
        assert record.title == "18 November 1939"
        assert record.source == "openlibrary_authors"
        assert "OL1234A" in record.profile_url

    def test_null_handling(self):
        """Records with missing fields map to None, not crash."""
        raw = {"key": "OL999A", "name": "Unknown Author"}
        record = self.extractor._map_to_record(raw)

        assert record is not None
        assert record.record_id == "OL999A"
        assert record.full_name == "Unknown Author"
        assert record.organization is None
        assert record.specialization is None
        assert record.title is None

    def test_invalid_record_skipped(self):
        """Malformed records return None and log warning."""
        # Simulate a record that causes an error in mapping
        raw = None
        record = self.extractor._map_to_record(raw)
        assert record is None

    def test_empty_subjects_handled(self):
        """Empty top_subjects list maps specialization to None."""
        raw = {
            "key": "OL111A",
            "name": "Test Author",
            "top_subjects": [],
        }
        record = self.extractor._map_to_record(raw)
        assert record is not None
        assert record.specialization is None


class TestRandomProfessionalsMapping:
    """Tests for RandomUser -> DirectoryRecord mapping."""

    def setup_method(self):
        self.extractor = RandomProfessionalsExtractor()

    def test_randomuser_mapping(self):
        """Mock API response, verify name/email/phone mapping."""
        raw = {
            "name": {"title": "Ms", "first": "Emily", "last": "Richardson"},
            "location": {
                "city": "London",
                "state": "England",
                "country": "United Kingdom",
            },
            "email": "emily.r@example.com",
            "phone": "+44-7700-900123",
            "login": {"uuid": "abc-123-def"},
            "nat": "GB",
        }
        record = self.extractor._map_to_record(raw)

        assert record is not None
        assert record.record_id == "abc-123-def"
        assert record.full_name == "Emily Richardson"
        assert record.title == "Ms"
        assert record.contact_email == "emily.r@example.com"
        assert record.contact_phone == "+44-7700-900123"
        assert record.country == "GB"
        assert "London" in record.location

    def test_null_handling(self):
        """Missing nested fields handled gracefully."""
        raw = {
            "name": {"first": "Test", "last": "User"},
            "location": {},
            "login": {"uuid": "test-uuid"},
        }
        record = self.extractor._map_to_record(raw)
        assert record is not None
        assert record.full_name == "Test User"
        assert record.contact_email is None


class TestCountriesMapping:
    """Tests for REST Countries -> DirectoryRecord mapping."""

    def setup_method(self):
        self.extractor = CountriesRegistryExtractor()

    def test_countries_mapping(self):
        """Mock API response, verify country code mapping."""
        raw = {
            "name": {"common": "United States", "official": "USA"},
            "cca2": "US",
            "region": "Americas",
            "subregion": "North America",
            "capital": ["Washington, D.C."],
        }
        record = self.extractor._map_to_record(raw)

        assert record is not None
        assert record.record_id == "US"
        assert record.full_name == "United States"
        assert record.specialization == "Americas"
        assert record.organization == "North America"
        assert record.location == "Washington, D.C."
        assert record.country == "US"

    def test_missing_capital(self):
        """Country with no capital handles gracefully."""
        raw = {
            "name": {"common": "Antarctica"},
            "cca2": "AQ",
            "region": "Antarctic",
            "capital": [],
        }
        record = self.extractor._map_to_record(raw)
        assert record is not None
        assert record.location is None

    def test_invalid_record_skipped(self):
        """Malformed record returns None."""
        record = self.extractor._map_to_record(None)
        assert record is None


class TestDirectoryRecord:
    """Tests for the DirectoryRecord dataclass."""

    def test_to_dict_excludes_raw_data(self):
        """to_dict() should not include raw_data."""
        record = DirectoryRecord(
            source="test",
            record_id="123",
            full_name="Test",
            raw_data={"key": "value"},
        )
        d = record.to_dict()
        assert "raw_data" not in d
        assert d["source"] == "test"
        assert d["record_id"] == "123"

    def test_to_dict_serializes_datetime(self):
        """extracted_at should be ISO format string."""
        record = DirectoryRecord(
            source="test",
            record_id="123",
            full_name="Test",
        )
        d = record.to_dict()
        assert isinstance(d["extracted_at"], str)
        assert "T" in d["extracted_at"]
