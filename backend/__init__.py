"""FastAPI backend for the factor-replication-agent web UI.

Wraps the existing pipeline logic in src/pipeline.py and src/steps/* /
src/infra/* -- no empirical/business logic is reimplemented here, only
exposed over HTTP (+ SSE for live job progress). See docs/decision-log.md
for the UI migration rationale. Streamlit remains available until feature
parity; empirical logic stays in `src/` throughout.
"""
