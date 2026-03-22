#!/usr/bin/env python3
"""
preprocess.py — Śilālipi Index Builder
=======================================
Downloads Epigraphia Indica PDFs from the BJP e-Library and extracts
inscription articles into a search index (search_index.json).

Usage:
  pip install pdfplumber requests tqdm
  python preprocess.py

Options:
  --volumes 1,5,11   Only process specific volumes (comma-separated)
  --skip-download    Use already-downloaded PDFs in ./pdfs/
  --output path      Output path (default: search_index.json)
  --sample           Quick test: only first 30 pages of each volume

The output search_index.json is committed to your GitHub repo and
loaded by index.html at runtime for instant client-side search.
"""

import os
import re
import sys
import json
import time
import argparse
import hashlib
from pathlib import Path
from datetime import datetime

try:
    import pdfplumber
except ImportError:
    sys.exit("❌  Missing: pip install pdfplumber")

try:
    import requests
    from tqdm import tqdm
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False
    print("⚠️  requests/tqdm not found — skipping auto-download. Place PDFs in ./pdfs/ manually.")

# ─────────────────────────────────────────────
# VOLUME MANIFEST — all 41 sources
# ─────────────────────────────────────────────
BASE = "https://library.bjp.org/jspui/bitstream/123456789/1910/"

VOLUMES = [
    # id, label, url, era
    ("v01",  "EI Vol.1",            BASE+"30/epigraphia-indica-vol-01.pdf",          "1892"),
    ("v02",  "EI Vol.2",            BASE+"31/epigraphia-indica-vol-02.pdf",          "1894"),
    ("v03",  "EI Vol.3",            BASE+"32/epigraphia-indica-vol-03.pdf",          "1895"),
    ("v04",  "EI Vol.4",            BASE+"33/epigraphia-indica-vol-04.pdf",          "1897"),
    ("v05",  "EI Vol.5",            BASE+"34/epigraphia-indica-vol-05.pdf",          "1899"),
    ("v06",  "EI Vol.6",            BASE+"35/epigraphia-indica-vol-06.pdf",          "1901"),
    ("v07",  "EI Vol.7",            BASE+"36/epigraphia-indica-vol-07.pdf",          "1903"),
    ("v08",  "EI Vol.8",            BASE+"37/epigraphia-indica-vol-08-1905-1906.pdf","1905"),
    ("v09",  "EI Vol.9",            BASE+"38/epigraphia-indica-vol-09.pdf",          "1908"),
    ("v10",  "EI Vol.10",           BASE+"39/epigraphia-indica-vol-10.pdf",          "1909"),
    ("v11",  "EI Vol.11",           BASE+"1/epigraphia-indica-vol-11.pdf",           "1911"),
    ("v12",  "EI Vol.12",           BASE+"2/epigraphia-indica-vol-12.pdf",           "1913"),
    ("v13",  "EI Vol.13",           BASE+"3/epigraphia-indica-vol-13.pdf",           "1915"),
    ("v14",  "EI Vol.14",           BASE+"4/epigraphia-indica-vol-14.pdf",           "1917"),
    ("v15a", "EI Vol.15 (I)",       BASE+"5/epigraphia-indica-vol-15-vol-01.pdf",    "1919"),
    ("v15b", "EI Vol.15 (II)",      BASE+"6/epigraphia-indica-vol-15-vol-02.pdf",    "1920"),
    ("v16",  "EI Vol.16",           BASE+"7/epigraphia-indica-vol-16.pdf",           "1921"),
    ("v17",  "EI Vol.17",           BASE+"8/epigraphia-indica-vol-17.pdf",           "1923"),
    ("v18",  "EI Vol.18",           BASE+"9/epigraphia-indica-vol-18.pdf",           "1925"),
    ("v19",  "EI Vol.19",           BASE+"10/epigraphia-indica-vol-19.pdf",          "1927"),
    ("v20",  "EI Vol.20",           BASE+"11/epigraphia-indica-vol-20.pdf",          "1929"),
    ("v21",  "EI Vol.21",           BASE+"12/epigraphia-indica-vol-21.pdf",          "1931"),
    ("v22",  "EI Vol.22",           BASE+"13/epigraphia-indica-vol-22.pdf",          "1933"),
    ("v23",  "EI Vol.23",           BASE+"14/epigraphia-indica-vol-23.pdf",          "1935"),
    ("v24",  "EI Vol.24",           BASE+"15/epigraphia-indica-vol-24.pdf",          "1937"),
    ("v25",  "EI Vol.25",           BASE+"16/epigraphia-indica-vol-25.pdf",          "1939"),
    ("v26",  "EI Vol.26",           BASE+"17/epigraphia-indica-vol-26.pdf",          "1941"),
    ("v27",  "EI Vol.27",           BASE+"18/epigraphia-indica-vol-27.pdf",          "1947"),
    ("v28",  "EI Vol.28",           BASE+"19/epigraphia-indica-vol-28.pdf",          "1949"),
    ("v29",  "EI Vol.29",           BASE+"20/epigraphia-indica-vol-29.pdf",          "1951"),
    ("v30",  "EI Vol.30",           BASE+"21/epigraphia-indica-vol-30.pdf",          "1953"),
    ("v31",  "EI Vol.31",           BASE+"22/epigraphia-indica-vol-31.pdf",          "1955"),
    ("v32",  "EI Vol.32",           BASE+"23/epigraphia-indica-vol-32.pdf",          "1957"),
    ("v33",  "EI Vol.33",           BASE+"24/epigraphia-indica-vol-33.pdf",          "1959"),
    ("v34",  "EI Vol.34",           BASE+"25/epigraphia-indica-vol-34.pdf",          "1961"),
    ("v35",  "EI Vol.35",           BASE+"26/epigraphia-indica-vol-35.pdf",          "1963"),
    ("v36",  "EI Vol.36",           BASE+"27/epigraphia-indica-vol-36.pdf",          "1965"),
    ("app10","Appendix Vol.10",     BASE+"29/appendix-to-epigraphia-indica-vol-10.pdf","1909"),
    ("app23","Appendix Vol.19–23",  BASE+"28/appendix-to-epigraphia-indica-and-record-of-the-archeological-survey-of-india-vol-19-23.pdf","1930s"),
]

