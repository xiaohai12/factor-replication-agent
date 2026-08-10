"""Declarative experiment matrix loader (Phase A2,
docs/multi-config-evidence-plan.md): one versioned
`experiments/<factor_id>.experiments.yaml` per factor, replacing the
previously hardcoded-in-Python `ExperimentPlan` construction and the
Streamlit ad hoc override controls (neither is versioned or auditable).

Design rules enforced here (see the plan's Decision 2 + Phase A2 section):

- `family` is NEVER authored in the yaml -- it's derived from the actual
  RESOLVED config diff against the baseline, so a declared
  "portfolio_ablation" experiment that (accidentally, or via a menu clamp)
  also changes a signal-input key is reported as what it actually is, not
  what its author intended.
- `identification_level` (`controlled`/`unidentified`) is likewise derived,
  never authored: exactly one differing resolved-config key -> `controlled`;
  zero or more-than-one -> `unidentified`/rejected (see below).
- The whole file is validated at LOAD time via `registry.build_config`'s
  existing override validation (unknown key / off-menu value both raise) --
  one bad experiment fails the whole file, not just that one run later.
- A no-op experiment (resolved config identical to baseline) is rejected at
  load time, matching the same "no silent no-ops" principle as
  `registry._validate_overrides`'s per-key warning, but stricter here since
  a whole NAMED experiment declaring zero real difference is unambiguously
  a caller mistake (unlike a single coincidentally-matching key inside a
  multi-key bundle like `HXZ_STANDARD_CONFIG` -- see docs/decision-log.md
  2026-08-03 eighth entry for why that case is only a warning).
- `expected_diff`, when given, is cross-checked against the actual resolved
  diff and mismatches are rejected -- catches "I said I changed weighting
  but the menu clamp actually left it unchanged" style bugs at load time.
- `sweep` grids are expanded via a cartesian product into individual named
  experiments, each independently validated the same way.

NOT yet implemented (documented limitation, not silently assumed): a
`baseline_ref`/`snapshot_ref` pointing at another EXPERIMENT's resolved
config (chained baselines) -- every experiment here resolves independently
from the reviewed MethodSpec plus its own `config_overrides`. `signal_input_ref`
(C&Z bridge) and `snapshot_ref` (data-vintage) are recorded on the
`ExperimentSpec` but this loader does not resolve or fetch them -- that's
Phase B/C&D's job once the underlying reference data adapters exist.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.infra.models.method_spec import ResolvedMethodSpec
from src.steps.step3_codegen.registry import ConfigOverrideError, build_config, stage_of


class ExperimentMatrixError(ValueError):
    """Raised when an `experiments/<factor_id>.experiments.yaml` file (or one
    entry in it) fails validation. One bad entry fails the WHOLE file --
    see this module's docstring."""


@dataclass
class ExperimentSpec:
    """One resolved, validated experiment from the matrix.

    `family`/`identification_level`/`resolved_diff` are always DERIVED by
    `load_experiment_matrix`, never authored in the yaml (see module
    docstring) -- the dataclass has no way to construct them independently
    of that derivation.
    """

    name: str
    config_overrides: dict[str, Any] = field(default_factory=dict)
    signal_input_ref: str | None = None
    snapshot_ref: str | None = None
    resolved_config: dict[str, Any] = field(default_factory=dict)
    resolved_diff: dict[str, dict[str, Any]] = field(default_factory=dict)
    family: str = ""
    identification_level: str = "unidentified"


@dataclass
class ExperimentMatrix:
    """The whole loaded/validated file: the baseline label, every resolved
    experiment, and `experiment_spec_hash` -- the matrix file's own content
    hash, since "this batch declared exactly these experiments" is itself
    part of a run's reproducible identity (docs/multi-config-evidence-plan.md
    Phase A2: "the matrix file itself is evidence")."""

    factor_id: str
    baseline: str
    experiments: list[ExperimentSpec]
    experiment_spec_hash: str


def _expand_sweep(sweep_entries: list[dict]) -> list[dict]:
    """Expand declarative sweep grids into individual named experiment
    dicts (cartesian product of each grid's key -> value list)."""
    expanded: list[dict] = []
    for grid in sweep_entries:
        keys = grid.get("keys")
        values = grid.get("values")
        if not keys or not values:
            raise ExperimentMatrixError(
                f"sweep entry missing 'keys' or 'values': {grid!r}"
            )
        value_lists = [values[k] for k in keys]
        for combo in itertools.product(*value_lists):
            overrides = dict(zip(keys, combo))
            name = "sweep_" + "_".join(f"{k}={v}" for k, v in overrides.items())
            expanded.append({"name": name, "config_overrides": overrides, "_from_sweep": True})
    return expanded


def _resolved_diff(baseline_config: dict, resolved_config: dict) -> dict[str, dict[str, Any]]:
    keys = set(baseline_config) | set(resolved_config)
    return {
        k: {"baseline_value": baseline_config.get(k), "track_value": resolved_config.get(k)}
        for k in keys
        if baseline_config.get(k) != resolved_config.get(k)
    }


def _derive_family(diff: dict, signal_input_ref: str | None, snapshot_ref: str | None) -> str:
    if signal_input_ref:
        return "reference_bridge"
    if snapshot_ref:
        return "data_vintage"
    stages = {stage_of(k) for k in diff}
    if stages == {"signal_input"}:
        return "signal_input"
    return "portfolio_ablation"


