"""Factor Replication Agent — Streamlit Dashboard.

Run: streamlit run app.py

Seven-page dashboard aligned with architecture.md pipeline:
  1. Pipeline — End to End
  2. Extractor
  3. Review & Resolve
  4. MetaCoder
  5. Backtest & Experiments
    6. Replication Diagnosis
  7. Trace & Logs
"""

import json
import os
import traceback
from pathlib import Path

import pandas as pd
import streamlit as st

try:
    import pymupdf
    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

st.set_page_config(page_title="Factor Replication Agent", layout="wide")

# ============================================================
# Paths
# ============================================================
PROJECT_ROOT = Path(__file__).parent
SIGNALDOC_PATH = PROJECT_ROOT / "data" / "osap" / "SignalDoc.csv"
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"
PAPER_TEXT_CACHE_DIR = PROJECT_ROOT / "data" / "paper_text_cache"
PAPER_TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# All pipeline-run-generated artifacts (MethodSpecs, plugins, backtest scripts,
# evidence) live under runs/ — a single gitignored directory — rather than
# scattered across data/ and a top-level evidence/. See CHANGELOG.md.
# Overridable (FACTOR_AGENT_RUNS_DIR) for ad-hoc test runs -- see backend/state.py.
_runs_dir_override = os.environ.get("FACTOR_AGENT_RUNS_DIR")
RUNS_DIR = (PROJECT_ROOT / _runs_dir_override) if _runs_dir_override else PROJECT_ROOT / "runs"

# Paper-first (MethodSpec/MethodReview/ImplementationResolution/
# ResolvedMethodSpec) artifact dirs (see backend/state.py for the matching
# backend-side dirs).
UNREVIEWED_DIR = RUNS_DIR / "method_specs" / "unreviewed"
UNREVIEWED_DIR.mkdir(parents=True, exist_ok=True)
REVIEWED_DIR = RUNS_DIR / "method_specs" / "reviewed"
REVIEWED_DIR.mkdir(parents=True, exist_ok=True)
RESOLUTIONS_DIR = RUNS_DIR / "method_specs" / "resolutions"
RESOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)
RESOLVED_DIR = RUNS_DIR / "method_specs" / "resolved"
RESOLVED_DIR.mkdir(parents=True, exist_ok=True)

PLUGINS_DIR = RUNS_DIR / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
BACKTEST_SCRIPTS_DIR = RUNS_DIR / "backtest_scripts"
EVIDENCE_DIR = RUNS_DIR / "evidence"

# Committed reference/test fixtures (plugins that golden-number tests and
# manual dashboard testing depend on) — tracked in git, unlike runs/ above.
# See tests/test_*_e2e.py.
FIXTURES_DIR = PROJECT_ROOT / "tests" / "fixtures"
FIXTURE_PLUGINS_DIR = FIXTURES_DIR / "plugins"

MSF_PATH = PROJECT_ROOT / "data" / "local" / "msf.parquet"
SYNTHETIC_MSF_PATH = PROJECT_ROOT / "data" / "synthetic_data" / "local" / "msf.parquet"
SYNTHETIC_SNAPSHOT_DIR = PROJECT_ROOT / "data" / "synthetic_data" / "mvp_v1"


def _load_any_spec(text: str):
    """Parse a ResolvedMethodSpec JSON string."""
    from src.infra.models.method_spec import ResolvedMethodSpec

    return ResolvedMethodSpec.model_validate(json.loads(text))


def _spec_factor_id(spec) -> str:
    return spec.paper.factor_id


def _spec_codegen_ready(spec) -> bool:
    """Whether MetaCoder should be allowed to run for this spec --
    `ResolvedMethodSpec.is_ready` computes readiness from hash-freshness +
    finding + capability checks."""
    return spec.is_ready


def _spec_stable_hash(spec) -> str:
    return spec.paper.content_hash()


def _default_signal_mode(spec) -> str:
    """UI-only: preselect the "Signal Input" radio from the spec's resolved
    sources, via the shared catalog-driven `pick_signal_input_mode`.

    Non-raising (unlike `pick_signal_input_mode`, which fails loud on an
    unknown/empty source): the dashboard human explicitly confirms the mode
    before running, and the pipeline itself still fails loud on an unregistered
    source at codegen time. Falls back to "compustat" as a mere UI preselection
    when the source can't be determined — NOT a silent pipeline default.
    """
    from src.steps.step3_codegen.script_generator import pick_signal_input_mode
    try:
        return pick_signal_input_mode(spec)
    except ValueError:
        return "compustat"


