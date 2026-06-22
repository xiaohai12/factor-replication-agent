"""Streamlit dashboard for visualizing pipeline step outputs.

Run: streamlit run app.py

Flow: Upload PDF → auto-match to SignalDoc factor → extract → compare with ground truth.
"""

import json
import csv
from pathlib import Path

import streamlit as st

try:
    import pymupdf

    HAS_PYMUPDF = True
except ImportError:
    HAS_PYMUPDF = False

st.set_page_config(page_title="Factor Replication Agent", layout="wide")

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent
SIGNALDOC_PATH = PROJECT_ROOT / "data" / "osap" / "SignalDoc.csv"
PAPERS_DIR = PROJECT_ROOT / "data" / "papers"


# --- Left sidebar navigation ---
st.sidebar.title("Pipeline Steps")
page = st.sidebar.radio(
    "Navigate",
    ["Extractor — Single Paper", "MetaCoder", "Extractor — Batch Evaluation", "Evaluation History"],
    index=0,
)
st.sidebar.markdown("---")
st.sidebar.markdown("**Status**")
st.sidebar.markdown("- Extractor ✅")
st.sidebar.markdown("- Review Gate ✅")
_plugin_count = len(list((PROJECT_ROOT / "data" / "plugins").glob("*.py"))) if (PROJECT_ROOT / "data" / "plugins").exists() else 0
st.sidebar.markdown(f"- MetaCoder {'✅' if _plugin_count else '🚧'} ({_plugin_count} plugins)")
st.sidebar.markdown("- Sandbox 🚧")
st.sidebar.markdown("- Backtest 🚧")

st.sidebar.markdown("---")
llm_provider = st.sidebar.selectbox(
    "LLM Provider",
    ["codex", "claude", "copilot", "openrouter"],
    index=0,
    help="codex = Codex CLI, claude = Claude Code CLI, copilot = Copilot CLI, openrouter = OpenRouter API",
)

# Model selection based on provider
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
    help="Model to use for extraction",
)

st.title("Factor Replication Agent")

# --- History storage ---
HISTORY_DIR = PROJECT_ROOT / "data" / "eval_history"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)
PAPER_TEXT_CACHE_DIR = PROJECT_ROOT / "data" / "paper_text_cache"
PAPER_TEXT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
CURATED_METHODSPEC_DIR = PROJECT_ROOT / "data" / "method_specs" / "curated"
CURATED_METHODSPEC_DIR.mkdir(parents=True, exist_ok=True)


def _save_checkpoint(checkpoint_path: Path, results: list, completed_pdfs: set) -> None:
    """Save batch evaluation progress to a checkpoint file for resumable runs."""
    from dataclasses import asdict
    serializable_results = []
    for r in results:
        d = {"factor_id": r.factor_id, "pdf_file": r.pdf_file, "error": r.error,
             "extraction_success": r.extraction_success, "score": r.score,
             "passed": r.passed, "field_details": r.field_details}
        if r.metrics:
            d["metrics"] = {"field_coverage": r.metrics.field_coverage,
                            "field_accuracy": r.metrics.field_accuracy,
                            "ambiguity_rate": r.metrics.ambiguity_rate,
                            "core_field_accuracy": r.metrics.core_field_accuracy}
        else:
            d["metrics"] = None
        serializable_results.append(d)
    data = {"completed_pdfs": sorted(completed_pdfs), "results": serializable_results}
    with open(checkpoint_path, "w") as f:
        json.dump(data, f, indent=2)


def _save_paper_text_cache(pdf_name: str, paper_text: str) -> Path:
    """Persist extracted paper text for auditability and later review reuse."""
    cache_path = PAPER_TEXT_CACHE_DIR / f"{Path(pdf_name).stem}.txt"
    cache_path.write_text(paper_text, encoding="utf-8")
    return cache_path


def _load_paper_text_from_cache() -> str | None:
    """Load paper text from the saved cache path, falling back to session memory."""
    cache_path = st.session_state.get("paper_text_path")
    if cache_path:
        path = Path(cache_path)
        if path.exists():
            text = path.read_text(encoding="utf-8")
            st.session_state["paper_text"] = text
            return text
    return st.session_state.get("paper_text")


