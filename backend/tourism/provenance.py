"""Provenance and data-origin models for Limen Tourism Management Agent."""
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class DataSourceType(str, Enum):
    LIVE = "live"
    SIMULATED = "simulated"
    OPERATOR_ENTERED = "operator_entered"
    CACHED = "cached"
    STALE = "stale"
    UNKNOWN = "unknown"
    FALLBACK = "fallback"


class Provenance(BaseModel):
    source_name: str
    source_type: DataSourceType
    source_url: Optional[str] = None
    fetched_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    effective_time: Optional[str] = None
    confidence: float = 1.0
    staleness: Optional[str] = None
    is_stale: bool = False
    notes: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "source_name": self.source_name,
            "source_type": self.source_type.value if isinstance(self.source_type, DataSourceType) else str(self.source_type),
            "source_url": self.source_url,
            "fetched_at": self.fetched_at,
            "effective_time": self.effective_time,
            "confidence": self.confidence,
            "staleness": self.staleness,
            "is_stale": self.is_stale,
            "notes": self.notes,
        }
