"""PDF-to-Factor mapping via paper title matching.

Matches PDF filenames to SignalDoc factors using the Paper title column.

Usage:
    from src.infra.pdf_mapper import build_pdf_factor_map, get_factor_to_pdf

    pdf_map = build_pdf_factor_map(papers_dir, signaldoc_path)
    # Returns: {"The Cross-Section of Expected Stock Returns.pdf": ["AM", "BMdec", ...], ...}
"""

import csv
import json
import os
import re
from pathlib import Path


# Cache file to avoid re-scanning PDFs every time
_CACHE_FILENAME = ".pdf_factor_map_cache.json"


def _normalize(s: str) -> str:
    """Normalize a string for fuzzy comparison: lowercase, strip non-alphanumeric."""
    return re.sub(r'[^a-z0-9]', '', s.lower())


def _load_paper_title_map(signaldoc_path: Path) -> dict[str, list[str]]:
    """Load Paper title -> list of factor Acronyms from SignalDoc.csv.

    Groups multiple factors that come from the same paper.
    """
    title_factors: dict[str, list[str]] = {}

    with open(signaldoc_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            paper = row.get("Paper", "").strip()
            acronym = row.get("Acronym", "").strip()
            if not paper or not acronym:
                continue
            title_factors.setdefault(paper, []).append(acronym)

    return title_factors


def build_pdf_factor_map(
    papers_dir: Path,
    signaldoc_path: Path,
    use_cache: bool = True,
) -> dict[str, list[str]]:
    """Build mapping from PDF filename -> list of SignalDoc factor Acronyms.

    Primary method: match PDF filename to SignalDoc Paper title column.
    Uses normalized string comparison (case-insensitive, ignoring punctuation).

    Args:
        papers_dir: Directory containing PDF files
        signaldoc_path: Path to SignalDoc.csv
        use_cache: Whether to use/update the cache file

    Returns:
        Dict mapping PDF filename to list of factor acronyms.
    """
    if not papers_dir.exists() or not signaldoc_path.exists():
        return {}

    # List PDF files
    pdf_files = sorted([f for f in os.listdir(papers_dir) if f.lower().endswith(".pdf")])

    # Check cache
    cache_path = papers_dir / _CACHE_FILENAME
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            cached_files = set(cache.get("_pdf_files", []))
            if cached_files == set(pdf_files):
                mapping = {k: v for k, v in cache.items() if not k.startswith("_")}
                return mapping
        except (json.JSONDecodeError, KeyError):
            pass

    # Load paper titles from SignalDoc
    title_factors = _load_paper_title_map(signaldoc_path)

    # Build normalized title index for matching
    norm_index: dict[str, str] = {}  # normalized_title -> original_title
    for title in title_factors:
        norm_index[_normalize(title)] = title

    # Match each PDF to a paper title
    mapping: dict[str, list[str]] = {}
    claimed_titles: set[str] = set()

    for pdf_file in pdf_files:
        pdf_stem = pdf_file.rsplit('.pdf', 1)[0] if pdf_file.lower().endswith('.pdf') else pdf_file
        pdf_norm = _normalize(pdf_stem)

        best_match = None
        best_score = 0.0

        for norm_title, orig_title in norm_index.items():
            if orig_title in claimed_titles:
                continue

            # Check if one contains the other
            if norm_title in pdf_norm or pdf_norm in norm_title:
                # Score by coverage ratio: how much of the longer string is matched
                overlap = min(len(norm_title), len(pdf_norm))
                max_len = max(len(norm_title), len(pdf_norm))
                score = overlap / max_len if max_len > 0 else 0
                if score > best_score:
                    best_score = score
                    best_match = orig_title

        # Require at least 70% coverage to avoid false substring matches
        if best_match and best_score >= 0.7:
            claimed_titles.add(best_match)
            mapping[pdf_file] = title_factors[best_match]

    # Save cache
    if use_cache:
        cache_data = dict(mapping)
        cache_data["_pdf_files"] = pdf_files
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache_data, f, indent=2)
        except OSError:
            pass

    return mapping


def get_factor_to_pdf(
    papers_dir: Path,
    signaldoc_path: Path,
    use_cache: bool = True,
) -> dict[str, str]:
    """Reverse lookup: factor_id -> pdf_filename.

    Returns dict mapping each factor acronym to its PDF filename.
    """
    pdf_map = build_pdf_factor_map(papers_dir, signaldoc_path, use_cache)
    factor_to_pdf = {}
    for pdf_name, factors in pdf_map.items():
        for factor in factors:
            factor_to_pdf[factor] = pdf_name
    return factor_to_pdf


def invalidate_cache(papers_dir: Path) -> None:
    """Delete the cache file to force re-scanning."""
    cache_path = papers_dir / _CACHE_FILENAME
    if cache_path.exists():
        cache_path.unlink()
