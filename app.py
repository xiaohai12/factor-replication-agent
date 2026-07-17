"""Factor Replication Agent — Streamlit Dashboard.

Run: streamlit run app.py

Seven-page dashboard aligned with architecture.md pipeline:
  1. Pipeline — End to End
  2. Extractor
  3. Review & Resolve
  4. MetaCoder
  5. Backtest & Experiments
  6. Attribution
  7. Trace & Logs
"""

import json
import csv
import traceback
from pathlib import Path
from datetime import datetime, timezone

import numpy as np
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
CURATED_METHODSPEC_DIR = PROJECT_ROOT / "data" / "method_specs" / "curated"
CURATED_METHODSPEC_DIR.mkdir(parents=True, exist_ok=True)
RESOLVED_DIR = PROJECT_ROOT / "data" / "method_specs" / "resolved"
RESOLVED_DIR.mkdir(parents=True, exist_ok=True)
REVIEWED_DIR = PROJECT_ROOT / "data" / "method_specs" / "reviewed"
REVIEWED_DIR.mkdir(parents=True, exist_ok=True)
RESOLUTIONS_DIR = PROJECT_ROOT / "data" / "method_specs" / "resolutions"
RESOLUTIONS_DIR.mkdir(parents=True, exist_ok=True)
PLUGINS_DIR = PROJECT_ROOT / "data" / "plugins"
PLUGINS_DIR.mkdir(parents=True, exist_ok=True)
TEST_SPECS_DIR = PROJECT_ROOT / "data" / "test_method_specs"
TEST_DIR = PROJECT_ROOT / "data" / "method_specs" / "test"
EVIDENCE_DIR = PROJECT_ROOT / "evidence"
MSF_PATH = PROJECT_ROOT / "data" / "local" / "msf.parquet"

# ============================================================
# Sidebar
# ============================================================
st.sidebar.title("Pipeline Steps")
page = st.sidebar.radio(
    "Navigate",
    [
        "Pipeline — End to End",
        "Extractor",
        "Review & Resolve",
        "MetaCoder",
        "Backtest & Experiments",
        "Attribution",
        "Trace & Logs",
    ],
    index=0,
)

st.sidebar.markdown("---")
st.sidebar.markdown("**Module Status**")
st.sidebar.markdown("- Extractor ✅")
st.sidebar.markdown("- Review Gate ✅")
_plugin_count = len(list(PLUGINS_DIR.glob("*.py"))) if PLUGINS_DIR.exists() else 0
st.sidebar.markdown(f"- MetaCoder {'✅' if _plugin_count else '🚧'} ({_plugin_count} plugins)")
st.sidebar.markdown("- Sandbox ✅")
st.sidebar.markdown("- Backtest ✅")
st.sidebar.markdown("- Attribution 🚧")
st.sidebar.markdown("- Trace ✅")

st.sidebar.markdown("---")
llm_provider = st.sidebar.selectbox(
    "LLM Provider",
    ["codex", "claude", "copilot", "openrouter"],
    index=0,
)
_PROVIDER_MODELS = {
    "codex": ["gpt-5.4", "gpt-5.5"],
    "copilot": ["claude-opus-4-6", "claude-sonnet-4-6", "gpt-5.4"],
    "claude": ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5-20251001"],
    "openrouter": ["openai/gpt-4o", "anthropic/claude-sonnet-4", "openai/gpt-5.4"],
}
llm_model = st.sidebar.selectbox(
    "Model",
    _PROVIDER_MODELS.get(llm_provider, []),
    index=0,
)

_gt_count = len(list(TEST_SPECS_DIR.glob("*.methodspec.json"))) if TEST_SPECS_DIR.exists() else 0
st.sidebar.markdown("---")
st.sidebar.markdown(f"**Ground Truth:** {_gt_count} specs in `test_method_specs/`")

st.title("Factor Replication Agent")

# ============================================================
# Shared helpers
# ============================================================

def _save_paper_text_cache(pdf_name: str, paper_text: str) -> Path:
    cache_path = PAPER_TEXT_CACHE_DIR / f"{Path(pdf_name).stem}.txt"
    cache_path.write_text(paper_text, encoding="utf-8")
    return cache_path


def _load_paper_text_from_cache() -> str | None:
    cache_path = st.session_state.get("paper_text_path")
    if cache_path:
        path = Path(cache_path)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            st.session_state["paper_text"] = text
            return text
    return st.session_state.get("paper_text")


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _resolve_review_inputs(provider: str) -> tuple[str | None, bytes | None]:
    paper_text = _load_paper_text_from_cache()
    pdf_bytes = st.session_state.get("pdf_bytes")
    if paper_text:
        return paper_text, pdf_bytes if provider == "claude" else None
    if pdf_bytes:
        if provider == "claude":
            return None, pdf_bytes
        extracted_text = _extract_text_from_pdf_bytes(pdf_bytes)
        st.session_state["paper_text"] = extracted_text
        pdf_name = st.session_state.get("pdf_name", "uploaded_paper.pdf")
        paper_text_path = _save_paper_text_cache(pdf_name, extracted_text)
        st.session_state["paper_text_path"] = str(paper_text_path)
        return extracted_text, None
    return None, None


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


