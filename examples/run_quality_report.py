#!/usr/bin/env python3
"""
Generate a standalone quality report from existing Silver data.

Usage:
    python examples/run_quality_report.py

Reads the latest Silver layer CSV and runs all quality checks.
Useful for monitoring data quality over time.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config.settings import Settings
from src.pipeline.silver import SilverLayer
from src.quality.validators import DataQualityValidator
from src.utils.logger import setup_logger


def main() -> None:
    """Generate quality report from latest Silver data."""
    setup_logger("pipeline", level="INFO")
    settings = Settings()

    print("Data Quality Report Generator")
    print("=" * 45)
    print()

    silver = SilverLayer(settings.silver_dir)
    df = silver.load_latest()

    if df is None or df.empty:
        print("No Silver data found. Run the full pipeline first:")
        print("  python examples/run_full_pipeline.py")
        return

    print(f"Loaded {len(df):,} records from Silver layer")
    print()

    validator = DataQualityValidator(settings.quality)
    report = validator.validate(df, "all_sources")

    print(report.summary())
    print()

    # Export report
    report_path = settings.gold_dir / "quality_standalone.json"
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2, default=str),
        encoding="utf-8",
    )
    print(f"Report saved to: {report_path}")


if __name__ == "__main__":
    main()
