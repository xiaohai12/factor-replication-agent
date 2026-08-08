"""Tests for `DataDictionary.normalize_fields_with_llm` -- the LLM fallback
for `data.normalized_mapping` fields the deterministic exact/substring
matcher (`normalize_fields`) can't resolve. Every LLM pick must be
hard-validated against the real catalog (`catalog.DATA_CATALOG`) before being
accepted; an invalid/hallucinated pick is dropped, never trusted."""

from __future__ import annotations

import json

from src.infra.data_layer import DataDictionary


class FakeLLM:
    """Minimal OpenAI-shaped client returning one canned JSON response."""

    def __init__(self, payload: dict):
        self._payload = payload
        self.calls: list[dict] = []
        outer = self

        class _Completions:
            def create(self, messages, **kwargs):
                outer.calls.append({"messages": messages, "kwargs": kwargs})
                return type(
                    "R",
                    (),
                    {
                        "choices": [
                            type(
                                "C",
                                (),
                                {"message": type("M", (), {"content": json.dumps(outer._payload)})()},
                            )()
                        ]
                    },
                )()

        self.chat = type("Chat", (), {"completions": _Completions()})()


def test_no_llm_client_returns_deterministic_result_unchanged():
    dd = DataDictionary()
    fields = [{"field": "total_assets", "concept": "total assets"}]
    det_only = dd.normalize_fields(fields)
    with_llm = dd.normalize_fields_with_llm(fields, llm_client=None)
    assert with_llm == det_only
    assert with_llm["total_assets"]["column"] == "at"


def test_already_resolved_fields_never_reach_the_llm():
    dd = DataDictionary()
    fields = [{"field": "total_assets", "concept": "total assets"}]
    llm = FakeLLM({})
    result = dd.normalize_fields_with_llm(fields, llm_client=llm)
    assert result["total_assets"]["column"] == "at"
    assert llm.calls == []  # deterministic match alone resolved it -- no LLM call needed


def test_llm_fallback_accepts_a_valid_registered_pick():
    dd = DataDictionary()
    # A field the deterministic matcher can't resolve via exact/substring rules.
    fields = [{"field": "unrecognized_paper_term", "concept": "firm's total balance sheet size"}]
    llm = FakeLLM({"unrecognized_paper_term": {"source": "comp_funda", "column": "at"}})
    result = dd.normalize_fields_with_llm(fields, llm_client=llm)
    assert result["unrecognized_paper_term"] == {"source": "comp_funda", "column": "at"}
    assert len(llm.calls) == 1


def test_llm_fallback_rejects_a_hallucinated_source():
    dd = DataDictionary()
    fields = [{"field": "unrecognized_paper_term", "concept": "something obscure"}]
    llm = FakeLLM({"unrecognized_paper_term": {"source": "made_up_source", "column": "at"}})
    result = dd.normalize_fields_with_llm(fields, llm_client=llm)
    assert "unrecognized_paper_term" not in result


def test_llm_fallback_rejects_a_column_not_owned_by_the_named_source():
    dd = DataDictionary()
    fields = [{"field": "unrecognized_paper_term", "concept": "something obscure"}]
    # "meanest" is a real column, but not on comp_funda -- must still be rejected.
    llm = FakeLLM({"unrecognized_paper_term": {"source": "comp_funda", "column": "meanest"}})
    result = dd.normalize_fields_with_llm(fields, llm_client=llm)
    assert "unrecognized_paper_term" not in result


def test_llm_fallback_survives_a_malformed_llm_response():
    dd = DataDictionary()
    fields = [{"field": "unrecognized_paper_term", "concept": "something obscure"}]

    class BrokenLLM:
        class chat:
            class completions:
                @staticmethod
                def create(**kwargs):
                    raise RuntimeError("simulated LLM failure")

    result = dd.normalize_fields_with_llm(fields, llm_client=BrokenLLM())
    assert "unrecognized_paper_term" not in result


def test_llm_fallback_omits_fields_the_llm_could_not_match():
    dd = DataDictionary()
    fields = [
        {"field": "unrecognized_paper_term", "concept": "something obscure"},
        {"field": "another_unrecognized_term", "concept": "also obscure"},
    ]
    # LLM only confidently matches one of the two fields -- the other stays unresolved.
    llm = FakeLLM({"unrecognized_paper_term": {"source": "comp_funda", "column": "ceq"}})
    result = dd.normalize_fields_with_llm(fields, llm_client=llm)
    assert result["unrecognized_paper_term"] == {"source": "comp_funda", "column": "ceq"}
    assert "another_unrecognized_term" not in result