def _ensure_synthetic_data() -> bool:
    """Generate the bundled synthetic demo data on the fly if it isn't already on disk.

    Uses the same deterministic builder as scripts/build_synthetic_data.py
    (tests/synthetic_data/asset_growth_synthetic_data.py). Returns True if the
    synthetic data is available (already present or just generated).
    """
    if SYNTHETIC_MSF_PATH.exists() and (SYNTHETIC_SNAPSHOT_DIR / "comp_funda.parquet").exists():
        return True
    try:
        from tests.synthetic_data.asset_growth_synthetic_data import (
            build_ccm_link,
            build_compustat_funda,
            build_crsp_msf,
        )
        SYNTHETIC_SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        SYNTHETIC_MSF_PATH.parent.mkdir(parents=True, exist_ok=True)
        crsp = build_crsp_msf()
        crsp.to_parquet(SYNTHETIC_SNAPSHOT_DIR / "crsp_msf.parquet", index=False)
        crsp.to_parquet(SYNTHETIC_MSF_PATH, index=False)
        # The declarative signal-master loader reads `comp_funda.parquet` +
        # `ccm_lnkhist.parquet` (CCM keyed on `lpermno`).
        build_compustat_funda().to_parquet(SYNTHETIC_SNAPSHOT_DIR / "comp_funda.parquet", index=False)
        build_ccm_link().rename(columns={"permno": "lpermno"}).to_parquet(
            SYNTHETIC_SNAPSHOT_DIR / "ccm_lnkhist.parquet", index=False
        )
        return True
    except Exception as e:
        st.error(f"Failed to auto-generate synthetic data: {e}")
        return False


