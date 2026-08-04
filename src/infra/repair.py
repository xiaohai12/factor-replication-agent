"""RepairLoop — the one shared technical self-debugging loop.

This is the ONLY automatic feedback loop in the pipeline: a bounded
"build the script -> validate/execute -> on a TECHNICAL failure, ask
MetaCoder to repair the code -> rebuild -> re-validate" cycle. It is used
identically by:
  - `Pipeline.run_from_method_spec` (single-track path),
  - `Pipeline.run_full_pipeline` (steps 3-4 validate stage), and
  - `DualTrackController._run_track` (per-track execute stage),
so there is exactly one implementation instead of three near-duplicates.

Scope discipline (see docs/decision-log.md): this loop only ever feeds back
"WHERE the problem is" (the raw validation errors / execution stderr) to
MetaCoder — never the answer, and never an empirical parameter. Empirical
correctness is decided upstream at the human-gated Review Gate, not here;
`MetaCoder.repair_plugin`'s prompt forbids touching empirical assumptions.

Every repair iteration is recorded as a `RepairAttempt` (audit trail); the
caller attaches the accumulated history to the RunRecord it persists.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.infra.models.method_spec import MethodSpec
from src.infra.models.plugin import PluginRecord
from src.infra.models.run_record import RepairAttempt


#: Bounded retry budget for the technical repair loop (both validate and
#: execute stages). Shared by every caller so there is one number, not three.
MAX_REPAIR_RETRIES = 3


@dataclass
class ValidateOutcome:
    """Result of `RepairLoop.build_validate_repair`."""

    plugin: PluginRecord
    built: dict
    history: list[RepairAttempt] = field(default_factory=list)


@dataclass
class ExecuteOutcome:
    """Result of `RepairLoop.execute_with_repair`.

    `error` is None on success (and `result` holds the execute() payload);
    on exhaustion `error` is the last failure text and `result` is None. The
    caller decides whether to raise or persist a failed RunRecord — the loop
    itself stays policy-free.
    """

    result: dict | None
    plugin: PluginRecord
    built: dict
    history: list[RepairAttempt] = field(default_factory=list)
    error: str | None = None


class RepairLoop:
    """Bounded technical repair loop shared across the pipeline.

    Collaborators mirror what `DualTrackController` already takes, so it can be
    constructed from the same objects:
      - `runner`     — BacktestRunner (build_script / execute)
      - `sandbox`    — AdversarialSandbox (validate)
      - `meta_coder` — MetaCoder (repair_plugin; its llm_client gates repair)
    """

    def __init__(self, runner, sandbox, meta_coder, max_retries: int = MAX_REPAIR_RETRIES):
        self.runner = runner
        self.sandbox = sandbox
        self.meta_coder = meta_coder
        self.max_retries = max_retries

    def build_validate_repair(
        self,
        plugin: PluginRecord,
        spec: MethodSpec,
        snapshot_id: str,
        config_overrides: dict | None,
        data=None,
        track_name: str | None = None,
    ) -> ValidateOutcome:
        """Build the ONE standalone script and validate it, repairing on a
        technical failure, up to `max_retries` times.

        Rebuilds fresh on every attempt (including after a repair produces new
        plugin code) and validates THAT exact script, so whatever comes back
        validated is byte-for-byte what will later be executed.

        `data`, when supplied, is a small real-data slice passed through to the
        sandbox's compute_signal execution smoke test.

        `track_name`, when supplied, is forwarded to `BacktestRunner.
        build_script()` so multi-track callers (`DualTrackController`) never
        collide on the same on-disk script/output filename.

        Raises RuntimeError if the plugin still fails after `max_retries`
        repairs.
        """
        history: list[RepairAttempt] = []
        built: dict = {}
        for attempt in range(self.max_retries + 1):
            built = self.runner.build_script(plugin, spec, snapshot_id, config_overrides, track_name)
            report = self.sandbox.validate(
                plugin, spec, script_text=built["script_text"], data=data
            )
            plugin.validation_report = report
            if report.passed:
                plugin.validation_status = "passed"
                if history:
                    history[-1].passed = True
                return ValidateOutcome(plugin=plugin, built=built, history=history)
            if attempt < self.max_retries:
                code_before = plugin.code_hash
                plugin = self.meta_coder.repair_plugin(plugin, report.errors)
                history.append(
                    RepairAttempt(
                        attempt_index=attempt,
                        trigger_stage="validate",
                        trigger_error="; ".join(report.errors)[:2000],
                        code_hash_before=code_before,
                        code_hash_after=plugin.code_hash,
                    )
                )
            else:
                raise RuntimeError(
                    f"Plugin repair failed after {self.max_retries} attempts: {report.errors}"
                )
        return ValidateOutcome(plugin=plugin, built=built, history=history)

    def execute_with_repair(
        self,
        plugin: PluginRecord,
        built: dict,
        spec: MethodSpec,
        snapshot_id: str,
        config_overrides: dict | None,
        data=None,
        track_name: str | None = None,
    ) -> ExecuteOutcome:
        """Execute the already-built script, repairing on a technical run
        failure, up to `max_retries` times.

        On each execution failure the run's stderr is fed back to MetaCoder and
        the script is rebuilt AND re-validated (`build_validate_repair`) before
        the next attempt, so the invariant "what was validated is exactly what
        gets executed" holds on every attempt. Repair is only attempted when an
        LLM client is available; otherwise the first failure ends the loop.

        Never raises for an execution failure — returns an `ExecuteOutcome`
        with `error` set so the caller chooses the failure policy (raise vs
        persist a failed RunRecord).
        """
        history: list[RepairAttempt] = []
        last_error: str | None = None
        for attempt in range(self.max_retries + 1):
            try:
                result = self.runner.execute(built)
                if history:
                    history[-1].passed = True
                return ExecuteOutcome(
                    result=result, plugin=plugin, built=built, history=history, error=None
                )
            except RuntimeError as run_error:
                last_error = str(run_error)
                can_repair = attempt < self.max_retries and self.meta_coder.llm_client is not None
                if not can_repair:
                    return ExecuteOutcome(
                        result=None, plugin=plugin, built=built, history=history, error=last_error
                    )
                code_before = plugin.code_hash
                plugin = self.meta_coder.repair_plugin(plugin, [last_error])
                history.append(
                    RepairAttempt(
                        attempt_index=attempt,
                        trigger_stage="execute",
                        trigger_error=last_error[:2000],
                        code_hash_before=code_before,
                        code_hash_after=plugin.code_hash,
                    )
                )
                revalidated = self.build_validate_repair(
                    plugin, spec, snapshot_id, config_overrides, data, track_name
                )
                plugin, built = revalidated.plugin, revalidated.built
                history.extend(revalidated.history)
        return ExecuteOutcome(
            result=None, plugin=plugin, built=built, history=history, error=last_error
        )
