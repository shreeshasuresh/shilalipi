#!/usr/bin/env python3
"""
preprocess.py — Śilālipi Index Builder  (v2)
=============================================
Downloads Epigraphia Indica PDFs and builds a search index.

KEY IMPROVEMENTS OVER v1
─────────────────────────
1. OCR CLEANING  — fixes character-level errors from 19th/20th-c. scanning
   without touching proper nouns, Sanskrit terms or dates.

2. EI TITLE EXTRACTION  — exploits EI's rigid article structure:
     No. N.                    ← article number
     TITLE IN ALL CAPS         ← one or two lines
     By AUTHOR NAME.           ← author credit
   Captures multi-line titles, strips OCR noise from them.

3. ARTICLE BOUNDARY DETECTION  — requires the full (No. + title + By)
   triad instead of firing on any caps line.

4. RICHER METADATA  — also captures article number and author,
   useful for citation display.

5. SNIPPET QUALITY  — skips header/footer lines, picks the most
   informative paragraph rather than just the first 5 lines.

Usage:
  pip install pdfplumber requests tqdm
  python preprocess.py                          # all volumes, full
  python preprocess.py --sample                 # first 40 pages each (test)
  python preprocess.py --volumes v11,v12,v13    # specific volumes
  python preprocess.py --skip-download          # use existing pdfs/ folder
"""

import os
import re
import sys
import json
import time
import unicodedata
import argparse
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
    print("⚠️  requests/tqdm not installed — auto-download disabled. Put PDFs in ./pdfs/ manually.")


# ══════════════════════════════════════════════════════
# VOLUME MANIFEST
# ══════════════════════════════════════════════════════
BASE = "https://library.bjp.org/jspui/bitstream/123456789/1910/"

VOLUMES = [
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
    ("app10", "Appendix Vol.10",    BASE+"29/appendix-to-epigraphia-indica-vol-10.pdf", "1909"),
    ("app23", "Appendix Vol.19–23", BASE+"28/appendix-to-epigraphia-indica-and-record-of-the-archeological-survey-of-india-vol-19-23.pdf", "1930s"),
]


# ══════════════════════════════════════════════════════
# PART 1 — OCR CLEANING
# All fixes are purely mechanical character/word substitutions.
# They never change proper nouns, dates, or Sanskrit terms.
# ══════════════════════════════════════════════════════

# Unicode ligature normalization — these come from old typesetting
LIGATURE_MAP = str.maketrans({
    'ﬁ': 'fi',  'ﬂ': 'fl',  'ﬀ': 'ff',  'ﬃ': 'ffi', 'ﬄ': 'ffl',
    'ﬅ': 'st',  'ﬆ': 'st',
    '\u00a0': ' ',   # non-breaking space → regular space
    '\u00ad': '',    # soft hyphen → remove
    '\ufb01': 'fi',  '\ufb02': 'fl',
})

# Long-s (ſ) — common in pre-1800 typefaces scanned into EI
# Replace ſ with s everywhere; it is NEVER meaningful in EI context
LONG_S_RE = re.compile(r'ſ')

# Hyphenated line breaks — "inscrip-\ntion" → "inscription"
# Only join if the hyphenated part ends a line and next line starts lowercase
HYPHEN_BREAK_RE = re.compile(r'(\w)-\n(\w)')

# Common OCR word-level confusions for English-language scholarly text.
# These are context-safe: they only match when surrounded by word boundaries
# and cannot accidentally alter Sanskrit transliterations or proper names.
# Format: (wrong_pattern, correct_string)
OCR_WORD_FIXES = [
    # Extremely common OCR confusions in Victorian/Edwardian typefaces
    (r'\btlie\b',       'the'),
    (r'\bTlie\b',       'The'),
    (r'\bTLIE\b',       'THE'),
    (r'\btho\b',        'the'),   # 'the' with bad o/e
    (r'\bTho\b',        'The'),
    (r'\bthc\b',        'the'),
    (r'\bTHC\b',        'THE'),
    (r'\blias\b',       'has'),
    (r'\bHas\b',        'Has'),   # keep only lower → title variants
    (r'\bliave\b',      'have'),
    (r'\bliis\b',       'his'),
    (r'\bIiis\b',       'His'),
    (r'\bliim\b',       'him'),
    (r'\btliis\b',      'this'),
    (r'\bTliis\b',      'This'),
    (r'\btliat\b',      'that'),
    (r'\bTliat\b',      'That'),
    (r'\bwliich\b',     'which'),
    (r'\bWliich\b',     'Which'),
    (r'\bwliere\b',     'where'),
    (r'\bWliere\b',     'Where'),
    (r'\bwlien\b',      'when'),
    (r'\bWlien\b',      'When'),
    (r'\bwliile\b',     'while'),
    (r'\btliem\b',      'them'),
    (r'\bwliat\b',      'what'),
    (r'\bWliat\b',      'What'),
    (r'\btliere\b',     'there'),
    (r'\bTliere\b',     'There'),
    (r'\bsliould\b',    'should'),
    (r'\bSliould\b',    'Should'),
    (r'\bsliown\b',     'shown'),
    (r'\bsliewn\b',     'shewn'),   # archaic spelling, keep as-is actually
    (r'\bwitli\b',      'with'),
    (r'\bWithi\b',      'With'),
    # Digit / letter confusions common in old typefaces
    (r'\b0f\b',         'of'),     # zero confused with O
    (r'\b0n\b',         'on'),
    (r'\b0r\b',         'or'),
    (r'\b1n\b',         'in'),     # 1 confused with l or i
    (r'\b1s\b',         'is'),
    (r'\b1t\b',         'it'),
    # "rn" pair often reads as "m" or vice versa
    (r'\bgoveniment\b', 'government'),
    (r'\bGoveniment\b', 'Government'),
    (r'\bgovemment\b',  'government'),
    (r'\bGoverninent\b','Government'),
    (r'\binsciption\b', 'inscription'),
    (r'\binsciiption\b','inscription'),
    (r'\binsciiptions\b','inscriptions'),
    (r'\binsciiption\b','inscription'),
    (r'\bepigi-aphy\b', 'epigraphy'),
    (r'\bepigi-aphic\b','epigraphic'),
    # Space insertion inside common words from line-wrapping artefacts
    (r'\bins cription\b','inscription'),
    (r'\bins criptions\b','inscriptions'),
    (r'\bpra shasti\b',  'prashasti'),
    (r'\bpra-shasti\b',  'prashasti'),
    (r'\bcopper- plate\b','copper-plate'),
    (r'\bcopper -plate\b','copper-plate'),
]

