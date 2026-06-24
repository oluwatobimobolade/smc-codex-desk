import hashlib
from pathlib import Path
from datetime import datetime, timezone
from pydantic import BaseModel
from typing import Optional

from smc_desk.data.quality_control import DataQualityReport

class ProvenanceRecord(BaseModel):
    file_path: str
    sha256: str
    venue: str
    instrument: str
    timeframe: str
    row_count: int
    start_time: datetime
    end_time: datetime
    quality_report: Optional[DataQualityReport] = None
    created_at: datetime = datetime.now(timezone.utc)

def compute_file_hash(path: Path) -> str:
    """Computes SHA-256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(path, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def build_provenance_record(path: Path, venue: str, instrument: str, timeframe: str, df_len: int, start_time: datetime, end_time: datetime, quality_report: DataQualityReport) -> ProvenanceRecord:
    file_hash = compute_file_hash(path)
    return ProvenanceRecord(
        file_path=str(path),
        sha256=file_hash,
        venue=venue,
        instrument=instrument,
        timeframe=timeframe,
        row_count=df_len,
        start_time=start_time,
        end_time=end_time,
        quality_report=quality_report
    )