def _run_backtest_via_script(
    spec,
    plugin_code: str,
    *,
    crsp_data_path,
    signal_input_mode: str,
    signal_data_dir=None,
    config_overrides: dict | None = None,
) -> dict:
    """Generate a standalone backtest script and execute it via subprocess.

    The script is written to ``runs/backtest_scripts/{factor_id}_backtest.py`` (a
    durable, independently re-runnable audit artifact — see
    src/steps/step3_codegen/script_generator.py) and run with the current Python
    interpreter. Results are read back from the CSV/metrics.json the script
    itself writes, so the persisted script — not this dashboard process — is
    the actual source of the reported numbers. No data is auto-generated
    here; the given paths must already exist on disk.
    """
    import os
    import subprocess
    import sys
    from src.steps.step3_codegen.script_generator import generate_backtest_script
    from src.steps.step3_codegen.registry import build_config

    scripts_dir = BACKTEST_SCRIPTS_DIR
    scripts_dir.mkdir(parents=True, exist_ok=True)
    results_dir = scripts_dir / "results"
    output_csv = results_dir / f"{_spec_factor_id(spec)}.csv"

    script = generate_backtest_script(
        spec,
        plugin_code,
        data_path=str(crsp_data_path),
        signal_input_mode=signal_input_mode,
        signal_data_dir=str(signal_data_dir or ""),
        output_path=str(output_csv),
        config_overrides=config_overrides,
    )
    script_path = scripts_dir / f"{_spec_factor_id(spec)}_backtest.py"
    script_path.write_text(script)

    # The generated script does `from src...` imports, but this repo's
    # editable install only puts `src/` itself on sys.path, and Python puts
    # the *script's own directory* (not the repo root) on sys.path[0] — so
    # PYTHONPATH must be set explicitly for the subprocess to find `src`.
    repo_root = Path(__file__).resolve().parent
    env = {**os.environ, "PYTHONPATH": f"{repo_root}{os.pathsep}{os.environ.get('PYTHONPATH', '')}"}

    proc = subprocess.run(
        [sys.executable, str(script_path)], capture_output=True, text=True, env=env
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"Backtest script {script_path} failed (exit {proc.returncode}):\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )

    metrics_path = output_csv.with_suffix(".metrics.json")
    metrics = json.loads(metrics_path.read_text())
    return_series = pd.read_csv(output_csv)
    config = build_config(spec, config_overrides)

    return {
        "metrics": metrics,
        "return_series": return_series,
        "config": config,
        "script_path": str(script_path),
        "stdout": proc.stdout,
    }


# ============================================================
# Sidebar
# ============================================================
st.sidebar.title("Pipeline Steps")
page = st.sidebar.radio(
    "Navigate",
    [
        "MetaCoder",
        "Backtest & Experiments",
        "Replication Diagnosis",
        "Trace & Logs",
        "Paper-First Workflow",
    ],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Module Status**")
st.sidebar.markdown("- Extractor ✅")
st.sidebar.markdown("- Review Gate ✅")
_plugin_count = len(list(PLUGINS_DIR.glob("*.py"))) + len(list(FIXTURE_PLUGINS_DIR.glob("*.py"))) if (PLUGINS_DIR.exists() or FIXTURE_PLUGINS_DIR.exists()) else 0
st.sidebar.markdown(f"- MetaCoder {'✅' if _plugin_count else '🚧'} ({_plugin_count} plugins)")
st.sidebar.markdown("- Sandbox ✅")
st.sidebar.markdown("- Backtest ✅")
st.sidebar.markdown("- Replication Diagnosis 🚧")
st.sidebar.markdown("- Trace ✅")

st.sidebar.markdown("---")
llm_provider = st.sidebar.selectbox(
    "LLM Provider",
    ["codex", "claude", "copilot", "openrouter"],
    index=0,
)
_PROVIDER_MODELS = {
    "codex": ["gpt-5.6-terra", "gpt-5.6-sol", "gpt-5.5"],
    "copilot": ["claude-opus-5", "claude-sonnet-5", "gpt-5.6-terra", "gpt-5.6-sol"],
    "claude": ["claude-sonnet-5", "claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
    "openrouter": ["openai/gpt-4o", "anthropic/claude-sonnet-4", "openai/gpt-5.4"],
}
llm_model = st.sidebar.selectbox(
    "Model",
    _PROVIDER_MODELS.get(llm_provider, []),
    index=0,
)

st.title("Factor Replication Agent")

# ============================================================
# Shared helpers
# ============================================================


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _show_token_usage(usage: dict | None, label: str = "Token Usage") -> None:
    if not usage:
        return
    estimated = usage.get("estimated", False)
    suffix = " (est.)" if estimated else ""
    with st.container():
        tc1, tc2, tc3 = st.columns(3)
        tc1.metric(f"Input tokens{suffix}", f"{usage.get('prompt_tokens', 0):,}")
        tc2.metric(f"Output tokens{suffix}", f"{usage.get('completion_tokens', 0):,}")
        tc3.metric(f"Total{suffix}", f"{usage.get('total_tokens', 0):,}")




# ############################################################
# PAGE 4: MetaCoder
# ############################################################
if page == "MetaCoder":
    st.header("MetaCoder — Generate Signal Plugin")
    st.markdown("Load an approved MethodSpec and generate a Python signal plugin.")

    st.subheader("1. Load Resolved MethodSpec")
    _spec_files_mc: list[tuple[str, Path]] = []
    for _p in sorted(RESOLVED_DIR.glob("*.resolved.json")):
        _spec_files_mc.append((f"[paper-first] {_p.name}", _p))
    mc_options = [""] + [l for l, _ in _spec_files_mc]
    mc_map = {l: p for l, p in _spec_files_mc}

    col_sel, col_up = st.columns([2, 1])
    with col_sel:
        mc_selected = st.selectbox("Resolved MethodSpec", mc_options, key="mc_sel")
    with col_up:
        mc_uploaded = st.file_uploader("Or upload JSON", type=["json"], key="mc_upload")

    if st.button("Load MethodSpec", key="mc_load"):
        try:
            if mc_uploaded:
                mc_spec = _load_any_spec(mc_uploaded.getvalue().decode())
            elif mc_selected:
                mc_spec = _load_any_spec(mc_map[mc_selected].read_text())
            else:
                st.warning("Select a spec.")
                mc_spec = None
            if mc_spec:
                st.session_state["mc_spec"] = mc_spec
                st.session_state.pop("mc_plugin", None)
                st.session_state.pop("mc_sandbox_report", None)
                st.success(f"Loaded: **{_spec_factor_id(mc_spec)}**")
        except Exception as e:
            st.error(str(e))

    mc_spec = st.session_state.get("mc_spec")
    if mc_spec:
        st.markdown("---")
        st.subheader("2. Spec Summary")
        sc1, sc2, sc3 = st.columns(3)
        sc1.metric("Schema", "paper-first")
        sc2.metric("Ready (is_ready)", "Yes" if mc_spec.is_ready else "No")

        # Generate
        st.markdown("---")
        st.subheader("3. Generate Plugin")
        approved = _spec_codegen_ready(mc_spec)
        if not approved:
            st.error("MethodSpec not codegen-ready. Go to Review & Resolve first.")

        if st.button("Generate Signal Plugin", type="primary", disabled=not approved, key="mc_gen"):
            from src.infra.llm import create_llm_client
            from src.steps.step3_codegen import MetaCoder
            with st.spinner("Generating..."):
                try:
                    llm = create_llm_client(provider=llm_provider, model=llm_model)
                    coder = MetaCoder(llm_client=llm)
                    plugin = coder.generate_plugin(mc_spec)
                    st.session_state["mc_plugin"] = plugin
                    st.session_state.pop("mc_sandbox_report", None)
                    st.success("Plugin generated!")
                except Exception as e:
                    st.error(str(e))

        mc_plugin = st.session_state.get("mc_plugin")
        if mc_plugin:
            st.subheader("4. Generated Code")
            st.code(mc_plugin.code, language="python")

            dl_col, save_col, _ = st.columns([1, 1, 2])
            with dl_col:
                st.download_button("Download", mc_plugin.code, f"{mc_plugin.factor_id}.py", key="mc_dl")
            with save_col:
                if st.button("Save to plugins/", key="mc_save"):
                    (PLUGINS_DIR / f"{mc_plugin.factor_id}.py").write_text(mc_plugin.code)
                    st.success("Saved!")

            # Sandbox
            st.subheader("5. Sandbox Validation")
            if st.button("Run Sandbox", key="mc_sandbox"):
                from src.steps.step4_validator import AdversarialSandbox
                report = AdversarialSandbox().validate(mc_plugin, mc_spec)
                st.session_state["mc_sandbox_report"] = report

            sb = st.session_state.get("mc_sandbox_report")
            if sb:
                if sb.passed:
                    st.success("Sandbox **passed**.")
                else:
                    st.error("Sandbox **failed**.")
                vc1, vc2, vc3, vc4 = st.columns(4)
                vc1.metric("Syntax", "✅" if sb.syntax_ok else "❌")
                vc2.metric("Schema", "✅" if sb.schema_ok else "❌")
                vc3.metric("No Leak", "✅" if sb.no_future_leak else "❌")
                vc4.metric("Reproducible", "✅" if sb.reproducible else "❌")
                if sb.errors:
                    for err in sb.errors:
                        st.error(err)

            # Backtest script generator
            if mc_plugin:
                st.subheader("7. Generate Backtest Script")
                bt_path = st.text_input("CRSP data path", value="data/local/msf.parquet", key="mc_bt_path")
                if st.button("Generate Script", key="mc_gen_bt"):
                    try:
                        from src.steps.step3_codegen.script_generator import generate_backtest_script
                        script = generate_backtest_script(mc_spec, mc_plugin.code, data_path=bt_path)
                        st.session_state["mc_bt_script"] = script
                        # Save to runs/backtest_scripts/
                        bt_scripts_dir = BACKTEST_SCRIPTS_DIR
                        bt_scripts_dir.mkdir(parents=True, exist_ok=True)
                        bt_file = bt_scripts_dir / f"{mc_plugin.factor_id}_backtest.py"
                        bt_file.write_text(script)
                        st.success(f"Generated and saved to `{bt_file}`!")
                    except Exception as e:
                        st.error(str(e))
                bt_script = st.session_state.get("mc_bt_script")
                if bt_script:
                    st.code(bt_script, language="python")
                    st.download_button("Download Script", bt_script, f"{mc_plugin.factor_id}_backtest.py", key="mc_dl_bt")

    # Existing plugins
    existing = sorted(PLUGINS_DIR.glob("*.py")) + sorted(FIXTURE_PLUGINS_DIR.glob("*.py"))
    if existing:
        st.markdown("---")
        st.subheader("Existing Plugins")
        for pp in existing:
            with st.expander(pp.name):
                st.code(pp.read_text(), language="python")


# ############################################################
# PAGE 5: Backtest & Experiments
# ############################################################
elif page == "Backtest & Experiments":
    st.header("Backtest & Experiments")

    tab_single, tab_tracks, tab_ablation = st.tabs(["Single Run", "Track Status", "Ablation Status"])

    with tab_single:
        st.subheader("Single Backtest Run")

        plugin_map = {p.name: p for p in sorted(PLUGINS_DIR.glob("*.py"))}
        plugin_map.update({f"[fixture] {p.name}": p for p in sorted(FIXTURE_PLUGINS_DIR.glob("*.py"))})
        spec_map = {f"[paper-first] {p.name}": p for p in sorted(RESOLVED_DIR.glob("*.resolved.json"))}

        col_p, col_s = st.columns(2)
        with col_p:
            bt_plugin = st.selectbox("Plugin", [""] + list(plugin_map), key="bt_plugin")
        with col_s:
            bt_spec = st.selectbox("MethodSpec", [""] + list(spec_map), key="bt_spec")

        bt_spec_obj = None
        if bt_spec:
            try:
                bt_spec_obj = _load_any_spec(spec_map[bt_spec].read_text())
            except Exception as e:
                st.error(f"Failed to load spec: {e}")

        data_options = ["Bundled synthetic demo data", "Local (data/local/msf.parquet)", "Upload"]
        data_src = st.radio("CRSP Data", data_options, horizontal=True, key="bt_data_src")
        if data_src == "Bundled synthetic demo data":
            if SYNTHETIC_MSF_PATH.exists():
                st.caption(
                    "10 synthetic permnos, deterministic returns — for pipeline smoke-testing only, "
                    "not real backtest results. See docs/roadmap.md Phase 1."
                )
            else:
                st.caption(
                    "Not generated yet — will be built automatically (via "
                    "scripts/build_synthetic_data.py's generator) when you click Run."
                )
        bt_uploaded_msf = None
        if data_src == "Upload":
            bt_uploaded_msf = st.file_uploader("Upload msf.parquet", type=["parquet"], key="bt_msf_upload")

        signal_mode_default = 0
        if bt_spec_obj is not None and _default_signal_mode(bt_spec_obj) == "crsp_only":
            signal_mode_default = 1
        signal_mode = st.radio(
            "Signal Input",
            ["Compustat + CRSP (via generated script)", "CRSP monthly only (price-based signals)"],
            index=signal_mode_default,
            horizontal=True,
            key="bt_signal_mode",
            help="Compustat mode builds the SignalMasterTable inline inside the generated backtest "
            "script (CCM link + accounting lag) for accounting-based signals (e.g. asset growth, "
            "book-to-market). CRSP-only mode is for signals computed directly from monthly returns "
            "(e.g. momentum) and only works with the bundled/local CRSP monthly file.",
        )
        needs_compustat = signal_mode.startswith("Compustat")
        if needs_compustat and data_src != "Bundled synthetic demo data" and not SYNTHETIC_SNAPSHOT_DIR.exists():
            st.warning(
                "Compustat mode currently only has a data source for the bundled synthetic "
                "snapshot (`data/synthetic_data/mvp_v1/`). Real WRDS snapshots aren't wired into "
                "this page yet — see docs/roadmap.md Phase 4."
            )

        with st.expander("Config Overrides"):
            ov1, ov2, ov3 = st.columns(3)
            with ov1:
                ov_nq = st.number_input("N quantiles", 2, 100, 10, key="bt_nq")
                ov_bp = st.selectbox("Breakpoint", ["(spec)", "nyse", "full_sample"], key="bt_bp")
            with ov2:
                ov_wt = st.selectbox("Weighting", ["(spec)", "vw", "ew"], key="bt_wt")
                ov_hp = st.number_input("Holding (months)", 1, 60, 12, key="bt_hp")
            with ov3:
                ov_ll = st.selectbox("Long leg", ["(spec)", "low", "high"], key="bt_ll")

        can_run = bool(bt_plugin and bt_spec)
        has_data = (
            data_src == "Bundled synthetic demo data"
            or (data_src == "Local (data/local/msf.parquet)" and MSF_PATH.exists())
            or bt_uploaded_msf is not None
        )
        has_compustat_data = (data_src == "Bundled synthetic demo data") or SYNTHETIC_SNAPSHOT_DIR.exists() if needs_compustat else True

        if st.button("Run Backtest", type="primary", disabled=not (can_run and has_data and has_compustat_data), key="bt_run"):
            with st.spinner("Generating backtest script and running via subprocess..."):
                try:
                    from src.infra.models.plugin import PluginRecord
                    from src.infra.models.run_record import RunRecord, RunMetrics
                    from src.infra.evidence import EvidenceStore
                    import hashlib

                    if data_src == "Bundled synthetic demo data":
                        _ensure_synthetic_data()

                    spec = bt_spec_obj
                    plugin_code = plugin_map[bt_plugin].read_text()

                    if data_src == "Bundled synthetic demo data":
                        crsp_data_path = SYNTHETIC_SNAPSHOT_DIR / "crsp_msf.parquet"
                    elif data_src == "Local (data/local/msf.parquet)":
                        crsp_data_path = MSF_PATH
                    else:
                        # Uploaded file: the generated script reads from a real path on
                        # disk, so materialize the upload there first.
                        uploads_dir = BACKTEST_SCRIPTS_DIR / "_uploads"
                        uploads_dir.mkdir(parents=True, exist_ok=True)
                        crsp_data_path = uploads_dir / f"{_spec_factor_id(spec)}_uploaded_msf.parquet"
                        crsp_data_path.write_bytes(bt_uploaded_msf.getvalue())

                    signal_data_dir = None
                    if needs_compustat:
                        if not SYNTHETIC_SNAPSHOT_DIR.exists():
                            raise RuntimeError(
                                "No Compustat snapshot available. Run scripts/build_synthetic_data.py "
                                "or select 'CRSP monthly only' signal input."
                            )
                        signal_data_dir = SYNTHETIC_SNAPSHOT_DIR

                    overrides = {}
                    if ov_nq != 10: overrides["breakpoint_quantiles"] = ov_nq
                    if ov_bp != "(spec)": overrides["breakpoint_source"] = ov_bp
                    if ov_wt != "(spec)": overrides["weighting_rule"] = ov_wt
                    if ov_hp != 12: overrides["holding_period_months"] = ov_hp
                    if ov_ll != "(spec)": overrides["long_leg"] = ov_ll

                    code_hash = hashlib.sha256(plugin_code.encode()).hexdigest()[:16]
                    plugin_record = PluginRecord(
                        plugin_id=_spec_factor_id(spec),
                        factor_id=_spec_factor_id(spec),
                        code=plugin_code,
                        code_hash=code_hash,
                    )

                    result = _run_backtest_via_script(
                        spec, plugin_code,
                        crsp_data_path=crsp_data_path,
                        signal_input_mode="compustat" if needs_compustat else "crsp_only",
                        signal_data_dir=signal_data_dir,
                        config_overrides=overrides or None,
                    )
                    st.session_state["bt_result"] = result

                    # Persist as an auditable RunRecord (same shape as Pipeline.run_from_method_spec()).
                    metrics = result["metrics"]
                    run = RunRecord(
                        run_id=f"{_spec_factor_id(spec)}_dashboard_{code_hash[:8]}",
                        factor_id=_spec_factor_id(spec),
                        plugin_id=plugin_record.plugin_id,
                        track="dashboard_single_run",
                        method_spec_hash=_spec_stable_hash(spec),
                        code_hash=code_hash,
                        config_hash=hashlib.sha256(
                            json.dumps(result["config"], sort_keys=True, default=str).encode()
                        ).hexdigest()[:16],
                        metrics=RunMetrics(
                            mean_return=metrics.get("mean_monthly_return"),
                            t_stat=metrics.get("t_stat"),
                            n_months=metrics.get("n_months"),
                        ),
                        status="success",
                    )
                    EvidenceStore(base_path=str(EVIDENCE_DIR)).save_run(run)
                    st.session_state["bt_run_record"] = run
                    st.success(f"Done! Saved as run `{run.run_id}` in evidence/.")
                except Exception as e:
                    st.error(str(e))
                    st.code(traceback.format_exc())

        bt_result = st.session_state.get("bt_result")
        if bt_result:
            m = bt_result["metrics"]
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Mean Monthly", f"{m.get('mean_monthly_return', 0)*100:.3f}%")
            mc2.metric("t-stat (NW)", f"{m.get('t_stat', 0):.2f}")
            mc3.metric("Annualized", f"{m.get('annualized_return', 0)*100:.1f}%")
            mc4.metric("N Months", m.get("n_months", 0))

            script_path = bt_result.get("script_path")
            if script_path:
                st.caption(f"Full backtest script saved to `{script_path}`")
                with st.expander("View generated backtest script"):
                    script_code = Path(script_path).read_text()
                    st.code(script_code, language="python")
                    st.download_button(
                        "Download Script", script_code, Path(script_path).name, key="bt_dl_script"
                    )

            ls = bt_result.get("return_series", pd.DataFrame())
            if not ls.empty and "ls_return" in ls.columns:
                chart = ls.copy()
                if "yyyymm" in chart.columns:
                    chart["date"] = pd.to_datetime(chart["yyyymm"].astype(str), format="%Y%m")
                    chart = chart.sort_values("date")
                    chart["cum_return"] = (1 + chart["ls_return"]).cumprod() - 1
                    tab_c, tab_m = st.tabs(["Cumulative", "Monthly"])
                    with tab_c:
                        st.line_chart(chart.set_index("date")["cum_return"])
                    with tab_m:
                        st.bar_chart(chart.set_index("date")["ls_return"])

            with st.expander("Config"):
                st.json(bt_result.get("config", {}))
            dl1, dl2 = st.columns(2)
            with dl1:
                st.download_button("Download Returns CSV", ls.to_csv(index=False), "ls_returns.csv", key="bt_dl_csv")
            with dl2:
                st.download_button("Download Metrics JSON", json.dumps(m, indent=2), "metrics.json", key="bt_dl_json")

    with tab_tracks:
        st.subheader("Basic Multi-Track Status")
        st.info(
            "`MultiTrackController` can orchestrate original/standardized/OAT runs through "
            "the pipeline, but this dashboard does not yet expose the controller or persist "
            "a collision-safe multi-config evidence matrix."
        )
        st.markdown(
            "The planned interface will load a versioned `experiments/<factor_id>.experiments.yaml`, "
            "freeze one plugin for the batch, and show deterministic pairwise comparisons. "
            "See `docs/multi-config-evidence-plan.md`."
        )

    with tab_ablation:
        st.subheader("Ablation Status")
        st.info(
            "The basic controller supports named one-at-a-time switches, but strict key "
            "validation, effective-diff checks, unique artifact paths, and factorial sweep "
            "expansion are not implemented."
        )
        st.caption("Use Single Run only for local inspection; do not treat manual overrides as a persisted experiment matrix.")


# ############################################################
# PAGE 6: Replication Diagnosis
# ############################################################
elif page == "Replication Diagnosis":
    st.header("Replication Diagnosis")
    st.info(
        "The deterministic diagnosis report is not wired into the dashboard yet. "
        "Current Step 7 computes only a basic structural gap and the pipeline does not "
        "persist or return it."
    )
    st.markdown(
        "The target design requires collision-safe multi-config evidence, pairwise "
        "identification levels, a C&Z-signal bridge, and a persisted "
        "`ReplicationDiagnosisReport`. No automatic threshold here changes a MethodSpec "
        "or config. See `docs/multi-config-evidence-plan.md`."
    )


# ############################################################
# PAGE 7: Trace & Logs
# ############################################################
elif page == "Trace & Logs":
    st.header("Trace & Logs")

    tab_registry, tab_evidence, tab_trace = st.tabs(["Run Registry", "Evidence Browser", "Pipeline Trace"])

    with tab_registry:
        st.subheader("Run Registry")
        try:
            from src.infra.evidence import RunRegistry
            registry = RunRegistry()
            # Try to load from evidence store
            if EVIDENCE_DIR.exists():
                for factor_dir in sorted(EVIDENCE_DIR.iterdir()):
                    if not factor_dir.is_dir():
                        continue
                    for run_dir in sorted(factor_dir.iterdir()):
                        meta = run_dir / "metadata.json"
                        if meta.exists():
                            try:
                                data = json.loads(meta.read_text())
                                from src.infra.models.run_record import RunRecord
                                run = RunRecord(**data)
                                registry.register(run)
                            except Exception:
                                pass

            summary = registry.get_summary()
            if summary:
                st.json(summary)
                all_runs = []
                for fid in set(r.factor_id for r in registry._runs.values()):
                    for r in registry.get_by_factor(fid):
                        all_runs.append({
                            "run_id": r.run_id,
                            "factor_id": r.factor_id,
                            "status": r.status,
                        })
                if all_runs:
                    st.dataframe(pd.DataFrame(all_runs), use_container_width=True)
            else:
                st.info("No runs recorded yet.")
        except Exception as e:
            st.info(f"Run registry empty or not initialized: {e}")

    with tab_evidence:
        st.subheader("Evidence Browser")
        if EVIDENCE_DIR.exists():
            for factor_dir in sorted(EVIDENCE_DIR.iterdir()):
                if not factor_dir.is_dir():
                    continue
                with st.expander(f"📁 {factor_dir.name}"):
                    for run_dir in sorted(factor_dir.iterdir()):
                        if not run_dir.is_dir():
                            continue
                        st.markdown(f"**{run_dir.name}**")
                        for artifact in sorted(run_dir.iterdir()):
                            if artifact.is_file():
                                col_name, col_dl = st.columns([3, 1])
                                col_name.text(artifact.name)
                                with col_dl:
                                    st.download_button(
                                        "⬇", artifact.read_bytes(), artifact.name,
                                        key=f"ev_dl_{factor_dir.name}_{run_dir.name}_{artifact.name}",
                                    )
        else:
            st.info("No evidence directory found. Run backtests to generate evidence.")

    with tab_trace:
        st.subheader("Pipeline Trace")
        tracer = st.session_state.get("e2e_tracer")
        if tracer:
            timeline = tracer.get_timeline()
            if timeline:
                for ev in timeline:
                    icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(ev["level"], "")
                    st.text(f"{ev['timestamp'][-8:]} {icon} [{ev['stage']}] {ev['event']} {ev['detail']}")

                st.download_button(
                    "Download Trace JSON",
                    json.dumps(timeline, indent=2),
                    "pipeline_trace.json",
                    key="trace_dl",
                )
            else:
                st.info("Trace is empty.")
        else:
            st.info("No pipeline trace available. Run the End-to-End pipeline first.")

        # Also show saved traces from session
        st.markdown("---")
        st.caption("Pipeline traces are generated during End-to-End runs and persist for the session.")


# ############################################################
# PAGE 8: Paper-First Workflow (MethodSpec / MethodReview /
# ImplementationResolution / ResolvedMethodSpec)
# ############################################################
elif page == "Paper-First Workflow":
    st.header("Paper-First Workflow")
    st.caption(
        "Extract from the paper text (`MethodSpec`) \u2192 deterministic review "
        "(`MethodReview`) \u2192 physical-field resolution "
        "(`ImplementationResolution` \u2192 `ResolvedMethodSpec`). A spec produced here "
        "can be loaded directly in MetaCoder/Backtest & Experiments."
    )

    if not HAS_PYMUPDF:
        st.error("pymupdf not installed. Run: `pip install pymupdf`")
        st.stop()

    tab_extract, tab_review, tab_resolve = st.tabs(["1. Extract", "2. Review", "3. Resolve"])

    # ---- Extract ----
    with tab_extract:
        st.subheader("Extract MethodSpec")
        pf_uploaded_pdf = st.file_uploader("Upload paper PDF", type=["pdf"], key="pf_pdf")
        if pf_uploaded_pdf:
            pf_pdf_bytes = pf_uploaded_pdf.read()
            pf_paper_text = _extract_text_from_pdf_bytes(pf_pdf_bytes)
            st.session_state["pf_paper_text"] = pf_paper_text
            st.session_state["pf_pdf_bytes"] = pf_pdf_bytes
            st.success(f"Extracted **{len(pf_paper_text):,}** chars from `{pf_uploaded_pdf.name}`")

        with st.expander("Or load an existing MethodSpec draft"):
            pf_saved_drafts = sorted(UNREVIEWED_DIR.glob("*.paper.json"))
            pf_draft_name = st.selectbox("Saved draft", [""] + [p.name for p in pf_saved_drafts], key="pf_draft_sel")
            if st.button("Load draft", key="pf_draft_load"):
                try:
                    from src.infra.models.method_spec import MethodSpec
                    draft_path = UNREVIEWED_DIR / pf_draft_name
                    pf_paper = MethodSpec.model_validate_json(draft_path.read_text())
                    st.session_state["pf_paper"] = pf_paper
                    st.success(f"Loaded: {pf_paper.factor_id}")
                except Exception as e:
                    st.error(str(e))

        pf_document_id = st.text_input("Document ID", key="pf_doc_id")
        pf_target_name = st.text_input("Target factor name", key="pf_target_name")
        pf_paper_text = st.session_state.get("pf_paper_text", "")
        pf_disabled = not (pf_paper_text and pf_document_id and pf_target_name)
        if st.button("Extract MethodSpec", type="primary", disabled=pf_disabled, key="pf_extract_run"):
            with st.spinner("Extracting..."):
                from src.infra.llm import create_llm_client
                from src.steps.step1_extractor.extractor import MethodSpecExtractor, persist_raw_spec
                from src.steps.step2_reviewer.spec_build import build_reviewed_method_spec
                client = create_llm_client(provider=llm_provider, model=llm_model)
                extractor = MethodSpecExtractor(llm_client=client)
                pf_bytes = st.session_state.get("pf_pdf_bytes") if llm_provider in ("claude", "codex") else None
                result = extractor.extract(pf_document_id, pf_target_name, pf_paper_text, pdf_bytes=pf_bytes)
                st.session_state["pf_extraction_token_usage"] = result.token_usage
                if result.raw_spec:
                    persist_raw_spec(pf_document_id, pf_target_name, result.raw_spec)
                    outcome = build_reviewed_method_spec(
                        result.raw_spec, pf_document_id, pf_target_name, pf_paper_text, client
                    )
                    if outcome.spec:
                        out_path = UNREVIEWED_DIR / f"{outcome.spec.factor_id}.paper.json"
                        out_path.write_text(outcome.spec.model_dump_json(indent=2) + "\n")
                        st.session_state["pf_paper"] = outcome.spec
                        st.success(f"Extracted + reviewed: **{outcome.spec.factor_id}**, saved to `{out_path}`")
                    else:
                        st.error(f"Review loop did not converge: {outcome.error}")
                else:
                    st.error(f"Extraction failed: {result.error}")

        _show_token_usage(st.session_state.get("pf_extraction_token_usage"))

        pf_paper = st.session_state.get("pf_paper")
        if pf_paper:
            st.markdown("---")
            st.markdown(f"**Factor ID:** `{pf_paper.factor_id}` · **Target:** {pf_paper.target_name}")
            with st.expander("Full MethodSpec JSON"):
                st.json(json.loads(pf_paper.model_dump_json()))

    # ---- Review ----
    with tab_review:
        st.subheader("Deterministic Review")
        pf_review_options = sorted(UNREVIEWED_DIR.glob("*.paper.json"))
        pf_current = st.session_state.get("pf_paper")
        pf_choice_labels = [""] + ([f"(current) {pf_current.factor_id}"] if pf_current else []) + [p.name for p in pf_review_options]
        pf_review_sel = st.selectbox("MethodSpec to review", pf_choice_labels, key="pf_review_sel")

        if st.button("Run Review", key="pf_review_run"):
            from src.infra.models.method_spec import MethodSpec
            from src.steps.step2_reviewer.review import review_method_spec
            try:
                if pf_review_sel.startswith("(current)") and pf_current:
                    pf_review_paper = pf_current
                elif pf_review_sel:
                    pf_review_paper = MethodSpec.model_validate_json((UNREVIEWED_DIR / pf_review_sel).read_text())
                else:
                    st.warning("Select a MethodSpec first.")
                    pf_review_paper = None
                if pf_review_paper:
                    result = review_method_spec(pf_review_paper)
                    (REVIEWED_DIR / f"{pf_review_paper.factor_id}.review.json").write_text(
                        result.model_dump_json(indent=2) + "\n"
                    )
                    st.session_state["pf_review_paper"] = pf_review_paper
                    st.session_state["pf_review_result"] = result
                    st.success(f"Reviewed: **{pf_review_paper.factor_id}** ({len(result.findings)} findings)")
            except Exception as e:
                st.error(str(e))

        pf_review_result = st.session_state.get("pf_review_result")
        if pf_review_result:
            st.markdown("---")
            needs_human = [f for f in pf_review_result.findings if f.disposition.value == "needs_human_confirmation"]
            st.metric("Findings", len(pf_review_result.findings))
            st.metric("Needs human confirmation", len(needs_human))
            for f in pf_review_result.findings:
                icon = "⚠️" if f.disposition.value == "needs_human_confirmation" else "ℹ️"
                st.text(f"{icon} [{f.kind}] {f.field_path}: {f.reason}")

    # ---- Resolve ----
    with tab_resolve:
        st.subheader("Resolve Physical Fields")
        pf_review_paper = st.session_state.get("pf_review_paper")
        pf_review_result = st.session_state.get("pf_review_result")
        if not (pf_review_paper and pf_review_result):
            st.info("Run Review first (previous tab).")
        else:
            pf_returns_source = st.text_input("Returns source", value="us_equity_crsp", key="pf_returns_source")
            pf_cz_acronym = st.text_input("C&Z acronym (optional)", key="pf_cz_acronym")
            if st.button("Resolve", type="primary", key="pf_resolve_run"):
                from src.infra.models.method_spec import ResolvedMethodSpec
                from src.steps.step2_reviewer.implementation_resolution import build_implementation_resolution
                try:
                    resolution = build_implementation_resolution(
                        pf_review_paper,
                        pf_review_result,
                        returns_source=pf_returns_source,
                        cz_acronym=pf_cz_acronym or None,
                    )
                    (RESOLUTIONS_DIR / f"{pf_review_paper.factor_id}.resolution.json").write_text(
                        resolution.model_dump_json(indent=2) + "\n"
                    )
                    resolved = ResolvedMethodSpec(paper=pf_review_paper, review=pf_review_result, resolution=resolution)
                    resolved_path = RESOLVED_DIR / f"{pf_review_paper.factor_id}.resolved.json"
                    resolved_path.write_text(resolved.model_dump_json(indent=2) + "\n")
                    st.session_state["pf_resolved"] = resolved
                    if resolved.is_ready:
                        st.success(f"Resolved and **ready**: saved to `{resolved_path}`")
                    else:
                        st.warning(f"Resolved but **not ready** (blocked findings or unmapped concepts): saved to `{resolved_path}`")
                except Exception as e:
                    st.error(str(e))

            pf_resolved = st.session_state.get("pf_resolved")
            if pf_resolved:
                st.markdown("---")
                st.metric("is_ready", "Yes" if pf_resolved.is_ready else "No")
                with st.expander("Concept Mapping"):
                    st.json({k: v.model_dump() for k, v in pf_resolved.resolution.concept_mapping.items()})
                st.caption(
                    "This ResolvedMethodSpec can now be loaded directly in the MetaCoder and "
                    "Backtest & Experiments pages (look for the `[paper-first]` entries)."
                )