# Compile OCR word fixes once for speed
_OCR_COMPILED = [(re.compile(pat, re.IGNORECASE if pat[0].islower() else 0), repl)
                 for pat, repl in OCR_WORD_FIXES]

# Actually use case-sensitive for replacements that preserve case
_OCR_COMPILED = [(re.compile(pat), repl) for pat, repl in OCR_WORD_FIXES]


def clean_ocr_text(text: str) -> str:
    """
    Clean OCR artefacts from scanned EI text.

    What we fix (purely mechanical, fact-preserving):
      • Unicode ligatures → ASCII equivalents
      • Long-s (ſ) → s
      • Hyphenated line breaks → rejoined word
      • Common English word-level OCR confusions (tlie→the, lias→has, etc.)
      • Excessive whitespace normalisation

    What we DO NOT touch:
      • Sanskrit/Prakrit transliterations (ā, ś, ṭ, ḥ etc.)
      • Proper names, place names, dynasty names
      • Dates, numbers
      • Any word not in our explicit fix list
    """
    if not text:
        return text

    # 1. Normalise Unicode — decompose then recompose; fixes garbled combining chars
    text = unicodedata.normalize('NFC', text)

    # 2. Ligatures
    text = text.translate(LIGATURE_MAP)

    # 3. Long-s
    text = LONG_S_RE.sub('s', text)

    # 4. Hyphenated line-break rejoining: "inscrip-\ntion" → "inscription"
    text = HYPHEN_BREAK_RE.sub(r'\1\2', text)

    # 5. Word-level OCR fixes
    for pattern, replacement in _OCR_COMPILED:
        text = pattern.sub(replacement, text)

    # 6. Normalise whitespace: multiple spaces → single space, but preserve newlines
    text = re.sub(r'[ \t]{2,}', ' ', text)

    # 7. Remove lines that are clearly OCR garbage (>40% non-alphanumeric, short)
    lines = text.split('\n')
    clean_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            clean_lines.append('')
            continue
        if len(stripped) < 4:
            # Very short — keep only if it looks like a page number or section marker
            if re.match(r'^\d+$', stripped) or re.match(r'^[IVX]+\.$', stripped):
                clean_lines.append(line)
            # else skip
            continue
        alnum = sum(1 for c in stripped if c.isalnum() or c.isspace())
        if len(stripped) > 10 and alnum / len(stripped) < 0.55:
            # Mostly symbols — likely OCR garbage row, skip
            continue
        clean_lines.append(line)

    return '\n'.join(clean_lines)


# ══════════════════════════════════════════════════════
# PART 2 — EI ARTICLE STRUCTURE PARSING
# EI (Epigraphia Indica) has a very consistent article format:
#
#   [page header: volume number, journal name]
#   [blank or short line]
#   No. N.                           ← article sequence number
#   TITLE OF INSCRIPTION             ← ALL CAPS, 1–3 lines
#   [subtitle or location, optional] ← still caps or mixed
#   By A. S. AUTHOR, M.A.            ← author credit
#   [blank]
#   Article body begins here...
#
# We use this structure for both boundary detection and title extraction.
# ══════════════════════════════════════════════════════

# Article number: "No. 1.", "No. 12.", "NO. 1."  or Roman "I.", "II.", "III." alone on a line
ARTICLE_NO_RE = re.compile(
    r'^\s*(?:No\.|NO\.)\s*(\d{1,3})\.\s*$'    # Arabic: "No. 5."
    r'|^\s*(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})\.\s*$'  # Roman: "XIV."
    , re.MULTILINE | re.IGNORECASE
)

