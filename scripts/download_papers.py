"""Download academic papers referenced in SignalDoc.csv.

Strategy:
1. Search CrossRef by author + year to get DOI (free, no key)
2. Query Unpaywall with DOI to find open-access PDF (free, email only)
3. If Unpaywall fails, try Semantic Scholar (needs S2_API_KEY)
4. Download PDF

Papers that cannot be downloaded are logged to data/papers/missing.txt
for manual retrieval.

Usage:
    python scripts/download_papers.py [--signal-doc PATH] [--output-dir PATH] [--limit N] [--email EMAIL]
"""

import argparse
import csv
import os
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
            })

    return papers


def search_crossref(authors: str, year: str, description: str = "") -> str | None:
    """Search CrossRef for a paper DOI by author + year + description.

    Returns DOI string or None.
    """
    first_author = authors.split(",")[0].strip().split()[-1] if authors else ""
    email = _get_email()

    # Use description (factor name) as additional query context
    query_parts = [first_author]
    if description:
        # Add first few words of description for better matching
        query_parts.append(description.split(":")[0][:50])

    query = urllib.parse.quote(" ".join(query_parts))
    url = (
        f"{CROSSREF_API}?query={query}"
        f"&filter=from-pub-date:{year},until-pub-date:{year}"
        f"&rows=5&mailto={email}"
    )

    try:
        req = urllib.request.Request(url)
        req.add_header("User-Agent", f"FactorReplicationAgent/0.3 (mailto:{email})")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            items = data.get("message", {}).get("items", [])
            # Find best match: prefer items where first author matches
            for item in items:
                item_authors = item.get("author", [])
                if item_authors:
                    family = item_authors[0].get("family", "").lower()
                    if first_author.lower() in family or family in first_author.lower():
                        return item.get("DOI")
            # Fallback: return first result
            if items:
                return items[0].get("DOI")
    except Exception as e:
        print(f"  [WARN] CrossRef error: {e}")

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


def search_s2_for_pdf(authors: str, year: str) -> str | None:
    """Search Semantic Scholar for open-access PDF (fallback).

    Requires S2_API_KEY env var. Rate limit: 1 req/sec.
    """
    api_key = os.environ.get("S2_API_KEY")
    if not api_key:
        return None

    first_author = authors.split(",")[0].strip().split()[-1] if authors else ""
    query = urllib.parse.quote(f"{first_author} {year}")
    url = f"{S2_API}?query={query}&year={year}&fields=openAccessPdf&limit=3"

    try:
        req = urllib.request.Request(url)
        req.add_header("x-api-key", api_key)
        req.add_header("User-Agent", "FactorReplicationAgent/0.3")
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            for paper in data.get("data", []):
                oa = paper.get("openAccessPdf")
                if oa and oa.get("url"):
                    return oa["url"]
    except Exception as e:
        print(f"  [WARN] S2 error: {e}")

    return None


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

    downloaded = 0
    failed = 0
    skipped = 0
    missing_entries = []

    for i, paper in enumerate(papers, 1):
        # Filename: AuthorLastName_Year.pdf
        first_author_last = paper["authors"].split(",")[0].strip().split()[-1]
        filename = f"{first_author_last}_{paper['year']}.pdf"
        output_path = args.output_dir / filename

        if output_path.exists():
            skipped += 1
            continue

        print(f"[{i}/{len(papers)}] {paper['authors']} ({paper['year']}) ...")

        # Step 1: Find DOI via CrossRef
        doi = search_crossref(paper["authors"], paper["year"], paper["description"])
        time.sleep(RATE_LIMIT_DELAY)

        pdf_url = None
        if doi:
            # Step 2: Find open-access PDF via Unpaywall
            pdf_url = get_open_access_pdf(doi)
            time.sleep(RATE_LIMIT_DELAY)

        # Step 3: Fallback to Semantic Scholar if Unpaywall failed
        if not pdf_url:
            pdf_url = search_s2_for_pdf(paper["authors"], paper["year"])
            time.sleep(RATE_LIMIT_DELAY)

        if pdf_url:
            print(f"  Found PDF: {pdf_url[:80]}...")
            if download_pdf(pdf_url, output_path):
                downloaded += 1
                print(f"  ✓ Saved to {output_path}")
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
                doi = parts[3]
                authors = parts[1]
                year = parts[2]
                first_author_last = authors.split(",")[0].strip().split()[-1]
                f.write(f"# {first_author_last}_{year}.pdf\n")
                f.write(f"https://doi.org/{doi}\n\n")

    print(f"\n--- Summary ---")
    print(f"Downloaded: {downloaded}")
    print(f"Skipped (already exist): {skipped}")
    print(f"Failed/No open-access: {failed}")
    if missing_entries:
        print(f"Missing papers logged to: {missing_log}")


if __name__ == "__main__":
    main()
