"""Pipeline Tracer — lightweight event logger for pipeline execution.

Records timestamped events as the pipeline progresses through stages.
Used by the Streamlit dashboard's Trace & Logs page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class TraceEvent:
    timestamp: str
    stage: str
    event: str
    detail: str = ""
    level: str = "info"  # info | warning | error


class PipelineTracer:
    """Accumulates pipeline events for display and persistence."""

    def __init__(self, factor_id: str = ""):
        self.factor_id = factor_id
        self.events: list[TraceEvent] = []

    def log(self, stage: str, event: str, detail: str = "", level: str = "info") -> None:
        self.events.append(TraceEvent(
            timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            stage=stage,
            event=event,
            detail=detail,
            level=level,
        ))

    def get_timeline(self) -> list[dict[str, str]]:
        return [
            {
                "timestamp": e.timestamp,
                "stage": e.stage,
                "event": e.event,
                "detail": e.detail,
                "level": e.level,
            }
            for e in self.events
        ]

    def to_json(self) -> list[dict[str, str]]:
        return self.get_timeline()

    def clear(self) -> None:
        self.events.clear()