# Author credit: "By J. F. Fleet." / "By A.S. Altekar, M.A." / "BY FLEET"
AUTHOR_LINE_RE = re.compile(
    r'^\s*By\s+[A-Z][A-Za-z .,-]{2,60}\.?\s*$',
    re.MULTILINE
)

# Strict all-caps title line: at least 3 words, mostly A-Z (allows spaces, hyphens, Roman numerals)
CAPS_TITLE_RE = re.compile(
    r'^([A-Z][A-Z0-9\s\-\,\.\'\(\)]{10,100})$'
)

# Table of contents signature — many lines of form "N. Title ... N" (page ref at end)
TOC_LINE_RE = re.compile(r'^\s*\d+\.\s+.{5,60}\s+\d+\s*$')


def is_toc_page(lines: list) -> bool:
    """Return True if this page looks like a Table of Contents."""
    toc_matches = sum(1 for l in lines if TOC_LINE_RE.match(l))
    return toc_matches >= 5


def looks_like_page_header(line: str) -> bool:
    """Epigraphia Indica page headers: 'EPIGRAPHIA INDICA' or 'VOL. X' etc."""
    return bool(re.match(
        r'^\s*(?:EPIGRAPHIA\s+INDICA|ARCHAEOLOGICAL\s+SURVEY|VOL(?:UME)?\.?\s+\d)',
        line, re.IGNORECASE
    ))


def extract_ei_article_header(page_text: str, start_line: int = 0) -> dict:
    """
    Parse an article header starting at start_line within page_text.
    Returns {'number': str, 'title': str, 'author': str}.

    start_line allows calling this for mid-page article starts.
    """
    all_lines = [l.rstrip() for l in page_text.split('\n')]
    lines = all_lines[start_line:]   # work from the start point

    result = {'number': '', 'title': '', 'author': ''}

    # ── Strategy A: explicit "No. N." marker ──────────────────────────
    no_idx = None
    for i, line in enumerate(lines):
        if re.match(r'^\s*(?:No\.|NO\.)\s*\d{1,3}\.\s*$', line.strip(), re.IGNORECASE):
            result['number'] = re.search(r'\d{1,3}', line).group(0)
            no_idx = i
            break

    if no_idx is not None:
        # Collect consecutive caps lines after the No. line
        title_parts = []
        for line in lines[no_idx + 1: no_idx + 8]:
            s = line.strip()
            if not s:
                if title_parts:
                    break   # blank line ends title block
                continue
            if looks_like_page_header(s):
                continue
            if AUTHOR_LINE_RE.match(s):
                result['author'] = re.sub(r'^By\s+', '', s.strip(), flags=re.IGNORECASE).rstrip('.')
                break
            if CAPS_TITLE_RE.match(s) or s.isupper():
                title_parts.append(s.strip())
            elif title_parts:
                # First non-caps line after collecting title — could be subtitle
                # Include if short and mostly caps (e.g., "OF PULAKESI II")
                upper_ratio = sum(1 for c in s if c.isupper()) / max(len(s), 1)
                if upper_ratio > 0.5 and len(s) < 80:
                    title_parts.append(s.strip())
                else:
                    break
        if title_parts:
            result['title'] = ' '.join(title_parts)

    # ── Strategy B: no explicit No. line — caps-title, By is optional ──────
    # Scan first 20 lines. Collect ALL-CAPS lines near the top of the page.
    # Stop collecting when we hit a mixed-case body line.
    # Author line is captured if present but not required.
    if not result['title']:
        caps_lines = []
        for i, line in enumerate(lines[:20]):
            s = line.strip()
            if not s or looks_like_page_header(s):
                continue
            if re.match(r'^\d+$', s):           # bare page number
                continue
            if re.match(r'^No\.\s*\d', s, re.IGNORECASE):  # already handled above
                continue

            if AUTHOR_LINE_RE.match(s):
                # Author line found — grab author and stop
                result['author'] = re.sub(r'^By\s+', '', s.strip(),
                                          flags=re.IGNORECASE).rstrip('.')
                if caps_lines:
                    result['title'] = ' '.join(caps_lines)
                break

            if s.isupper() and len(s.split()) >= 2 and len(s) >= 8:
                caps_lines.append(s)
            elif caps_lines:
                # First non-caps line after title block — check if it's a
                # high-caps mixed line (e.g. "Of Pulakesi II") to include
                upper_ratio = sum(1 for c in s if c.isupper()) / max(len(s), 1)
                if upper_ratio > 0.55 and len(s) < 90:
                    caps_lines.append(s)
                else:
                    # Body text has started — stop, save what we have
                    result['title'] = ' '.join(caps_lines)
                    break

        # If we collected caps lines but never hit a body line or By line
        if caps_lines and not result['title']:
            result['title'] = ' '.join(caps_lines)

    # ── Author fallback: scan entire first 30 lines ───────────────────
    if not result['author']:
        for line in lines[:30]:
            m = AUTHOR_LINE_RE.match(line.strip())
            if m:
                result['author'] = re.sub(r'^By\s+', '', line.strip(),
                                          flags=re.IGNORECASE).rstrip('.')
                break

    # ── Clean up title ────────────────────────────────────────────────
    title = result['title']
    # Convert ALL CAPS to Title Case — looks better, preserves content
    if title and title == title.upper():
        title = title.title()

    # Re-uppercase Roman numerals that title() lowercased (e.g. "Iii" → "III", "Iv" → "IV")
    title = re.sub(
        r'\b(X{0,3}(?:IX|IV|VIII|VII|VI|V|IV|III|II|I))\b',
        lambda m: m.group(0).upper(),
        title,
        flags=re.IGNORECASE
    )

    # Strip trailing punctuation artefacts
    title = title.rstrip('.,;:')
    result['title'] = title.strip()

    return result