# ─────────────────────────────────────────────
# REGEX PATTERNS for parsing EI article structure
# ─────────────────────────────────────────────

# Article title patterns: EI articles are typically headed by an
# all-caps or title-case line followed by author ("By JOHN DOE.")
ARTICLE_TITLE_RE = re.compile(
    r'^([A-Z][A-Z\s\-\,\.\(\)\']{8,80})\s*$', re.MULTILINE
)
# Author line: "By A.S. Altekar." or "BY FLEET."
AUTHOR_RE = re.compile(r'\bBy\s+[A-Z][a-z]|BY\s+[A-Z]{2}', re.IGNORECASE)

# Date extraction patterns
DATE_PATTERNS = [
    re.compile(r'\bSaka\s+(\d{3,4})\b', re.IGNORECASE),          # Saka era
    re.compile(r'\bShaka\s+(\d{3,4})\b', re.IGNORECASE),
    re.compile(r'\b(\d{3,4})\s+A\.?D\.?\b'),                      # AD year
    re.compile(r'\b(\d{3,4})\s+C\.?E\.?\b'),                      # CE year
    re.compile(r'\b(\d{1,2})th\s+[Cc]entury\b'),                  # Nth century
    re.compile(r'\b(\d{1,2})th[\-–](\d{1,2})th\s+[Cc]entury\b'), # range
    re.compile(r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|eleventh|twelfth|thirteenth|fourteenth|fifteenth)\s+century\b', re.IGNORECASE),
]

# Place/region hints
PLACE_RE = re.compile(
    r'\b(Mysore|Karnataka|Tamil\s*Nadu|Andhra|Telangana|Kerala|Maharashtra|'
    r'Rajasthan|Gujarat|Bengal|Odisha|Orissa|Madhya\s*Pradesh|Deccan|'
    r'Badami|Hampi|Kanchi|Kanchipuram|Mahabalipuram|Thanjavur|Tanjore|'
    r'Warangal|Belur|Halebidu|Vijayanagara|Bijapur|Aihole|Pattadakal|'
    r'Ellora|Ajanta|Nasik|Junagadh|Mathura|Varanasi|Allahabad|Gaya|'
    r'Udayagiri|Sarnath|Bodh\s*Gaya|Amaravati|Nagarjunakonda|Sanchi)\b',
    re.IGNORECASE
)

