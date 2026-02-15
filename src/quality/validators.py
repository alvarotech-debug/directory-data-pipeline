"""
Data Quality Validation Framework.

Implements quality checks at multiple levels:
- Record-level: individual record validation
- Field-level: specific field format/content checks
- Dataset-level: aggregate quality metrics

Quality checks are inspired by Great Expectations patterns
but implemented without the dependency for simplicity.
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import pandas as pd

from config.settings import QualityThresholds


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
    checks: list[QualityCheck] = field(default_factory=list)
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
        """Failed checks with error severity."""
        return [
            c for c in self.checks
            if not c.passed and c.severity == "error"
        ]

    @property
    def warnings(self) -> list[QualityCheck]:
        """Failed checks with warning severity."""
        return [
            c for c in self.checks
            if not c.passed and c.severity == "warning"
        ]

    def summary(self) -> str:
        """Human-readable quality summary."""
        total = len(self.checks)
        passed = sum(1 for c in self.checks if c.passed)
        lines = [
            f"Quality Report: {self.source}",
            f"  Records: {self.total_records:,}",
            f"  Checks: {passed}/{total} passed"
            f" ({self.pass_rate:.1%})",
            f"  Errors: {len(self.errors)}",
            f"  Warnings: {len(self.warnings)}",
        ]
        for check in self.checks:
            status = "PASS" if check.passed else "FAIL"
            lines.append(
                f"    [{status}] {check.check_name}: "
                f"{check.actual} (expected {check.expected})"
            )
        return "\n".join(lines)

    def to_dict(self) -> dict:
        """Serialize for JSON export."""
        return {
            "source": self.source,
            "total_records": self.total_records,
            "generated_at": self.generated_at.isoformat(),
            "overall_pass_rate": round(self.pass_rate, 4),
            "checks": [
                {
                    "check_name": c.check_name,
                    "field": c.field,
                    "passed": c.passed,
                    "expected": c.expected,
                    "actual": c.actual,
                    "severity": c.severity,
                }
                for c in self.checks
            ],
        }


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

    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    def __init__(
        self,
        thresholds: QualityThresholds | None = None,
    ) -> None:
        self.thresholds = thresholds or QualityThresholds()
        self.logger = logging.getLogger(self.__class__.__name__)

    def validate(
        self, df: pd.DataFrame, source: str
    ) -> QualityReport:
        """Run all quality checks and return report."""
        checks: list[QualityCheck] = []
        checks.extend(self._check_completeness(df))
        checks.extend(self._check_uniqueness(df))
        checks.extend(self._check_format_compliance(df))
        checks.extend(self._check_consistency(df))
        checks.extend(self._check_freshness(df))

        report = QualityReport(
            source=source,
            total_records=len(df),
            checks=checks,
        )
        self.logger.info(report.summary())
        return report

    def _check_completeness(
        self, df: pd.DataFrame
    ) -> list[QualityCheck]:
        """
        Check that required fields have sufficient non-null values.

        Required fields: record_id, full_name, source
        Important fields (warning): location, country, specialization
        """
        checks = []

        if df.empty:
            return checks

        required = {
            "record_id": ("error", 1.0),
            "full_name": ("error", self.thresholds.min_completeness),
            "source": ("error", 1.0),
        }
        important = {
            "location": "warning",
            "country": "warning",
            "specialization": "warning",
        }

        for field_name, (severity, threshold) in required.items():
            if field_name not in df.columns:
                checks.append(QualityCheck(
                    check_name=f"completeness_{field_name}",
                    field=field_name,
                    passed=False,
                    expected=f">= {threshold:.1%} non-null",
                    actual="column missing",
                    severity=severity,
                ))
                continue

            rate = float(df[field_name].notna().mean())
            checks.append(QualityCheck(
                check_name=f"completeness_{field_name}",
                field=field_name,
                passed=rate >= threshold,
                expected=f">= {threshold:.1%} non-null",
                actual=f"{rate:.1%}",
                severity=severity,
            ))

        for field_name, severity in important.items():
            if field_name not in df.columns:
                continue
            rate = float(df[field_name].notna().mean())
            checks.append(QualityCheck(
                check_name=f"completeness_{field_name}",
                field=field_name,
                passed=rate >= self.thresholds.min_completeness,
                expected=(
                    f">= {self.thresholds.min_completeness:.1%}"
                    " non-null"
                ),
                actual=f"{rate:.1%}",
                severity=severity,
            ))

        return checks

    def _check_uniqueness(
        self, df: pd.DataFrame
    ) -> list[QualityCheck]:
        """Check for duplicate record_ids."""
        checks = []

        if df.empty or "record_id" not in df.columns:
            return checks

        unique_rate = df["record_id"].nunique() / len(df)
        checks.append(QualityCheck(
            check_name="uniqueness_record_id",
            field="record_id",
            passed=unique_rate >= self.thresholds.min_uniqueness,
            expected="100% unique",
            actual=f"{unique_rate:.1%}",
            severity="error",
        ))

        return checks

    def _check_format_compliance(
        self, df: pd.DataFrame
    ) -> list[QualityCheck]:
        """
        Validate field formats:
        - contact_email: basic email regex
        - contact_phone: contains digits, reasonable length
        - country: 2-letter ISO code
        """
        checks = []
        threshold = self.thresholds.min_format_compliance

        # Email format
        if "contact_email" in df.columns:
            emails = df["contact_email"].dropna()
            if len(emails) > 0:
                valid = emails.apply(
                    lambda e: bool(self.EMAIL_PATTERN.match(str(e)))
                )
                rate = float(valid.mean())
                checks.append(QualityCheck(
                    check_name="format_contact_email",
                    field="contact_email",
                    passed=rate >= threshold,
                    expected=f">= {threshold:.1%} valid format",
                    actual=f"{rate:.1%}",
                    severity="error",
                ))

        # Phone format
        if "contact_phone" in df.columns:
            phones = df["contact_phone"].dropna()
            if len(phones) > 0:
                valid = phones.apply(
                    lambda p: (
                        len(re.sub(r"[^\d]", "", str(p))) >= 7
                    )
                )
                rate = float(valid.mean())
                checks.append(QualityCheck(
                    check_name="format_contact_phone",
                    field="contact_phone",
                    passed=rate >= threshold,
                    expected=f">= {threshold:.1%} valid format",
                    actual=f"{rate:.1%}",
                    severity="warning",
                ))

        # Country code format
        if "country" in df.columns:
            countries = df["country"].dropna()
            if len(countries) > 0:
                valid = countries.apply(
                    lambda c: (
                        len(str(c)) == 2 and str(c).isalpha()
                    )
                )
                rate = float(valid.mean())
                checks.append(QualityCheck(
                    check_name="format_country_code",
                    field="country",
                    passed=rate >= threshold,
                    expected=f">= {threshold:.1%} valid ISO code",
                    actual=f"{rate:.1%}",
                    severity="warning",
                ))

        return checks

    def _check_consistency(
        self, df: pd.DataFrame
    ) -> list[QualityCheck]:
        """
        Cross-field logical checks:
        - If country is set, it should be a valid ISO code
        - If contact_email is set, it should contain @
        """
        checks = []

        if df.empty:
            return checks

        # Email consistency
        if "contact_email" in df.columns:
            emails = df["contact_email"].dropna()
            if len(emails) > 0:
                has_at = emails.apply(lambda e: "@" in str(e))
                rate = float(has_at.mean())
                checks.append(QualityCheck(
                    check_name="consistency_email_has_at",
                    field="contact_email",
                    passed=rate >= 0.99,
                    expected=">= 99.0% contain @",
                    actual=f"{rate:.1%}",
                    severity="error",
                ))

        # Country consistency
        if "country" in df.columns:
            countries = df["country"].dropna()
            if len(countries) > 0:
                valid_iso = countries.apply(
                    lambda c: (
                        isinstance(c, str)
                        and len(c) == 2
                        and c.isalpha()
                        and c.isupper()
                    )
                )
                rate = float(valid_iso.mean())
                checks.append(QualityCheck(
                    check_name="consistency_country_iso",
                    field="country",
                    passed=rate >= 0.95,
                    expected=">= 95.0% valid ISO alpha-2",
                    actual=f"{rate:.1%}",
                    severity="warning",
                ))

        return checks

    def _check_freshness(
        self, df: pd.DataFrame
    ) -> list[QualityCheck]:
        """Check that extracted_at is within last 24 hours."""
        checks = []

        if df.empty or "extracted_at" not in df.columns:
            return checks

        try:
            timestamps = pd.to_datetime(df["extracted_at"])
            cutoff = datetime.utcnow() - timedelta(hours=24)
            fresh = timestamps >= cutoff
            rate = float(fresh.mean())
            checks.append(QualityCheck(
                check_name="freshness_extracted_at",
                field="extracted_at",
                passed=rate >= 0.90,
                expected=">= 90.0% within 24h",
                actual=f"{rate:.1%}",
                severity="warning",
            ))
        except (ValueError, TypeError):
            checks.append(QualityCheck(
                check_name="freshness_extracted_at",
                field="extracted_at",
                passed=False,
                expected="valid datetime",
                actual="unparseable",
                severity="warning",
            ))

        return checks