def _derive_identification_level(diff: dict) -> str:
    # Exactly one differing resolved-config key -> controlled, regardless of
    # whether it's a pre-signal or post-signal key (see Decision 2). Zero or
    # more than one -> unidentified. A zero-diff experiment is rejected
    # entirely before this is even called (see load_experiment_matrix).
    return "controlled" if len(diff) == 1 else "unidentified"


def build_experiment_spec(
    name: str,
    spec: ResolvedMethodSpec,
    baseline_config: dict,
    config_overrides: dict[str, Any] | None = None,
    signal_input_ref: str | None = None,
    snapshot_ref: str | None = None,
) -> ExperimentSpec:
    """Build one resolved `ExperimentSpec` -- the SAME derivation
    `load_experiment_matrix` uses per yaml entry (resolve config, diff
    against baseline, derive `family`/`identification_level`), exposed as a
    public building block so OTHER experiment sources besides a yaml file
    (e.g. `DualTrackController`'s legacy `ExperimentPlan`) produce
    `ExperimentSpec` objects with IDENTICAL classification instead of a
    second, divergent implementation.

    Raises `ConfigOverrideError` (via `registry.build_config`) for an
    unknown/off-menu override, same as the yaml path. Does NOT reject a
    no-op override here -- unlike `load_experiment_matrix`'s stricter
    yaml-loading-time policy for a single named entry, a caller like
    `ExperimentPlan`'s `HXZ_STANDARD_CONFIG` legitimately bundles several
    settings where one key can coincide with the baseline (see
    docs/decision-log.md 2026-08-03 eighth entry) -- that's a warning at
    `build_config`'s own level, not a rejection here.
    """
    overrides = config_overrides or {}
    resolved_config = build_config(spec, overrides or None)
    diff = _resolved_diff(baseline_config, resolved_config)
    return ExperimentSpec(
        name=name,
        config_overrides=overrides,
        signal_input_ref=signal_input_ref,
        snapshot_ref=snapshot_ref,
        resolved_config=resolved_config,
        resolved_diff=diff,
        family=_derive_family(diff, signal_input_ref, snapshot_ref),
        identification_level=_derive_identification_level(diff),
    )


def load_experiment_matrix(path: str | Path, spec: ResolvedMethodSpec) -> ExperimentMatrix:
    """Load, validate, and resolve one `experiments/<factor_id>.experiments.yaml`.

    Raises `ExperimentMatrixError` for: a factor_id mismatch, a duplicate
    experiment name, a malformed sweep entry, an override that
    `registry.build_config` itself rejects (unknown key / off-menu value --
    wrapped with the experiment name for context), a no-op experiment
    (resolved config identical to baseline), or an `expected_diff` that
    doesn't match the actual resolved diff.
    """
    text = Path(path).read_text()
    raw = yaml.safe_load(text) or {}

    factor_id = raw.get("factor_id")
    spec_factor_id = spec.paper.factor_id
    if factor_id != spec_factor_id:
        raise ExperimentMatrixError(
            f"experiments file factor_id {factor_id!r} does not match "
            f"MethodSpec.factor_id {spec_factor_id!r}"
        )
    baseline = raw.get("baseline", "original_method")

    entries = list(raw.get("experiments", []) or [])
    entries.extend(_expand_sweep(raw.get("sweep", []) or []))

    baseline_config = build_config(spec, None)

    resolved_specs: list[ExperimentSpec] = []
    seen_names: set[str] = set()
    for entry in entries:
        name = entry.get("name")
        if not name:
            raise ExperimentMatrixError(f"experiment entry missing 'name': {entry!r}")
        if name in seen_names:
            raise ExperimentMatrixError(f"duplicate experiment name: {name!r}")
        seen_names.add(name)

        overrides = entry.get("config_overrides") or {}
        signal_input_ref = entry.get("signal_input_ref")
        snapshot_ref = entry.get("snapshot_ref")
        expected_diff = entry.get("expected_diff")

        try:
            exp_spec = build_experiment_spec(
                name, spec, baseline_config, overrides, signal_input_ref, snapshot_ref
            )
        except ConfigOverrideError as exc:
            raise ExperimentMatrixError(f"experiment {name!r}: {exc}") from exc

        if not exp_spec.resolved_diff and not signal_input_ref and not snapshot_ref:
            if entry.get("_from_sweep"):
                # A declarative sweep grid naturally covers every combination
                # of its keys' values, including the one that happens to
                # coincide with the baseline's own resolved config (the
                # baseline is, by construction, some point inside the grid).
                # That corner isn't a caller mistake the way a single named
                # `experiments:` entry declaring no real change would be --
                # it's just skipped, since the baseline itself is already run
                # separately.
                continue
            raise ExperimentMatrixError(
                f"experiment {name!r} is a no-op: resolved config is identical "
                "to the baseline and it declares no signal_input_ref/snapshot_ref"
            )

        if expected_diff is not None:
            actual = {k: v["track_value"] for k, v in exp_spec.resolved_diff.items()}
            if actual != expected_diff:
                raise ExperimentMatrixError(
                    f"experiment {name!r}: expected_diff {expected_diff!r} does "
                    f"not match the actual resolved diff {actual!r}"
                )

        resolved_specs.append(exp_spec)

    experiment_spec_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return ExperimentMatrix(
        factor_id=factor_id,
        baseline=baseline,
        experiments=resolved_specs,
        experiment_spec_hash=experiment_spec_hash,
    )