def _is_caps_title_line(line: str) -> bool:
    """True if this line looks like an EI article title in ALL CAPS."""
    return (
        line.isupper()
        and len(line.split()) >= 2
        and len(line) >= 8
        and not looks_like_page_header(line)
        and not re.match(r'^\d+$', line)
    )


def find_article_starts_in_lines(lines: list) -> list:
    """
    Scan ALL lines of a page and return the indices where a new EI article
    header begins.  Articles can start at the top OR in the middle of a page
    (after the previous article ends).

    Returns a list of line indices (0-based). Empty list = no article start
    found anywhere on this page.

    Detection rules (any one is sufficient):
      A) 'No. N.' line  — strongest signal, always triggers
      B) ALL-CAPS line (≥ 2 words) that is NOT a known mid-article
         subheading like TRANSLITERATION, TRANSLATION, NOTES, PLATES.
         We allow this anywhere on the page since EI articles can start
         mid-page after the previous article ends.
      C) ALL-CAPS block + 'By AUTHOR' line within 8 lines of the caps block
         — allows detection even when rule B would be too aggressive.

    Guards:
      - Journal/volume headers (EPIGRAPHIA INDICA, VOL.) never trigger
      - Known mid-article section labels never trigger
      - TOC pages never trigger
    """
    if not lines or len(lines) < 2:
        return []
    if is_toc_page(lines):
        return []

    # Section labels that appear mid-article — must NOT trigger a new article
    SECTION_LABELS = {
        'TRANSLITERATION', 'TRANSLATION', 'NOTES', 'PLATES', 'FACSIMILE',
        'TEXT', 'APPENDIX', 'ADDENDA', 'CORRIGENDA', 'ERRATA',
        'INTRODUCTION', 'CONCLUSION', 'SUMMARY', 'INDEX', 'CONTENTS',
        'REFERENCES', 'BIBLIOGRAPHY', 'SEAL', 'PLATE',
    }

    starts = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # ── Rule A: explicit "No. N." line ──────────────────────────
        if re.match(r'^No\.\s*\d{1,3}\.$', line, re.IGNORECASE):
            starts.append(i)
            # Skip past the title block that follows (caps lines + By line)
            # so they don't re-trigger Rule B
            i += 1
            while i < len(lines):
                l = lines[i]
                if _is_caps_title_line(l) or AUTHOR_LINE_RE.match(l) or not l.strip():
                    i += 1
                else:
                    break
            continue

        # ── Rule B: ALL-CAPS line, not a section label ────────────────
        if _is_caps_title_line(line):
            stripped = line.strip().rstrip('.')
            if stripped in SECTION_LABELS:
                i += 1
                continue

            # Check if a 'By AUTHOR' line follows within the next 8 lines
            lookahead = lines[i+1 : i+9]
            has_by = any(AUTHOR_LINE_RE.match(l) for l in lookahead)

            if has_by:
                starts.append(i)
                # Skip the rest of this header block
                i += 1
                while i < len(lines):
                    l = lines[i]
                    if _is_caps_title_line(l) or AUTHOR_LINE_RE.match(l) or not l.strip():
                        i += 1
                    else:
                        break
                continue

            # No By line — use position / gap heuristic
            prev_content_lines = [l for l in lines[max(0,i-4):i] if l.strip()]
            after_gap = len(prev_content_lines) == 0

            if i < 6 or after_gap:
                starts.append(i)
                i += 1
                # Also skip contiguous caps lines (multi-line title)
                while i < len(lines) and _is_caps_title_line(lines[i]):
                    i += 1
                continue

        i += 1

    return starts


def is_ei_article_start(page_text: str) -> bool:
    """Convenience wrapper — True if any article start found anywhere on page."""
    lines = [l.strip() for l in page_text.split('\n') if l.strip()]
    return bool(find_article_starts_in_lines(lines))


# ══════════════════════════════════════════════════════
# PART 3 — METADATA EXTRACTION
# ══════════════════════════════════════════════════════

def saka_to_ce(n: int) -> int:
    return n + 78

