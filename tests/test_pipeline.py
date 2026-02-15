"""Tests for Bronze, Silver, and Gold pipeline layers."""

import json
from datetime import datetime

import pandas as pd
import pytest

from src.extractor.base import DirectoryRecord
from src.pipeline.bronze import BronzeLayer
from src.pipeline.gold import GoldLayer
from src.pipeline.silver import SilverLayer


class TestBronzeLayer:
    """Tests for raw data ingestion."""

    def test_bronze_creates_json(
        self, sample_records, tmp_data_dir
    ):
        """Verify JSON file with correct naming."""
        bronze = BronzeLayer(tmp_data_dir["bronze"])
        path = bronze.ingest(sample_records, "test_source")

        assert path.exists()
        assert path.suffix == ".json"
        assert "test_source" in path.name

    def test_bronze_preserves_raw(
        self, sample_records, tmp_data_dir
    ):
        """All fields including raw_data saved."""
        sample_records[0].raw_data = {"original": "data"}
        bronze = BronzeLayer(tmp_data_dir["bronze"])
        path = bronze.ingest(sample_records, "test_source")

        data = json.loads(path.read_text())
        assert data["record_count"] == 3
        assert len(data["records"]) == 3
        # First record should use raw_data
        assert data["records"][0] == {"original": "data"}

    def test_bronze_load_latest(
        self, sample_records, tmp_data_dir
    ):
        """load_latest returns the most recent file's records."""
        bronze = BronzeLayer(tmp_data_dir["bronze"])
        bronze.ingest(sample_records, "test_source")
        loaded = bronze.load_latest("test_source")

        assert loaded is not None
        assert len(loaded) == 3

    def test_bronze_list_files(
        self, sample_records, tmp_data_dir
    ):
        """list_files returns correct file count."""
        bronze = BronzeLayer(tmp_data_dir["bronze"])
        bronze.ingest(sample_records, "source_a")
        bronze.ingest(sample_records, "source_b")

        all_files = bronze.list_files()
        assert len(all_files) == 2

        a_files = bronze.list_files("source_a")
        assert len(a_files) == 1

    def test_bronze_stats(self, sample_records, tmp_data_dir):
        """Stats report correct file count and sources."""
        bronze = BronzeLayer(tmp_data_dir["bronze"])
        bronze.ingest(sample_records, "test_source")

        stats = bronze.stats
        assert stats["file_count"] == 1
        assert stats["total_size_mb"] >= 0
        # Verify sources listed
        assert "test_source" in stats["sources"]


class TestSilverLayer:
    """Tests for data cleaning and standardization."""

    def test_silver_deduplicates(self, tmp_data_dir):
        """Duplicate record_ids -> keep latest."""
        records = [
            DirectoryRecord(
                source="test", record_id="DUP1",
                full_name="First Version",
                extracted_at=datetime(2024, 1, 1),
            ),
            DirectoryRecord(
                source="test", record_id="DUP1",
                full_name="Second Version",
                extracted_at=datetime(2024, 6, 1),
            ),
            DirectoryRecord(
                source="test", record_id="UNIQUE",
                full_name="Unique Record",
            ),
        ]
        silver = SilverLayer(tmp_data_dir["silver"])
        result = silver.process(records)

        assert result.clean_records == 2
        assert result.duplicates_removed == 1

    def test_silver_standardizes_names(self, tmp_data_dir):
        """'  john DOE  ' -> 'John Doe'."""
        records = [
            DirectoryRecord(
                source="test", record_id="R1",
                full_name="  john DOE  ",
            ),
            DirectoryRecord(
                source="test", record_id="R2",
                full_name="jane   smith",
            ),
        ]
        silver = SilverLayer(tmp_data_dir["silver"])
        result = silver.process(records)

        df = pd.read_csv(result.output_path)
        names = df["full_name"].tolist()
        assert "John Doe" in names
        assert "Jane Smith" in names

    def test_silver_validates_emails(self, tmp_data_dir):
        """Invalid emails set to None."""
        records = [
            DirectoryRecord(
                source="test", record_id="R1",
                full_name="Valid Email",
                contact_email="user@example.com",
            ),
            DirectoryRecord(
                source="test", record_id="R2",
                full_name="Invalid Email",
                contact_email="not-an-email",
            ),
        ]
        silver = SilverLayer(tmp_data_dir["silver"])
        result = silver.process(records)

        df = pd.read_csv(result.output_path)
        # Valid email preserved
        assert "user@example.com" in df["contact_email"].tolist()
        # Invalid email should be NaN after validation
        invalid_row = df[df["full_name"] == "Invalid Email"]
        assert invalid_row["contact_email"].isna().all()

    def test_silver_rejects_invalid(self, tmp_data_dir):
        """Missing required fields -> rejected."""
        records = [
            DirectoryRecord(
                source="test", record_id="GOOD",
                full_name="Valid Record",
            ),
            DirectoryRecord(
                source="test", record_id="",
                full_name="",
            ),
        ]
        silver = SilverLayer(tmp_data_dir["silver"])
        result = silver.process(records)

        assert result.clean_records == 1
        assert result.invalid_removed >= 1

    def test_silver_exports_csv(self, tmp_data_dir):
        """Process creates a CSV file."""
        records = [
            DirectoryRecord(
                source="test", record_id="R1",
                full_name="Test User",
            ),
        ]
        silver = SilverLayer(tmp_data_dir["silver"])
        result = silver.process(records)

        assert result.output_path.exists()
        assert result.output_path.suffix == ".csv"


