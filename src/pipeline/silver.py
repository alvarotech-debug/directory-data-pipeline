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

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.extractor.base import DirectoryRecord


@dataclass
class SilverResult:
    """Results from Silver layer processing."""

    clean_records: int
    duplicates_removed: int
    invalid_removed: int
    output_path: Path
    rejection_reasons: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        """Human-readable processing summary."""
        lines = [
            "Silver Layer Summary:",
            f"  Clean records: {self.clean_records:,}",
            f"  Duplicates removed: {self.duplicates_removed:,}",
            f"  Invalid removed: {self.invalid_removed:,}",
            f"  Output: {self.output_path}",
        ]
        if self.rejection_reasons:
            lines.append(
                f"  Top rejection reasons: "
                f"{len(self.rejection_reasons)}"
            )
        return "\n".join(lines)


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

    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    def __init__(
        self,
        silver_dir: Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.silver_dir = silver_dir
        self.silver_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(
            self.__class__.__name__
        )

    def process(
        self,
        records: list[DirectoryRecord],
    ) -> SilverResult:
        """
        Run full Silver processing pipeline.

        Returns SilverResult with clean records and processing stats.
        """
        df = pd.DataFrame([r.to_dict() for r in records])

        if df.empty:
            output_path = self._export(df)
            return SilverResult(
                clean_records=0,
                duplicates_removed=0,
                invalid_removed=0,
                output_path=output_path,
            )

        # Step 1: Deduplicate
        before_dedup = len(df)
        df = self._deduplicate(df)
        dupes_removed = before_dedup - len(df)

        # Step 2: Standardize fields
        df = self._standardize_names(df)
        df = self._standardize_phones(df)
        df = self._validate_emails(df)
        df = self._normalize_countries(df)

        # Step 3: Remove invalid
        df, rejected = self._remove_invalid(df)

        # Step 4: Export
        output_path = self._export(df)

        result = SilverResult(
            clean_records=len(df),
            duplicates_removed=dupes_removed,
            invalid_removed=len(rejected),
            output_path=output_path,
            rejection_reasons=rejected,
        )
        self.logger.info(result.summary())
        return result

    def _deduplicate(self, df: pd.DataFrame) -> pd.DataFrame:
        """Remove duplicate record_ids, keeping the latest extraction."""
        if "record_id" not in df.columns:
            return df
        df = df.sort_values("extracted_at", ascending=False)
        df = df.drop_duplicates(subset=["record_id"], keep="first")
        return df.reset_index(drop=True)

    def _standardize_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize name fields:
        - Strip whitespace
        - Title case
        - Remove extra internal spaces
        """
        if "full_name" in df.columns:
            df["full_name"] = (
                df["full_name"]
                .fillna("")
                .str.strip()
                .str.replace(r"\s+", " ", regex=True)
                .str.title()
            )
        return df

    def _standardize_phones(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Attempt to standardize phone numbers.
        Strips non-digit characters except leading +.
        Best-effort — not all formats will parse cleanly.
        """
        if "contact_phone" not in df.columns:
            return df

        def clean_phone(phone: str | None) -> str | None:
            if not phone or pd.isna(phone):
                return None
            cleaned = phone.strip()
            if not cleaned:
                return None
            # Keep leading +, strip other non-digit characters
            if cleaned.startswith("+"):
                digits = "+" + re.sub(r"[^\d]", "", cleaned[1:])
            else:
                digits = re.sub(r"[^\d]", "", cleaned)
            if len(digits.replace("+", "")) < 7:
                return None
            return digits

        df["contact_phone"] = df["contact_phone"].apply(clean_phone)
        return df

    def _validate_emails(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Validate email format using regex.
        Marks invalid emails as None rather than removing records.
        """
        if "contact_email" not in df.columns:
            return df

        def validate_email(email: str | None) -> str | None:
            if not email or pd.isna(email):
                return None
            email = email.strip().lower()
            if self.EMAIL_PATTERN.match(email):
                return email
            return None

        df["contact_email"] = df["contact_email"].apply(
            validate_email
        )
        return df

    def _normalize_countries(self, df: pd.DataFrame) -> pd.DataFrame:
        """Normalize country fields to ISO 3166 alpha-2 codes."""
        if "country" not in df.columns:
            return df

        def normalize(code: str | None) -> str | None:
            if not code or pd.isna(code):
                return None
            code = str(code).strip().upper()
            if len(code) == 2 and code.isalpha():
                return code
            return code

        df["country"] = df["country"].apply(normalize)
        return df

    def _remove_invalid(
        self, df: pd.DataFrame
    ) -> tuple[pd.DataFrame, list[dict]]:
        """
        Remove records that fail minimum requirements:
        - record_id is required
        - full_name is required and non-empty

        Returns (valid_df, list of rejected records with reasons).
        """
        rejected = []

        # Check record_id
        mask_no_id = df["record_id"].isna() | (
            df["record_id"].astype(str).str.strip() == ""
        )
        for idx in df[mask_no_id].index:
            rejected.append({
                "index": int(idx),
                "reason": "missing_record_id",
                "record_id": None,
            })

        # Check full_name
        mask_no_name = df["full_name"].isna() | (
            df["full_name"].astype(str).str.strip() == ""
        )
        for idx in df[mask_no_name].index:
            rejected.append({
                "index": int(idx),
                "reason": "missing_full_name",
                "record_id": str(
                    df.loc[idx, "record_id"]
                ) if not pd.isna(df.loc[idx, "record_id"]) else None,
            })

        invalid_mask = mask_no_id | mask_no_name
        valid_df = df[~invalid_mask].reset_index(drop=True)

        if rejected:
            self.logger.info(
                "Silver: Rejected %d invalid records",
                len(rejected),
            )

        return valid_df, rejected

    def _export(self, df: pd.DataFrame) -> Path:
        """Save to Silver directory as CSV."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"all_professionals_{timestamp}.csv"
        filepath = self.silver_dir / filename
        df.to_csv(filepath, index=False, encoding="utf-8")

        # Also save as "latest" for easy access
        latest = self.silver_dir / "all_professionals_latest.csv"
        df.to_csv(latest, index=False, encoding="utf-8")

        self.logger.info(
            "Silver: Exported %d records to %s",
            len(df),
            filename,
        )
        return filepath

    def load_latest(
        self, source: str | None = None
    ) -> pd.DataFrame | None:
        """Load the latest Silver dataset."""
        latest = self.silver_dir / "all_professionals_latest.csv"
        if not latest.exists():
            self.logger.warning("No Silver data found")
            return None

        df = pd.read_csv(latest)
        if source:
            df = df[df["source"] == source]
        return df
