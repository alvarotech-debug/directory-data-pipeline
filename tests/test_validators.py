"""Tests for data quality validation framework."""

from datetime import datetime, timedelta

import pandas as pd
import pytest

from config.settings import QualityThresholds
from src.quality.validators import (
    DataQualityValidator,
    QualityCheck,
    QualityReport,
)


class TestCompleteness:
    """Tests for completeness checks."""

    def test_completeness_pass(self, quality_thresholds):
        """All required fields present -> pass."""
        df = pd.DataFrame([
            {
                "record_id": "R1", "full_name": "Test User",
                "source": "test",
            },
            {
                "record_id": "R2", "full_name": "Other User",
                "source": "test",
            },
        ])
        validator = DataQualityValidator(quality_thresholds)
        report = validator.validate(df, "test")

        completeness_checks = [
            c for c in report.checks
            if c.check_name.startswith("completeness_")
            and c.field in ("record_id", "full_name", "source")
        ]
        assert all(c.passed for c in completeness_checks)

    def test_completeness_fail(self, quality_thresholds):
        """Missing full_name -> fail."""
        df = pd.DataFrame([
            {"record_id": "R1", "full_name": None, "source": "test"},
            {"record_id": "R2", "full_name": None, "source": "test"},
        ])
        validator = DataQualityValidator(quality_thresholds)
        report = validator.validate(df, "test")

        name_check = next(
            c for c in report.checks
            if c.check_name == "completeness_full_name"
        )
        assert not name_check.passed


class TestUniqueness:
    """Tests for uniqueness checks."""

    def test_uniqueness_pass(self, quality_thresholds):
        """All unique IDs -> pass."""
        df = pd.DataFrame([
            {"record_id": "R1", "full_name": "A", "source": "test"},
            {"record_id": "R2", "full_name": "B", "source": "test"},
        ])
        validator = DataQualityValidator(quality_thresholds)
        report = validator.validate(df, "test")

        uniq_check = next(
            c for c in report.checks
            if c.check_name == "uniqueness_record_id"
        )
        assert uniq_check.passed

    def test_uniqueness_fail(self, quality_thresholds):
        """Duplicate IDs -> fail with count."""
        df = pd.DataFrame([
            {"record_id": "R1", "full_name": "A", "source": "test"},
            {"record_id": "R1", "full_name": "B", "source": "test"},
        ])
        validator = DataQualityValidator(quality_thresholds)
        report = validator.validate(df, "test")

        uniq_check = next(
            c for c in report.checks
            if c.check_name == "uniqueness_record_id"
        )
        assert not uniq_check.passed


class TestFormatCompliance:
    """Tests for format validation."""

    def test_email_format_valid(self, quality_thresholds):
        """'user@example.com' -> pass."""
        df = pd.DataFrame([
            {
                "record_id": "R1", "full_name": "A",
                "source": "test",
                "contact_email": "user@example.com",
            },
        ])
        validator = DataQualityValidator(quality_thresholds)
        report = validator.validate(df, "test")

        email_check = next(
            (c for c in report.checks
             if c.check_name == "format_contact_email"),
            None,
        )
        assert email_check is not None
        assert email_check.passed

    def test_email_format_invalid(self, quality_thresholds):
        """'not-an-email' -> fail."""
        df = pd.DataFrame([
            {
                "record_id": "R1", "full_name": "A",
                "source": "test",
                "contact_email": "not-an-email",
            },
        ])
        validator = DataQualityValidator(quality_thresholds)
        report = validator.validate(df, "test")

        email_check = next(
            (c for c in report.checks
             if c.check_name == "format_contact_email"),
            None,
        )
        assert email_check is not None
        assert not email_check.passed


class TestQualityReport:
    """Tests for QualityReport dataclass."""

    def test_quality_report_summary(self):
        """Report generates readable summary."""
        report = QualityReport(
            source="test",
            total_records=100,
            checks=[
                QualityCheck(
                    check_name="test_pass",
                    field="field_a",
                    passed=True,
                    expected=">= 90%",
                    actual="95%",
                ),
                QualityCheck(
                    check_name="test_fail",
                    field="field_b",
                    passed=False,
                    expected=">= 90%",
                    actual="80%",
                ),
            ],
        )
        summary = report.summary()
        assert "test" in summary
        assert "100" in summary
        assert "PASS" in summary
        assert "FAIL" in summary

    def test_quality_report_pass_rate(self):
        """Pass rate calculated correctly."""
        report = QualityReport(
            source="test",
            total_records=100,
            checks=[
                QualityCheck(
                    check_name="c1", field=None,
                    passed=True, expected="", actual="",
                ),
                QualityCheck(
                    check_name="c2", field=None,
                    passed=True, expected="", actual="",
                ),
                QualityCheck(
                    check_name="c3", field=None,
                    passed=False, expected="", actual="",
                ),
            ],
        )
        assert abs(report.pass_rate - 2 / 3) < 0.01

    def test_quality_report_to_dict(self):
        """to_dict serializes correctly for JSON export."""
        report = QualityReport(
            source="test",
            total_records=50,
            checks=[
                QualityCheck(
                    check_name="test_check",
                    field="record_id",
                    passed=True,
                    expected="100% unique",
                    actual="100.0%",
                    severity="error",
                ),
            ],
        )
        d = report.to_dict()
        assert d["source"] == "test"
        assert d["total_records"] == 50
        assert len(d["checks"]) == 1
        assert d["checks"][0]["check_name"] == "test_check"

    def test_errors_and_warnings(self):
        """Errors and warnings properties filter correctly."""
        report = QualityReport(
            source="test",
            total_records=10,
            checks=[
                QualityCheck(
                    check_name="err", field=None, passed=False,
                    expected="", actual="", severity="error",
                ),
                QualityCheck(
                    check_name="warn", field=None, passed=False,
                    expected="", actual="", severity="warning",
                ),
                QualityCheck(
                    check_name="ok", field=None, passed=True,
                    expected="", actual="", severity="error",
                ),
            ],
        )
        assert len(report.errors) == 1
        assert len(report.warnings) == 1


class TestFreshness:
    """Tests for freshness checks."""

    def test_freshness_check(self, quality_thresholds):
        """Old timestamps flagged."""
        old_time = (
            datetime.utcnow() - timedelta(hours=48)
        ).isoformat()
        df = pd.DataFrame([
            {
                "record_id": "R1", "full_name": "A",
                "source": "test", "extracted_at": old_time,
            },
        ])
        validator = DataQualityValidator(quality_thresholds)
        report = validator.validate(df, "test")

        freshness = next(
            (c for c in report.checks
             if c.check_name == "freshness_extracted_at"),
            None,
        )
        assert freshness is not None
        assert not freshness.passed
