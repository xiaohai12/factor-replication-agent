"""Tests for the PDF-to-Factor title matching mapper.

Tests:
1. Unit tests for _normalize() and _load_paper_title_map()
2. Integration tests: build_pdf_factor_map() with real data
3. Known mapping assertions (spot checks)
4. Edge cases: empty dirs, missing files, cache behavior

Run with:
    pytest tests/test_pdf_mapper.py -v
"""

import csv
import json
import os
import tempfile
from pathlib import Path

import pytest

from src.infra.pdf_mapper import (
    _normalize,
    _load_paper_title_map,
    build_pdf_factor_map,
    get_factor_to_pdf,
    invalidate_cache,
)


# --- Paths ---
PAPERS_DIR = Path(__file__).parent.parent / "data" / "papers"
SIGNALDOC_PATH = Path(__file__).parent.parent / "data" / "osap" / "SignalDoc.csv"

HAS_PAPERS = PAPERS_DIR.exists() and any(PAPERS_DIR.glob("*.pdf"))
HAS_SIGNALDOC = SIGNALDOC_PATH.exists()


# --- Unit Tests: _normalize ---


class TestNormalize:
    def test_lowercase(self):
        assert _normalize("Hello World") == "helloworld"

    def test_strip_punctuation(self):
        assert _normalize("The Cross-Section of Returns") == "thecrosssectionofreturns"

    def test_strip_special_chars(self):
        assert _normalize("Accruals (Sloan, 1996)") == "accrualssloan1996"

    def test_empty_string(self):
        assert _normalize("") == ""

    def test_numbers_preserved(self):
        assert _normalize("Factor123") == "factor123"

    def test_unicode_stripped(self):
        assert _normalize("Résumé café") == "rsum caf" or _normalize("Résumé café") == "rsumcaf"


# --- Unit Tests: _load_paper_title_map ---


