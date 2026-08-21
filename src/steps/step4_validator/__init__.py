"""Adversarial Sandbox - Validate generated plugins before use."""

from __future__ import annotations

import ast
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from src.infra.market_equity_policy import (
    FORBIDDEN_COMPUSTAT_MARKET_EQUITY_COLUMNS,
    requires_crsp_fiscal_year_end_market_equity,
)
from src.infra.models.method_spec import ResolvedMethodSpec
from src.infra.models.plugin import PluginRecord, ValidationReport

# Patterns that indicate potential future information leakage
FORBIDDEN_PATTERNS = [
    "shift(-",   # backward shift (future data)
    ".future",
    "lead(",
]

_FAITHFULNESS_PROMPT_PATH = (
    Path(__file__).resolve().parents[3] / "prompts" / "meta_coder" / "faithfulness_check.md"
)
_FAITHFULNESS_PROMPT_TEMPLATE = (
    _FAITHFULNESS_PROMPT_PATH.read_text(encoding="utf-8")
    if _FAITHFULNESS_PROMPT_PATH.exists()
    else ""
)


def _extract_json_object(text: str) -> str:
    """Pull the first top-level `{...}` object out of an LLM response,
    tolerating stray code fences/prose around it (mirrors the leniency
    `_strip_code_fences` gives codegen responses in step3_codegen)."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]

# Seconds a compute_signal execution smoke test may run before it's treated as
# a hang (a hang is a real defect, not an inconclusive result -- see
# _check_executes). Deliberately generous: the slice is small, but the plugin
# code is imported/compiled fresh in a subprocess.
_EXECUTE_TIMEOUT_SECONDS = 60


class AdversarialSandbox:
    """Validates generated signal plugins for correctness and safety.

    Layered, cheap -> expensive; every layer gates codegen -> run and (via
    Pipeline's bounded repair loop) feeds only technical/execution errors back
    to MetaCoder -- never any C&Z ground-truth comparison, which stays a
    post-hoc, never-fed-back evaluation (see docs/decision-log.md).

    Checks:
    - Syntax validity (the compute_signal plugin)
    - Forbidden pattern scan (future functions)
    - Schema/contract: compute_signal exists
    - Execution smoke test: the ONE complete standalone script Pipeline built
      (`_build_script`) is imported (not run as `__main__` -- its `main()` is
      guarded, so no full-data load is triggered by the import itself) in a
      subprocess, and its `compute_signal` is called on a small real-data
      slice (already table-joined the same way the generated script would --
      see `Pipeline._build_validation_slice`), confirming it doesn't raise
      (lenient -- an empty/degenerate result on a thin slice is inconclusive,
      not a failure; only a raised exception fails it). This validates the
      EXACT artifact Step5 will later execute -- no separate hand-rolled
      "exec the plugin code" runner. Deliberately stops at compute_signal --
      no full-engine (breakpoints/portfolio construction) attempt here, since
      that layer's failures aren't something `MetaCoder.repair_plugin` (which
      only rewrites `compute_signal`) could ever fix. A Step-5 run failure on
      full data is the guaranteed safety net for full-engine bugs.
    - Faithfulness check (opt-in, only when `llm_client` is supplied): an LLM
      re-reads `spec.paper.signal.formula` and `plugin.code` and reports
      whether the code correctly implements that SAME approved formula --
      never whether the formula itself is the right empirical choice (that
      stays Review Gate's job, see docs/decision-log.md). Skipped entirely
      (stays passing) when no `llm_client` was given, so every existing
      static/default validation path is unaffected.
    """

    def __init__(self, llm_client=None):
        self.llm_client = llm_client

    def validate(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        script_text: str | None = None,
        data=None,
    ) -> ValidationReport:
        """Run full validation suite on a plugin.

        Args:
            plugin:      the generated plugin (the compute_signal function).
            spec:        the resolved MethodSpec the plugin was generated from
                         (accepted for API/provenance parity with `MetaCoder.
                         generate_plugin`/`script_generator.
                         generate_backtest_script` -- every check below reads
                         only `plugin`/`script_text`/`data`, so `spec` itself
                         is never inspected here).
            script_text: the ONE complete standalone backtest script built from
                         this exact plugin (see `Pipeline._build_script`) --
                         the same text Step5 will execute. When None, the
                         execution check is skipped (executes_ok stays True) so
                         static-only callers (e.g. app.py's inline validate
                         button, which has no snapshot to build a script from)
                         still pass.
            data:        optional small real-data slice (a pandas DataFrame
                         keyed [permno, time_avail_m, ...]) for the
                         compute_signal execution smoke test. Required
                         alongside `script_text` for the execution check to run.
        """
        report = ValidationReport()

        report.syntax_ok = self._check_syntax(plugin, report)
        if report.syntax_ok:
            report.schema_ok = self._check_schema(plugin, report)
            report.no_future_leak = self._check_no_future_leak(plugin, report)
            report.no_future_leak = self._check_market_equity_policy(plugin, spec, report) and report.no_future_leak
            report.reproducible = self._check_reproducibility(plugin, report)
            report.executes_ok = self._check_executes(script_text, data, report)
            report.faithful_ok = self._check_faithfulness(plugin, spec, report)

        report.passed = all([
            report.syntax_ok,
            report.schema_ok,
            report.no_future_leak,
            report.reproducible,
            report.executes_ok,
            report.faithful_ok,
        ])
        return report

    def _check_syntax(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check that code parses without syntax errors."""
        try:
            ast.parse(plugin.code)
            return True
        except SyntaxError as e:
            report.errors.append(f"SyntaxError: {e}")
            return False

    def _check_schema(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check that plugin defines expected entry function with correct signature."""
        try:
            tree = ast.parse(plugin.code)
            func_names = [
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            if plugin.entry_function not in func_names:
                report.errors.append(
                    f"Entry function '{plugin.entry_function}' not found in code"
                )
                return False
            return True
        except Exception as e:
            report.errors.append(f"Schema check failed: {e}")
            return False

    def _check_no_future_leak(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Scan for patterns that might indicate future information usage."""
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in plugin.code:
                report.errors.append(f"Forbidden pattern detected: '{pattern}'")
                return False
        return True

    def _check_market_equity_policy(
        self, plugin: PluginRecord, spec: ResolvedMethodSpec, report: ValidationReport
    ) -> bool:
        """Hard validation of the approved Dichev Z-score implementation choice."""
        if not requires_crsp_fiscal_year_end_market_equity(spec):
            return True
        tree = ast.parse(plugin.code)
        references = {node.id.lower() for node in ast.walk(tree) if isinstance(node, ast.Name)}
        references |= {
            node.value.lower()
            for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }
        forbidden = sorted(references & FORBIDDEN_COMPUSTAT_MARKET_EQUITY_COLUMNS)
        missing = sorted({"prc", "shrout", "lt"} - references)
        constants = {node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, (int, float))}
        has_price_abs = any(
            isinstance(node, ast.Attribute)
            and node.attr == "abs"
            and any(
                isinstance(child, ast.Constant) and child.value == "prc"
                for child in ast.walk(node.value)
            )
            for node in ast.walk(tree)
        )
        has_price_share_product = any(
            isinstance(node, ast.BinOp)
            and isinstance(node.op, ast.Mult)
            and {"prc", "shrout"}.issubset({
                child.value.lower()
                for child in ast.walk(node)
                if isinstance(child, ast.Constant) and isinstance(child.value, str)
            })
            for node in ast.walk(tree)
        )
        if forbidden or missing or 1000 not in constants or not has_price_abs or not has_price_share_product:
            details = []
            if forbidden:
                details.append(f"forbidden Compustat proxy reference(s): {', '.join(forbidden)}")
            if missing:
                details.append(f"missing required raw column reference(s): {', '.join(missing)}")
            if 1000 not in constants:
                details.append("missing / 1000 unit conversion (CRSP shares are thousands; Compustat lt is millions)")
            if not has_price_abs:
                details.append("price is not explicitly absolute-valued")
            if not has_price_share_product:
                details.append("no explicit prc * shrout market-equity product")
            report.errors.append(
                "Dichev Z-score implementation policy violation: must compute market equity as "
                "abs(prc) * shrout / 1000 through CCM at fiscal year end, then divide by Compustat lt; "
                + "; ".join(details)
            )
            return False
        return True

    def _check_reproducibility(self, plugin: PluginRecord, report: ValidationReport) -> bool:
        """Check for non-deterministic operations."""
        # TODO: Run plugin twice with same input, check outputs match
        return True

    def _check_executes(
        self,
        script_text: str | None,
        data,
        report: ValidationReport,
    ) -> bool:
        """Execution smoke test: import the ALREADY-BUILT complete backtest
        script (see `Pipeline._build_script`) in an isolated subprocess (with a
        timeout) and call its `compute_signal` on a small real-data slice,
        confirming it doesn't raise.

        Importing the script (rather than running it) never triggers its
        `main()` -- the generated template guards that call with
        `if __name__ == "__main__":` -- so no full snapshot load or full
        BacktestExecutor run happens here; only the module-level
        `exec(compile(PLUGIN_CODE, ...))` line runs, which defines the
        formula-only `compute_signal` in the imported module's namespace. This
        reuses the single generated artifact directly
        instead of re-deriving a separate "how do I exec this plugin" runner.

        Lenient by design (see class docstring): only a raised exception or a
        hang (timeout) fails this check. A result that runs but is empty or
        degenerate is treated as INCONCLUSIVE -- recorded as a warning, not a
        failure -- because on a thin validation slice that usually reflects
        data coverage, not a code defect. The guaranteed net for anything this
        lenient check lets through is the real Step-5 run (which executes
        compute_signal AND every hook on full data and feeds failures back to
        repair).

        Deliberately does NOT also run the full backtest engine here (no
        breakpoints/portfolio construction) -- that layer's failures on a thin
        validation slice are not attributable to `compute_signal`, so they'd
        be noise the LLM repair loop can't act on anyway (`MetaCoder.
        repair_plugin` only rewrites `compute_signal`). Full-engine
        correctness is Step5's job, on full data.

        Skipped (returns True) when no `script_text` or no `data` slice is
        supplied.
        """
        if script_text is None or data is None:
            return True

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_pkl = tmp_path / "slice.pkl"
            target_py = tmp_path / "validation_target.py"
            driver_py = tmp_path / "driver.py"
            # Pickle (not parquet) so the subprocess needs no pyarrow/fastparquet.
            data.to_pickle(data_pkl)
            target_py.write_text(script_text)
            driver_py.write_text(_EXECUTE_DRIVER.format(
                target_py=repr(str(target_py)),
                data_pkl=repr(str(data_pkl)),
            ))

            repo_root = Path(__file__).resolve().parents[3]
            import os
            env = {**os.environ, "PYTHONPATH": f"{repo_root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}
            try:
                proc = subprocess.run(
                    [sys.executable, str(driver_py)],
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=_EXECUTE_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired:
                report.errors.append(
                    f"compute_signal execution timed out after {_EXECUTE_TIMEOUT_SECONDS}s (possible hang)"
                )
                return False

        result = None
        for line in reversed(proc.stdout.splitlines()):
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    result = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue

        if result is None:
            # Driver produced no parseable verdict -- treat as a real failure
            # (e.g. the script failed to import at module-load time).
            tail = (proc.stderr or proc.stdout or "").strip()[-500:]
            report.errors.append(f"compute_signal execution produced no result. stderr: {tail}")
            return False

        if result.get("error"):
            report.errors.append(f"compute_signal raised: {result['error']}")
            return False

        report.technical_metrics = result.get("technical_metrics") or {}

        if result.get("empty"):
            report.warnings.append(
                "compute_signal execution smoke test inconclusive: empty/degenerate "
                "output on the validation slice (likely data coverage, not a code "
                "defect) -- deferring to the full Step-5 run"
            )

        # Group-balance findings: thresholded on RATES across all sampled
        # months (never a single occurrence) since a thin validation slice
        # legitimately produces one empty/merged bin here and there just
        # from having few names that month -- that's sampling noise, not a
        # defect. `median_distinct_value_ratio` is the sample-size-INDEPENDENT
        # signal (see the sandbox script's own comment) and is checked first;
        # the rate-based checks below only escalate when they're frequent,
        # not merely present.
        #
        # The two clearest, most sample-size-robust findings (low distinct-
        # value ratio + the CONFIGURED long/short leg itself going empty)
        # are hard FAILURES (appended to report.errors, this method returns
        # False), not warnings -- unlike the "empty/degenerate" leniency
        # above, this is not attributable to thin data coverage (it's
        # sample-size independent by construction), so it belongs in the
        # SAME technical-repair loop a syntax/schema failure triggers
        # (RepairLoop feeds report.errors back to MetaCoder, which only
        # rewrites compute_signal -- never the approved empirical formula,
        # same posture as every other repairable finding here). The broader
        # corroborating signals (any-group-empty, duplicate breakpoints)
        # stay informational warnings, since they're less specific to which
        # leg the config actually uses.
        sampled = report.technical_metrics.get("leg_check_sampled_months") or 0
        failed = False
        median_ratio = report.technical_metrics.get("median_distinct_value_ratio")
        low_card_frac = report.technical_metrics.get("low_cardinality_month_frac")
        if sampled >= 3 and median_ratio is not None and low_card_frac is not None \
                and median_ratio < 0.3 and low_card_frac > 0.5:
            failed = True
            report.errors.append(
                f"compute_signal's signal has an unusually low distinct-value ratio "
                f"(median {median_ratio:.2f}) and <= breakpoint_quantiles+2 distinct values in "
                f"{low_card_frac:.0%} of {sampled} sampled months -- both sample-size-independent, "
                "so this isn't validation-slice noise. A genuinely continuous characteristic "
                "keeps near-unique values even with few names; this looks pre-bucketed instead "
                "(e.g. an off-by-one/truncation error collapsing a rank into a handful of "
                "discrete levels), which silently breaks the engine's own quantile-cut "
                "portfolio formation. Rewrite compute_signal to return the continuous "
                "characteristic (or its plain percentile rank) and let the engine's own "
                "breakpoint_quantiles cut form the groups -- do not pre-bucket in the plugin."
            )

        empty_leg_frac = report.technical_metrics.get("empty_leg_month_frac")
        if sampled >= 5 and empty_leg_frac is not None and empty_leg_frac > 0.3:
            failed = True
            report.errors.append(
                f"compute_signal's own signal distribution leaves the CONFIGURED long/short "
                f"leg empty in {empty_leg_frac:.0%} of {sampled} sampled months when "
                "value-quantile-cut into breakpoint_quantiles groups (mirrors BacktestExecutor."
                "assign_portfolios' own algorithm) -- this is exactly how a factor's return "
                "series silently loses whole calendar months without ever raising an error. "
                "Fix compute_signal so its signal supports forming breakpoint_quantiles clean "
                "groups (a continuous characteristic, not a pre-bucketed one)."
            )

        if failed:
            return False

        empty_any_frac = report.technical_metrics.get("empty_any_group_month_frac")
        if sampled >= 5 and empty_any_frac is not None and empty_any_frac > 0.3:
            report.warnings.append(
                f"compute_signal's signal leaves AT LEAST ONE of the breakpoint_quantiles "
                f"groups empty (not necessarily the configured long/short leg) in "
                f"{empty_any_frac:.0%} of {sampled} sampled months -- a broader corroborating "
                "sign the signal doesn't actually support forming that many clean quantile "
                "groups, even on months where the configured leg itself happens to survive."
            )

        degenerate_frac = report.technical_metrics.get("degenerate_breakpoint_month_frac")
        if sampled >= 5 and degenerate_frac is not None and degenerate_frac > 0.2:
            report.warnings.append(
                f"compute_signal's signal produces duplicate quantile breakpoints (too few "
                f"distinct values to cut into breakpoint_quantiles groups) in "
                f"{degenerate_frac:.0%} of {sampled} sampled months -- the real engine silently "
                "forms NO portfolios at all for a month like this (BacktestExecutor."
                "assign_portfolios' own duplicate-breakpoint skip), which is how large "
                "calendar gaps can vanish from the final return series without ever raising "
                "an error."
            )

        return True

    def _check_faithfulness(
        self,
        plugin: PluginRecord,
        spec: ResolvedMethodSpec,
        report: ValidationReport,
    ) -> bool:
        """Ask an LLM whether `plugin.code` correctly implements the SAME
        approved `spec.paper.signal.formula` -- never whether that formula is
        the right empirical choice (see class docstring). Skipped (returns
        True) when no `llm_client` was configured.

        Anti-hallucination guard (same discipline as Step 8's evidence-cited
        claims, see docs/tools-plus-llm-plan.md): the LLM must quote a
        verbatim substring of the code AND of the formula text back to us.
        Any unparsed response, or a quote that doesn't actually appear in the
        code/formula, is treated as inconclusive (a warning, not a failure)
        rather than blocking the plugin on an unverifiable claim.
        """
        if self.llm_client is None:
            return True

        formula = spec.paper.signal.formula
        step_lines = [
            f"  {i}. {s.description}" + (f" ({s.expression})" if s.expression else "")
            for i, s in enumerate(formula.steps, start=1)
        ]
        spec_text = "\n".join([
            f"Paper expression: {formula.paper_expression}",
            f"Output concept: {formula.output_concept}",
            f"Inputs: {', '.join(formula.inputs)}",
            "Calculation steps:" if step_lines else "Calculation steps: (none given)",
            *step_lines,
        ])

        prompt = _FAITHFULNESS_PROMPT_TEMPLATE.format(spec_text=spec_text, code=plugin.code)
        try:
            response = self.llm_client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
            )
            raw = response.choices[0].message.content or ""
            verdict = json.loads(_extract_json_object(raw))
        except Exception as e:
            report.warnings.append(f"Faithfulness check inconclusive (LLM/parse error: {e})")
            return True

        if verdict.get("faithful", True):
            return True

        reason = str(verdict.get("reason", ""))
        quoted_code = str(verdict.get("quoted_code", ""))
        quoted_spec = str(verdict.get("quoted_spec", ""))

        if quoted_code and quoted_code not in plugin.code:
            report.warnings.append(
                f"Faithfulness check flagged a mismatch but its quoted code snippet "
                f"wasn't found verbatim in the plugin -- treating as inconclusive: {reason}"
            )
            return True
        if quoted_spec and quoted_spec not in spec_text:
            report.warnings.append(
                f"Faithfulness check flagged a mismatch but its quoted formula snippet "
                f"wasn't found verbatim in the approved formula -- treating as inconclusive: {reason}"
            )
            return True

        report.errors.append(
            "Faithfulness check FAILED: compute_signal does not correctly implement "
            f"the approved formula. {reason} Approved formula/steps:\n{spec_text}\n"
            f"Offending code fragment: {quoted_code!r}"
        )
        return False


# Generic driver exec'd in a subprocess by _check_executes: imports whatever
# script it's pointed at (the exact artifact Step5 will run) and calls its
# `compute_signal`. Doesn't know anything about plugin internals -- it would
# work against any script with the same shape, so there's no separate
# "how do I run a plugin" logic duplicated here. Catches every error into a
# single JSON verdict line so the parent can distinguish a raised exception
# (real defect -> fail) from an empty result (inconclusive -> warn).
_EXECUTE_DRIVER = '''\
import importlib.util
import json
import sys
import traceback

import pandas as pd

TARGET_PY = {target_py}
DATA_PKL = {data_pkl}


def _main():
    spec = importlib.util.spec_from_file_location("validation_target", TARGET_PY)
    mod = importlib.util.module_from_spec(spec)
    try:
        # Runs the script's module-level code only -- NOT its `main()`, which
        # is guarded by `if __name__ == "__main__":` in the generated template.
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001
        return {{"error": "script import failed: " + repr(e), "trace": traceback.format_exc()}}

    fn = getattr(mod, "compute_signal", None)
    if not callable(fn):
        return {{"error": "compute_signal not defined in generated script"}}

    df = pd.read_pickle(DATA_PKL)
    try:
        out = fn(df)
    except Exception as e:  # noqa: BLE001
        return {{"error": repr(e), "trace": traceback.format_exc()}}

    if not isinstance(out, pd.DataFrame):
        return {{"error": "compute_signal returned " + type(out).__name__ + ", expected DataFrame"}}

    missing = [c for c in ("permno", "yyyymm", "signal") if c not in out.columns]
    if missing:
        return {{"error": "compute_signal output missing columns: " + repr(missing)}}

    signal_dtype = str(out["signal"].dtype)
    if len(out) and not pd.api.types.is_numeric_dtype(out["signal"]):
        return {{"error": "compute_signal output 'signal' column has non-numeric dtype: " + signal_dtype}}

    technical_metrics = {{
        "nan_ratio": float(out["signal"].isna().mean()) if len(out) else None,
        "n_permno": int(out["permno"].nunique()) if len(out) else 0,
        "n_months": int(out["yyyymm"].nunique()) if len(out) else 0,
        "missing_columns": missing,
        "dtype": signal_dtype,
    }}

    # Group-balance check: does this signal look like it can actually support
    # breakpoint_quantiles clean groups, in a way that's robust to a SMALL
    # validation slice (a thin sample legitimately produces an empty/merged
    # bin here and there just from having few names that month -- that's
    # sampling noise, not a defect, and must not be flagged as one).
    #
    # Primary signal: per-month DISTINCT-VALUE ratio (nunique / n_obs), which
    # is sample-size INDEPENDENT -- a genuinely continuous characteristic
    # (returns, ratios, ranks) produces near-nunique==n_obs even with a
    # handful of names, while a plugin that pre-buckets its own signal into
    # ~breakpoint_quantiles discrete levels (e.g. an off-by-one/truncation
    # error collapsing what should be continuous into ~11 integer levels)
    # shows a low ratio regardless of whether N is 50 or 6000 -- this is
    # what actually caught the incident this check exists for.
    # Secondary signal: mirrors BacktestExecutor.compute_breakpoints/
    # assign_portfolios (signal.quantile(linspace(0,1,n+1)) value
    # breakpoints, pd.cut into n groups, skip the whole cross-section on any
    # duplicate breakpoint value) to see how often the configured long/short
    # leg -- or ANY group -- comes back empty. Reported as a RATE across all
    # sampled months, not flagged on any single occurrence, since one thin
    # month having an empty/merged bin is expected noise, not a defect.
    # Still compute_signal-output-only (no cohort/holding-period/exchcd-
    # breakpoint machinery here) -- consistent with this sandbox never
    # invoking the full engine.
    config = getattr(mod, "CONFIG", {{}}) or {{}}
    n_groups = int(config.get("breakpoint_quantiles", 10) or 10)
    long_leg = config.get("long_leg", "high")
    default_long_port = 1 if long_leg == "low" else n_groups
    default_short_port = n_groups if long_leg == "low" else 1
    long_ports = set(config.get("long_portfolios") or [default_long_port])
    short_ports = set(config.get("short_portfolios") or [default_short_port])

    distinct_ratios = []
    low_cardinality_months = 0
    empty_leg_months = 0
    empty_any_group_months = 0
    degenerate_months = 0
    sampled_months = 0
    if len(out) and n_groups > 1:
        quantile_vals = [i / n_groups for i in range(n_groups + 1)]
        for ym, g in out.groupby("yyyymm"):
            vals = g["signal"].dropna()
            if len(vals) < n_groups:
                continue  # too few names that month to form n_groups at all
            sampled_months += 1

            ratio = vals.nunique() / len(vals)
            distinct_ratios.append(ratio)
            # A real continuous characteristic collapsing to roughly one
            # distinct value per breakpoint_quantiles group (or fewer) is
            # the structural signature this check targets -- independent of
            # how many names happen to be in this month's sample.
            if vals.nunique() <= n_groups + 2:
                low_cardinality_months += 1

            bins = vals.quantile(quantile_vals).tolist()
            bins[0] = float("-inf")
            bins[-1] = float("inf")
            if len(set(bins)) != len(bins):
                # Same skip condition as the real engine's assign_portfolios:
                # duplicate breakpoints -> no portfolios formed AT ALL this
                # month, for either leg.
                degenerate_months += 1
                continue
            portfolio = pd.cut(vals, bins=bins, labels=range(1, n_groups + 1), include_lowest=True)
            present = set(int(p) for p in portfolio.dropna().unique().tolist())
            if len(present) < n_groups:
                empty_any_group_months += 1
            if not (long_ports & present) or not (short_ports & present):
                empty_leg_months += 1

    technical_metrics["median_distinct_value_ratio"] = (
        float(pd.Series(distinct_ratios).median()) if distinct_ratios else None
    )
    technical_metrics["low_cardinality_month_frac"] = (
        low_cardinality_months / sampled_months if sampled_months else None
    )
    technical_metrics["empty_leg_month_frac"] = empty_leg_months / sampled_months if sampled_months else None
    technical_metrics["empty_any_group_month_frac"] = (
        empty_any_group_months / sampled_months if sampled_months else None
    )
    technical_metrics["degenerate_breakpoint_month_frac"] = (
        degenerate_months / sampled_months if sampled_months else None
    )
    technical_metrics["leg_check_sampled_months"] = sampled_months

    empty = len(out) == 0 or out["signal"].notna().sum() == 0

    return {{"error": None, "empty": bool(empty), "n_rows": int(len(out)), "technical_metrics": technical_metrics}}


print(json.dumps(_main()))
'''