# ── Date patterns ──────────────────────────────────────
_SAKA_RE  = re.compile(r'\b(?:Saka|Śaka|Shaka)\s+(\d{3,4})\b', re.IGNORECASE)
_VIKRAMA_RE = re.compile(r'\b(?:Vikrama|Vikramaditya|V\.S\.)\s+(\d{3,4})\b', re.IGNORECASE)
_AD_RE    = re.compile(r'\b(\d{3,4})\s+A\.?\s*D\.?\b')
_CE_RE    = re.compile(r'\b(\d{3,4})\s+C\.?\s*E\.?\b')
_CENTURY_RE = re.compile(r'\b(\d{1,2})(?:st|nd|rd|th)[-–]?(?:\s*(?:or|to)\s*\d{1,2}(?:st|nd|rd|th))?\s+[Cc]entury\b')
_CENT_WORD_RE = re.compile(
    r'\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth|'
    r'eleventh|twelfth|thirteenth|fourteenth|fifteenth|sixteenth|seventeenth)\s+century\b',
    re.IGNORECASE
)

_ORDINAL_TO_NUM = {
    'first':1,'second':2,'third':3,'fourth':4,'fifth':5,'sixth':6,'seventh':7,
    'eighth':8,'ninth':9,'tenth':10,'eleventh':11,'twelfth':12,'thirteenth':13,
    'fourteenth':14,'fifteenth':15,'sixteenth':16,'seventeenth':17,
}


def extract_era(text: str) -> str:
    """Extract the most specific date expression from text."""
    # Saka era (most common in EI)
    m = _SAKA_RE.search(text)
    if m:
        ce = saka_to_ce(int(m.group(1)))
        return f"Saka {m.group(1)} (c. {ce} CE)"

    # AD/CE year
    m = _AD_RE.search(text) or _CE_RE.search(text)
    if m:
        return m.group(0).strip()

    # Vikrama samvat (subtract 57 for approximate BCE/CE)
    m = _VIKRAMA_RE.search(text)
    if m:
        ce = int(m.group(1)) - 57
        return f"VS {m.group(1)} (c. {ce} CE)"

    # Ordinal century — numeric
    m = _CENTURY_RE.search(text)
    if m:
        return m.group(0).strip().capitalize()

    # Ordinal century — word form ("seventh century")
    m = _CENT_WORD_RE.search(text)
    if m:
        n = _ORDINAL_TO_NUM.get(m.group(1).lower(), '?')
        suffix = {1:'st',2:'nd',3:'rd'}.get(n,'th')
        return f"{n}{suffix} century CE"

    return ""


# ── Place patterns ─────────────────────────────────────
_PLACE_RE = re.compile(
    r'\b(Mysore|Mysuru|Karnataka|Tamil\s*Nadu|Andhra(?:\s+Pradesh)?|Telangana|'
    r'Kerala|Maharashtra|Rajasthan|Gujarat|Bengal|Odisha|Orissa|'
    r'Madhya\s*Pradesh|Uttar\s*Pradesh|Deccan|Punjab|'
    # Major sites
    r'Badami|Hampi|Kanchi|Kanchipuram|Mahabalipuram|Mamallapuram|'
    r'Thanjavur|Tanjore|Tanjore|Gangaikondacholapuram|'
    r'Warangal|Belur|Halebidu|Halebid|Dwarasamudra|'
    r'Vijayanagara|Bijapur|Vijayapura|Aihole|Pattadakal|'
    r'Ellora|Ajanta|Nasik|Nashik|Junagadh|'
    r'Mathura|Varanasi|Banaras|Allahabad|Prayagraj|Gaya|Bodh\s*Gaya|'
    r'Udayagiri|Sarnath|Amaravati|Nagarjunakonda|Sanchi|'
    r'Srirangam|Chidambaram|Madurai|Rameswaram|'
    r'Puri|Konark|Bhubaneswar|Khajuraho|Gwalior|'
    r'Shravanabelagola|Manyakheta|Malkhed|Rashtrakuta|Devagiri|'
    r'Daulatabad|Kondavidu|Mukhalingam|Draksharama)\b',
    re.IGNORECASE
)

# ── Dynasty patterns ────────────────────────────────────
_DYNASTY_RE = re.compile(
    r'\b(Gupta|Pallava|Chalukya|Badami\s+Chalukya|Vengi\s+Chalukya|'
    r'Kalyani\s+Chalukya|Rashtrakuta|Chola|Pandya|Hoysala|Kakatiya|'
    r'Vijayanagara|Sangama|Saluva|Tuluva|Aravidu|'
    r'Ganga|Kadamba|Kalachuri|Paramara|Chandela|Gahadavala|'
    r'Satavahana|Kushana|Kushān|Maurya|Nanda|'
    r'Ikshvaku|Salankyana|Vishnukundin|Vakataka|'
    r'Eastern\s+Chalukya|Western\s+Chalukya|Western\s+Ganga|Eastern\s+Ganga|'
    r'Bahmani|Bidar|Ahmadnagar|Golconda|Bijapur\s+Adil\s+Shah|'
    r'Nayaka|Sena|Pala|Pratihara|Gurjara.Pratihara|'
    r'Yadava|Silahara|Shilahara|Kalachuri|Kalacuri|'
    r'Maukhari|Pushyabhuti|Vardhana|Harsha)\b',
    re.IGNORECASE
)

