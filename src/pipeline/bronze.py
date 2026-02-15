"""
Bronze Layer — Raw Data Ingestion.

Stores raw API responses exactly as received. No cleaning,
no transformation, no deduplication. This is the immutable
source of truth that all downstream processing references.

Design principle: If the API changes or we discover a mapping
error, we can always reprocess from Bronze without re-extracting.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

from src.extractor.base import DirectoryRecord


class BronzeLayer:
    """
    Manages Bronze (raw) data storage.

    Storage format: JSON files, one per extraction batch.
    Naming: {source}_{timestamp}.json
    Policy: Append-only, never modify or delete.
    """

    def __init__(
        self,
        bronze_dir: Path,
        logger: logging.Logger | None = None,
    ) -> None:
        self.bronze_dir = bronze_dir
        self.bronze_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger or logging.getLogger(
            self.__class__.__name__
        )

    def ingest(
        self,
        records: list[DirectoryRecord],
        source: str,
    ) -> Path:
        """
        Save raw records to Bronze layer.

        Returns the path to the created file.
        Each record's raw_data field is preserved if available.
        """
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{source}_{timestamp}.json"
        filepath = self.bronze_dir / filename

        payload = {
            "source": source,
            "extracted_at": datetime.utcnow().isoformat(),
            "record_count": len(records),
            "records": [
                r.raw_data if r.raw_data else r.to_dict()
                for r in records
            ],
        }

        filepath.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )

        self.logger.info(
            "Bronze: Saved %d records to %s",
            len(records),
            filename,
        )
        return filepath

    def load_latest(self, source: str) -> list[dict] | None:
        """Load the most recent Bronze file for a given source."""
        files = self.list_files(source)
        if not files:
            self.logger.warning(
                "No Bronze files found for source: %s", source
            )
            return None

        latest = files[-1]
        data = json.loads(latest.read_text(encoding="utf-8"))
        self.logger.info(
            "Bronze: Loaded %d records from %s",
            len(data.get("records", [])),
            latest.name,
        )
        return data.get("records", [])

    def list_files(self, source: str | None = None) -> list[Path]:
        """List all Bronze files, optionally filtered by source."""
        pattern = f"{source}_*.json" if source else "*.json"
        files = sorted(self.bronze_dir.glob(pattern))
        return files

    @property
    def stats(self) -> dict:
        """Storage statistics: file count, total size, date range."""
        files = self.list_files()
        if not files:
            return {
                "file_count": 0,
                "total_size_mb": 0,
                "sources": [],
            }

        total_size = sum(f.stat().st_size for f in files)
        sources = list({
            f.stem.rsplit("_", 2)[0] for f in files
        })

        return {
            "file_count": len(files),
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "sources": sources,
        }
