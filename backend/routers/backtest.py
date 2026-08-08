"""Single-run backtest execution (BacktestRunner.build_script + .execute, as
a job since the subprocess run can take up to ~2 minutes) + snapshot listing
(data-source picker for the frontend).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.jobs import job_manager
from backend.serialization import to_jsonable
from backend.spec_parsing import parse_spec, spec_factor_id
from backend.state import (
    ensure_local_snapshot,
    ensure_real_wrds_snapshot,
    ensure_synthetic_snapshot,
    ensure_validation_sample_snapshot,
    pipeline,
)
from src.infra.models.plugin import PluginRecord

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.get("/snapshots")
def list_snapshots() -> list[dict]:
    ensure_synthetic_snapshot()
    ensure_local_snapshot()
    ensure_real_wrds_snapshot()
    ensure_validation_sample_snapshot()
    return [to_jsonable(s) for s in pipeline.data_layer.snapshots.list_snapshots()]


class BacktestRunRequest(BaseModel):
    spec: dict
    plugin: dict
    snapshot_id: str
    config_overrides: dict | None = None
    track: str = "original_method"


@router.post("/run")
async def run_backtest(req: BacktestRunRequest) -> dict:
    def run(log):
        spec = parse_spec(req.spec)
        plugin = PluginRecord.model_validate(req.plugin)
        log(f"Building backtest script for '{spec_factor_id(spec)}' (snapshot '{req.snapshot_id}')...")
        built = pipeline.runner.build_script(plugin, spec, req.snapshot_id, req.config_overrides)
        log("Executing backtest script via subprocess...")
        result = pipeline.runner.execute(built, log=log)
        log("Backtest finished; persisting RunRecord to evidence store...")
        run_record = pipeline.runner.make_run_record(spec, plugin, req.track, result)
        pipeline.evidence_store.save_run(run_record)
        pipeline.run_registry.register(run_record)
        log(f"Run '{run_record.run_id}' saved.")
        return {
            "run_record": run_record,
            "metrics": result["metrics"],
            "return_series": result["return_series"],
            "config": result["config"],
            "script_path": result["script_path"],
        }

    job_id = job_manager.create_job(run)
    return {"job_id": job_id}