# ── Religion patterns ───────────────────────────────────
_RELIGION_RE = re.compile(
    r'\b(Shaiva|Shiva|Siva|Vaishnava|Vishnu|Vaishnavam|'
    r'Jain|Jaina|Digambara|Shvetambara|Tirthankara|Arhat|'
    r'Buddhist|Buddhism|Theravada|Mahayana|Vajrayana|Stupa|Vihara|Sangha|Dhamma|'
    r'Vedic|Brahmin|Brahmanical|Brahmana|Shakta|Devi|Durga|Ganesha|Skanda|Kumara|'
    r'Advaita|Vedanta|Lingayat|Veerashaiva|Virashaiva|Basavanna|'
    r'Agama|Agamic|Pancharatra|Bhagavata|'
    r'Pasupata|Pashupata|Kapalika|Kalamukha|Shaiva\s+Siddhanta)\b',
    re.IGNORECASE
)

# ── Script patterns ─────────────────────────────────────
_SCRIPT_RE = re.compile(
    r'\b(Brahmi|Br[aā]hm[iī]|Kharosthi|Kharoṣṭhī|'
    r'Grantha|Vatteluttu|Tamil\s+Grantha|'
    r'Kannada|Telugu|Nagari|Devanagari|Nāgarī|'
    r'Sharada|Sharda|Śāradā|Siddham|Siddhamatrika|'
    r'Proto.Kannada|Old\s+Kannada|Old\s+Telugu|'
    r'Kalinga|Nandinagari|Bhattiprolu)\b',
    re.IGNORECASE
)

# ── Inscription type patterns ───────────────────────────
_GRANT_TYPE_RE = re.compile(
    r'\b(copper.plate\s+grant|copper.plate|tamrashasana|tamra.sasana|'
    r'prasasti|prashasti|praśasti|stone\s+inscription|rock\s+inscription|'
    r'pillar\s+inscription|cave\s+inscription|slab\s+inscription|'
    r'land\s+grant|agrahara\s+grant|brahmadeya|devadana|paliyam|'
    r'shasana|s[aā]sana|firman)\b',
    re.IGNORECASE
)


def extract_all_unique(text: str, pattern: re.Pattern, limit: int = 4) -> list:
    """Return deduplicated, title-cased matches up to limit."""
    seen, result = set(), []
    for m in pattern.finditer(text):
        val = m.group(0).strip()
        key = val.lower()
        if key not in seen:
            seen.add(key)
            # Title-case multi-word matches; preserve single words as-is
            result.append(val.title() if ' ' in val else val)
        if len(result) >= limit:
            break
    return result


def extract_metadata(text: str) -> dict:
    """Extract structured metadata fields from article text."""
    era       = extract_era(text)
    places    = extract_all_unique(text, _PLACE_RE,    4)
    dynasties = extract_all_unique(text, _DYNASTY_RE,  3)
    religions = extract_all_unique(text, _RELIGION_RE, 4)
    scripts   = extract_all_unique(text, _SCRIPT_RE,   3)
    grant_types = extract_all_unique(text, _GRANT_TYPE_RE, 2)

    return {
        "era":       era,
        "place":     ", ".join(places),
        "dynasty":   ", ".join(dynasties),
        "religion":  ", ".join(religions),
        "script":    ", ".join(scripts),
        "grantType": ", ".join(grant_types),
    }


# ══════════════════════════════════════════════════════
# PART 5 — PAGE-LEVEL INDEXING
#
# Every page = one record. Nothing is skipped.
# Article detection enriches records (title, author, article no)
# but never gates whether a page is indexed.
# ══════════════════════════════════════════════════════