def _extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    """Extract paper text from in-memory PDF bytes and close the document promptly."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    try:
        return "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()


def _resolve_review_inputs(provider: str) -> tuple[str | None, bytes | None]:
    """Resolve the best available review inputs from cache/session state.

    Priority:
    1. Saved paper-text cache path
    2. Session paper text
    3. Session PDF bytes, auto-extracting text for non-Claude providers
    """
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


# --- Load SignalDoc ---
@st.cache_data
def load_signaldoc():
    rows = {}
    if SIGNALDOC_PATH.exists():
        with open(SIGNALDOC_PATH, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows[row["Acronym"]] = row
    return rows


signaldoc = load_signaldoc()


# --- Factor matching from PDF text ---
def match_factor_from_text(text: str, signaldoc: dict) -> list[tuple[str, float, dict]]:
    """Match uploaded paper text to SignalDoc factors.

    Uses author last names + year + keywords from LongDescription.
    Returns list of (acronym, score, row) sorted by score descending.
    """
    text_lower = text[:10000].lower()  # Search in first 10k chars (title/abstract)
    matches = []

    for acronym, row in signaldoc.items():
        score = 0.0

        # Match authors (split by comma or space, check each last name)
        authors = row.get("Authors", "")
        if authors:
            for author in authors.replace(",", " ").split():
                author_clean = author.strip().lower()
                if len(author_clean) >= 3 and author_clean in text_lower:
                    score += 3.0

        # Match year
        year = row.get("Year", "")
        if year and year in text[:5000]:
            score += 1.0

        # Match long description keywords
        desc = row.get("LongDescription", "").lower()
        if desc:
            keywords = [w for w in desc.split() if len(w) >= 4]
            for kw in keywords:
                if kw in text_lower:
                    score += 0.5

        # Match acronym in text
        if f" {acronym.lower()} " in text_lower or f"({acronym})" in text_lower:
            score += 2.0

        if score > 0:
            matches.append((acronym, score, row))

    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:10]


# --- Helpers ---


def _parse_signaldoc_row(row: dict) -> dict:
    """Convert a SignalDoc.csv row into ground truth dict for evaluation."""
    gt = {}

    if row.get("Stock Weight"):
        gt["stock_weight"] = row["Stock Weight"].lower().strip()

    if row.get("Start Month"):
        try:
            gt["formation_month"] = str(int(float(row["Start Month"])))
        except (ValueError, TypeError):
            pass

    if row.get("Portfolio Period"):
        try:
            gt["holding_period"] = str(int(float(row["Portfolio Period"])))
        except (ValueError, TypeError):
            pass

    if row.get("Sign"):
        try:
            sign = int(float(row["Sign"]))
            gt["sign"] = str(sign)
            gt["long_leg"] = "high" if sign == 1 else "low"
            gt["short_leg"] = "low" if sign == 1 else "high"
        except (ValueError, TypeError):
            pass

    if row.get("LS Quantile"):
        try:
            gt["ls_quantile"] = str(float(row["LS Quantile"]))
        except (ValueError, TypeError):
            pass

    if row.get("Filter"):
        gt["filter"] = row["Filter"].strip()

    if row.get("Cat.Form"):
        gt["cat_form"] = row["Cat.Form"].strip().lower()

    return gt


def _save_review_artifacts(spec, review_result, raw_llm_review=None) -> None:
    """Save review report and reviewed MethodSpec to data/method_specs/reviewed/."""
    import dataclasses as _dc

    reviewed_dir = PROJECT_ROOT / "data" / "method_specs" / "reviewed"
    reviewed_dir.mkdir(parents=True, exist_ok=True)
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

    (reviewed_dir / f"{factor_id}.review_report.json").write_text(
        json.dumps(report_dict, indent=2, ensure_ascii=False) + "\n"
    )
    (reviewed_dir / f"{factor_id}.reviewed.methodspec.json").write_text(
        spec.model_dump_json(indent=2) + "\n"
    )


def _show_token_usage(usage: dict | None, label: str = "Token Usage") -> None:
    """Display token usage as a compact metric row."""
    if not usage:
        return
    estimated = usage.get("estimated", False)
    suffix = " (est.)" if estimated else ""
    with st.container():
        tc1, tc2, tc3 = st.columns(3)
        tc1.metric(f"Input tokens{suffix}", f"{usage.get('prompt_tokens', 0):,}")
        tc2.metric(f"Output tokens{suffix}", f"{usage.get('completion_tokens', 0):,}")
        tc3.metric(f"Total{suffix}", f"{usage.get('total_tokens', 0):,}")


# --- Main flow ---
if page == "Extractor — Single Paper":

    # Step 1: Upload PDF
    st.header("1. Upload Paper or Resume from Saved Artifacts")

    if not HAS_PYMUPDF:
        st.error("pymupdf not installed. Run: `pip install pymupdf`")
        st.stop()

    uploaded_pdf = st.file_uploader("Upload paper PDF", type=["pdf"])
    saved_specs = sorted(CURATED_METHODSPEC_DIR.glob("*.methodspec.json"))
    saved_texts = sorted(PAPER_TEXT_CACHE_DIR.glob("*.txt"))

    if uploaded_pdf:
        pdf_bytes = uploaded_pdf.read()
        doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
        page_count = doc.page_count
        doc.close()
        paper_text = _extract_text_from_pdf_bytes(pdf_bytes)
        paper_text_path = _save_paper_text_cache(uploaded_pdf.name, paper_text)
        st.session_state["paper_text"] = paper_text
        st.session_state["paper_text_path"] = str(paper_text_path)
        st.session_state["pdf_bytes"] = pdf_bytes
        st.session_state["pdf_name"] = uploaded_pdf.name
        st.success(f"Extracted **{len(paper_text):,}** chars from `{uploaded_pdf.name}` ({page_count} pages)")

    with st.expander("Import Existing MethodSpec", expanded=not bool(uploaded_pdf)):
        if saved_specs:
            spec_options = [""] + [path.name for path in saved_specs]
            selected_spec_name = st.selectbox(
                "Saved MethodSpec",
                spec_options,
                index=0,
                help="Load a previously extracted MethodSpec from data/method_specs/curated/.",
            )
        else:
            selected_spec_name = ""
            st.caption("No saved MethodSpecs found under `data/method_specs/curated/` yet.")

        text_options = [""] + [path.name for path in saved_texts]
        selected_text_name = st.selectbox(
            "Saved paper text cache (optional)",
            text_options,
            index=0,
            help="Choose the cached paper text if you want to run non-Claude LLM review without re-uploading the PDF.",
        )

        imported_spec_file = st.file_uploader(
            "Or upload a MethodSpec JSON",
            type=["json"],
            key="methodspec_import_uploader",
        )

        if st.button("Load Saved MethodSpec", key="load_saved_methodspec"):
            try:
                from src.models import MethodSpec

                if imported_spec_file is not None:
                    spec_payload = imported_spec_file.getvalue().decode("utf-8")
                    spec = MethodSpec.model_validate_json(spec_payload)
                    spec_path = imported_spec_file.name
                elif selected_spec_name:
                    selected_path = CURATED_METHODSPEC_DIR / selected_spec_name
                    spec = MethodSpec.model_validate_json(selected_path.read_text(encoding="utf-8"))
                    spec_path = str(selected_path)
                else:
                    st.warning("Choose a saved MethodSpec or upload one before loading.")
                    spec = None

                if spec is not None:
                    st.session_state["extracted_spec"] = spec
                    st.session_state["extracted_spec_path"] = spec_path
                    st.session_state["raw_llm_output"] = None
                    st.session_state["review_result"] = None
                    st.session_state["review_raw"] = None
                    st.session_state["resolution_inputs"] = {}

                    if selected_text_name:
                        text_path = PAPER_TEXT_CACHE_DIR / selected_text_name
                        st.session_state["paper_text_path"] = str(text_path)
                        st.session_state["paper_text"] = text_path.read_text(encoding="utf-8")

                    st.success("Loaded saved MethodSpec into the review workflow.")
            except Exception as e:
                st.error(f"Failed to load MethodSpec: {e}")

    paper_text = _load_paper_text_from_cache()
    if st.session_state.get("paper_text_path"):
        st.caption(f"Paper text cached: `{st.session_state['paper_text_path']}`")
    if not paper_text and not st.session_state.get("extracted_spec"):
        st.info("Upload a PDF to extract a new MethodSpec, or load a saved MethodSpec to continue review.")
        st.stop()
    if not paper_text and st.session_state.get("extracted_spec"):
        st.info("Loaded MethodSpec without paper text. Rules review will work; non-Claude LLM review needs a saved text cache or PDF upload.")

    # Step 2: Extract
    st.header("2. Extraction")

    # Use PDF filename stem as a temporary seed ID; LLM will set the real factor_id in the spec
    _pdf_stem = Path(st.session_state.get("pdf_name", "unknown")).stem

    col_extract, col_raw = st.columns([1, 1])

    with col_extract:
        if st.button("Extract MethodSpec", type="primary", disabled=not bool(paper_text)):
            with st.spinner("Extracting..."):
                from src.extractor import SemanticExtractor
                from src.llm import create_llm_client

                client = create_llm_client(provider=llm_provider, model=llm_model)

                # Wire up streaming preview for claude provider
                _stream_placeholder = st.empty()
                if hasattr(client, "stream_callback"):
                    def _on_token(text: str):
                        preview = text[:1500]
                        _stream_placeholder.markdown(
                            f"**Streaming output** ({len(text):,} chars so far)\n```\n{preview}\n```"
                        )
                    client.stream_callback = _on_token

                extractor = SemanticExtractor(llm_client=client)
                # Pass raw PDF bytes for CLI providers that support it (preserves formulas/tables)
                _pdf_bytes = st.session_state.get("pdf_bytes") if llm_provider in ("claude", "codex") else None
                result = extractor.extract(_pdf_stem, paper_text, pdf_bytes=_pdf_bytes)
                _stream_placeholder.empty()
                st.session_state["raw_llm_output"] = result.raw_llm_output
                st.session_state["extracted_spec"] = result.spec

                st.session_state["extraction_token_usage"] = result.token_usage
                if result.spec:
                    # Use the factor_id the LLM extracted, fall back to pdf stem
                    factor_id_for_file = result.spec.factor_id or _pdf_stem
                    st.session_state["matched_factor"] = factor_id_for_file
                    curated_dir = PROJECT_ROOT / "data" / "method_specs" / "curated"
                    curated_dir.mkdir(parents=True, exist_ok=True)
                    out_path = curated_dir / f"{factor_id_for_file}.methodspec.json"
                    out_path.write_text(
                        result.spec.model_dump_json(indent=2) + "\n"
                    )
                    st.session_state["extracted_spec_path"] = str(out_path)

    if st.session_state.get("extracted_spec_path"):
        st.caption(f"Saved: `{st.session_state['extracted_spec_path']}`")
    _show_token_usage(st.session_state.get("extraction_token_usage"))

    with col_raw:
        if st.session_state.get("raw_llm_output"):
            st.subheader("Raw LLM Output")
            st.json(st.session_state["raw_llm_output"])

    # Step 3: Results
    if st.session_state.get("extracted_spec"):
        st.markdown("---")
        st.header("3. Extraction Results")

        spec = st.session_state["extracted_spec"]

        st.markdown(f"**Factor:** {spec.factor_name}")
        st.markdown(f"**Paper:** {spec.paper_ref}")
        st.markdown(f"**Intuition:** {spec.economic_intuition}")
        st.markdown(f"**Formula:** `{spec.signal.formula}`")
        st.markdown(f"**Required fields:** {', '.join(spec.signal.required_fields)}")

        st.markdown("**Timing:**")
        timing = spec.signal.timing
        st.markdown(f"- Formation month: `{timing.formation_month}`")
        st.markdown(f"- Rebalance: `{timing.rebalance_frequency.value}`")
        st.markdown(f"- Holding period: `{timing.holding_period}` months")
        st.markdown(f"- Accounting lag: `{timing.accounting_lag}` months")
        st.markdown(f"- Skip month: `{timing.skip_month}`")

        st.markdown("**Portfolio:**")
        st.markdown(f"- Universe: {spec.portfolio.universe}")
        st.markdown(f"- Breakpoints: `{spec.portfolio.breakpoints.source.value}` {spec.portfolio.breakpoints.quantiles}")
        st.markdown(f"- Weighting: `{spec.portfolio.weighting.value}`")
        st.markdown(f"- Long leg: `{spec.portfolio.long_leg}`")
        st.markdown(f"- Short leg: `{spec.portfolio.short_leg}`")

        st.markdown("**Missing Policy:**")
        st.markdown(f"- Action: `{spec.signal.missing_policy.action.value}`")

        if spec.ambiguous_fields:
            st.markdown("**Ambiguous Fields:**")
            for af in spec.ambiguous_fields:
                st.warning(f"**{af.field}**: {af.reason}")

        # --- Expandable sections ---
        with st.expander("Full MethodSpec JSON"):
            st.json(json.loads(spec.model_dump_json()))

        with st.expander("Raw LLM Output"):
            if st.session_state.get("raw_llm_output"):
                st.json(st.session_state["raw_llm_output"])

        with st.expander("📄 Extracted Paper Text (first 3000 chars)"):
            if paper_text:
                st.text(paper_text[:3000])
            else:
                st.caption("No paper text is currently loaded.")

        # --- Step 4: Review Gate ---
        st.markdown("---")
        st.header("4. Review Gate")
        st.markdown("Validate the MethodSpec for completeness, empirical-impact classification, and codegen readiness.")

        col_review_rules, col_review_llm = st.columns(2)

        with col_review_rules:
            if st.button("Run Rules Review", key="run_rules_review"):
                from src.review_gate import ReviewGate
                gate = ReviewGate()
                review_result = gate.review(spec)
                st.session_state["review_result"] = review_result
                st.session_state["review_raw"] = None
                try:
                    _save_review_artifacts(spec, review_result, raw_llm_review=None)
                except Exception as save_error:
                    st.warning(f"Rules review completed, but saving review artifacts failed: {save_error}")

        with col_review_llm:
            if st.button("Run LLM Review", key="run_llm_review", type="primary"):
                from src.review_gate import ReviewGate
                from src.llm import create_llm_client
                with st.spinner("Running LLM review..."):
                    try:
                        review_paper_text, review_pdf_bytes = _resolve_review_inputs(llm_provider)
                        if not review_paper_text and not review_pdf_bytes:
                            raise RuntimeError(
                                "No paper source is loaded. Upload the PDF, keep the extractor session, or pick a cached paper text file before LLM review."
                            )
                        llm_client_review = create_llm_client(provider=llm_provider, model=llm_model)
                        _review_stream_ph = st.empty()
                        if hasattr(llm_client_review, "stream_callback"):
                            def _on_review_token(text: str):
                                preview = text[:1500]
                                _review_stream_ph.markdown(
                                    f"**Reviewing** ({len(text):,} chars so far)\n```\n{preview}\n```"
                                )
                            llm_client_review.stream_callback = _on_review_token
                        gate = ReviewGate(llm_client=llm_client_review)
                        review_result, raw_review = gate.review_with_llm(
                            spec,
                            review_paper_text or "",
                            pdf_bytes=review_pdf_bytes,
                        )
                        _review_stream_ph.empty()
                        st.session_state["review_result"] = review_result
                        st.session_state["review_raw"] = raw_review
                        try:
                            _save_review_artifacts(spec, review_result, raw_llm_review=raw_review)
                        except Exception as save_error:
                            st.warning(f"LLM review completed, but saving review artifacts failed: {save_error}")
                    except Exception as e:
                        st.error(f"LLM review failed: {e}")

        if st.session_state.get("review_result"):
            review = st.session_state["review_result"]
            _show_token_usage(
                (st.session_state.get("review_raw") or {}).get("_token_usage"),
            )

            # Disposition badge
            _disp_icons = {"approved": "✅", "revision_required": "⚠️", "blocked": "🚫", "pending": "🔄"}
            disp_icon = _disp_icons.get(review.disposition, "❓")
            st.subheader(f"Disposition: {disp_icon} {review.disposition.upper()}")

            rcol1, rcol2, rcol3, rcol4 = st.columns(4)
            rcol1.metric("Codegen Ready", "Yes" if review.codegen_ready else "No")
            rcol2.metric("Paper Faithful", "Yes" if review.paper_faithful else "No")
            rcol3.metric("Blocked Fields", len(review.blocked_fields))
            rcol4.metric("Issues", len(review.issues))

            if review.blocked_fields:
                st.error(f"**Blocked fields** (require human confirmation): {', '.join(review.blocked_fields)}")

            if review.issues:
                st.subheader("Issues")
                for issue in review.issues:
                    st.error(issue)

            if review.warnings:
                st.subheader("Warnings")
                for warning in review.warnings:
                    st.warning(warning)

            if review.field_notes:
                st.subheader("Field Notes")
                _status_icons = {
                    "auto_approve": "✅",
                    "auto_approve_with_flag": "🟡",
                    "approve_with_default": "🟢",
                    "needs_llm_review": "🔵",
                    "needs_human_confirmation": "🔴",
                }
                field_note_data = []
                for note in review.field_notes:
                    status_val = note.status.value if hasattr(note.status, "value") else str(note.status)
                    icon = _status_icons.get(status_val, "❓")
                    field_note_data.append({
                        "Field": note.field,
                        "Status": f"{icon} {status_val}",
                        "Impact": note.empirical_impact,
                        "Current Value": str(note.current_value),
                        "Reason": note.reason,
                    })
                st.table(field_note_data)

            raw_review = st.session_state.get("review_raw")
            if raw_review and raw_review.get("markdown_report"):
                with st.expander("📋 Full LLM Review Report"):
                    st.markdown(raw_review["markdown_report"])

            with st.expander("Raw Review JSON"):
                import dataclasses
                review_dict = dataclasses.asdict(review) if dataclasses.is_dataclass(review) else vars(review)
                # Convert non-serializable enums
                def _make_serializable(obj):
                    if isinstance(obj, dict):
                        return {k: _make_serializable(v) for k, v in obj.items()}
                    if isinstance(obj, list):
                        return [_make_serializable(i) for i in obj]
                    if hasattr(obj, "value"):
                        return obj.value
                    return obj
                st.json(_make_serializable(review_dict))

            # --- Step 5: Resolve ---
            st.markdown("---")
            st.header("5. Resolve")
            st.markdown("Apply resolutions for flagged fields, then generate `resolution.json` and `resolved.methodspec.json`.")

            from src.review_gate import SENSIBLE_DEFAULTS

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
                # Deduplicate preserving order
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

            human_fields = [n for n in review.field_notes if _status_val(n) == "needs_human_confirmation"]
            llm_fields   = [n for n in review.field_notes if _status_val(n) == "needs_llm_review"]
            default_fields = [n for n in review.field_notes if _status_val(n) == "approve_with_default"]
            action_fields = human_fields + llm_fields + default_fields

            if "resolution_inputs" not in st.session_state:
                st.session_state["resolution_inputs"] = {}

            if not action_fields and review.disposition == "approved":
                st.success("No fields require resolution — MethodSpec is already approved and codegen-ready.")

            else:
                if action_fields:
                    st.info(
                        f"**{len(human_fields)}** need human confirmation  ·  "
                        f"**{len(llm_fields)}** need LLM review  ·  "
                        f"**{len(default_fields)}** can use sensible defaults"
                    )

                # --- Human confirmation fields ---
                if human_fields:
                    st.subheader("Human Confirmation Required")
                    for note in human_fields:
                        fp = note.field
                        opts = _field_options(fp, note.current_value, note.candidate_value)
                        with st.expander(f"🔴 {fp}", expanded=True):
                            st.markdown(f"**Reason:** {note.reason}")
                            st.markdown(f"**Current value:** `{note.current_value}`")
                            if note.candidate_value:
                                st.markdown(f"**Candidate:** `{note.candidate_value}`")
                            for ev in (note.evidence or []):
                                quote = ev.quote if hasattr(ev, "quote") else ev.get("quote", "")
                                if quote:
                                    st.info(f"Paper evidence: {quote}")

                            labels = [lbl for lbl, _ in opts]
                            sel = st.selectbox("Resolution:", labels, key=f"hres_sel_{fp}")
                            val = dict(opts)[sel]
                            if val == "__custom__":
                                val = st.text_input("Custom value:", key=f"hres_custom_{fp}")

                            reason = st.text_area(
                                "Citation / reason:",
                                key=f"hres_reason_{fp}",
                                placeholder="Quote the paper section or table supporting this choice.",
                            )
                            st.session_state["resolution_inputs"][fp] = {
                                "value": val,
                                "reason": reason or "Human reviewer confirmed this empirical assumption.",
                                "decision_type": "human_empirical_assumption",
                            }

                # --- LLM-assisted fields ---
                if llm_fields:
                    st.subheader("LLM-Assisted Resolution")
                    for note in llm_fields:
                        fp = note.field
                        sugg_key = f"llm_sugg_{fp}"
                        with st.expander(f"🔵 {fp}", expanded=False):
                            st.markdown(f"**Reason:** {note.reason}")
                            st.markdown(f"**Current value:** `{note.current_value}`")
                            col_btn, col_res = st.columns([1, 2])
                            with col_btn:
                                if st.button("Resolve with LLM", key=f"llm_btn_{fp}"):
                                    with st.spinner(f"Asking LLM about {fp}…"):
                                        try:
                                            resolution_paper_text, _ = _resolve_review_inputs(llm_provider)
                                            if not resolution_paper_text:
                                                raise RuntimeError(
                                                    "No paper text is loaded. Upload the PDF, keep the extractor session, or pick a cached paper text file before LLM-assisted resolution."
                                                )
                                            from src.llm import create_llm_client
                                            _lc = create_llm_client(provider=llm_provider, model=llm_model)
                                            _prompt = (
                                                f"Resolve this ambiguous field in a MethodSpec extracted from a financial paper.\n\n"
                                                f"Field: {fp}\n"
                                                f"Current value: {note.current_value}\n"
                                                f"Why flagged: {note.reason}\n\n"
                                                f"Paper text (first 12 000 chars):\n{resolution_paper_text[:12000]}\n\n"
                                                f'Return JSON only: {{"resolved_value": <value>, "citation": "exact quote"}}'
                                            )
                                            _resp = _lc.chat.completions.create(
                                                messages=[{"role": "user", "content": _prompt}],
                                                temperature=0.0,
                                                response_format={"type": "json_object"},
                                            )
                                            from src.llm import extract_usage as _eu
                                            st.session_state[f"{sugg_key}_usage"] = _eu(_resp)
                                            st.session_state[sugg_key] = json.loads(_resp.choices[0].message.content)
                                        except Exception as e:
                                            st.error(f"LLM resolution failed: {e}")

                            sugg = st.session_state.get(sugg_key)
                            _show_token_usage(st.session_state.get(f"{sugg_key}_usage"))
                            if sugg:
                                with col_res:
                                    st.success(f"Suggested: `{sugg.get('resolved_value')}`")
                                    if sugg.get("citation"):
                                        st.caption(sugg["citation"])
                                if st.checkbox("Accept LLM suggestion", key=f"llm_accept_{fp}", value=True):
                                    st.session_state["resolution_inputs"][fp] = {
                                        "value": sugg.get("resolved_value"),
                                        "reason": sugg.get("citation", "LLM-resolved from paper text."),
                                        "decision_type": "llm_empirical_resolution",
                                    }
                            else:
                                manual = st.text_input("Or enter manually:", key=f"llm_manual_{fp}")
                                if manual:
                                    st.session_state["resolution_inputs"][fp] = {
                                        "value": manual,
                                        "reason": "Manual entry by reviewer.",
                                        "decision_type": "human_empirical_assumption",
                                    }

                # --- Sensible-default fields ---
                if default_fields:
                    st.subheader("Sensible Defaults")
                    for note in default_fields:
                        fp = note.field
                        default_val = SENSIBLE_DEFAULTS.get(fp, note.candidate_value)
                        col_d1, col_d2 = st.columns([3, 1])
                        with col_d1:
                            st.markdown(f"**🟢 {fp}** — default: `{default_val}`  \n_{note.reason}_")
                        with col_d2:
                            override = st.text_input("Override:", key=f"def_override_{fp}", placeholder=str(default_val))
                        final_val = override if override else default_val
                        st.session_state["resolution_inputs"][fp] = {
                            "value": final_val,
                            "reason": f"Sensible default (HXZ/CZ convention): {final_val}",
                            "decision_type": "sensible_default",
                        }

                # --- Apply button ---
                st.markdown("---")
                if st.button("Apply All Resolutions", type="primary", key="apply_resolutions"):
                    inputs = st.session_state.get("resolution_inputs", {})
                    if not inputs and not review.issues:
                        st.warning("No resolutions entered yet.")
                    else:
                        from datetime import datetime, timezone
                        from src.models.method_spec import MethodSpec as _MS
                        from src.review_gate import ReviewGate as _RG

                        spec_dict = json.loads(spec.model_dump_json())
                        decisions = []
                        for fp, inp in inputs.items():
                            decisions.append({
                                "field_path": fp,
                                "canonical_field_path": _PATH_ALIASES_RES.get(fp, fp),
                                "old_value": _res_get_path(spec_dict, fp),
                                "new_value": inp["value"],
                                "decision_type": inp["decision_type"],
                                "reason": inp["reason"],
                                "reviewer": "human",
                                "paper_evidence": [],
                            })

                        resolved_dict = json.loads(json.dumps(spec_dict))
                        for dec in decisions:
                            _res_set_path(resolved_dict, dec["field_path"], dec["new_value"])
                            for amb in resolved_dict.get("ambiguous_fields", []):
                                if isinstance(amb, dict) and amb.get("field") == dec["field_path"]:
                                    amb["source"] = "clear"
                                    amb["confidence"] = "high"
                                    amb["candidate_value"] = dec["new_value"]
                        resolved_dict.setdefault("resolution_log", []).extend(decisions)

                        try:
                            resolved_spec = _MS.model_validate(resolved_dict)
                            re_review = _RG().review(resolved_spec)

                            # Hard structural errors (missing formula, empty required_fields, etc.)
                            # block approval. Remaining ambiguous_field flags do not — the human
                            # clicking "Apply All Resolutions" is the explicit approval action.
                            has_hard_errors = bool(re_review.issues)
                            if not has_hard_errors:
                                resolved_dict["codegen_ready"] = True
                                resolved_dict["review_status"] = "approved"

                            # Re-validate with the updated approval flags
                            resolved_spec = _MS.model_validate(resolved_dict)
                            st.session_state["resolved_spec"] = resolved_spec
                            st.session_state["resolved_dict"] = resolved_dict
                            st.session_state["resolution_decisions"] = decisions

                            factor_id = spec.factor_id
                            res_dir = PROJECT_ROOT / "data" / "method_specs" / "resolutions"
                            resolved_dir_path = PROJECT_ROOT / "data" / "method_specs" / "resolved"
                            res_dir.mkdir(parents=True, exist_ok=True)
                            resolved_dir_path.mkdir(parents=True, exist_ok=True)

                            resolution_payload = {
                                "factor_id": factor_id,
                                "reviewer": "human",
                                "created_at": datetime.now(timezone.utc).isoformat(),
                                "decisions": decisions,
                            }
                            (res_dir / f"{factor_id}.resolution.json").write_text(
                                json.dumps(resolution_payload, indent=2, ensure_ascii=False) + "\n"
                            )
                            (resolved_dir_path / f"{factor_id}.resolved.methodspec.json").write_text(
                                json.dumps(resolved_dict, indent=2, ensure_ascii=False) + "\n"
                            )

                            if not has_hard_errors:
                                st.success(
                                    f"Resolved! MethodSpec is now **codegen-ready**. "
                                    f"Written to `data/method_specs/`."
                                )
                            else:
                                st.error(
                                    f"Applied {len(decisions)} resolutions but {len(re_review.issues)} "
                                    f"hard error(s) remain: {'; '.join(re_review.issues)}"
                                )

                        except Exception as e:
                            st.error(f"Validation failed after applying resolutions: {e}")

            # Show resolved spec after applying
            if st.session_state.get("resolved_spec"):
                st.markdown("---")
                resolved_spec = st.session_state["resolved_spec"]
                with st.expander("Resolved MethodSpec JSON", expanded=False):
                    st.json(json.loads(resolved_spec.model_dump_json()))
                with st.expander("Resolution Log"):
                    for dec in st.session_state.get("resolution_decisions", []):
                        st.markdown(
                            f"- **{dec['field_path']}**: `{dec['old_value']}` → `{dec['new_value']}`  "
                            f"_{dec['decision_type']}_"
                        )
                        if dec.get("reason"):
                            st.caption(dec["reason"])


# --- MetaCoder Page ---
elif page == "MetaCoder":
    st.header("MetaCoder — Generate Signal Plugin")
    st.markdown(
        "Load an approved (resolved) MethodSpec and generate a Python signal plugin. "
        "The plugin computes only the raw signal formula — no portfolio logic, no lag handling."
    )

    RESOLVED_DIR = PROJECT_ROOT / "data" / "method_specs" / "resolved"
    TEST_DIR     = PROJECT_ROOT / "data" / "method_specs" / "test"
    PLUGINS_DIR  = PROJECT_ROOT / "data" / "plugins"
    PLUGINS_DIR.mkdir(parents=True, exist_ok=True)

    # --- Load resolved MethodSpec ---
    st.subheader("1. Load Resolved MethodSpec")

    _spec_files: list[tuple[str, Path]] = []
    for _dir, _label in ((RESOLVED_DIR, "resolved"), (TEST_DIR, "test")):
        if _dir.exists():
            for _p in sorted(_dir.glob("*.resolved.methodspec.json")):
                _spec_files.append((f"[{_label}] {_p.name}", _p))
    spec_options = [""] + [label for label, _ in _spec_files]
    _spec_path_map = {label: path for label, path in _spec_files}

    col_sel, col_up = st.columns([2, 1])
    with col_sel:
        selected_resolved_name = st.selectbox(
            "Resolved MethodSpec",
            spec_options,
            index=0,
            help="Files from data/method_specs/resolved/ and test/",
        )
    with col_up:
        uploaded_resolved = st.file_uploader(
            "Or upload a resolved MethodSpec JSON",
            type=["json"],
            key="metacoder_resolved_uploader",
        )

    if st.button("Load MethodSpec", key="mc_load_spec"):
        try:
            from src.models import MethodSpec as _MS
            if uploaded_resolved is not None:
                spec_payload = uploaded_resolved.getvalue().decode("utf-8")
                _mc_spec = _MS.model_validate_json(spec_payload)
            elif selected_resolved_name:
                _mc_spec = _MS.model_validate_json(
                    _spec_path_map[selected_resolved_name].read_text(encoding="utf-8")
                )
            else:
                st.warning("Select a resolved MethodSpec or upload one.")
                _mc_spec = None
            if _mc_spec is not None:
                st.session_state["mc_spec"] = _mc_spec
                st.session_state.pop("mc_plugin", None)
                st.session_state.pop("mc_sandbox_report", None)
                st.session_state.pop("mc_hooks_needed", None)
                st.success(f"Loaded: **{_mc_spec.factor_id}**")
        except Exception as e:
            st.error(f"Failed to load MethodSpec: {e}")

    mc_spec = st.session_state.get("mc_spec")

    if mc_spec:
        st.markdown("---")
        st.subheader("2. Spec Summary")

        # Display key fields
        scol1, scol2, scol3 = st.columns(3)
        rs_val = getattr(mc_spec.review_status, "value", mc_spec.review_status)
        scol1.metric("Review Status", rs_val)
        scol2.metric("Codegen Ready", "Yes" if mc_spec.codegen_ready else "No")
        scol3.metric("Version", mc_spec.version)

        st.markdown(f"**Factor:** {mc_spec.factor_name}")
        formula = mc_spec.signal.formula
        formula_str = formula.expression if hasattr(formula, "expression") else str(formula)
        st.markdown(f"**Formula:** `{formula_str}`")
        st.markdown(f"**Required fields:** {', '.join(mc_spec.signal.required_fields or mc_spec.required_fields)}")

        norm_map = (mc_spec.data.normalized_mapping or {}) if mc_spec.data else {}
        if norm_map:
            st.markdown("**Column mapping** (paper field → parquet column):")
            st.dataframe(
                {"paper field": list(norm_map.keys()), "parquet column": list(norm_map.values())},
                use_container_width=False,
                hide_index=True,
            )
        else:
            st.warning("No `data.normalized_mapping` found — MetaCoder will not know physical column names.")

        with st.expander("Full MethodSpec JSON"):
            st.json(json.loads(mc_spec.model_dump_json()))

        # --- Hook detection ---
        st.markdown("---")
        st.subheader("3. Hook Detection")
        try:
            from src.engine import BacktestEngine
            _hooks_needed = BacktestEngine._detect_hooks(mc_spec)
            st.session_state["mc_hooks_needed"] = _hooks_needed
            if _hooks_needed:
                st.warning(f"**{len(_hooks_needed)} non-standard step(s) detected — LLM will generate hook functions:**")
                for _step, _reason in _hooks_needed.items():
                    st.markdown(f"- `{_step}_hook` — {_reason}")
            else:
                st.success("All backtest steps are **standard** — only `compute_signal()` will be generated.")
        except Exception as _e:
            st.error(f"Hook detection failed: {_e}")

        # --- Approval gate ---
        st.markdown("---")
        st.subheader("4. Approval Gate")

        if rs_val == "approved" and mc_spec.codegen_ready:
            st.success("MethodSpec is **approved** and codegen-ready.")
            approved_for_gen = True
        else:
            st.error(
                f"MethodSpec is not codegen-ready (review_status=`{rs_val}`, codegen_ready=`{mc_spec.codegen_ready}`). "
                "Return to the Extractor page, apply resolutions, and re-save."
            )
            approved_for_gen = False

        # --- Generate ---
        st.markdown("---")
        st.subheader("5. Generate Plugin")

        gen_col, _ = st.columns([1, 2])
        with gen_col:
            gen_disabled = not approved_for_gen
            if st.button("Generate Signal Plugin", type="primary", disabled=gen_disabled, key="mc_generate"):
                from src.llm import create_llm_client
                from src.meta_coder import MetaCoder
                from src.models.method_spec import ReviewStatus

                with st.spinner("Generating plugin code..."):
                    try:
                        # Temporarily patch spec to approved so MetaCoder guard passes
                        gen_spec = mc_spec.model_copy(
                            update={"codegen_ready": True, "review_status": ReviewStatus.APPROVED}
                        )
                        llm = create_llm_client(provider=llm_provider, model=llm_model)
                        _mc_stream_ph = st.empty()
                        if hasattr(llm, "stream_callback"):
                            def _on_mc_token(text: str):
                                preview = text[:800]
                                _mc_stream_ph.markdown(
                                    f"**Generating** ({len(text):,} chars so far)\n```python\n{preview}\n```"
                                )
                            llm.stream_callback = _on_mc_token

                        coder = MetaCoder(llm_client=llm)
                        plugin = coder.generate_plugin(gen_spec)
                        _mc_stream_ph.empty()
                        st.session_state["mc_plugin"] = plugin
                        token_usage = plugin.__dict__.get("_token_usage")
                        st.session_state["mc_token_usage"] = token_usage
                        st.session_state.pop("mc_sandbox_report", None)
                        st.success("Plugin generated!")
                    except Exception as e:
                        st.error(f"Generation failed: {e}")

        _show_token_usage(st.session_state.get("mc_token_usage"), label="Generation Token Usage")

        mc_plugin = st.session_state.get("mc_plugin")
        if mc_plugin:
            st.markdown("---")
            st.subheader("6. Generated Plugin Code")
            _pcol1, _pcol2, _pcol3 = st.columns(3)
            _pcol1.metric("Plugin ID", mc_plugin.plugin_id)
            _pcol2.metric("Code Hash", mc_plugin.code_hash)
            _pcol3.metric("Hooks", len(mc_plugin.hooks) if mc_plugin.hooks else 0)
            if mc_plugin.hooks:
                st.info("**Generated hook functions:** " + ", ".join(f"`{fn}`" for fn in mc_plugin.hooks.values()))
            st.code(mc_plugin.code, language="python")

            dl_col, repair_col, _ = st.columns([1, 1, 2])
            with dl_col:
                st.download_button(
                    "Download plugin.py",
                    data=mc_plugin.code,
                    file_name=f"{mc_plugin.factor_id}.py",
                    mime="text/plain",
                )
            with repair_col:
                if st.button("Save to data/plugins/", key="mc_save_plugin"):
                    plugin_path = PLUGINS_DIR / f"{mc_plugin.factor_id}.py"
                    plugin_path.write_text(mc_plugin.code, encoding="utf-8")
                    st.success(f"Saved: `{plugin_path.relative_to(PROJECT_ROOT)}`")

            # --- Sandbox Validation ---
            st.markdown("---")
            st.subheader("7. Sandbox Validation")

            if st.button("Run Sandbox Validation", key="mc_sandbox"):
                from src.sandbox import AdversarialSandbox
                sandbox = AdversarialSandbox()
                report = sandbox.validate(mc_plugin, mc_spec)
                st.session_state["mc_sandbox_report"] = report

            sandbox_report = st.session_state.get("mc_sandbox_report")
            if sandbox_report:
                passed = sandbox_report.passed
                if passed:
                    st.success("Sandbox validation **passed**.")
                else:
                    st.error("Sandbox validation **failed**.")

                vcol1, vcol2, vcol3, vcol4 = st.columns(4)
                vcol1.metric("Syntax OK", "✅" if sandbox_report.syntax_ok else "❌")
                vcol2.metric("Schema OK", "✅" if sandbox_report.schema_ok else "❌")
                vcol3.metric("No Future Leak", "✅" if sandbox_report.no_future_leak else "❌")
                vcol4.metric("Reproducible", "✅" if sandbox_report.reproducible else "❌")

                if sandbox_report.errors:
                    st.error("**Errors:**")
                    for err in sandbox_report.errors:
                        st.markdown(f"- {err}")

                if sandbox_report.warnings:
                    for w in sandbox_report.warnings:
                        st.warning(w)

                # Auto-repair loop (up to 2 attempts)
                if not passed and sandbox_report.errors:
                    st.markdown("---")
                    st.subheader("Repair")
                    repair_attempts = len(mc_plugin.repair_trace)
                    if repair_attempts < 3:
                        if st.button(f"Attempt Auto-Repair ({repair_attempts}/3 used)", key="mc_repair"):
                            from src.llm import create_llm_client
                            from src.meta_coder import MetaCoder
                            with st.spinner("Repairing..."):
                                try:
                                    llm = create_llm_client(provider=llm_provider, model=llm_model)
                                    coder = MetaCoder(llm_client=llm)
                                    repaired = coder.repair_plugin(mc_plugin, sandbox_report.errors)
                                    st.session_state["mc_plugin"] = repaired
                                    st.session_state.pop("mc_sandbox_report", None)
                                    st.success("Repaired — re-run sandbox validation to verify.")
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Repair failed: {e}")
                    else:
                        st.error("Max repair attempts (3) reached. Empirical issues must go back through Review Gate.")

    # --- Existing plugins ---
    existing_plugins = sorted(PLUGINS_DIR.glob("*.py"))
    if existing_plugins:
        st.markdown("---")
        st.subheader("Existing Plugins")
        for pp in existing_plugins:
            with st.expander(pp.name):
                st.code(pp.read_text(), language="python")


# --- Batch Evaluation Page ---
elif page == "Extractor — Batch Evaluation":
    st.header("Batch Evaluation")
    st.markdown("Run extraction evaluation across PDFs in `data/papers/` and compare with SignalDoc ground truth.")

    # Import evaluation utilities
    from src.evaluation.helpers import (
        PDF_FACTOR_MAP, FACTOR_TO_PDF, extract_pdf_text as _extract_pdf_text,
        parse_signaldoc_ground_truth as _parse_signaldoc_ground_truth,
        build_field_details as _build_field_details,
        compute_score as _compute_score, PASS_THRESHOLD,
        FactorEvalResult, EvalReport,
    )

    # Show available PDFs and their factor mappings
    available_pdfs = list(PDF_FACTOR_MAP.keys())

    if not available_pdfs:
        st.warning("No PDFs mapped in `PDF_FACTOR_MAP`. Add PDFs to `data/papers/` and update the mapping.")
        st.stop()

    with st.expander("📂 PDF → Factor Mapping", expanded=False):
        mapping_data = []
        for pdf_name, factors in PDF_FACTOR_MAP.items():
            mapping_data.append({
                "PDF": pdf_name,
                "Factors": ", ".join(factors),
                "Count": len(factors),
            })
        st.dataframe(mapping_data)

    st.subheader("Select Papers to Test")

    # Paper selection
    select_mode = st.radio(
        "Selection mode:",
        ["All PDFs", "First N PDFs", "Select specific PDFs"],
        horizontal=True,
    )

    if select_mode == "First N PDFs":
        n_pdfs = st.slider("Number of papers to run:", min_value=1, max_value=len(available_pdfs), value=min(30, len(available_pdfs)))
        selected_pdfs = available_pdfs[:n_pdfs]
    elif select_mode == "Select specific PDFs":
        selected_pdfs = st.multiselect(
            "Choose PDFs to evaluate:",
            available_pdfs,
            default=available_pdfs[:3] if len(available_pdfs) >= 3 else available_pdfs,
        )
    else:
        selected_pdfs = available_pdfs

    # Show what will be tested
    total_factors_selected = sum(len(PDF_FACTOR_MAP[p]) for p in selected_pdfs)
    st.info(f"**{len(selected_pdfs)}** PDFs selected → **{total_factors_selected}** factors to evaluate")

    # Run button
    run_batch = st.button("▶️ Run Evaluation", type="primary", disabled=len(selected_pdfs) == 0)

    # Checkpoint file for resumable runs
    CHECKPOINT_PATH = HISTORY_DIR / "_checkpoint.json"

    # Load existing checkpoint
    checkpoint: dict = {}
    if CHECKPOINT_PATH.exists():
        try:
            with open(CHECKPOINT_PATH, "r") as f:
                checkpoint = json.load(f)
        except (json.JSONDecodeError, OSError):
            checkpoint = {}

    completed_pdfs = set(checkpoint.get("completed_pdfs", []))
    if completed_pdfs:
        remaining = [p for p in selected_pdfs if p not in completed_pdfs]
        st.warning(
            f"**Checkpoint found**: {len(completed_pdfs)} PDFs already done, "
            f"{len(remaining)} remaining. Click Run to resume."
        )
        col_resume, col_reset = st.columns(2)
        with col_reset:
            if st.button("🗑️ Clear Checkpoint (start fresh)"):
                CHECKPOINT_PATH.unlink(missing_ok=True)
                st.rerun()

    if run_batch:
        from src.extractor import SemanticExtractor, RateLimitExhausted
        from src.llm import create_llm_client

        with st.spinner("Running extraction evaluation..."):
            client = create_llm_client(provider=llm_provider, model=llm_model)
            extractor = SemanticExtractor(llm_client=client)

            # Load previous results from checkpoint
            results = []
            for r in checkpoint.get("results", []):
                metrics = None
                if r.get("metrics"):
                    from src.extractor import ExtractionMetrics
                    metrics = ExtractionMetrics(**r["metrics"])
                results.append(FactorEvalResult(
                    factor_id=r["factor_id"], pdf_file=r["pdf_file"],
                    error=r.get("error"), extraction_success=r.get("extraction_success", False),
                    score=r.get("score", 0.0), passed=r.get("passed", False),
                    metrics=metrics, field_details=r.get("field_details"),
                ))

            progress_bar = st.progress(0)
            status_text = st.empty()
            done = len(results)
            rate_limited = False

            for pdf_name in selected_pdfs:
                if pdf_name in completed_pdfs:
                    continue

                pdf_path = PAPERS_DIR / pdf_name
                status_text.markdown(f"**{done}/{total_factors_selected}** done — processing `{pdf_name}` ...")

                if not pdf_path.exists():
                    for fid in PDF_FACTOR_MAP[pdf_name]:
                        results.append(FactorEvalResult(
                            factor_id=fid, pdf_file=pdf_name, error="PDF not found"
                        ))
                        done += 1
                        progress_bar.progress(done / total_factors_selected)
                    completed_pdfs.add(pdf_name)
                    continue

                try:
                    paper_text_batch = _extract_pdf_text(pdf_path)
                except Exception as e:
                    for fid in PDF_FACTOR_MAP[pdf_name]:
                        results.append(FactorEvalResult(
                            factor_id=fid, pdf_file=pdf_name, error=f"PDF read error: {e}"
                        ))
                        done += 1
                        progress_bar.progress(done / total_factors_selected)
                    completed_pdfs.add(pdf_name)
                    continue

                # Use batch extraction: one LLM call for all factors in same paper
                factor_ids = PDF_FACTOR_MAP[pdf_name]
                status_text.markdown(f"**{done}/{total_factors_selected}** done — extracting `{pdf_name}` → {len(factor_ids)} factors ...")

                try:
                    batch_results = extractor.extract_batch(factor_ids, paper_text_batch)
                except RateLimitExhausted as e:
                    status_text.error(f"⚠️ Rate limit hit after {done} factors. Progress saved — run again to resume.")
                    rate_limited = True
                    break
                except Exception as e:
                    for fid in factor_ids:
                        results.append(FactorEvalResult(
                            factor_id=fid, pdf_file=pdf_name, error=str(e)
                        ))
                        done += 1
                        progress_bar.progress(done / total_factors_selected)
                    completed_pdfs.add(pdf_name)
                    continue

                for factor_id in factor_ids:
                    eval_result = FactorEvalResult(factor_id=factor_id, pdf_file=pdf_name)
                    extraction = batch_results.get(factor_id)
                    try:
                        if extraction is None or extraction.spec is None:
                            eval_result.error = extraction.error if extraction else "Extraction returned None"
                        else:
                            eval_result.extraction_success = True
                            row = signaldoc.get(factor_id)
                            if row:
                                gt = _parse_signaldoc_ground_truth(row)
                                metrics = extractor.evaluate_extraction(extraction.spec, gt)
                                eval_result.metrics = metrics
                                eval_result.score = _compute_score(metrics)
                                eval_result.passed = eval_result.score >= PASS_THRESHOLD
                                eval_result.field_details = _build_field_details(extractor, extraction.spec, gt, extraction.reasons)
                            else:
                                eval_result.error = "Factor not in SignalDoc"
                    except Exception as e:
                        eval_result.error = str(e)

                    results.append(eval_result)
                    done += 1
                    progress_bar.progress(done / total_factors_selected)

                completed_pdfs.add(pdf_name)

                # Save checkpoint after each paper
                _save_checkpoint(CHECKPOINT_PATH, results, completed_pdfs)

            progress_bar.empty()

            if rate_limited:
                _save_checkpoint(CHECKPOINT_PATH, results, completed_pdfs)
                st.warning(f"Processed **{done}/{total_factors_selected}** factors before rate limit. "
                           f"Run again to continue from where you left off.")
            else:
                status_text.success(f"Done! Evaluated **{done}** factors.")
                # Clear checkpoint on completion
                CHECKPOINT_PATH.unlink(missing_ok=True)

            # Build report
            report = EvalReport(
                total_factors=len(results),
                successful_extractions=sum(1 for r in results if r.extraction_success),
                per_factor=results,
            )
            accuracies = [r.metrics.field_accuracy for r in results if r.metrics]
            core_accs = [r.metrics.core_field_accuracy for r in results if r.metrics]
            coverages = [r.metrics.field_coverage for r in results if r.metrics]
            if accuracies:
                report.avg_field_accuracy = sum(accuracies) / len(accuracies)
                report.avg_core_accuracy = sum(core_accs) / len(core_accs)
                report.avg_field_coverage = sum(coverages) / len(coverages)
            report.compute_aggregates()

            st.session_state["batch_report"] = report

            # Save to history
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            pdfs_label = selected_pdfs[0].replace(".pdf", "") if len(selected_pdfs) == 1 else f"{len(selected_pdfs)}pdfs"
            history_file = HISTORY_DIR / f"{timestamp}_{pdfs_label}.json"
            history_entry = {
                "timestamp": timestamp,
                "label": f"{pdfs_label} — {report.avg_score:.0f}/100 ({report.pass_rate:.0%} pass)",
                "report": report.to_json(),
            }
            with open(history_file, "w") as f:
                json.dump(history_entry, f, indent=2)

    # Display results
    if "batch_report" in st.session_state:
        report = st.session_state["batch_report"]

        # Aggregate metrics
        st.subheader("📊 Aggregate Metrics")
        mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
        mcol1.metric("Avg Score", f"{report.avg_score:.1f}/100")
        mcol2.metric("Pass Rate", f"{report.pass_rate:.0%}")
        mcol3.metric("Passed", f"{report.passed_count}/{report.total_factors}")
        mcol4.metric("Avg Field Accuracy", f"{report.avg_field_accuracy:.0%}")
        mcol5.metric("Avg Core Accuracy", f"{report.avg_core_accuracy:.0%}")

        # Per-field accuracy summary
        st.subheader("📋 Per-Field Accuracy")
        field_stats = {}  # field_name -> {total, matched}
        for r in report.per_factor:
            if r.field_details:
                for field_name, detail in r.field_details.items():
                    if field_name not in field_stats:
                        field_stats[field_name] = {"total": 0, "matched": 0}
                    field_stats[field_name]["total"] += 1
                    if detail["match"]:
                        field_stats[field_name]["matched"] += 1
        if field_stats:
            field_summary = []
            for fname, stats in sorted(field_stats.items(), key=lambda x: x[1]["matched"] / max(x[1]["total"], 1)):
                acc = stats["matched"] / stats["total"] if stats["total"] else 0
                field_summary.append({
                    "Field": fname,
                    "Accuracy": f"{acc:.0%}",
                    "Matched": f"{stats['matched']}/{stats['total']}",
                })
            st.table(field_summary)

        # Per-factor results
        st.subheader("📝 Per-Factor Results")
        for r in report.per_factor:
            status_icon = "✅" if r.passed else ("❌" if r.extraction_success else "⚠️")
            score_text = f"{r.score:.0f}/100" if r.extraction_success else "N/A"
            with st.expander(f"{status_icon} {r.factor_id} — Score: {score_text} ({r.pdf_file})"):
                if r.error:
                    st.error(f"Error: {r.error}")
                if r.field_details:
                    detail_data = []
                    for field_name, detail in r.field_details.items():
                        detail_data.append({
                            "Field": field_name,
                            "Extracted": str(detail["actual"]),
                            "Ground Truth": str(detail["expected"]),
                            "Reason": str(detail.get("reason", "")),
                            "Match": "✅" if detail["match"] else "❌",
                        })
                    st.table(detail_data)

        # Download report
        report_json = json.dumps(report.to_json(), indent=2)
        st.download_button(
            "📥 Download Full Report (JSON)",
            data=report_json,
            file_name="batch_eval_report.json",
            mime="application/json",
        )

# --- Evaluation History Page ---
elif page == "Evaluation History":
    st.header("📜 Evaluation History")
    st.markdown("Browse past evaluation runs. Reports are saved automatically after each batch evaluation.")

    # List history files
    history_files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)

    if not history_files:
        st.info("No evaluation history yet. Run a batch evaluation first.")
    else:
        # Show list of past runs
        history_labels = []
        for hf in history_files:
            try:
                with open(hf) as f:
                    entry = json.load(f)
                ts = entry.get("timestamp", hf.stem)
                label = entry.get("label", hf.stem)
                display = f"{ts[:4]}-{ts[4:6]}-{ts[6:8]} {ts[9:11]}:{ts[11:13]}:{ts[13:15]} — {label}"
                history_labels.append((display, hf))
            except Exception:
                history_labels.append((hf.stem, hf))

        selected_history = st.selectbox(
            "Select a past evaluation run:",
            range(len(history_labels)),
            format_func=lambda i: history_labels[i][0],
        )

        if selected_history is not None:
            hf_path = history_labels[selected_history][1]
            with open(hf_path) as f:
                history_data = json.load(f)

            report_data = history_data["report"]

            # Aggregate metrics
            st.subheader("📊 Aggregate Metrics")
            mcol1, mcol2, mcol3, mcol4, mcol5 = st.columns(5)
            mcol1.metric("Avg Score", f"{report_data.get('avg_score', 0):.1f}/100")
            mcol2.metric("Pass Rate", f"{report_data.get('pass_rate', 0):.0%}")
            mcol3.metric("Passed", f"{report_data.get('passed_count', 0)}/{report_data.get('total_factors', 0)}")
            mcol4.metric("Avg Field Accuracy", f"{report_data.get('avg_field_accuracy', 0):.0%}")
            mcol5.metric("Avg Core Accuracy", f"{report_data.get('avg_core_accuracy', 0):.0%}")

            # Per-field accuracy summary
            st.subheader("📋 Per-Field Accuracy")
            field_stats = {}
            for r in report_data.get("per_factor", []):
                if r.get("field_details"):
                    for field_name, detail in r["field_details"].items():
                        if field_name not in field_stats:
                            field_stats[field_name] = {"total": 0, "matched": 0}
                        field_stats[field_name]["total"] += 1
                        if detail.get("match"):
                            field_stats[field_name]["matched"] += 1
            if field_stats:
                field_summary = []
                for fname, stats in sorted(field_stats.items(), key=lambda x: x[1]["matched"] / max(x[1]["total"], 1)):
                    acc = stats["matched"] / stats["total"] if stats["total"] else 0
                    field_summary.append({
                        "Field": fname,
                        "Accuracy": f"{acc:.0%}",
                        "Matched": f"{stats['matched']}/{stats['total']}",
                    })
                st.table(field_summary)

            # Per-factor results
            st.subheader("📝 Per-Factor Results")
            for r in report_data.get("per_factor", []):
                passed = r.get("passed", False)
                success = r.get("extraction_success", False)
                status_icon = "✅" if passed else ("❌" if success else "⚠️")
                score = r.get("score", 0)
                score_text = f"{score:.0f}/100" if success else "N/A"
                with st.expander(f"{status_icon} {r['factor_id']} — Score: {score_text} ({r['pdf_file']})"):
                    if r.get("error"):
                        st.error(f"Error: {r['error']}")
                    if r.get("field_details"):
                        detail_data = []
                        for field_name, detail in r["field_details"].items():
                            detail_data.append({
                                "Field": field_name,
                                "Extracted": str(detail.get("actual", "")),
                                "Ground Truth": str(detail.get("expected", "")),
                                "Reason": str(detail.get("reason", "")),
                                "Match": "✅" if detail.get("match") else "❌",
                            })
                        st.table(detail_data)

            # Delete button
            col_dl, col_del = st.columns([1, 1])
            with col_dl:
                st.download_button(
                    "📥 Download Report (JSON)",
                    data=json.dumps(report_data, indent=2),
                    file_name=hf_path.name,
                    mime="application/json",
                )
            with col_del:
                if st.button("🗑️ Delete this report", type="secondary"):
                    hf_path.unlink()
                    st.rerun()
