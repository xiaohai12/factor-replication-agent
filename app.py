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
st.title("Factor Replication Agent — Pipeline Viewer")

# --- Paths ---
PROJECT_ROOT = Path(__file__).parent
SIGNALDOC_PATH = PROJECT_ROOT / "data" / "osap" / "SignalDoc.csv"


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


# --- Main flow ---

# Step 1: Upload PDF
st.header("1. Upload Paper")

if not HAS_PYMUPDF:
    st.error("pymupdf not installed. Run: `pip install pymupdf`")
    st.stop()

uploaded_pdf = st.file_uploader("Upload paper PDF", type=["pdf"])

if uploaded_pdf:
    pdf_bytes = uploaded_pdf.read()
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    paper_text = "\n".join(page.get_text() for page in doc)
    page_count = doc.page_count
    doc.close()
    st.session_state["paper_text"] = paper_text
    st.session_state["pdf_name"] = uploaded_pdf.name
    st.success(f"Extracted **{len(paper_text):,}** chars from `{uploaded_pdf.name}` ({page_count} pages)")

if not st.session_state.get("paper_text"):
    st.info("Upload a paper PDF to get started.")
    st.stop()

paper_text = st.session_state["paper_text"]

# Step 2: Auto-match factor
st.header("2. Factor Identification")

matches = match_factor_from_text(paper_text, signaldoc)

if matches:
    # Show top matches
    match_options = [
        f"{acronym} — {row.get('LongDescription', '')} ({row.get('Authors', '')}, {row.get('Year', '')})"
        for acronym, _, row in matches[:5]
    ]
    selected_idx = st.radio(
        "Best matches from SignalDoc (select the correct one):",
        range(len(match_options)),
        format_func=lambda i: match_options[i],
        index=0,
    )
    matched_acronym = matches[selected_idx][0]
    matched_row = matches[selected_idx][2]
    st.session_state["matched_factor"] = matched_acronym
    st.session_state["matched_row"] = matched_row

    st.markdown(f"**Selected:** `{matched_acronym}` (score: {matches[selected_idx][1]:.1f})")
else:
    st.warning("No matching factor found in SignalDoc. Enter factor ID manually:")
    matched_acronym = st.text_input("Factor ID", value="")
    matched_row = signaldoc.get(matched_acronym, {})
    if matched_acronym:
        st.session_state["matched_factor"] = matched_acronym
        st.session_state["matched_row"] = matched_row

if not st.session_state.get("matched_factor"):
    st.stop()

matched_acronym = st.session_state["matched_factor"]
matched_row = st.session_state.get("matched_row", {})

# Step 3: Extract
st.header("3. Extraction")

col_extract, col_raw = st.columns([1, 1])

with col_extract:
    if st.button("Extract MethodSpec", type="primary"):
        with st.spinner("Extracting..."):
            from src.extractor import SemanticExtractor
            from src.llm import create_llm_client

            client = create_llm_client()
            extractor = SemanticExtractor(llm_client=client)
            result = extractor.extract(matched_acronym, paper_text)
            st.session_state["raw_llm_output"] = result.raw_llm_output
            st.session_state["extracted_spec"] = result.spec

with col_raw:
    if st.session_state.get("raw_llm_output"):
        st.subheader("Raw LLM Output")
        st.json(st.session_state["raw_llm_output"])

# Step 4: Results
if st.session_state.get("extracted_spec"):
    st.markdown("---")

    spec = st.session_state["extracted_spec"]

    # --- Metrics bar ---
    if matched_row:
        from src.extractor import SemanticExtractor

        extractor = SemanticExtractor(llm_client=None)
        gt = _parse_signaldoc_row(matched_row)

        if gt:
            metrics = extractor.evaluate_extraction(spec, gt)
            mcol1, mcol2, mcol3, mcol4 = st.columns(4)
            mcol1.metric("Field Coverage", f"{metrics.field_coverage:.0%}")
            mcol2.metric("Field Accuracy", f"{metrics.field_accuracy:.0%}")
            mcol3.metric("Core Accuracy", f"{metrics.core_field_accuracy:.0%}")
            mcol4.metric("Ambiguity Rate", f"{metrics.ambiguity_rate:.0%}")

    # --- Side-by-side: LLM Extraction vs Ground Truth ---
    st.header("LLM Extraction vs Ground Truth")

    col_llm, col_gt = st.columns(2)

    with col_llm:
        st.subheader("🤖 LLM Extraction")

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

    with col_gt:
        st.subheader("📊 SignalDoc Ground Truth")

        if matched_row:
            st.markdown(f"**Long Description:** {matched_row.get('LongDescription', '')}")
            st.markdown(f"**Authors:** {matched_row.get('Authors', '')} ({matched_row.get('Year', '')})")
            st.markdown(f"**Journal:** {matched_row.get('Journal', '')}")
            st.markdown(f"**Detailed Definition:** {matched_row.get('Detailed Definition', 'N/A')[:300]}")

            st.markdown("**Key Parameters:**")
            st.markdown(f"- Stock Weight: `{matched_row.get('Stock Weight', 'N/A')}`")
            st.markdown(f"- Start Month: `{matched_row.get('Start Month', 'N/A')}`")
            st.markdown(f"- Portfolio Period: `{matched_row.get('Portfolio Period', 'N/A')}`")
            st.markdown(f"- Sign: `{matched_row.get('Sign', 'N/A')}`")
            st.markdown(f"- LS Quantile: `{matched_row.get('LS Quantile', 'N/A')}`")
            st.markdown(f"- Filter: `{matched_row.get('Filter', 'N/A')}`")

            st.markdown("**Categories:**")
            st.markdown(f"- Economic: {matched_row.get('Cat.Economic', '')}")
            st.markdown(f"- Data: {matched_row.get('Cat.Data', '')}")
            st.markdown(f"- Form: {matched_row.get('Cat.Form', '')}")

            st.markdown("**Performance:**")
            st.markdown(f"- Predictability: {matched_row.get('Predictability in OP', 'N/A')}")
            st.markdown(f"- Rep Quality: {matched_row.get('Signal Rep Quality', 'N/A')}")
            st.markdown(f"- Return: {matched_row.get('Return', 'N/A')}")
            st.markdown(f"- T-Stat: {matched_row.get('T-Stat', 'N/A')}")
        else:
            st.warning("No SignalDoc entry found.")

    # --- Field-by-field comparison table ---
    if matched_row and gt:
        st.subheader("⚖️ Field-by-Field Comparison")
        comparison_data = []
        for key, expected in gt.items():
            actual = extractor._get_spec_field(spec, key)
            match = "✅" if extractor._values_match(actual, expected) else "❌"
            comparison_data.append({
                "Field": key,
                "LLM Extracted": str(actual),
                "Ground Truth": str(expected),
                "Match": match,
            })
        st.table(comparison_data)

    # --- Expandable sections ---
    with st.expander("Full MethodSpec JSON"):
        st.json(json.loads(spec.model_dump_json()))

    with st.expander("Raw LLM Output"):
        if st.session_state.get("raw_llm_output"):
            st.json(st.session_state["raw_llm_output"])

    with st.expander("📄 Extracted Paper Text (first 3000 chars)"):
        st.text(paper_text[:3000])