# Dynasty hints
DYNASTY_RE = re.compile(
    r'\b(Gupta|Pallava|Chalukya|Rashtrakuta|Chola|Pandya|Hoysala|Kakatiya|'
    r'Vijayanagara|Ganga|Kadamba|Kalachuri|Paramar|Chandela|Gahadavala|'
    r'Satavahana|Kushana|Kushān|Maurya|Ikshvaku|Salankyana|Vishnukundin|'
    r'Vakatakas?|Vakataka|Eastern\s+Chalukya|Western\s+Chalukya|'
    r'Rashtrakutas?|Bahmani|Nayaka|Sena|Pala)\b',
    re.IGNORECASE
)

# Religion hints
RELIGION_RE = re.compile(
    r'\b(Shaiva|Shiva|Siva|Vaishnava|Vishnu|Jain|Jaina|Buddhist|Buddhism|'
    r'Vedic|Brahmin|Brahmanical|Shakta|Devi|Durga|Ganesha|Skanda|'
    r'Advaita|Vedanta|Lingayat|Veerashaiva|Agama|Agamic|Pancharatra|'
    r'Digambara|Tirthankara|Arhat|Stupa|Vihara|Sangha|Dhamma|Dharma)\b',
    re.IGNORECASE
)

# Script hints
SCRIPT_RE = re.compile(
    r'\b(Brahmi|Brāhmī|Kharosthi|Grantha|Vatteluttu|Tamil|Kannada|Telugu|'
    r'Nagari|Devanagari|Sharada|Sharda|Siddham|Siddhamatrika|'
    r'Proto-Kannada|Proto-Telugu|Old\s+Kannada|Old\s+Telugu)\b',
    re.IGNORECASE
)


def extract_first_match(text, patterns):
    """Return first regex match across a list of patterns."""
    for p in patterns:
        m = p.search(text)
        if m:
            return m.group(0).strip()
    return ""


def extract_all_matches(text, pattern, limit=5):
    """Return deduplicated list of matches up to limit."""
    seen = set()
    result = []
    for m in pattern.finditer(text):
        val = m.group(0).strip().title()
        if val not in seen:
            seen.add(val)
            result.append(val)
        if len(result) >= limit:
            break
    return result


def saka_to_ce(saka_str):
    """Convert Saka year string to approximate CE year."""
    try:
        return int(saka_str) + 78
    except:
        return None


def parse_page_text(text):
    """
    Extract structured metadata from a page's raw text.
    Returns dict with era, place, dynasty, religion, script.
    """
    # Era: prefer AD/CE, fall back to Saka conversion
    era = ""
    saka_m = re.search(r'\bSaka\s+(\d{3,4})\b', text, re.IGNORECASE)
    if saka_m:
        ce = saka_to_ce(saka_m.group(1))
        era = f"Saka {saka_m.group(1)} (c. {ce} CE)" if ce else f"Saka {saka_m.group(1)}"
    else:
        ad_m = re.search(r'\b(\d{3,4})\s+A\.?D\.?\b', text)
        ce_m = re.search(r'\b(\d{3,4})\s+C\.?E\.?\b', text)
        cent_m = re.search(r'\b(\d{1,2})(?:st|nd|rd|th)\s+[Cc]entury\b', text)
        if ad_m:
            era = ad_m.group(0)
        elif ce_m:
            era = ce_m.group(0)
        elif cent_m:
            era = cent_m.group(0).capitalize()

    places    = extract_all_matches(text, PLACE_RE, 3)
    dynasties = extract_all_matches(text, DYNASTY_RE, 2)
    religions = extract_all_matches(text, RELIGION_RE, 3)
    scripts   = extract_all_matches(text, SCRIPT_RE, 2)

    return {
        "era":      era,
        "place":    ", ".join(places),
        "dynasty":  ", ".join(dynasties),
        "religion": ", ".join(religions),
        "script":   ", ".join(scripts),
    }


