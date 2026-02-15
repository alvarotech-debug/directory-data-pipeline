#!/usr/bin/env python3
"""
Full directory extraction pipeline demo.

Extracts records from 3 demo sources, processes through
Bronze -> Silver -> Gold layers, and generates a quality report.

Usage:
    python examples/run_full_pipeline.py

No configuration needed — uses public APIs only.
Expected runtime: ~2-3 minutes (depending on rate limits).
Expected output: ~2,500+ records across all sources.
"""

import asyncio
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from config.settings import Settings
from src.discovery.api_analyzer import APIAnalyzer
from src.extractor.api_client import (
    CountriesRegistryExtractor,
    OpenLibraryExtractor,
    RandomProfessionalsExtractor,
)
from src.pipeline.bronze import BronzeLayer
from src.pipeline.gold import GoldLayer
from src.pipeline.silver import SilverLayer
from src.quality.validators import DataQualityValidator
from src.utils.logger import setup_logger


async def main() -> None:
    """Run the complete directory data pipeline."""
    logger = setup_logger("pipeline", level="INFO")
    settings = Settings()
    start_time = time.time()

    print("=" * 55)
    print("  Directory Data Pipeline — Full Extraction")
    print("=" * 55)
    print()

    # ── Phase 1: API Discovery (demonstration) ──────────
    print("Phase 1: API Discovery")
    print("-" * 40)
    analyzer = APIAnalyzer()
    report = await analyzer.analyze("https://openlibrary.org")
    print(report.summary())
    print()

    # ── Phase 2: Extraction ─────────────────────────────
    print("Phase 2: Data Extraction")
    print("-" * 40)

    ol_config = settings.sources[0]
    rp_config = settings.sources[1]
    cr_config = settings.sources[2]

    extractors = [
        OpenLibraryExtractor(config=ol_config),
        RandomProfessionalsExtractor(config=rp_config),
        CountriesRegistryExtractor(config=cr_config),
    ]

    all_records = []
    for extractor in extractors:
        logger.info(
            "Extracting from %s...", extractor.config.name
        )
        records = await extractor.extract_all()
        all_records.extend(records)
        logger.info(
            "  -> %d records from %s",
            len(records),
            extractor.config.name,
        )

    print(f"\nTotal records extracted: {len(all_records):,}")
    print()

    # ── Phase 3: Bronze Layer ───────────────────────────
    print("Phase 3: Bronze Layer (raw ingestion)")
    print("-" * 40)
    bronze = BronzeLayer(settings.bronze_dir)

    bronze_files = []
    for source_cfg in settings.sources:
        source_records = [
            r for r in all_records
            if r.source == source_cfg.name
        ]
        if source_records:
            path = bronze.ingest(source_records, source_cfg.name)
            bronze_files.append(path)
            print(f"  {path.name}: {len(source_records):,} records")

    print()

    # ── Phase 4: Silver Layer ───────────────────────────
    print("Phase 4: Silver Layer (cleaning)")
    print("-" * 40)
    silver = SilverLayer(settings.silver_dir)
    silver_result = silver.process(all_records)
    print(silver_result.summary())
    print()

    # ── Phase 5: Gold Layer ─────────────────────────────
    print("Phase 5: Gold Layer (enrichment)")
    print("-" * 40)
    gold = GoldLayer(settings.gold_dir)

    silver_df = silver.load_latest()
    countries_df = silver.load_latest("countries_registry")

    gold_result = gold.process(
        silver_df=silver_df,
        enrichment_data=countries_df,
    )
    gold_result.print_summary()
    print()

    # ── Phase 6: Quality Validation ─────────────────────
    print("Phase 6: Quality Validation")
    print("-" * 40)
    validator = DataQualityValidator(settings.quality)
    quality_report = validator.validate(silver_df, "all_sources")
    print(quality_report.summary())
    print()

    # ── Final Summary ───────────────────────────────────
    elapsed = time.time() - start_time
    minutes = int(elapsed // 60)
    seconds = int(elapsed % 60)

    print("=" * 55)
    print("  Directory Data Pipeline — Complete")
    print("=" * 55)
    print()
    print(f"Sources processed: {len(settings.sources)}")
    print(f"Total records extracted: {len(all_records):,}")
    print(f"Pipeline duration: {minutes}m {seconds}s")
    print()
    print("Bronze Layer:")
    print(f"  Files created: {len(bronze_files)}")
    print(f"  Raw records: {len(all_records):,}")
    print()
    print("Silver Layer:")
    print(f"  Clean records: {silver_result.clean_records:,}")
    print(
        f"  Duplicates removed: "
        f"{silver_result.duplicates_removed:,}"
    )
    print(f"  Invalid removed: {silver_result.invalid_removed:,}")
    print()
    print("Gold Layer:")
    print(f"  Enriched records: {gold_result.total_records:,}")
    if "unique_countries" in gold_result.summary:
        print(
            f"  Geographic coverage: "
            f"{gold_result.summary['unique_countries']} countries"
        )
    if "avg_completeness" in gold_result.summary:
        print(
            f"  Avg completeness score: "
            f"{gold_result.summary['avg_completeness']}"
        )
    print()
    print("Quality Report:")
    total_checks = len(quality_report.checks)
    passed_checks = sum(
        1 for c in quality_report.checks if c.passed
    )
    print(
        f"  Checks passed: {passed_checks}/{total_checks}"
        f" ({quality_report.pass_rate:.1%})"
    )
    print(f"  Errors: {len(quality_report.errors)}")
    print(f"  Warnings: {len(quality_report.warnings)}")
    for w in quality_report.warnings:
        print(f"    - {w.check_name}: {w.actual}")
    print()
    print("Output files:")
    for f in bronze_files:
        print(f"  {f}")
    print(f"  {silver_result.output_path}")
    print(f"  {gold_result.enriched_path}")
    print(f"  {gold_result.summary_path}")
    print(f"  {gold_result.quality_path}")


if __name__ == "__main__":
    asyncio.run(main())