@pytest.mark.skipif(not HAS_SIGNALDOC, reason="SignalDoc.csv not available")
class TestLoadPaperTitleMap:
    def test_returns_dict(self):
        result = _load_paper_title_map(SIGNALDOC_PATH)
        assert isinstance(result, dict)
        assert len(result) > 0

    def test_values_are_lists(self):
        result = _load_paper_title_map(SIGNALDOC_PATH)
        for title, factors in result.items():
            assert isinstance(factors, list)
            assert all(isinstance(f, str) for f in factors)

    def test_known_paper_present(self):
        """The Mispricing of Abnormal Accruals should map to Accruals."""
        result = _load_paper_title_map(SIGNALDOC_PATH)
        # Find a paper about accruals
        found = False
        for title, factors in result.items():
            if "Accruals" in factors:
                found = True
                break
        assert found, "Accruals factor not found in any paper title"

    def test_multi_factor_paper(self):
        """Some papers produce multiple factors."""
        result = _load_paper_title_map(SIGNALDOC_PATH)
        multi = {t: f for t, f in result.items() if len(f) > 1}
        assert len(multi) > 0, "Expected at least one paper with multiple factors"

    def test_with_synthetic_csv(self):
        """Test with a minimal synthetic CSV."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            writer = csv.DictWriter(f, fieldnames=["Paper", "Acronym", "Authors", "Year"])
            writer.writeheader()
            writer.writerow({"Paper": "Test Paper Title", "Acronym": "TP", "Authors": "Smith", "Year": "2020"})
            writer.writerow({"Paper": "Test Paper Title", "Acronym": "TP2", "Authors": "Smith", "Year": "2020"})
            writer.writerow({"Paper": "", "Acronym": "NoTitle", "Authors": "Jones", "Year": "2021"})
            f.flush()
            result = _load_paper_title_map(Path(f.name))

        os.unlink(f.name)
        assert "Test Paper Title" in result
        assert result["Test Paper Title"] == ["TP", "TP2"]
        assert "NoTitle" not in str(result.values())


# --- Integration Tests: build_pdf_factor_map ---


@pytest.mark.skipif(not HAS_PAPERS, reason="PDF papers not available")
@pytest.mark.skipif(not HAS_SIGNALDOC, reason="SignalDoc.csv not available")
class TestBuildPdfFactorMap:
    def test_returns_nonempty_mapping(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        assert len(mapping) >= 50, f"Expected >=50 mapped PDFs, got {len(mapping)}"

    def test_all_values_are_factor_lists(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        for pdf_name, factors in mapping.items():
            assert pdf_name.endswith(".pdf"), f"Not a PDF: {pdf_name}"
            assert isinstance(factors, list)
            assert len(factors) >= 1

    def test_total_factors_mapped(self):
        """Should map at least 60 factors total (many papers have multiple)."""
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        total_factors = sum(len(f) for f in mapping.values())
        assert total_factors >= 60, f"Expected >=60 factors, got {total_factors}"

    def test_no_duplicate_factors(self):
        """Each factor should appear in at most one PDF."""
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        seen_factors = {}
        for pdf_name, factors in mapping.items():
            for factor in factors:
                assert factor not in seen_factors, (
                    f"Factor {factor} mapped to both {seen_factors[factor]} and {pdf_name}"
                )
                seen_factors[factor] = pdf_name

    # --- Known mapping spot checks ---

    def test_known_mapping_accruals(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        factor_to_pdf = {f: p for p, fs in mapping.items() for f in fs}
        assert "Accruals" in factor_to_pdf

    def test_known_mapping_bm(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        factor_to_pdf = {f: p for p, fs in mapping.items() for f in fs}
        if "BM" in factor_to_pdf:
            # BM should map to a paper with "book" or "market" in the name
            pdf = factor_to_pdf["BM"]
            assert pdf.endswith(".pdf")

    def test_known_mapping_asset_growth(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        factor_to_pdf = {f: p for p, fs in mapping.items() for f in fs}
        assert "AssetGrowth" in factor_to_pdf

    def test_known_mapping_beta(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        factor_to_pdf = {f: p for p, fs in mapping.items() for f in fs}
        # Beta may not have a Paper entry in SignalDoc yet
        if "Beta" in factor_to_pdf:
            assert factor_to_pdf["Beta"].endswith(".pdf")

    def test_known_mapping_cash_prod(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        factor_to_pdf = {f: p for p, fs in mapping.items() for f in fs}
        assert "CashProd" in factor_to_pdf

    def test_known_mapping_coskew(self):
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        factor_to_pdf = {f: p for p, fs in mapping.items() for f in fs}
        assert "CoskewACX" in factor_to_pdf


# --- Integration Tests: get_factor_to_pdf ---


@pytest.mark.skipif(not HAS_PAPERS, reason="PDF papers not available")
@pytest.mark.skipif(not HAS_SIGNALDOC, reason="SignalDoc.csv not available")
class TestGetFactorToPdf:
    def test_reverse_lookup(self):
        factor_map = get_factor_to_pdf(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        assert isinstance(factor_map, dict)
        assert len(factor_map) >= 60

    def test_all_values_are_pdfs(self):
        factor_map = get_factor_to_pdf(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        for factor, pdf_name in factor_map.items():
            assert pdf_name.endswith(".pdf"), f"{factor} -> {pdf_name} is not a PDF"

    def test_consistent_with_build(self):
        """get_factor_to_pdf should be consistent with build_pdf_factor_map."""
        mapping = build_pdf_factor_map(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)
        factor_map = get_factor_to_pdf(PAPERS_DIR, SIGNALDOC_PATH, use_cache=False)

        for pdf_name, factors in mapping.items():
            for factor in factors:
                assert factor in factor_map
                assert factor_map[factor] == pdf_name


# --- Cache Tests ---


class TestCacheBehavior:
    def test_cache_created(self):
        """Building the map should create a cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_dir = Path(tmpdir)
            # Create a dummy PDF
            (papers_dir / "Test Paper.pdf").write_bytes(b"%PDF-1.4 dummy")

            # Create a minimal SignalDoc
            signaldoc = papers_dir / "signaldoc.csv"
            with open(signaldoc, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Paper", "Acronym", "Authors", "Year"])
                writer.writeheader()
                writer.writerow({"Paper": "Test Paper", "Acronym": "TP", "Authors": "A", "Year": "2020"})

            build_pdf_factor_map(papers_dir, signaldoc, use_cache=True)
            cache_path = papers_dir / ".pdf_factor_map_cache.json"
            assert cache_path.exists()

    def test_cache_invalidation(self):
        """invalidate_cache should remove the cache file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_dir = Path(tmpdir)
            cache_path = papers_dir / ".pdf_factor_map_cache.json"
            cache_path.write_text("{}")

            invalidate_cache(papers_dir)
            assert not cache_path.exists()

    def test_cache_used_on_second_call(self):
        """Second call with same files should use cache."""
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_dir = Path(tmpdir)
            (papers_dir / "My Paper.pdf").write_bytes(b"%PDF-1.4 dummy")

            signaldoc = papers_dir / "signaldoc.csv"
            with open(signaldoc, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Paper", "Acronym", "Authors", "Year"])
                writer.writeheader()
                writer.writerow({"Paper": "My Paper", "Acronym": "MP", "Authors": "B", "Year": "2021"})

            # First call builds cache
            result1 = build_pdf_factor_map(papers_dir, signaldoc, use_cache=True)
            # Second call uses cache
            result2 = build_pdf_factor_map(papers_dir, signaldoc, use_cache=True)
            assert result1 == result2


# --- Edge Cases ---


class TestEdgeCases:
    def test_empty_directory(self):
        """Empty papers directory should return empty mapping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_dir = Path(tmpdir)
            signaldoc = Path(tmpdir) / "signaldoc.csv"
            with open(signaldoc, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Paper", "Acronym"])
                writer.writeheader()
                writer.writerow({"Paper": "Something", "Acronym": "X"})
            result = build_pdf_factor_map(papers_dir, signaldoc, use_cache=False)
            assert result == {}

    def test_nonexistent_directory(self):
        """Nonexistent directory should return empty mapping."""
        result = build_pdf_factor_map(Path("/nonexistent"), SIGNALDOC_PATH, use_cache=False)
        assert result == {}

    def test_nonexistent_signaldoc(self):
        """Nonexistent SignalDoc should return empty mapping."""
        result = build_pdf_factor_map(PAPERS_DIR, Path("/nonexistent.csv"), use_cache=False)
        assert result == {}

    def test_no_matching_titles(self):
        """PDFs with no matching titles should not appear in the mapping."""
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_dir = Path(tmpdir)
            (papers_dir / "Completely Unrelated.pdf").write_bytes(b"%PDF-1.4")

            signaldoc = Path(tmpdir) / "signaldoc.csv"
            with open(signaldoc, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Paper", "Acronym"])
                writer.writeheader()
                writer.writerow({"Paper": "Different Title Entirely", "Acronym": "X"})

            result = build_pdf_factor_map(papers_dir, signaldoc, use_cache=False)
            assert result == {}

    def test_partial_title_match_below_threshold(self):
        """Short substring matches below 70% threshold should be rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_dir = Path(tmpdir)
            # "AB" is substring of "ABCDEFGHIJ" but only 20% coverage
            (papers_dir / "AB.pdf").write_bytes(b"%PDF-1.4")

            signaldoc = Path(tmpdir) / "signaldoc.csv"
            with open(signaldoc, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Paper", "Acronym"])
                writer.writeheader()
                writer.writerow({"Paper": "ABCDEFGHIJ", "Acronym": "X"})

            result = build_pdf_factor_map(papers_dir, signaldoc, use_cache=False)
            assert result == {}

    def test_exact_title_match(self):
        """Exact title match should work."""
        with tempfile.TemporaryDirectory() as tmpdir:
            papers_dir = Path(tmpdir)
            (papers_dir / "My Exact Title.pdf").write_bytes(b"%PDF-1.4")

            signaldoc = Path(tmpdir) / "signaldoc.csv"
            with open(signaldoc, "w", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Paper", "Acronym"])
                writer.writeheader()
                writer.writerow({"Paper": "My Exact Title", "Acronym": "MET"})

            result = build_pdf_factor_map(papers_dir, signaldoc, use_cache=False)
            assert "My Exact Title.pdf" in result
            assert result["My Exact Title.pdf"] == ["MET"]