def extract_article_title(text):
    """
    Try to extract the article title from page text.
    EI articles typically open with an ALL-CAPS or Title Case heading.
    """
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:15]:  # Title is almost always in first 15 lines
        # Skip very short or very long lines, page numbers, etc.
        if len(line) < 8 or len(line) > 120:
            continue
        if re.match(r'^\d+$', line):  # pure page number
            continue
        # All-caps heading (classic EI style)
        if line.isupper() and len(line.split()) >= 2:
            return line.title()
        # Title case with all significant words capitalised
        words = line.split()
        if len(words) >= 3 and sum(1 for w in words if w[0].isupper()) >= len(words) * 0.7:
            return line
    return ""


def is_article_start(page_text, prev_text=""):
    """
    Heuristic: detect whether this page starts a new inscription article.
    EI articles typically start with a bold/caps title + "By AUTHOR." line.
    """
    lines = [l.strip() for l in page_text.split('\n') if l.strip()][:20]
    has_caps_title = any(
        l.isupper() and 4 < len(l.split()) < 20
        for l in lines[:10]
    )
    has_by_line = any(AUTHOR_RE.search(l) for l in lines[:15])
    return has_caps_title or has_by_line


def chunk_pdf_into_articles(pdf_path, vol_id, vol_label, vol_url, max_pages=None):
    """
    Open a PDF and segment it into inscription articles.
    Each article = one or more consecutive pages belonging to the same piece.

    Returns list of article dicts.
    """
    articles = []
    current_article = None
    current_pages = []
    current_text = []

    print(f"  Processing {pdf_path.name} …")

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            limit = min(total, max_pages) if max_pages else total

            for page_num in range(limit):
                page = pdf.pages[page_num]
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""

                # Skip near-empty pages (plates, blank pages)
                if len(text.strip()) < 60:
                    continue

                # Detect article boundary
                if is_article_start(text) and current_text:
                    # Save completed article
                    full_text = "\n".join(current_text)
                    if len(full_text.strip()) > 200:
                        meta = parse_page_text(full_text)
                        title = extract_article_title(current_text[0]) or current_article or "Untitled Inscription"
                        articles.append(build_article_record(
                            vol_id, vol_label, vol_url,
                            title, current_pages, full_text, meta
                        ))
                    # Start fresh
                    current_pages = []
                    current_text = []
                    current_article = extract_article_title(text)

                if current_article is None:
                    current_article = extract_article_title(text)

                current_pages.append(page_num + 1)  # 1-indexed
                current_text.append(text)

            # Don't forget last article
            if current_text:
                full_text = "\n".join(current_text)
                if len(full_text.strip()) > 200:
                    meta = parse_page_text(full_text)
                    title = extract_article_title(current_text[0]) or current_article or "Untitled Inscription"
                    articles.append(build_article_record(
                        vol_id, vol_label, vol_url,
                        title, current_pages, full_text, meta
                    ))

    except Exception as e:
        print(f"  ⚠️  Error reading {pdf_path.name}: {e}")

    return articles


def build_article_record(vol_id, vol_label, vol_url, title, pages, full_text, meta):
    """Build the JSON record for one inscription article."""
    # Snippet: first 400 chars of meaningful text, skip short lines
    lines = [l.strip() for l in full_text.split('\n') if len(l.strip()) > 30]
    snippet = " ".join(lines[:5])[:400].strip()
    if len(snippet) == 400:
        snippet = snippet.rsplit(' ', 1)[0] + "…"

    # Stable ID from vol + page
    uid = f"{vol_id}-p{pages[0]:04d}"

    return {
        "id":          uid,
        "volume":      vol_label,
        "volId":       vol_id,
        "page":        pages[0],
        "pageEnd":     pages[-1],
        "title":       title,
        "era":         meta["era"],
        "place":       meta["place"],
        "dynasty":     meta["dynasty"],
        "religion":    meta["religion"],
        "script":      meta["script"],
        "snippet":     snippet,
        # Full text kept for keyword search — trim to 2000 chars to keep index size manageable
        "text":        full_text[:2000],
        "url":         vol_url,
    }


# ─────────────────────────────────────────────
# DOWNLOAD
# ─────────────────────────────────────────────