class TestGoldLayer:
    """Tests for enrichment and aggregation."""

    def test_gold_enriches_countries(self, tmp_data_dir):
        """Country code joined with region data."""
        silver_df = pd.DataFrame([
            {
                "source": "test",
                "record_id": "R1",
                "full_name": "Test User",
                "country": "US",
            },
        ])
        countries_df = pd.DataFrame([
            {
                "record_id": "US",
                "full_name": "United States",
                "specialization": "Americas",
                "organization": "North America",
            },
        ])

        gold = GoldLayer(tmp_data_dir["gold"])
        result = gold.process(silver_df, countries_df)

        enriched = pd.read_csv(result.enriched_path)
        assert "region" in enriched.columns
        assert enriched.iloc[0]["region"] == "Americas"

    def test_gold_completeness_score(self, tmp_data_dir):
        """Score calculated correctly."""
        silver_df = pd.DataFrame([
            {
                "source": "test",
                "record_id": "R1",
                "full_name": "Full Record",
                "title": "Eng",
                "organization": "Corp",
                "specialization": "SW",
                "location": "NYC",
                "country": "US",
                "contact_email": "a@b.com",
                "contact_phone": "+1234567890",
                "website": "https://test.com",
            },
            {
                "source": "test",
                "record_id": "R2",
                "full_name": "Sparse Record",
            },
        ])

        gold = GoldLayer(tmp_data_dir["gold"])
        result = gold.process(silver_df)

        enriched = pd.read_csv(result.enriched_path)
        scores = enriched["completeness_score"].tolist()
        assert scores[0] == 1.0  # All optional fields filled
        assert scores[1] == 0.0  # No optional fields filled

    def test_gold_aggregation(self, tmp_data_dir):
        """Records per country/source counted."""
        silver_df = pd.DataFrame([
            {
                "source": "source_a", "record_id": "R1",
                "full_name": "A1", "country": "US",
            },
            {
                "source": "source_a", "record_id": "R2",
                "full_name": "A2", "country": "US",
            },
            {
                "source": "source_b", "record_id": "R3",
                "full_name": "B1", "country": "GB",
            },
        ])

        gold = GoldLayer(tmp_data_dir["gold"])
        result = gold.process(silver_df)

        assert result.summary["by_source"]["source_a"] == 2
        assert result.summary["by_source"]["source_b"] == 1
        assert result.summary["unique_countries"] == 2

    def test_gold_exports_files(self, tmp_data_dir):
        """Gold produces enriched CSV, summary JSON, quality JSON."""
        silver_df = pd.DataFrame([
            {
                "source": "test", "record_id": "R1",
                "full_name": "Test",
            },
        ])

        gold = GoldLayer(tmp_data_dir["gold"])
        result = gold.process(silver_df)

        assert result.enriched_path.exists()
        assert result.summary_path.exists()
        assert result.quality_path.exists()
