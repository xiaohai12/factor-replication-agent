"""Recursive, best-effort JSON serialization for job/route results that mix
pydantic BaseModels, dataclasses (ExtractionResult/ReviewResult/...), Enums,
pandas DataFrames, and plain dicts/lists -- the shapes returned by the
existing pipeline classes (SemanticExtractor, ReviewGate, MetaCoder,
AdversarialSandbox, BacktestRunner, EvidenceStore).
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel


def to_jsonable(obj: Any) -> Any:
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json")
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, pd.DataFrame):
        return obj.to_dict(orient="records")
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [to_jsonable(v) for v in obj]
    # Fallback: let FastAPI's default encoder try (e.g. numpy scalars); if
    # that also fails it's a genuine bug in what a route/job is returning.
    return obj
