"""Download academic papers referenced in SignalDoc.csv.

Strategy:
1. Search CrossRef by author + year + journal + title keywords to get DOI
2. Validate DOI result matches expected paper (author, year, journal check)
3. Query Unpaywall with DOI to find open-access PDF (free, email only)
4. If Unpaywall fails, try Semantic Scholar (needs S2_API_KEY)
5. After download, verify PDF contains expected author name
6. Papers that cannot be downloaded are logged to data/papers/missing.txt

Usage:
    python scripts/download_papers.py [--signal-doc PATH] [--output-dir PATH] [--limit N] [--email EMAIL]
    python scripts/download_papers.py --revalidate  # check existing PDFs
"""

import argparse
import csv
import os
import re
import time
import urllib.request
import urllib.parse
import json
from pathlib import Path


# CrossRef API - free, no key needed, polite pool with email
CROSSREF_API = "https://api.crossref.org/works"

# Unpaywall API - free, just needs email
UNPAYWALL_API = "https://api.unpaywall.org/v2"

# Semantic Scholar API - needs S2_API_KEY env var
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"

RATE_LIMIT_DELAY = 1.5  # seconds between requests


def _get_email() -> str:
    """Get email for API polite pool. Must be a real email (not example.com)."""
    email = os.environ.get("CROSSREF_EMAIL", "")
    if not email:
        raise RuntimeError(
            "Please provide a real email via --email or CROSSREF_EMAIL env var.\n"
            "Unpaywall API rejects example.com addresses."
        )
    return email


def load_signal_doc(path: Path) -> list[dict]:
    """Load SignalDoc.csv and extract paper info."""
    papers = []
    seen = set()

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            authors = row.get("Authors", "").strip()
            year = row.get("Year", "").strip()
            acronym = row.get("Acronym", "").strip()
            long_desc = row.get("LongDescription", "").strip()
            journal = row.get("Journal", "").strip()

            if not authors or not year:
                continue

            # Deduplicate by (authors, year) since multiple factors can come from same paper
            key = (authors, year)
            if key in seen:
                continue
            seen.add(key)

            papers.append({
                "acronym": acronym,
                "authors": authors,
                "year": year,
                "description": long_desc,
                "journal": journal,
            })

    return papers


def _extract_author_last_names(authors: str) -> list[str]:
    """Extract last names from author string like 'Fama and French' or 'Titman, Wei and Xie'."""
    # Remove "and", split by comma/space
    cleaned = authors.replace(" and ", ", ").replace(" & ", ", ")
    parts = [p.strip() for p in cleaned.split(",") if p.strip()]
    last_names = []
    for part in parts:
        words = part.split()
        if words:
            last_names.append(words[-1])
    return last_names


def _validate_crossref_item(item: dict, authors: str, year: str, journal: str = "") -> float:
    """Score how well a CrossRef result matches our expected paper.

    Returns confidence score 0.0-1.0.
    """
    score = 0.0
    expected_names = _extract_author_last_names(authors)

    # Check author match
    item_authors = item.get("author", [])
    if item_authors and expected_names:
        matched_authors = 0
        for exp_name in expected_names:
            for ia in item_authors:
                if exp_name.lower() in ia.get("family", "").lower():
                    matched_authors += 1
                    break
        score += 0.4 * (matched_authors / len(expected_names))

    # Check year match
    pub_date = item.get("published-print") or item.get("published-online") or item.get("created")
    if pub_date:
        date_parts = pub_date.get("date-parts", [[]])
        if date_parts and date_parts[0]:
            item_year = str(date_parts[0][0])
            if item_year == year.split(".")[0]:
                score += 0.3

    # Check journal match
    if journal:
        container = " ".join(item.get("container-title", [])).lower()
        # Normalize common abbreviations
        journal_lower = journal.lower()
        if journal_lower in container or container in journal_lower:
            score += 0.2
        elif any(w in container for w in journal_lower.split() if len(w) > 3):
            score += 0.1

    # Check title contains relevant keywords
    item_title = " ".join(item.get("title", [])).lower()
    if item_title and len(item_title) > 5:
        score += 0.1  # Has a real title

    return score