def _save_review_artifacts(spec, review_result, raw_llm_review=None) -> None:
    import dataclasses as _dc
    factor_id = spec.factor_id
    def _ser(obj):
        if hasattr(obj, "model_dump"):
            return _ser(obj.model_dump(mode="json"))
        if _dc.is_dataclass(obj):
            return _ser(_dc.asdict(obj))
        if isinstance(obj, dict):
            return {k: _ser(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_ser(i) for i in obj]
        if hasattr(obj, "value"):
            return obj.value
        return obj
    report_dict = _ser(review_result)
    if raw_llm_review:
        report_dict["_llm_raw"] = _ser(raw_llm_review)
    (REVIEWED_DIR / f"{factor_id}.review_report.json").write_text(
        json.dumps(report_dict, indent=2, ensure_ascii=False) + "\n"
    )
    (REVIEWED_DIR / f"{factor_id}.reviewed.methodspec.json").write_text(
        spec.model_dump_json(indent=2) + "\n"
    )


def _load_ground_truth_specs() -> dict[str, dict]:
    """Load all ground truth MethodSpecs from test_method_specs/."""
    specs = {}
    if TEST_SPECS_DIR.exists():
        for p in sorted(TEST_SPECS_DIR.glob("*.methodspec.json")):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                fid = data.get("factor_id", p.stem.replace(".methodspec", ""))
                specs[fid] = data
            except Exception:
                pass
    return specs


def _compare_specs(extracted: dict, ground_truth: dict) -> list[dict]:
    """Compare extracted spec fields against ground truth. Returns list of field comparisons."""
    fields_to_compare = [
        ("signal.formula.expression", "signal.formula.expression"),
        ("signal.formula.paper_expression", "signal.formula.paper_expression"),
        ("signal.timing.formation_month", "signal.timing.formation_month"),
        ("signal.timing.rebalance_frequency", "signal.timing.rebalance_frequency"),
        ("signal.timing.holding_period", "signal.timing.holding_period"),
        ("signal.timing.accounting_lag", "signal.timing.accounting_lag"),
        ("signal.timing.skip_month", "signal.timing.skip_month"),
        ("signal.missing_policy.action", "signal.missing_policy.action"),
        ("portfolio.sort.breakpoint_source", "portfolio.sort.breakpoint_source"),
        ("portfolio.weighting", "portfolio.weighting"),
        ("portfolio.long_leg", "portfolio.long_leg"),
        ("portfolio.short_leg", "portfolio.short_leg"),
        ("sign", "signal.sign"),
    ]
    results = []
    for ext_path, gt_path in fields_to_compare:
        ext_val = _get_nested(extracted, ext_path)
        gt_val = _get_nested(ground_truth, gt_path)
        match = _values_match(ext_val, gt_val)
        results.append({
            "field": ext_path,
            "extracted": str(ext_val) if ext_val is not None else "",
            "ground_truth": str(gt_val) if gt_val is not None else "",
            "match": match,
        })
    return results


def _get_nested(d: dict, path: str):
    """Get a nested value from a dict using dot-separated path."""
    cur = d
    for key in path.split("."):
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            return None
    return cur


def _values_match(a, b) -> bool:
    """Compare two values flexibly."""
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    sa, sb = str(a).strip().lower(), str(b).strip().lower()
    if sa == sb:
        return True
    # Handle enum values
    for prefix in ("breakpointsource.", "weightingrule.", "missingaction.", "rebalancefrequency."):
        sa = sa.replace(prefix, "")
        sb = sb.replace(prefix, "")
    return sa == sb


def _compute_eval_metrics(comparisons: list[dict]) -> dict:
    """Compute evaluation metrics from field comparisons."""
    total = len(comparisons)
    matched = sum(1 for c in comparisons if c["match"])
    gt_present = sum(1 for c in comparisons if c["ground_truth"])
    extracted_present = sum(1 for c in comparisons if c["extracted"])
    return {
        "field_accuracy": matched / total if total > 0 else 0,
        "field_coverage": extracted_present / gt_present if gt_present > 0 else 0,
        "matched": matched,
        "total": total,
    }


# Resolution helpers
_PATH_ALIASES_RES = {
    "universe.missing_policy.action": "signal.missing_policy.action",
    "universe.winsorize_bounds": "signal.missing_policy.winsorize_bounds",
}

def _res_get_path(data, path):
    cur = data
    for p in _PATH_ALIASES_RES.get(path, path).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(p)
    return cur

def _res_set_path(data, path, value):
    parts = _PATH_ALIASES_RES.get(path, path).split(".")
    cur = data
    for p in parts[:-1]:
        cur = cur.setdefault(p, {})
    cur[parts[-1]] = value

def _field_options(field_path, current_value, candidate_value):
    opts = []
    if candidate_value not in (None, "", "unspecified"):
        opts.append((f"candidate: {candidate_value}", candidate_value))
    if field_path.endswith("breakpoint_source"):
        opts += [("nyse", "nyse"), ("full_sample", "full_sample")]
    elif "missing_policy" in field_path:
        opts += [("drop", "drop"), ("keep", "keep"), ("winsorize", "winsorize")]
    elif field_path.endswith("weighting") or field_path.endswith("stock_weight"):
        opts += [("vw", "vw"), ("ew", "ew"), ("capped_vw", "capped_vw")]
    elif "rebalance_frequency" in field_path:
        opts += [("annual", "annual"), ("monthly", "monthly"), ("quarterly", "quarterly")]
    elif "formation_month" in field_path:
        opts += [(f"month {m}", m) for m in [6, 7, 12]]
    elif "accounting_lag" in field_path:
        opts += [(f"{m} months", m) for m in [4, 5, 6]]
    else:
        if current_value not in (None, "", "unspecified"):
            opts.append((f"keep current: {current_value}", current_value))
        opts.append(("unspecified", "unspecified"))
    seen, deduped = set(), []
    for label, val in opts:
        k = str(val)
        if k not in seen:
            deduped.append((label, val))
            seen.add(k)
    deduped.append(("custom value...", "__custom__"))
    return deduped

def _status_val(note):
    return note.status.value if hasattr(note.status, "value") else str(note.status)


# ############################################################
# PAGE 1: Pipeline — End to End
# ############################################################
if page == "Pipeline — End to End":
    st.header("Pipeline — End to End")
    st.markdown(
        "Run the full pipeline from PDF upload through backtest in one go. "
        "Each stage output is displayed in an expandable section."
    )

    # Input selection
    input_mode = st.radio("Input", ["Upload PDF", "Select existing MethodSpec"], horizontal=True)

    if input_mode == "Upload PDF":
        e2e_pdf = st.file_uploader("Upload paper PDF", type=["pdf"], key="e2e_pdf")
    else:
        spec_files_e2e = []
        for d, label in [(CURATED_METHODSPEC_DIR, "curated"), (RESOLVED_DIR, "resolved")]:
            if d.exists():
                for p in sorted(d.glob("*.methodspec.json")) + sorted(d.glob("*.resolved.methodspec.json")):
                    spec_files_e2e.append((f"[{label}] {p.name}", p))
        e2e_spec_options = [""] + [l for l, _ in spec_files_e2e]
        e2e_spec_map = {l: p for l, p in spec_files_e2e}
        e2e_selected = st.selectbox("MethodSpec", e2e_spec_options, key="e2e_spec_sel")
        e2e_pdf = None

    run_e2e = st.button("Run Full Pipeline", type="primary", key="e2e_run")

    if run_e2e:
        from src.infra.trace import PipelineTracer
        tracer = PipelineTracer()
        stages = {}
        st.session_state["e2e_tracer"] = tracer
        progress = st.progress(0, text="Starting...")

        try:
            # Stage 1: Extract
            progress.progress(1 / 7, text="Stage 1/7 — Extracting...")
            tracer.log("extract", "started")

            from src.infra.models import MethodSpec as _MS

            if input_mode == "Upload PDF" and e2e_pdf:
                pdf_bytes = e2e_pdf.read()
                paper_text = _extract_text_from_pdf_bytes(pdf_bytes)
                pdf_stem = Path(e2e_pdf.name).stem
                _save_paper_text_cache(e2e_pdf.name, paper_text)

                from src.steps.extractor import SemanticExtractor
                from src.infra.llm import create_llm_client
                client = create_llm_client(provider=llm_provider, model=llm_model)
                extractor = SemanticExtractor(llm_client=client)
                _pdf_b = pdf_bytes if llm_provider in ("claude", "codex") else None
                result = extractor.extract(pdf_stem, paper_text, pdf_bytes=_pdf_b)
                spec = result.spec
                tracer.log("extract", "done", f"{len(paper_text)} chars, factor_id={spec.factor_id}")
            elif input_mode == "Select existing MethodSpec" and e2e_selected:
                spec = _MS.model_validate_json(e2e_spec_map[e2e_selected].read_text())
                paper_text = None
                tracer.log("extract", "skipped — loaded existing spec", spec.factor_id)
            else:
                st.warning("Select an input.")
                st.stop()

            stages["extract"] = {"status": "done", "factor_id": spec.factor_id}

            # Stage 2: Review
            progress.progress(2 / 7, text="Stage 2/7 — Reviewing...")
            tracer.log("review", "started")
            from src.steps.reviewer import ReviewGate
            gate = ReviewGate()
            review_result = gate.review(spec)
            tracer.log("review", "done", f"disposition={review_result.disposition}")
            stages["review"] = {"status": "done", "disposition": review_result.disposition}

            # Stage 3: Resolve (auto-apply sensible defaults)
            progress.progress(3 / 7, text="Stage 3/7 — Resolving...")
            tracer.log("resolve", "started")
            from src.steps.reviewer import SENSIBLE_DEFAULTS
            spec_dict = json.loads(spec.model_dump_json())
            n_resolved = 0
            for note in review_result.field_notes:
                sv = _status_val(note)
                if sv in ("approve_with_default", "needs_llm_review"):
                    default_val = SENSIBLE_DEFAULTS.get(note.field, note.candidate_value)
                    if default_val not in (None, "", "unspecified"):
                        _res_set_path(spec_dict, note.field, default_val)
                        n_resolved += 1
            spec_dict["codegen_ready"] = True
            spec_dict["review_status"] = "approved"
            spec = _MS.model_validate(spec_dict)
            tracer.log("resolve", "done", f"{n_resolved} fields auto-resolved")
            stages["resolve"] = {"status": "done", "n_resolved": n_resolved}

            # Stage 4: MetaCoder
            progress.progress(4 / 7, text="Stage 4/7 — Generating plugin...")
            tracer.log("metacoder", "started")
            from src.steps.codegen import MetaCoder
            from src.infra.llm import create_llm_client as _clc
            from src.infra.models.method_spec import ReviewStatus
            gen_spec = spec.model_copy(update={"codegen_ready": True, "review_status": ReviewStatus.APPROVED})
            llm = _clc(provider=llm_provider, model=llm_model)
            coder = MetaCoder(llm_client=llm)
            plugin = coder.generate_plugin(gen_spec)
            tracer.log("metacoder", "done", f"code_hash={plugin.code_hash}, hooks={len(plugin.hooks or {})}")
            stages["metacoder"] = {"status": "done", "code_hash": plugin.code_hash}

            # Stage 5: Sandbox
            progress.progress(5 / 7, text="Stage 5/7 — Sandbox validation...")
            tracer.log("sandbox", "started")
            from src.steps.validator import AdversarialSandbox
            sandbox = AdversarialSandbox()
            report = sandbox.validate(plugin, spec)
            tracer.log("sandbox", "done" if report.passed else "FAILED", str(report.errors))
            stages["sandbox"] = {"status": "passed" if report.passed else "failed", "errors": report.errors}

            if not report.passed:
                tracer.log("sandbox", "repair needed", level="warning")

            # Stage 6: Backtest
            progress.progress(6 / 7, text="Stage 6/7 — Backtesting...")
            tracer.log("backtest", "started")
            if MSF_PATH.exists():
                from src.steps.engine import BacktestEngine
                engine = BacktestEngine(data_path=str(PROJECT_ROOT / "data"))
                msf = pd.read_parquet(MSF_PATH)
                # Standardize
                msf.columns = [c.lower() for c in msf.columns]
                if "date" in msf.columns and "yyyymm" not in msf.columns:
                    msf["yyyymm"] = pd.to_datetime(msf["date"]).dt.year * 100 + pd.to_datetime(msf["date"]).dt.month
                for c in ("permno", "yyyymm"):
                    if c in msf.columns:
                        msf[c] = msf[c].astype(int)

                plugin_ns = {}
                exec(compile(plugin.code, f"<plugin:{plugin.factor_id}>", "exec"), plugin_ns)
                compute_signal = plugin_ns["compute_signal"]
                signal_df = compute_signal(msf)

                def _patched_load(config):
                    return msf
                engine._load_data = _patched_load
                bt_result = engine.run(signal=signal_df, spec=spec, plugin=plugin)
                tracer.log("backtest", "done", f"t_stat={bt_result['metrics'].get('t_stat', 'N/A'):.2f}")
                stages["backtest"] = {"status": "done", "metrics": bt_result["metrics"]}
            else:
                tracer.log("backtest", "skipped — data/local/msf.parquet not found", level="warning")
                stages["backtest"] = {"status": "skipped", "reason": "no data"}
                bt_result = None

            # Stage 7: Attribution (placeholder)
            progress.progress(7 / 7, text="Stage 7/7 — Attribution...")
            tracer.log("attribution", "skipped — requires dual-track runs")
            stages["attribution"] = {"status": "skipped"}

            progress.progress(1.0, text="Pipeline complete!")
            st.session_state["e2e_stages"] = stages
            st.session_state["e2e_spec"] = spec
            st.session_state["e2e_plugin"] = plugin
            st.session_state["e2e_bt_result"] = bt_result

        except Exception as e:
            tracer.log("pipeline", f"ERROR: {e}", level="error")
            st.error(f"Pipeline failed: {e}")
            st.code(traceback.format_exc())
            st.session_state["e2e_stages"] = stages

    # Display results
    stages = st.session_state.get("e2e_stages", {})
    if stages:
        st.markdown("---")
        st.subheader("Stage Results")
        stage_names = ["extract", "review", "resolve", "metacoder", "sandbox", "backtest", "attribution"]
        stage_icons = {"done": "✅", "passed": "✅", "failed": "❌", "skipped": "⏭️"}
        for sn in stage_names:
            s = stages.get(sn, {})
            status = s.get("status", "pending")
            icon = stage_icons.get(status, "⏳")
            with st.expander(f"{icon} {sn.capitalize()}", expanded=(status == "failed")):
                st.json(s)

        # Final metrics
        bt_result = st.session_state.get("e2e_bt_result")
        if bt_result:
            st.markdown("---")
            st.subheader("Backtest Results")
            m = bt_result["metrics"]
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("Mean Monthly", f"{m.get('mean_monthly_return', 0)*100:.3f}%")
            mc2.metric("t-stat (NW)", f"{m.get('t_stat', 0):.2f}")
            mc3.metric("Annualized", f"{m.get('annualized_return', 0)*100:.1f}%")
            mc4.metric("N Months", m.get("n_months", 0))

    # Trace
    tracer = st.session_state.get("e2e_tracer")
    if tracer:
        with st.expander("Pipeline Trace"):
            for ev in tracer.get_timeline():
                level_icon = {"info": "ℹ️", "warning": "⚠️", "error": "❌"}.get(ev["level"], "")
                st.text(f"{ev['timestamp'][-8:]} {level_icon} [{ev['stage']}] {ev['event']} {ev['detail']}")


# ############################################################
# PAGE 2: Extractor
# ############################################################
elif page == "Extractor":
    st.header("Extractor — Extract MethodSpec from Paper")

    if not HAS_PYMUPDF:
        st.error("pymupdf not installed. Run: `pip install pymupdf`")
        st.stop()

    # Upload / load
    st.subheader("1. Upload Paper or Load Saved Spec")
    uploaded_pdf = st.file_uploader("Upload paper PDF", type=["pdf"], key="ext_pdf")

    if uploaded_pdf:
        pdf_bytes = uploaded_pdf.read()
        paper_text = _extract_text_from_pdf_bytes(pdf_bytes)
        paper_text_path = _save_paper_text_cache(uploaded_pdf.name, paper_text)
        st.session_state["paper_text"] = paper_text
        st.session_state["paper_text_path"] = str(paper_text_path)
        st.session_state["pdf_bytes"] = pdf_bytes
        st.session_state["pdf_name"] = uploaded_pdf.name
        st.success(f"Extracted **{len(paper_text):,}** chars from `{uploaded_pdf.name}`")

    with st.expander("Import Existing MethodSpec"):
        saved_specs = sorted(CURATED_METHODSPEC_DIR.glob("*.methodspec.json"))
        saved_texts = sorted(PAPER_TEXT_CACHE_DIR.glob("*.txt"))
        spec_options = [""] + [p.name for p in saved_specs]
        selected_spec_name = st.selectbox("Saved MethodSpec", spec_options, index=0, key="ext_saved_spec")
        text_options = [""] + [p.name for p in saved_texts]
        selected_text_name = st.selectbox("Saved paper text", text_options, index=0, key="ext_saved_text")
        imported_spec_file = st.file_uploader("Or upload JSON", type=["json"], key="ext_import_json")

        if st.button("Load", key="ext_load_saved"):
            try:
                from src.infra.models import MethodSpec
                if imported_spec_file:
                    spec = MethodSpec.model_validate_json(imported_spec_file.getvalue().decode())
                elif selected_spec_name:
                    spec = MethodSpec.model_validate_json((CURATED_METHODSPEC_DIR / selected_spec_name).read_text())
                else:
                    st.warning("Select or upload a spec.")
                    spec = None
                if spec:
                    st.session_state["extracted_spec"] = spec
                    if selected_text_name:
                        tp = PAPER_TEXT_CACHE_DIR / selected_text_name
                        st.session_state["paper_text_path"] = str(tp)
                        st.session_state["paper_text"] = tp.read_text()
                    st.success(f"Loaded: {spec.factor_id}")
            except Exception as e:
                st.error(str(e))

    paper_text = _load_paper_text_from_cache()
    if not paper_text and not st.session_state.get("extracted_spec"):
        st.info("Upload a PDF or load a saved MethodSpec.")
        st.stop()

    # Extract
    st.subheader("2. Extract")
    _pdf_stem = Path(st.session_state.get("pdf_name", "unknown")).stem

    if st.button("Extract MethodSpec", type="primary", disabled=not bool(paper_text), key="ext_run"):
        with st.spinner("Extracting..."):
            from src.steps.extractor import SemanticExtractor
            from src.infra.llm import create_llm_client
            client = create_llm_client(provider=llm_provider, model=llm_model)
            extractor = SemanticExtractor(llm_client=client)
            _pdf_b = st.session_state.get("pdf_bytes") if llm_provider in ("claude", "codex") else None
            result = extractor.extract(_pdf_stem, paper_text, pdf_bytes=_pdf_b)
            st.session_state["raw_llm_output"] = result.raw_llm_output
            st.session_state["extracted_spec"] = result.spec
            st.session_state["extraction_token_usage"] = result.token_usage
            if result.spec:
                fid = result.spec.factor_id or _pdf_stem
                out_path = CURATED_METHODSPEC_DIR / f"{fid}.methodspec.json"
                out_path.write_text(result.spec.model_dump_json(indent=2) + "\n")
                st.session_state["extracted_spec_path"] = str(out_path)
                st.success(f"Extracted: **{fid}**")

    _show_token_usage(st.session_state.get("extraction_token_usage"))

    # Results
    spec = st.session_state.get("extracted_spec")
    if spec:
        st.markdown("---")
        st.subheader("3. Extraction Results")
        st.markdown(f"**Factor:** {spec.factor_name} · **Formula:** `{spec.signal.formula}`")
        st.markdown(f"**Required fields:** {', '.join(spec.signal.required_fields)}")

        timing = spec.signal.timing
        tcol1, tcol2, tcol3, tcol4 = st.columns(4)
        tcol1.metric("Formation Month", timing.formation_month)
        tcol2.metric("Rebalance", getattr(timing.rebalance_frequency, "value", timing.rebalance_frequency))
        tcol3.metric("Holding (months)", timing.holding_period)
        tcol4.metric("Lag (months)", timing.accounting_lag)

        if spec.ambiguous_fields:
            st.warning(f"**{len(spec.ambiguous_fields)} ambiguous fields**")
            for af in spec.ambiguous_fields:
                st.caption(f"- **{af.field}**: {af.reason}")

        with st.expander("Full MethodSpec JSON"):
            st.json(json.loads(spec.model_dump_json()))

        # Eval vs ground truth
        st.markdown("---")
        st.subheader("4. Eval vs Ground Truth")
        gt_specs = _load_ground_truth_specs()
        gt_match = gt_specs.get(spec.factor_id) or gt_specs.get(getattr(spec, "cz_acronym", "") or "")

        if gt_match:
            ext_dict = json.loads(spec.model_dump_json())
            comparisons = _compare_specs(ext_dict, gt_match)
            metrics = _compute_eval_metrics(comparisons)

            ecol1, ecol2, ecol3 = st.columns(3)
            ecol1.metric("Field Accuracy", f"{metrics['field_accuracy']:.0%}")
            ecol2.metric("Field Coverage", f"{metrics['field_coverage']:.0%}")
            ecol3.metric("Matched", f"{metrics['matched']}/{metrics['total']}")

            eval_data = []
            for c in comparisons:
                eval_data.append({
                    "Field": c["field"],
                    "Extracted": c["extracted"],
                    "Ground Truth": c["ground_truth"],
                    "Match": "✅" if c["match"] else "❌",
                })
            st.table(eval_data)
        else:
            st.info(f"No ground truth found for `{spec.factor_id}` in `data/test_method_specs/`.")

        # Batch eval
        with st.expander("Batch Eval — All Ground Truth Specs"):
            if st.button("Run Batch Extraction Eval", key="ext_batch_eval"):
                st.info("Batch eval compares already-extracted specs against ground truth. "
                        "For full re-extraction, use the CLI scripts.")
                batch_results = []
                for fid, gt_data in gt_specs.items():
                    # Check if we have a curated spec
                    curated = CURATED_METHODSPEC_DIR / f"{fid}.methodspec.json"
                    if curated.exists():
                        try:
                            ext_data = json.loads(curated.read_text())
                            comps = _compare_specs(ext_data, gt_data)
                            m = _compute_eval_metrics(comps)
                            batch_results.append({"factor_id": fid, **m})
                        except Exception:
                            batch_results.append({"factor_id": fid, "field_accuracy": 0, "error": True})
                if batch_results:
                    st.dataframe(pd.DataFrame(batch_results), use_container_width=True)
                else:
                    st.caption("No curated specs found to compare.")


# ############################################################
# PAGE 3: Review & Resolve
# ############################################################
elif page == "Review & Resolve":
    st.header("Review & Resolve")

    tab_review, tab_resolve, tab_eval = st.tabs(["Review", "Resolution", "Eval"])

    # --- Load spec ---
    spec_files_rr = []
    for d, label in [(CURATED_METHODSPEC_DIR, "curated"), (RESOLVED_DIR, "resolved")]:
        if d.exists():
            for p in sorted(d.glob("*.methodspec.json")) + sorted(d.glob("*.resolved.methodspec.json")):
                spec_files_rr.append((f"[{label}] {p.name}", p))
    rr_options = [""] + [l for l, _ in spec_files_rr]
    rr_map = {l: p for l, p in spec_files_rr}

    rr_selected = st.selectbox("Select MethodSpec to review", rr_options, key="rr_spec_sel")

    if rr_selected and st.button("Load", key="rr_load"):
        from src.infra.models import MethodSpec as _MS
        try:
            rr_spec = _MS.model_validate_json(rr_map[rr_selected].read_text())
            st.session_state["rr_spec"] = rr_spec
            st.session_state["rr_review"] = None
            st.session_state["rr_resolution_inputs"] = {}
            st.success(f"Loaded: {rr_spec.factor_id}")
        except Exception as e:
            st.error(str(e))

    rr_spec = st.session_state.get("rr_spec")
    if not rr_spec:
        st.info("Select and load a MethodSpec to begin review.")
        st.stop()

    with tab_review:
        st.subheader("Review Gate")
        col_rules, col_llm = st.columns(2)
        with col_rules:
            if st.button("Run Rules Review", key="rr_rules"):
                from src.steps.reviewer import ReviewGate
                review = ReviewGate().review(rr_spec)
                st.session_state["rr_review"] = review
        with col_llm:
            if st.button("Run LLM Review", type="primary", key="rr_llm"):
                from src.steps.reviewer import ReviewGate
                from src.infra.llm import create_llm_client
                with st.spinner("LLM reviewing..."):
                    try:
                        pt, pb = _resolve_review_inputs(llm_provider)
                        if not pt and not pb:
                            raise RuntimeError("No paper text loaded.")
                        llm = create_llm_client(provider=llm_provider, model=llm_model)
                        gate = ReviewGate(llm_client=llm)
                        review, raw = gate.review_with_llm(rr_spec, pt or "", pdf_bytes=pb)
                        st.session_state["rr_review"] = review
                        st.session_state["rr_review_raw"] = raw
                        _save_review_artifacts(rr_spec, review, raw)
                    except Exception as e:
                        st.error(str(e))

        review = st.session_state.get("rr_review")
        if review:
            _disp_icons = {"approved": "✅", "revision_required": "⚠️", "blocked": "🚫"}
            st.subheader(f"Disposition: {_disp_icons.get(review.disposition, '❓')} {review.disposition.upper()}")
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Codegen Ready", "Yes" if review.codegen_ready else "No")
            rc2.metric("Blocked Fields", len(review.blocked_fields))
            rc3.metric("Issues", len(review.issues))

            if review.issues:
                for issue in review.issues:
                    st.error(issue)
            if review.field_notes:
                _status_icons = {
                    "auto_approve": "✅", "auto_approve_with_flag": "🟡",
                    "approve_with_default": "🟢", "needs_llm_review": "🔵",
                    "needs_human_confirmation": "🔴",
                }
                fn_data = []
                for note in review.field_notes:
                    sv = _status_val(note)
                    fn_data.append({
                        "Field": note.field,
                        "Status": f"{_status_icons.get(sv, '❓')} {sv}",
                        "Impact": note.empirical_impact,
                        "Current": str(note.current_value),
                        "Reason": note.reason,
                    })
                st.table(fn_data)

    with tab_resolve:
        st.subheader("Apply Resolutions")
        review = st.session_state.get("rr_review")
        if not review:
            st.info("Run a review first.")
        else:
            from src.steps.reviewer import SENSIBLE_DEFAULTS
            if "rr_resolution_inputs" not in st.session_state:
                st.session_state["rr_resolution_inputs"] = {}

            human_fields = [n for n in review.field_notes if _status_val(n) == "needs_human_confirmation"]
            llm_fields = [n for n in review.field_notes if _status_val(n) == "needs_llm_review"]
            default_fields = [n for n in review.field_notes if _status_val(n) == "approve_with_default"]

            if human_fields:
                st.markdown("#### 🔴 Human Confirmation Required")
                for note in human_fields:
                    fp = note.field
                    opts = _field_options(fp, note.current_value, note.candidate_value)
                    with st.expander(f"{fp}", expanded=True):
                        st.caption(note.reason)
                        labels = [l for l, _ in opts]
                        sel = st.selectbox("Resolution:", labels, key=f"rr_hres_{fp}")
                        val = dict(opts)[sel]
                        if val == "__custom__":
                            val = st.text_input("Custom:", key=f"rr_hcustom_{fp}")
                        st.session_state["rr_resolution_inputs"][fp] = {
                            "value": val, "reason": "Human confirmed.", "decision_type": "human_empirical_assumption",
                        }

            if default_fields:
                st.markdown("#### 🟢 Sensible Defaults")
                for note in default_fields:
                    fp = note.field
                    default_val = SENSIBLE_DEFAULTS.get(fp, note.candidate_value)
                    st.markdown(f"**{fp}**: `{default_val}` — _{note.reason}_")
                    st.session_state["rr_resolution_inputs"][fp] = {
                        "value": default_val, "reason": "Sensible default.", "decision_type": "sensible_default",
                    }

            if st.button("Apply All Resolutions", type="primary", key="rr_apply"):
                inputs = st.session_state.get("rr_resolution_inputs", {})
                from src.infra.models.method_spec import MethodSpec as _MS
                spec_dict = json.loads(rr_spec.model_dump_json())
                decisions = []
                for fp, inp in inputs.items():
                    decisions.append({
                        "field_path": fp, "old_value": _res_get_path(spec_dict, fp),
                        "new_value": inp["value"], "decision_type": inp["decision_type"],
                        "reason": inp["reason"], "reviewer": "human",
                    })
                    _res_set_path(spec_dict, fp, inp["value"])
                spec_dict["codegen_ready"] = True
                spec_dict["review_status"] = "approved"
                spec_dict.setdefault("resolution_log", []).extend(decisions)
                try:
                    resolved = _MS.model_validate(spec_dict)
                    st.session_state["rr_resolved"] = resolved
                    fid = rr_spec.factor_id
                    (RESOLVED_DIR / f"{fid}.resolved.methodspec.json").write_text(
                        json.dumps(spec_dict, indent=2, ensure_ascii=False) + "\n"
                    )
                    (RESOLUTIONS_DIR / f"{fid}.resolution.json").write_text(
                        json.dumps({"factor_id": fid, "decisions": decisions}, indent=2) + "\n"
                    )
                    st.success(f"Resolved! codegen_ready=true. Saved to `resolved/`.")
                except Exception as e:
                    st.error(str(e))

    with tab_eval:
        st.subheader("Resolution Eval vs Ground Truth")
        resolved = st.session_state.get("rr_resolved", rr_spec)
        gt_specs = _load_ground_truth_specs()
        gt = gt_specs.get(resolved.factor_id) or gt_specs.get(getattr(resolved, "cz_acronym", "") or "")
        if gt:
            ext_dict = json.loads(resolved.model_dump_json())
            comps = _compare_specs(ext_dict, gt)
            metrics = _compute_eval_metrics(comps)
            ec1, ec2 = st.columns(2)
            ec1.metric("Resolution Accuracy", f"{metrics['field_accuracy']:.0%}")
            ec2.metric("Matched", f"{metrics['matched']}/{metrics['total']}")
            eval_data = [{"Field": c["field"], "Resolved": c["extracted"], "Ground Truth": c["ground_truth"],
                          "Correct": "✅" if c["match"] else "❌"} for c in comps]
            st.table(eval_data)
        else:
            st.info(f"No ground truth for `{resolved.factor_id}` in `test_method_specs/`.")


# ############################################################
# PAGE 4: MetaCoder
# ############################################################
elif page == "MetaCoder":
    st.header("MetaCoder — Generate Signal Plugin")
    st.markdown("Load an approved MethodSpec and generate a Python signal plugin.")

    st.subheader("1. Load Resolved MethodSpec")
    _spec_files_mc: list[tuple[str, Path]] = []
    for _dir, _label in ((RESOLVED_DIR, "resolved"), (TEST_DIR, "test")):
        if _dir and _dir.exists():
            for _p in sorted(_dir.glob("*.resolved.methodspec.json")):
                _spec_files_mc.append((f"[{_label}] {_p.name}", _p))
    mc_options = [""] + [l for l, _ in _spec_files_mc]
    mc_map = {l: p for l, p in _spec_files_mc}

    col_sel, col_up = st.columns([2, 1])
    with col_sel:
        mc_selected = st.selectbox("Resolved MethodSpec", mc_options, key="mc_sel")
    with col_up:
        mc_uploaded = st.file_uploader("Or upload JSON", type=["json"], key="mc_upload")

    if st.button("Load MethodSpec", key="mc_load"):
        from src.infra.models import MethodSpec as _MS
        try:
            if mc_uploaded:
                mc_spec = _MS.model_validate_json(mc_uploaded.getvalue().decode())
            elif mc_selected:
                mc_spec = _MS.model_validate_json(mc_map[mc_selected].read_text())
            else:
                st.warning("Select a spec.")
                mc_spec = None
            if mc_spec:
                st.session_state["mc_spec"] = mc_spec
                st.session_state.pop("mc_plugin", None)
                st.session_state.pop("mc_sandbox_report", None)
                st.success(f"Loaded: **{mc_spec.factor_id}**")
        except Exception as e:
            st.error(str(e))

    mc_spec = st.session_state.get("mc_spec")
    if mc_spec:
        st.markdown("---")
        st.subheader("2. Spec Summary")
        sc1, sc2, sc3 = st.columns(3)
        rs_val = getattr(mc_spec.review_status, "value", mc_spec.review_status)
        sc1.metric("Review Status", rs_val)
        sc2.metric("Codegen Ready", "Yes" if mc_spec.codegen_ready else "No")
        sc3.metric("Version", mc_spec.version)

        # Hook detection
        st.subheader("3. Hook Detection")
        try:
            from src.steps.engine import BacktestEngine
            hooks_needed = BacktestEngine._detect_hooks(mc_spec)
            if hooks_needed:
                st.warning(f"**{len(hooks_needed)} non-standard step(s):**")
                for step, reason in hooks_needed.items():
                    st.markdown(f"- `{step}_hook` — {reason}")
            else:
                st.success("All steps standard — only `compute_signal()` needed.")
        except Exception as e:
            st.error(str(e))

        # Generate
        st.markdown("---")
        st.subheader("4. Generate Plugin")
        approved = rs_val == "approved" and mc_spec.codegen_ready
        if not approved:
            st.error("MethodSpec not codegen-ready. Go to Review & Resolve first.")

        if st.button("Generate Signal Plugin", type="primary", disabled=not approved, key="mc_gen"):
            from src.infra.llm import create_llm_client
            from src.steps.codegen import MetaCoder
            from src.infra.models.method_spec import ReviewStatus
            with st.spinner("Generating..."):
                try:
                    gen_spec = mc_spec.model_copy(update={"codegen_ready": True, "review_status": ReviewStatus.APPROVED})
                    llm = create_llm_client(provider=llm_provider, model=llm_model)
                    coder = MetaCoder(llm_client=llm)
                    plugin = coder.generate_plugin(gen_spec)
                    st.session_state["mc_plugin"] = plugin
                    st.session_state.pop("mc_sandbox_report", None)
                    st.success("Plugin generated!")
                except Exception as e:
                    st.error(str(e))

        mc_plugin = st.session_state.get("mc_plugin")
        if mc_plugin:
            st.subheader("5. Generated Code")
            st.code(mc_plugin.code, language="python")

            dl_col, save_col, _ = st.columns([1, 1, 2])
            with dl_col:
                st.download_button("Download", mc_plugin.code, f"{mc_plugin.factor_id}.py", key="mc_dl")
            with save_col:
                if st.button("Save to plugins/", key="mc_save"):
                    (PLUGINS_DIR / f"{mc_plugin.factor_id}.py").write_text(mc_plugin.code)
                    st.success("Saved!")

            # Sandbox
            st.subheader("6. Sandbox Validation")
            if st.button("Run Sandbox", key="mc_sandbox"):
                from src.steps.validator import AdversarialSandbox
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
                        from src.steps.codegen.script_generator import generate_backtest_script
                        script = generate_backtest_script(mc_spec, mc_plugin.code, data_path=bt_path)
                        st.session_state["mc_bt_script"] = script
                        # Save to data/backtest_scripts/
                        bt_scripts_dir = Path("data/backtest_scripts")
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
    existing = sorted(PLUGINS_DIR.glob("*.py"))
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

    tab_single, tab_dual, tab_ablation = st.tabs(["Single Run", "Dual-Track", "Ablation"])

    with tab_single:
        st.subheader("Single Backtest Run")

        plugin_files = sorted(PLUGINS_DIR.glob("*.py")) if PLUGINS_DIR.exists() else []
        spec_files_bt = sorted(RESOLVED_DIR.glob("*.resolved.methodspec.json")) if RESOLVED_DIR.exists() else []

        col_p, col_s = st.columns(2)
        with col_p:
            bt_plugin = st.selectbox("Plugin", [""] + [f.name for f in plugin_files], key="bt_plugin")
        with col_s:
            bt_spec = st.selectbox("MethodSpec", [""] + [f.name for f in spec_files_bt], key="bt_spec")

        data_src = st.radio("CRSP Data", ["Local (data/local/msf.parquet)", "Upload"], horizontal=True, key="bt_data_src")
        bt_uploaded_msf = None
        if data_src == "Upload":
            bt_uploaded_msf = st.file_uploader("Upload msf.parquet", type=["parquet"], key="bt_msf_upload")

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
        has_data = MSF_PATH.exists() or bt_uploaded_msf is not None

        if st.button("Run Backtest", type="primary", disabled=not (can_run and has_data), key="bt_run"):
            with st.spinner("Running..."):
                try:
                    from src.steps.engine import BacktestEngine
                    from src.infra.models import MethodSpec as _MS
                    import io

                    spec = _MS.model_validate_json((RESOLVED_DIR / bt_spec).read_text())
                    plugin_code = (PLUGINS_DIR / bt_plugin).read_text()
                    plugin_ns = {}
                    exec(compile(plugin_code, bt_plugin, "exec"), plugin_ns)
                    compute_signal = plugin_ns["compute_signal"]

                    msf = pd.read_parquet(io.BytesIO(bt_uploaded_msf.getvalue())) if bt_uploaded_msf else pd.read_parquet(MSF_PATH)
                    msf.columns = [c.lower() for c in msf.columns]
                    if "date" in msf.columns and "yyyymm" not in msf.columns:
                        msf["yyyymm"] = pd.to_datetime(msf["date"]).dt.year * 100 + pd.to_datetime(msf["date"]).dt.month
                    for c in ("permno", "yyyymm"):
                        if c in msf.columns:
                            msf[c] = msf[c].astype(int)

                    signal_df = compute_signal(msf)

                    overrides = {}
                    if ov_nq != 10: overrides["breakpoint_quantiles"] = ov_nq
                    if ov_bp != "(spec)": overrides["breakpoint_source"] = ov_bp
                    if ov_wt != "(spec)": overrides["weighting_rule"] = ov_wt
                    if ov_hp != 12: overrides["holding_period_months"] = ov_hp
                    if ov_ll != "(spec)": overrides["long_leg"] = ov_ll

                    engine = BacktestEngine(data_path=str(PROJECT_ROOT / "data"))
                    engine._load_data = lambda config: msf
                    result = engine.run(signal=signal_df, spec=spec, config_overrides=overrides or None)
                    st.session_state["bt_result"] = result
                    st.session_state["bt_signal"] = signal_df
                    st.success("Done!")
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

    with tab_dual:
        st.subheader("Dual-Track Comparison")
        st.info("**Disabled** — `DualTrackController._run_track()` is not yet implemented. "
                "Run same plugin under `original_method` vs `standardized_hxz` configs.")
        st.markdown(
            "Once implemented, this tab will:\n"
            "- Run the same plugin with paper-stated config vs HXZ-standard config\n"
            "- Show side-by-side metrics comparison\n"
            "- Overlay cumulative return charts"
        )

    with tab_ablation:
        st.subheader("Ablation Experiments")
        st.info("Select implementation switches to vary one at a time.")
        st.markdown(
            "Available switches:\n"
            "- `breakpoint_source`: nyse ↔ full_sample\n"
            "- `weighting_rule`: vw ↔ ew\n"
            "- `accounting_lag`: 4m ↔ 6m\n"
            "- `universe`: with/without financials"
        )
        st.caption("Run ablations from the Single Run tab by changing config overrides, "
                    "then compare results in the Attribution page.")


# ############################################################
# PAGE 6: Attribution
# ############################################################
elif page == "Attribution":
    st.header("Attribution — Implementation Gap Decomposition")
    st.markdown("Compare runs to decompose the replication gap by implementation choice.")

    # Load evidence
    evidence_factors = []
    if EVIDENCE_DIR.exists():
        evidence_factors = sorted([d.name for d in EVIDENCE_DIR.iterdir() if d.is_dir()])

    if not evidence_factors:
        st.info("No evidence runs found. Run backtests first (they will be saved to `evidence/`).")
        st.markdown(
            "### How Attribution Works\n\n"
            "1. Run the same factor with different configs (original vs standardized vs ablations)\n"
            "2. Each run is saved to the Evidence Store\n"
            "3. Attribution decomposes the gap:\n\n"
            "```\n"
            "Gap = Σ contribution(switch_i) + residual\n"
            "```\n\n"
            "**Anomaly triggers:**\n"
            "- t-stat sign flip between tracks\n"
            "- |gap| / |original_tstat| > 50%"
        )
    else:
        factor_sel = st.selectbox("Factor", evidence_factors, key="attr_factor")
        if factor_sel and st.button("Run Attribution", key="attr_run"):
            try:
                from src.steps.attribution import AttributionLayer
                from src.infra.evidence import EvidenceStore
                store = EvidenceStore(base_path=str(EVIDENCE_DIR))
                # Load runs for this factor
                factor_dir = EVIDENCE_DIR / factor_sel
                runs = []
                for run_dir in sorted(factor_dir.iterdir()):
                    meta_path = run_dir / "metadata.json"
                    if meta_path.exists():
                        runs.append(json.loads(meta_path.read_text()))

                if len(runs) < 2:
                    st.warning("Need at least 2 runs for attribution. Run ablations first.")
                else:
                    attr = AttributionLayer()
                    result = attr.attribute_ablation(runs)
                    st.session_state["attr_result"] = result
            except Exception as e:
                st.error(str(e))

        attr_result = st.session_state.get("attr_result")
        if attr_result:
            ac1, ac2, ac3 = st.columns(3)
            ac1.metric("Original t-stat", f"{attr_result.original_tstat:.2f}")
            ac2.metric("Standardized t-stat", f"{attr_result.standardized_tstat:.2f}")
            ac3.metric("Explained", f"{attr_result.explained_fraction:.0%}")

            if attr_result.contributions:
                st.subheader("Contribution Breakdown")
                contrib_df = pd.DataFrame([
                    {"Switch": k, "Contribution": v}
                    for k, v in attr_result.contributions.items()
                ])
                st.bar_chart(contrib_df.set_index("Switch"))

            # Anomaly check
            if attr_result.original_tstat * attr_result.standardized_tstat < 0:
                st.error("⚠️ **Anomaly: t-stat sign flip** — consider re-review.")
            elif abs(attr_result.total_gap) / max(abs(attr_result.original_tstat), 0.01) > 0.5:
                st.warning("⚠️ **Large gap (>50%)** — consider re-review.")
            else:
                st.success("No anomalies detected.")


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
