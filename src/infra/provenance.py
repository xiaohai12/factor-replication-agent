"""Runtime provenance collection (docs/multi-config-evidence-plan.md Phase
0.5): a generated backtest script does `from src.infra.backtest_engine import
BacktestExecutor` at run time, so two runs with byte-identical generated
script text can still execute genuinely different engine logic if the
repository changed between them. "Same script bytes" alone does not prove
"same execution logic" -- this module records what actually executed.

Best-effort by design: provenance collection must never fail or block a run.
Any individual field that can't be determined (no git repo, package not
installed, file missing) falls back to a documented sentinel rather than
raising, and the whole function never raises.
"""

from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]

# The engine module whose *content* (not just its existence) actually
# determines execution logic for every generated script's
# `BacktestExecutor.run_with_config()` call.
_ENGINE_SOURCE_FILE = _REPO_ROOT / "src" / "infra" / "backtest_engine" / "__init__.py"

# Packages whose exact installed version can change engine numerics
# (statsmodels/linearmodels affect alpha/Fama-MacBeth estimation; pandas/numpy
# affect groupby/rolling semantics across versions).
_TRACKED_PACKAGES = ("pandas", "numpy", "statsmodels", "linearmodels")


def _run_git(*args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=_REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _git_commit() -> str:
    return _run_git("rev-parse", "HEAD") or "unknown"


def _git_dirty() -> bool | None:
    status = _run_git("status", "--porcelain")
    if status is None:
        return None
    return bool(status)


def _file_sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (OSError, ValueError):
        return None


def _package_versions() -> dict[str, str]:
    from importlib import metadata

    versions: dict[str, str] = {}
    for pkg in _TRACKED_PACKAGES:
        try:
            versions[pkg] = metadata.version(pkg)
        except metadata.PackageNotFoundError:
            versions[pkg] = "not_installed"
    return versions


def collect_runtime_provenance(
    ff_factors_path: str | None = None, liquidity_factors_path: str | None = None
) -> dict[str, Any]:
    """Collect a best-effort snapshot of "what actually ran" for a RunRecord.

    Returns a plain JSON-serializable dict (never raises):
      - git_commit: HEAD commit hash, or "unknown" if not a git checkout.
      - git_dirty: True if the worktree has uncommitted changes, None if
        undeterminable (not a git checkout / git not on PATH).
      - engine_source_hash: sha256 of the single-file BacktestExecutor engine
        module's current on-disk content. Two runs sharing this hash ran
        provably identical engine logic regardless of git commit (e.g. an
        uncommitted local edit); differing hashes mean the engine itself
        changed between runs even at the same commit.
      - python_version: the interpreter version string.
      - package_versions: pinned versions of numerics-affecting dependencies.
      - ff_factors_hash: sha256 of the external FF-factor file actually
        consumed for alpha computation, if one was supplied and exists.
      - liquidity_factors_hash: sha256 of the external Pastor-Stambaugh
        liquidity_factors.csv actually consumed for `alpha_liq`, if one was
        supplied and exists (2026-08-13).
    """
    return {
        "git_commit": _git_commit(),
        "git_dirty": _git_dirty(),
        "engine_source_hash": _file_sha256(_ENGINE_SOURCE_FILE),
        "python_version": sys.version.split()[0],
        "package_versions": _package_versions(),
        "ff_factors_hash": (
            _file_sha256(Path(ff_factors_path)) if ff_factors_path else None
        ),
        "liquidity_factors_hash": (
            _file_sha256(Path(liquidity_factors_path)) if liquidity_factors_path else None
        ),
    }
