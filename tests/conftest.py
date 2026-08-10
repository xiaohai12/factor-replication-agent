"""Collection-time setup shared by the whole test suite.

Must run BEFORE any test module imports `backend.main`/`backend.state`
(several backend router test files, e.g. test_session_api.py,
test_backend_api.py, test_experiment_replication_diagnosis_api.py,
test_backend_methodspecs_api.py, do `from backend.main import app` at
module level) -- `backend.state.RUNS_DIR` is resolved from
`FACTOR_AGENT_RUNS_DIR` once, at import time, not per-request. Without this,
those tests' real FastAPI `TestClient` calls write real session/evidence/
method-spec artifacts straight into the actual `runs/` directory (confirmed:
a full `pytest tests/` run left ~114 stray files there). Setting the env var
here, at conftest module level (executed during pytest collection, before
any test module import), redirects them into the same gitignored
`.runs_scratch/` convention already used for manual live-server testing (see
/memories/repo/build_commands.md).
"""

import os

os.environ.setdefault("FACTOR_AGENT_RUNS_DIR", ".runs_scratch")