def index_pdf_pages(pdf_path: Path, vol_id: str, vol_label: str,
                    vol_url: str, max_pages=None) -> list:
    """
    Index every page of a PDF. Each page can produce MULTIPLE records if
    it contains more than one article start (e.g. one article ending and
    another beginning mid-page).

    Algorithm per physical page:
      1. Extract and clean text
      2. Split lines and call find_article_starts_in_lines()
      3. If 0 starts found → one record for the whole page (inherits ctx)
         If N starts found → split the page into N+1 fragments:
           - fragment before first start  → belongs to previous article (ctx)
           - each fragment from a start   → new article context
      4. Emit one search record per fragment (if fragment has ≥ 30 chars)

    Every fragment is indexed regardless of whether an article was detected.
    The only pages skipped are truly blank / image-only (< 40 chars total).
    """
    records = []

    # Current article context — carried forward across pages and fragments
    ctx_title  = ""
    ctx_author = ""
    ctx_no     = ""
    ctx_start  = 0    # page number where this article started

    print(f"  Indexing {pdf_path.name} ...", end="", flush=True)
    indexed = 0
    skipped = 0

    def make_record(page_1indexed, fragment_lines, frag_idx, total_frags):
        """Build one search record from a list of text lines."""
        text = "\n".join(fragment_lines).strip()
        if len(text) < 30:
            return None

        clean = clean_ocr_text(text)
        meta  = extract_metadata(clean)

        # Title: prefer article context, then metadata, then vol+page
        if ctx_title:
            title = ctx_title
        elif meta["dynasty"]:
            title = meta["dynasty"].split(",")[0] + " Inscription"
        elif meta["place"]:
            title = "Inscription at " + meta["place"].split(",")[0]
        else:
            title = f"{vol_label} — p.{page_1indexed}"

        # Unique id: page + fragment suffix if multiple fragments on this page
        frag_suffix = f"-f{frag_idx}" if total_frags > 1 else ""
        uid = f"{vol_id}-p{page_1indexed:04d}{frag_suffix}"

        cite = vol_label
        if ctx_no:
            cite += f", No. {ctx_no}"
        if ctx_start and ctx_start != page_1indexed:
            cite += f" (art. starts p.{ctx_start})"

        return {
            "id":          uid,
            "volume":      vol_label,
            "citation":    cite,
            "volId":       vol_id,
            "page":        page_1indexed,
            "pageEnd":     page_1indexed,
            "articleNo":   ctx_no,
            "articlePage": ctx_start,
            "author":      ctx_author,
            "title":       title,
            "era":         meta["era"],
            "place":       meta["place"],
            "dynasty":     meta["dynasty"],
            "religion":    meta["religion"],
            "script":      meta["script"],
            "grantType":   meta["grantType"],
            "snippet":     extract_page_snippet(clean),
            "text":        clean[:1800],
            "url":         vol_url,
        }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            total = len(pdf.pages)
            limit = min(total, max_pages) if max_pages else total

            for page_num in range(limit):
                pg = pdf.pages[page_num]
                p1 = page_num + 1

                try:
                    raw = pg.extract_text() or ""
                except Exception:
                    raw = ""

                if len(raw.strip()) < 40:
                    skipped += 1
                    continue

                # Split into non-empty lines (preserve originals for splitting)
                all_lines     = raw.split('\n')
                stripped_lines = [l.strip() for l in all_lines]
                nonempty_lines = [l for l in stripped_lines if l]

                # Find article starts (indices into nonempty_lines)
                start_indices = find_article_starts_in_lines(nonempty_lines)

                # Build fragments: split nonempty_lines at each start index
                # Fragment 0: lines before first start (may be empty)
                # Fragment k: lines from start_indices[k-1] onward
                if not start_indices:
                    # Whole page → one record inheriting current context
                    rec = make_record(p1, nonempty_lines, 0, 1)
                    if rec:
                        records.append(rec)
                        indexed += 1
                else:
                    # Build split points: [0, s0, s1, ..., end]
                    split_points = [0] + start_indices + [len(nonempty_lines)]
                    fragments = [
                        nonempty_lines[split_points[k]:split_points[k+1]]
                        for k in range(len(split_points)-1)
                    ]
                    total_frags = len(fragments)

                    for frag_idx, fragment in enumerate(fragments):
                        if not fragment:
                            continue

                        # Is this fragment a new article start?
                        is_new = frag_idx > 0 or (
                            frag_idx == 0 and 0 in start_indices
                        )

                        if is_new:
                            # Update article context from this fragment's header
                            frag_text = "\n".join(fragment)
                            hdr = extract_ei_article_header(frag_text, start_line=0)
                            if hdr["title"]:
                                ctx_title  = hdr["title"]
                                ctx_author = hdr["author"]
                                ctx_no     = hdr["number"]
                                ctx_start  = p1

                        rec = make_record(p1, fragment, frag_idx, total_frags)
                        if rec:
                            records.append(rec)
                            indexed += 1

    except Exception as e:
        print(f"\n  WARNING: error in {pdf_path.name}: {e}")
        import traceback; traceback.print_exc()

    print(f" {indexed} records, {skipped} blank pages skipped")
    return records


def extract_page_snippet(text: str, max_chars: int = 380) -> str:
    """Best readable snippet from a single page, skipping header lines."""
    body = []
    for line in text.split("\n"):
        s = line.strip()
        if not s or len(s) < 30:
            continue
        if re.match(r"^\d+$", s):
            continue
        if s.isupper() and len(s) < 80:
            continue
        if looks_like_page_header(s):
            continue
        if re.match(r"^No\.\s*\d", s, re.IGNORECASE):
            continue
        if AUTHOR_LINE_RE.match(s):
            continue
        body.append(s)
    snippet = " ".join(body)
    snippet = re.sub(r"\s+", " ", snippet).strip()
    if len(snippet) > max_chars:
        snippet = snippet[:max_chars].rsplit(" ", 1)[0] + "\u2026"
    if len(snippet) < 30:
        snippet = re.sub(r"\s+", " ", text).strip()[:max_chars]
    return snippet


# ══════════════════════════════════════════════════════
# PART 6 — DOWNLOAD
# ══════════════════════════════════════════════════════

