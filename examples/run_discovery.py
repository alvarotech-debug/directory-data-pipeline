#!/usr/bin/env python3
"""
API Discovery demo — analyze a website for hidden API endpoints.

Usage:
    python examples/run_discovery.py [url]
    python examples/run_discovery.py  # defaults to openlibrary.org

Demonstrates the reverse engineering methodology:
1. Probe common API path patterns
2. Analyze response formats
3. Detect pagination schemes
4. Report findings
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.discovery.api_analyzer import APIAnalyzer
from src.utils.logger import setup_logger


async def main() -> None:
    """Run API discovery against a target URL."""
    setup_logger("pipeline", level="INFO")

    url = sys.argv[1] if len(sys.argv) > 1 else "https://openlibrary.org"

    print(f"API Discovery — Analyzing: {url}")
    print("=" * 50)
    print()

    analyzer = APIAnalyzer(timeout=15)
    report = await analyzer.analyze(url)

    print(report.summary())
    print()

    if report.discovered_endpoints:
        print("Recommended extraction approach:")
        print(f"  Pagination: {report.pagination_type.value}")
        print(f"  Format: {report.response_format.value}")
        if report.estimated_total_records:
            print(
                f"  Estimated records: "
                f"{report.estimated_total_records:,}"
            )
        print(
            f"  Auth required: "
            f"{'Yes' if report.auth_required else 'No'}"
        )
    else:
        print("No API endpoints found via automated probing.")
        print("Manual DevTools analysis recommended.")


if __name__ == "__main__":
    asyncio.run(main())
