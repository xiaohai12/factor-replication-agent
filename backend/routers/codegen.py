"""Signal plugin generation (MetaCoder, LLM job) + sandbox validation (fast,
sync -- no LLM call, matches AdversarialSandbox.validate()'s own cost).
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

from backend.jobs import job_manager
from backend.serialization import to_jsonable
from backend.spec_parsing import parse_spec, spec_factor_id
from backend.state import build_llm_client, build_meta_coder, pipeline
from src.infra.models.plugin import PluginRecord

router = APIRouter(prefix="/api", tags=["codegen"])


class CodegenRequest(BaseModel):
    spec: dict
    llm_provider: str = "codex"
    llm_model: str | None = None


@router.post("/codegen")
async def codegen(req: CodegenRequest) -> dict:
    def run(log):
        spec = parse_spec(req.spec)
        log(f"Building {req.llm_provider} LLM client...")
        client = build_llm_client(req.llm_provider, req.llm_model)
        meta_coder = build_meta_coder(client)
        log(f"Generating signal plugin for '{spec_factor_id(spec)}'...")
        return meta_coder.generate_plugin(spec)

    job_id = job_manager.create_job(run)
    return {"job_id": job_id}


class ValidateRequest(BaseModel):
    spec: dict
    plugin: dict
    snapshot_id: str | None = None
    config_overrides: dict | None = None


@router.post("/validate")
def validate(req: ValidateRequest) -> dict:
    spec = parse_spec(req.spec)
    plugin = PluginRecord.model_validate(req.plugin)
    script_text = None
    if req.snapshot_id:
        built = pipeline.runner.build_script(plugin, spec, req.snapshot_id, req.config_overrides)
        script_text = built["script_text"]
    report = pipeline.sandbox.validate(plugin, spec, script_text=script_text)
    return to_jsonable(report)