def download_pdf(url: str, dest_path: Path) -> bool:
    if dest_path.exists():
        print(f"  ✓ Already have {dest_path.name}")
        return True
    if not HAS_REQUESTS:
        print(f"  ⚠️  requests not installed — cannot download {dest_path.name}")
        return False
    print(f"  ↓ Downloading {dest_path.name} …")
    try:
        resp = requests.get(url, stream=True, timeout=90,
                            headers={"User-Agent": "Mozilla/5.0 (compatible; Silalipi)"})
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest_path.with_suffix(".tmp")
        with open(tmp, "wb") as f, tqdm(
            total=total, unit="B", unit_scale=True,
            desc=dest_path.name, leave=False
        ) as bar:
            for chunk in resp.iter_content(65536):
                f.write(chunk); bar.update(len(chunk))
        tmp.rename(dest_path)
        return True
    except Exception as e:
        print(f"  ❌ Download failed: {e}")
        try: dest_path.with_suffix(".tmp").unlink()
        except FileNotFoundError: pass
        return False


# ══════════════════════════════════════════════════════
# PART 7 — MAIN
# ══════════════════════════════════════════════════════

def main():
    p = argparse.ArgumentParser(description="Śilālipi Index Builder v2")
    p.add_argument("--volumes",       default="all",
                   help="Comma-separated vol IDs e.g. v01,v11,v12")
    p.add_argument("--skip-download", action="store_true",
                   help="Use already-downloaded PDFs in ./pdfs/")
    p.add_argument("--output",        default="search_index.json")
    p.add_argument("--pdf-dir",       default="pdfs")
    p.add_argument("--sample",        action="store_true",
                   help="Only first 40 pages per volume (quick test)")
    p.add_argument("--debug",         action="store_true",
                   help="Print first 5 page records per volume for inspection")
    args = p.parse_args()

    pdf_dir = Path(args.pdf_dir)
    pdf_dir.mkdir(exist_ok=True)

    if args.volumes == "all":
        selected = VOLUMES
    else:
        wanted = set(args.volumes.split(","))
        selected = [v for v in VOLUMES if v[0] in wanted]
        if not selected:
            sys.exit(f"❌  No volumes matched: {args.volumes}")

    print(f"\n{'═'*58}")
    print(f"  Śilālipi Index Builder  v2")
    print(f"  Volumes : {len(selected)}")
    print(f"  Sample  : {args.sample} (first 40 pages only)" if args.sample else f"  Mode    : Full index")
    print(f"  Output  : {args.output}")
    print(f"{'═'*58}\n")

    all_articles = []
    max_pages = 40 if args.sample else None

    for (vol_id, vol_label, vol_url, _era) in selected:
        filename = vol_url.split("/")[-1]
        pdf_path = pdf_dir / filename
        print(f"[{vol_label}]")

        if not args.skip_download:
            if not download_pdf(vol_url, pdf_path):
                print(f"  Skipping {vol_label}\n"); continue

        if not pdf_path.exists():
            print(f"  ⚠️  PDF not found: {pdf_path} — skipping\n"); continue

        articles = index_pdf_pages(pdf_path, vol_id, vol_label, vol_url, max_pages)
        all_articles.extend(articles)

        if args.debug:
            for a in articles[:5]:
                print(f"     p.{a['page']:>4}  [{a['articleNo'] or '—':>3}]  {a['title'][:60]!r}")
        time.sleep(0.05)

    if not all_articles:
        sys.exit("❌  No articles extracted.")

    output_path = Path(args.output)
    meta_block = {
        "generated":    datetime.utcnow().isoformat() + "Z",
        "total_pages":  len(all_articles),
        "total_articles": len(all_articles),   # alias for backward compat
        "volumes":      len(selected),
        "sample_mode":  args.sample,
        "version":      3,
        "index_mode":   "page",
    }

    # JS module (loaded by index.html)
    js_path = output_path.with_suffix(".js")
    with open(js_path, "w", encoding="utf-8") as f:
        f.write("// Auto-generated by preprocess.py v2 — do not edit manually\n")
        f.write("window.SILALIPI_INDEX = ")
        json.dump(all_articles, f, ensure_ascii=False, separators=(',', ':'))
        f.write(";\n")
        f.write(f"window.SILALIPI_META = {json.dumps(meta_block)};\n")

    # Plain JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump({"meta": meta_block, "articles": all_articles},
                  f, ensure_ascii=False, indent=2)

    size_mb = output_path.stat().st_size / 1_048_576
    print(f"\n{'═'*58}")
    print(f"  ✅  Done!")
    print(f"  Pages indexed : {len(all_articles):,}")
    print(f"  Size          : {size_mb:.1f} MB  →  {output_path}")
    print(f"  JS file       : {js_path}")
    print(f"\n  Every page is indexed — search finds exact page numbers.")
    print(f"  Tip: --debug shows the first 5 page records per volume")
    print(f"  Tip: --sample processes first 40 pages per volume for quick testing")
    print(f"{'═'*58}\n")


if __name__ == "__main__":
    main()