def search_crossref(authors: str, year: str, description: str = "", journal: str = "") -> str | None:
    """Search CrossRef for a paper DOI by author + year + journal.

    Uses multiple search strategies and validates results.
    Returns DOI string or None.
    """
    author_names = _extract_author_last_names(authors)
    first_author = author_names[0] if author_names else ""
    email = _get_email()

    # Build query: all author last names + year context
    query_parts = author_names.copy()
    if journal:
        # Add key journal words (helps disambiguate)
        journal_words = [w for w in journal.split() if len(w) > 3 and w.lower() not in ("the", "and", "for")]
        query_parts.extend(journal_words[:2])

    query = urllib.parse.quote(" ".join(query_parts))

    # Try with year filter first
    url = (
        f"{CROSSREF_API}?query.author={urllib.parse.quote(first_author)}"
        f"&query.bibliographic={query}"
        f"&filter=from-pub-date:{year},until-pub-date:{year}"
        f"&rows=10&mailto={email}"
    )

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", f"FactorReplicationAgent/0.5 (mailto:{email})")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("message", {}).get("items", [])

            # Score and rank all results
            scored = []
            for item in items:
                conf = _validate_crossref_item(item, authors, year, journal)
                scored.append((conf, item))

            scored.sort(key=lambda x: x[0], reverse=True)

            # Only accept if confidence is reasonable
            if scored and scored[0][0] >= 0.5:
                return scored[0][1].get("DOI")

    except Exception as e:
        print(f"  [WARN] CrossRef error: {e}")

    # Retry without year filter (some papers have different pub dates)
    try:
        url2 = (
            f"{CROSSREF_API}?query.author={urllib.parse.quote(first_author)}"
            f"&query.bibliographic={query}"
            f"&rows=10&mailto={email}"
        )
        req = urllib.request.Request(url2)
        req.add_header("User-Agent", f"FactorReplicationAgent/0.5 (mailto:{email})")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("message", {}).get("items", [])

            scored = []
            for item in items:
                conf = _validate_crossref_item(item, authors, year, journal)
                scored.append((conf, item))

            scored.sort(key=lambda x: x[0], reverse=True)

            if scored and scored[0][0] >= 0.5:
                return scored[0][1].get("DOI")

    except Exception as e:
        print(f"  [WARN] CrossRef retry error: {e}")

    return None


def get_open_access_pdf(doi: str) -> str | None:
    """Query Unpaywall for an open-access PDF URL given a DOI."""
    email = _get_email()
    # DOI must be URL-encoded in the path
    encoded_doi = urllib.parse.quote(doi, safe="")
    url = f"{UNPAYWALL_API}/{encoded_doi}?email={email}"

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", f"FactorReplicationAgent/0.3 (mailto:{email})")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            if not data.get("is_oa"):
                return None
            # Try best_oa_location first
            best = data.get("best_oa_location")
            if best:
                if best.get("url_for_pdf"):
                    return best["url_for_pdf"]
                # Some repos (SSRN) only have landing page
                if best.get("url"):
                    return best["url"]
            # Try any oa_location with pdf
            for loc in data.get("oa_locations", []):
                if loc.get("url_for_pdf"):
                    return loc["url_for_pdf"]
            # Last resort: any url
            for loc in data.get("oa_locations", []):
                if loc.get("url"):
                    return loc["url"]
    except urllib.error.HTTPError as e:
        if e.code != 404:  # 404 = not in Unpaywall, that's normal
            print(f"  [WARN] Unpaywall error for DOI {doi}: {e}")
    except Exception as e:
        print(f"  [WARN] Unpaywall error: {e}")

    return None


def search_s2_for_pdf(authors: str, year: str, journal: str = "") -> str | None:
    """Search Semantic Scholar for open-access PDF (fallback).

    Requires S2_API_KEY env var. Rate limit: 1 req/sec.
    """
    api_key = os.environ.get("S2_API_KEY")
    if not api_key:
        return None

    author_names = _extract_author_last_names(authors)
    first_author = author_names[0] if author_names else ""
    query = urllib.parse.quote(f"{first_author} {year}")
    url = f"{S2_API}?query={query}&year={year}&fields=openAccessPdf,authors,title&limit=5"

    try:
        req = urllib.request.Request(url)
        req.add_header("x-api-key", api_key)
        req.add_header("User-Agent", "FactorReplicationAgent/0.5")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            for paper in data.get("data", []):
                # Validate author match
                paper_authors = [a.get("name", "") for a in paper.get("authors", [])]
                paper_authors_lower = " ".join(paper_authors).lower()
                if first_author.lower() in paper_authors_lower:
                    oa = paper.get("openAccessPdf")
                    if oa and oa.get("url"):
                        return oa["url"]
    except Exception as e:
        print(f"  [WARN] S2 error: {e}")

    return None


