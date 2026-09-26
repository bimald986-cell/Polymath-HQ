"""Evidence/provenance records used before knowledge promotion."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from typing import Optional

@dataclass(frozen=True)
class Evidence:
    source: str
    claim: str
    retrieved_at: str
    confidence: str = "medium"
    evidence_status: str = "unverified"
    published_at: Optional[str] = None

    @classmethod
    def capture(cls, source: str, claim: str, confidence: str = "medium", evidence_status: str = "unverified", published_at: Optional[str] = None):
        return cls(source, claim, datetime.now(timezone.utc).isoformat(), confidence, evidence_status, published_at)

    def as_dict(self):
        return asdict(self)

    def promotable(self) -> bool:
        return self.evidence_status in {"verified", "corroborated"} and self.confidence in {"medium", "high"}
