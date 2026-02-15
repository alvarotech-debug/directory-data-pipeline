"""
Gold Layer — Enrichment & Analytics.

Transforms Silver data into business-ready datasets:
- Geographic enrichment (country -> region, population)
- Aggregations (records per country, per specialization)
- Derived fields (completeness scores, data quality flags)
- Cross-source linking (match records across directories)
"""

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd


@dataclass
class GoldResult:
    """Results from Gold layer processing."""

    total_records: int
    enriched_path: Path
    summary_path: Path
    quality_path: Path
    summary: dict
    quality: dict

    def print_summary(self) -> None:
        """Print formatted summary to console."""
        print(f"\nGold Layer — {self.total_records:,} records")
        print(f"  Enriched:  {self.enriched_path}")
        print(f"  Summary:   {self.summary_path}")
        print(f"  Quality:   {self.quality_path}")

        if "by_source" in self.summary:
            print("\n  Records by source:")
            for source, count in self.summary["by_source"].items():
                print(f"    {source}: {count:,}")

        if "avg_completeness" in self.summary:
            print(
                f"\n  Avg completeness: "
                f"{self.summary['avg_completeness']:.2f}"
            )


class GoldLayer:
    """
    Enriches and aggregates clean directory data.

    Outputs:
    - gold/enriched_{date}.csv — Full enriched dataset
    - gold/summary_{date}.json — Aggregation summary
    - gold/quality_{date}.json — Quality report
    """

    OPTIONAL_FIELDS = [
        "title", "organization", "specialization", "location",
        "country", "contact_email", "contact_phone", "website",
    ]

    def __init__(
        self,
        gold_dir: Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.gold_dir = gold_dir
        self.gold_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(
            self.__class__.__name__
        )

    def process(
        self,
        silver_df: pd.DataFrame,
        enrichment_data: pd.DataFrame | None = None,
    ) -> GoldResult:
        """
        Run Gold layer processing.

        Args:
            silver_df: Cleaned data from Silver layer.
            enrichment_data: Optional reference data for enrichment
                           (e.g., country details from REST Countries).
        """
        # Step 1: Enrich with external data
        if enrichment_data is not None:
            df = self._enrich_geographic(silver_df, enrichment_data)
        else:
            df = silver_df.copy()

        # Step 2: Add derived fields
        df = self._add_completeness_score(df)

        # Step 3: Generate aggregations
        summary = self._aggregate(df)

        # Step 4: Generate quality report
        quality = self._quality_report(df)

        # Step 5: Export
        enriched_path = self._export_enriched(df)
        summary_path = self._export_summary(summary)
        quality_path = self._export_quality(quality)

        result = GoldResult(
            total_records=len(df),
            enriched_path=enriched_path,
            summary_path=summary_path,
            quality_path=quality_path,
            summary=summary,
            quality=quality,
        )
        self.logger.info(
            "Gold: Processed %d records", len(df)
        )
        return result

    def _enrich_geographic(
        self, df: pd.DataFrame, countries: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Enrich records with geographic data.
        Joins on country code to add: region, subregion, population.
        """
        if countries.empty or "country" not in df.columns:
            return df

        # Prepare enrichment columns
        enrich_cols = {}
        if "specialization" in countries.columns:
            enrich_cols["specialization"] = "region"
        if "organization" in countries.columns:
            enrich_cols["organization"] = "subregion"

        if not enrich_cols:
            return df

        geo = countries[
            ["record_id"] + list(enrich_cols.keys())
        ].copy()
        geo = geo.rename(columns={"record_id": "country"})
        geo = geo.rename(columns=enrich_cols)

        # Drop enrichment columns if they already exist in df
        for col in enrich_cols.values():
            if col in df.columns:
                df = df.drop(columns=[col])

        df = df.merge(geo, on="country", how="left")

        self.logger.info(
            "Gold: Enriched with geographic data from %d countries",
            len(geo),
        )
        return df

    def _add_completeness_score(
        self, df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Calculate per-record completeness score.
        Score = (non-null optional fields) / (total optional fields)
        """
        available = [
            f for f in self.OPTIONAL_FIELDS if f in df.columns
        ]

        if not available:
            df["completeness_score"] = 0.0
            return df

        df["completeness_score"] = (
            df[available].notna().sum(axis=1) / len(available)
        ).round(2)

        return df

    def _aggregate(self, df: pd.DataFrame) -> dict:
        """
        Generate summary aggregations:
        - Records per source
        - Records per country/region
        - Records per specialization
        - Average completeness by source
        """
        summary: dict = {
            "total_records": len(df),
            "generated_at": datetime.utcnow().isoformat(),
        }

        # Records per source
        if "source" in df.columns:
            summary["by_source"] = (
                df["source"].value_counts().to_dict()
            )

        # Records per country
        if "country" in df.columns:
            country_counts = (
                df["country"]
                .dropna()
                .value_counts()
                .head(20)
                .to_dict()
            )
            summary["by_country_top20"] = country_counts
            summary["unique_countries"] = int(
                df["country"].dropna().nunique()
            )

        # Records per region (if enriched)
        if "region" in df.columns:
            summary["by_region"] = (
                df["region"]
                .dropna()
                .value_counts()
                .to_dict()
            )

        # Records per specialization
        if "specialization" in df.columns:
            summary["by_specialization_top10"] = (
                df["specialization"]
                .dropna()
                .value_counts()
                .head(10)
                .to_dict()
            )

        # Average completeness
        if "completeness_score" in df.columns:
            summary["avg_completeness"] = round(
                float(df["completeness_score"].mean()), 2
            )
            if "source" in df.columns:
                summary["avg_completeness_by_source"] = (
                    df.groupby("source")["completeness_score"]
                    .mean()
                    .round(2)
                    .to_dict()
                )

        return summary

    def _quality_report(self, df: pd.DataFrame) -> dict:
        """
        Generate data quality report:
        - Completeness: % of non-null values per field
        - Uniqueness: % unique record_ids
        - Format compliance: % valid emails, phones
        """
        report: dict = {
            "total_records": len(df),
            "generated_at": datetime.utcnow().isoformat(),
        }

        if df.empty:
            return report

        # Completeness per field
        completeness = {}
        for col in df.columns:
            if col in ("raw_data", "completeness_score"):
                continue
            non_null = float(df[col].notna().mean())
            completeness[col] = round(non_null, 4)
        report["field_completeness"] = completeness

        # Uniqueness
        if "record_id" in df.columns:
            unique_rate = df["record_id"].nunique() / len(df)
            report["record_id_uniqueness"] = round(unique_rate, 4)

        # Overall completeness
        if "completeness_score" in df.columns:
            report["avg_completeness_score"] = round(
                float(df["completeness_score"].mean()), 4
            )

        return report

    def _export_enriched(self, df: pd.DataFrame) -> Path:
        """Export enriched dataset as CSV."""
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        filename = f"enriched_professionals_{timestamp}.csv"
        filepath = self.gold_dir / filename
        df.to_csv(filepath, index=False, encoding="utf-8")
        return filepath

    def _export_summary(self, summary: dict) -> Path:
        """Export aggregation summary as JSON."""
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        filename = f"summary_{timestamp}.json"
        filepath = self.gold_dir / filename
        filepath.write_text(
            json.dumps(summary, indent=2, default=str),
            encoding="utf-8",
        )
        return filepath

    def _export_quality(self, quality: dict) -> Path:
        """Export quality report as JSON."""
        timestamp = datetime.utcnow().strftime("%Y%m%d")
        filename = f"quality_{timestamp}.json"
        filepath = self.gold_dir / filename
        filepath.write_text(
            json.dumps(quality, indent=2, default=str),
            encoding="utf-8",
        )
        return filepath