def validate_pdf_content(pdf_path: Path, authors: str) -> bool:
    """Validate that a downloaded PDF contains the expected author name.

    Uses simple byte-level search — no pymupdf needed.
    Returns True if at least one author last name is found in PDF text.
    """
    if not pdf_path.exists():
        return False

    try:
        content = pdf_path.read_bytes()

        # Check it's a real PDF
        if not content[:5].startswith(b"%PDF"):
            return False

        # Check file isn't too small (likely corrupt)
        if len(content) < 10000:
            return False

        # Search for author names in raw bytes (works for text-based PDFs)
        author_names = _extract_author_last_names(authors)
        content_str = content.decode("latin-1", errors="ignore").lower()

        for name in author_names:
            if name.lower() in content_str:
                return True

        return False
    except Exception:
        return False


def download_pdf(url: str, output_path: Path) -> bool:
    """Download a PDF from URL. Returns True if successful."""
    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "FactorReplicationAgent/0.3 (research)")
        with urllib.request.urlopen(req, timeout=30) as resp:
            content = resp.read()
            # Check if it's actually a PDF
            if content[:5].startswith(b"%PDF"):
                output_path.write_bytes(content)
                return True
            # If it's HTML (landing page), save the URL for manual download
            output_path.with_suffix(".url").write_text(url)
            print(f"  [INFO] Got landing page, saved URL to {output_path.with_suffix('.url')}")
            return False
    except Exception as e:
        print(f"  [WARN] Download failed: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Download C&Z reference papers")
    parser.add_argument(
        "--signal-doc",
        type=Path,
        default=Path("data/osap/SignalDoc.csv"),
        help="Path to SignalDoc.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/papers"),
        help="Output directory for PDFs",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max number of papers to attempt (for testing)",
    )
    parser.add_argument(
        "--email",
        type=str,
        default=None,
        help="Email for CrossRef/Unpaywall polite pool (or set CROSSREF_EMAIL env var)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if file already exists",
    )
    parser.add_argument(
        "--revalidate",
        action="store_true",
        help="Check existing PDFs contain expected author names (no download)",
    )
    args = parser.parse_args()

    if args.email:
        os.environ["CROSSREF_EMAIL"] = args.email

    if not args.signal_doc.exists():
        print(f"ERROR: SignalDoc.csv not found at {args.signal_doc}")
        print("Run scripts/download_osap.py first to get SignalDoc.csv")
        return

    args.output_dir.mkdir(parents=True, exist_ok=True)
    missing_log = args.output_dir / "missing.txt"

    papers = load_signal_doc(args.signal_doc)
    print(f"Found {len(papers)} unique papers in SignalDoc.csv")

    if args.limit:
        papers = papers[: args.limit]
        print(f"Limiting to first {args.limit} papers")

    # --- Revalidation mode ---
    if args.revalidate:
        print("\n--- Revalidating existing PDFs ---")
        valid = 0
        invalid = 0
        missing = 0
        invalid_files = []

        for paper in papers:
            first_author_last = _extract_author_last_names(paper["authors"])[0] if paper["authors"] else "Unknown"
            filename = f"{first_author_last}_{paper['year']}.pdf"
            pdf_path = args.output_dir / filename

            if not pdf_path.exists():
                missing += 1
                continue

            if validate_pdf_content(pdf_path, paper["authors"]):
                valid += 1
            else:
                invalid += 1
                invalid_files.append(f"{filename}\t{paper['authors']}\t{paper['year']}")
                print(f"  ✗ INVALID: {filename} (expected: {paper['authors']})")

        print(f"\n--- Revalidation Summary ---")
        print(f"Valid: {valid}")
        print(f"Invalid/Wrong: {invalid}")
        print(f"Missing: {missing}")

        if invalid_files:
            invalid_log = args.output_dir / "invalid_pdfs.txt"
            with open(invalid_log, "w", encoding="utf-8") as f:
                f.write("# PDFs that don't contain expected author names\n")
                f.write("# These may be wrong papers - consider re-downloading with --force\n\n")
                f.write("\n".join(invalid_files))
            print(f"Invalid PDFs logged to: {invalid_log}")
        return

    # --- Normal download mode ---
    downloaded = 0
    failed = 0
    skipped = 0
    missing_entries = []

    for i, paper in enumerate(papers, 1):
        # Filename: AuthorLastName_Year.pdf
        author_names = _extract_author_last_names(paper["authors"])
        first_author_last = author_names[0] if author_names else "Unknown"
        filename = f"{first_author_last}_{paper['year']}.pdf"
        output_path = args.output_dir / filename

        if output_path.exists() and not args.force:
            skipped += 1
            continue

        print(f"[{i}/{len(papers)}] {paper['authors']} ({paper['year']}) ...")

        # Step 1: Find DOI via CrossRef (with journal for disambiguation)
        doi = search_crossref(paper["authors"], paper["year"], paper["description"], paper["journal"])
        time.sleep(RATE_LIMIT_DELAY)

        pdf_url = None
        if doi:
            print(f"  DOI: {doi}")
            # Step 2: Find open-access PDF via Unpaywall
            pdf_url = get_open_access_pdf(doi)
            time.sleep(RATE_LIMIT_DELAY)

        # Step 3: Fallback to Semantic Scholar if Unpaywall failed
        if not pdf_url:
            pdf_url = search_s2_for_pdf(paper["authors"], paper["year"], paper["journal"])
            time.sleep(RATE_LIMIT_DELAY)

        if pdf_url:
            print(f"  Found PDF: {pdf_url[:80]}...")
            if download_pdf(pdf_url, output_path):
                # Step 4: Validate downloaded PDF
                if validate_pdf_content(output_path, paper["authors"]):
                    downloaded += 1
                    print(f"  ✓ Saved and validated: {output_path}")
                else:
                    print(f"  ⚠ Saved but UNVERIFIED (author name not found in PDF text): {output_path}")
                    downloaded += 1  # Still count it — may be image-scanned PDF
            else:
                failed += 1
                missing_entries.append(
                    f"{paper['acronym']}\t{paper['authors']}\t{paper['year']}\t{doi or 'no-doi'}\t{paper['description']}"
                )
                print(f"  ✗ Download failed")
        else:
            failed += 1
            missing_entries.append(
                f"{paper['acronym']}\t{paper['authors']}\t{paper['year']}\t{doi or 'no-doi'}\t{paper['description']}"
            )
            reason = "No open-access PDF" if doi else "DOI not found"
            print(f"  ✗ {reason}")

    # Write missing papers log
    if missing_entries:
        with open(missing_log, "w", encoding="utf-8") as f:
            f.write("# Papers not automatically downloaded\n")
            f.write("# Format: Acronym\tAuthors\tYear\tDOI\tDescription\n\n")
            f.write("\n".join(missing_entries))

    # Write a clickable DOI list for manual download
    doi_list_path = args.output_dir / "download_links.txt"
    with open(doi_list_path, "w", encoding="utf-8") as f:
        f.write("# Open these links in browser (with library proxy) to download PDFs\n")
        f.write("# Save as: AuthorLastName_Year.pdf into this folder\n\n")
        for entry in missing_entries:
            parts = entry.split("\t")
            if len(parts) >= 4 and parts[3] != "no-doi":
                entry_doi = parts[3]
                entry_authors = parts[1]
                entry_year = parts[2]
                first_last = _extract_author_last_names(entry_authors)
                name = first_last[0] if first_last else "Unknown"
                f.write(f"# {name}_{entry_year}.pdf\n")
                f.write(f"https://doi.org/{entry_doi}\n\n")

    print(f"\n--- Summary ---")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped (already exist): {skipped}")
    print(f"Failed/No open-access: {failed}")
    if missing_entries:
        print(f"Missing papers logged to: {missing_log}")


if __name__ == "__main__":
    main()