def download_pdf(url, dest_path):
    """Download a PDF with progress bar and resume support."""
    if dest_path.exists():
        print(f"  ✓ Already exists: {dest_path.name}")
        return True

    if not HAS_REQUESTS:
        print(f"  ⚠️  Cannot download {dest_path.name} (requests not installed)")
        return False

    print(f"  ↓ Downloading {dest_path.name} …")
    try:
        resp = requests.get(url, stream=True, timeout=60,
                            headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest_path.with_suffix(".tmp")
        with open(tmp, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True,
            desc=dest_path.name, leave=False
        ) as bar:
            for chunk in resp.iter_content(chunk_size=65536):
                f.write(chunk)
                bar.update(len(chunk))
        tmp.rename(dest_path)
        return True
    except Exception as e:
        print(f"  ❌ Failed: {e}")
        if dest_path.with_suffix(".tmp").exists():
            dest_path.with_suffix(".tmp").unlink()
        return False


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Build Śilālipi search index from EI PDFs")
    parser.add_argument("--volumes",       default="all",  help="Comma-separated vol IDs e.g. v01,v11,v12")
    parser.add_argument("--skip-download", action="store_true", help="Use existing PDFs in ./pdfs/")
    parser.add_argument("--output",        default="search_index.json", help="Output JSON path")
    parser.add_argument("--pdf-dir",       default="pdfs", help="Directory for downloaded PDFs")
    parser.add_argument("--sample",        action="store_true", help="Only process first 40 pages per volume (fast test)")
    args = parser.parse_args()

    pdf_dir = Path(args.pdf_dir)
    pdf_dir.mkdir(exist_ok=True)

    # Filter volumes
    if args.volumes == "all":
        selected = VOLUMES
    else:
        wanted = set(args.volumes.split(","))
        selected = [v for v in VOLUMES if v[0] in wanted]
        if not selected:
            sys.exit(f"❌  No volumes matched: {args.volumes}")

    print(f"\n{'═'*55}")
    print(f"  Śilālipi Index Builder")
    print(f"  Volumes: {len(selected)}  |  Sample: {args.sample}")
    print(f"  Output:  {args.output}")
    print(f"{'═'*55}\n")

    all_articles = []
    max_pages = 40 if args.sample else None

    for (vol_id, vol_label, vol_url, era) in selected:
        # Derive local filename from URL
        filename = vol_url.split("/")[-1]
        pdf_path = pdf_dir / filename

        print(f"[{vol_label}]")

        if not args.skip_download:
            ok = download_pdf(vol_url, pdf_path)
            if not ok:
                print(f"  Skipping {vol_label}\n")
                continue

        if not pdf_path.exists():
            print(f"  ⚠️  PDF not found: {pdf_path} — skipping\n")
            continue

        articles = chunk_pdf_into_articles(pdf_path, vol_id, vol_label, vol_url, max_pages)
        all_articles.extend(articles)
        print(f"  → {len(articles)} articles extracted\n")
        time.sleep(0.1)  # be polite to filesystem

    if not all_articles:
        sys.exit("❌  No articles extracted. Check that PDFs are in place.")

    # Write index
    output_path = Path(args.output)
    meta = {
        "_meta": {
            "generated":     datetime.utcnow().isoformat() + "Z",
            "total_articles": len(all_articles),
            "volumes":       len(selected),
            "sample_mode":   args.sample,
        }
    }

    # Write as a JS module for easier loading (avoids CORS issues with fetch on file://)
    js_output = output_path.with_suffix(".js")
    with open(js_output, "w", encoding="utf-8") as f:
        f.write("// Auto-generated by preprocess.py — do not edit manually\n")
        f.write("window.SILALIPI_INDEX = ")
        json.dump(all_articles, f, ensure_ascii=False, indent=None, separators=(',', ':'))
        f.write(";\n")
        f.write(f"window.SILALIPI_META = {json.dumps(meta['_meta'])};\n")

    # Also write plain JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta["_meta"], "articles": all_articles},
                  f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"\n{'═'*55}")
    print(f"  ✅  Done!")
    print(f"  Articles indexed : {len(all_articles)}")
    print(f"  JSON size        : {size_mb:.1f} MB  ({output_path})")
    print(f"  JS module        : {js_output}")
    print(f"\n  Next steps:")
    print(f"  1. Copy search_index.js into your repo root")
    print(f"  2. git add search_index.js index.html && git commit -m 'Add search index'")
    print(f"  3. Enable GitHub Pages (Settings → Pages → Branch: main)")
    print(f"{'═'*55}\n")


if __name__ == "__main__":
    main()
