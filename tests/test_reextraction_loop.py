"""Unit tests for the Review -> Extractor targeted re-extraction loop in
`Pipeline.run_full_pipeline` (step 2 feedback loop).

Exercised with fakes (no LLM, no data, no subprocess) so the tests are pure
control flow: when the reviewer returns remediation_mode ==
TARGETED_REEXTRACTION with a paper-cited flagged field, the pipeline re-extracts
with feedback and re-reviews; it escalates to a human when the budget is
exhausted, when there's no actionable citation, or on FULL_REGENERATION.
"""

from __future__ import annotations

from src.infra.models.method_spec import MethodSpec, SignalSpec, RemediationMode
from src.steps.step2_reviewer import ReviewResult, FieldReviewNote, Disposition
from src.infra.models.method_spec import EvidenceCitation
from src.pipeline import Pipeline, MAX_REEXTRACT


def _spec() -> MethodSpec:
    return MethodSpec(factor_id="t", factor_name="Test", signal=SignalSpec())


class FakeExtraction:
    def __init__(self, spec, error=None):
        self.spec = spec
        self.error = error


class FakeExtractor:
    """Returns a fresh spec each call; records only the re-extraction calls
    (those carrying reviewer feedback), separate from the initial extraction."""

    def __init__(self):
        self.calls = []  # feedback from re-extraction calls only

    def extract(self, factor_id, paper_text, reextract_feedback=None, **kw):
        if reextract_feedback is not None:
            self.calls.append(reextract_feedback)
        return FakeExtraction(_spec())


def _approved() -> ReviewResult:
    return ReviewResult(disposition="approved", approved=True, codegen_ready=True, paper_faithful=True)


def _targeted_with_citation() -> ReviewResult:
    r = ReviewResult(disposition="revision_required", approved=False)
    r.remediation_mode = RemediationMode.TARGETED_REEXTRACTION.value
    r.field_notes = [
        FieldReviewNote(
            field="signal.timing.accounting_lag",
            status=Disposition.NEEDS_LLM_REVIEW,
            reason="lag looks misread",
            current_value=3,
            evidence=[EvidenceCitation(quote="we use a six-month reporting lag")],
        )
    ]
    return r


def _targeted_no_citation() -> ReviewResult:
    r = ReviewResult(disposition="revision_required", approved=False)
    r.remediation_mode = RemediationMode.TARGETED_REEXTRACTION.value
    r.field_notes = [
        FieldReviewNote(
            field="signal.timing.accounting_lag",
            status=Disposition.NEEDS_LLM_REVIEW,
            reason="paper seems silent",
            current_value=3,
            evidence=[],  # no paper quote -> not re-extractable
        )
    ]
    return r


def _full_regen() -> ReviewResult:
    r = ReviewResult(disposition="revision_required", approved=False)
    r.remediation_mode = RemediationMode.FULL_REGENERATION.value
    return r


class FakeReviewGate:
    """Returns queued ReviewResults in order via review_with_llm."""

    def __init__(self, results):
        self.llm_client = object()  # so _review uses review_with_llm
        self._results = list(results)
        self.calls = 0

    def review_with_llm(self, spec, paper_text):
        self.calls += 1
        return self._results.pop(0), {}


def _pipeline_with(extractor, review_gate, tmp_path) -> Pipeline:
    p = Pipeline(data_path=str(tmp_path), evidence_path=str(tmp_path / "ev"), scripts_path=str(tmp_path / "sc"))
    p.extractor = extractor
    p.review_gate = review_gate
    return p


def test_targeted_reextraction_then_approved(tmp_path):
    extractor = FakeExtractor()
    # first review -> targeted re-extract; second review -> approved
    review = FakeReviewGate([_targeted_with_citation(), _approved()])
    p = _pipeline_with(extractor, review, tmp_path)

    # It will proceed past review to generate; stub generate to stop early by
    # raising so we only test the review loop.
    class _StopHere(Exception):
        pass

    def _boom(spec):
        raise _StopHere()

    p.meta_coder.generate_plugin = _boom

    try:
        p.run_full_pipeline("t", "snap", paper_text="paper")
    except _StopHere:
        pass

    # one re-extraction happened, with feedback carrying the paper quote
    assert len(extractor.calls) == 1
    feedback = extractor.calls[0]
    assert feedback and feedback[0]["field"] == "signal.timing.accounting_lag"
    assert "six-month" in feedback[0]["paper_evidence"][0]["quote"]
    assert review.calls == 2


def test_targeted_no_citation_escalates_to_human(tmp_path):
    extractor = FakeExtractor()
    review = FakeReviewGate([_targeted_no_citation()])
    p = _pipeline_with(extractor, review, tmp_path)

    runs, status = p.run_full_pipeline("t", "snap", paper_text="paper")

    assert runs == []
    assert status.needs_manual is True
    assert status.stage == "failed"
    assert extractor.calls == []  # never re-extracted (nothing actionable)


def test_targeted_budget_exhausts_to_human(tmp_path):
    extractor = FakeExtractor()
    # always targeted-with-citation -> loops until budget then human
    review = FakeReviewGate([_targeted_with_citation() for _ in range(MAX_REEXTRACT + 2)])
    p = _pipeline_with(extractor, review, tmp_path)

    runs, status = p.run_full_pipeline("t", "snap", paper_text="paper")

    assert runs == []
    assert status.needs_manual is True
    assert len(extractor.calls) == MAX_REEXTRACT  # bounded


def test_full_regeneration_escalates_without_reextract(tmp_path):
    extractor = FakeExtractor()
    review = FakeReviewGate([_full_regen()])
    p = _pipeline_with(extractor, review, tmp_path)

    runs, status = p.run_full_pipeline("t", "snap", paper_text="paper")

    assert runs == []
    assert status.needs_manual is True
    assert extractor.calls == []  # FULL_REGENERATION does not spend re-extract budget
