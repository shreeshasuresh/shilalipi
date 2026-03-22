# Śilālipi — India's Epigraphic Heritage Portal

A fully static, self-hostable portal for searching and exploring the
**Epigraphia Indica** (Vols. 1–36, ASI 1892–1965) and **Epigraphia Carnatica**
(B.L. Rice, 1886–1912) — with real full-text search over the actual PDF text,
zero server, zero database.

---

## How it works

```
┌─────────────────────────────────────────────┐
│  preprocess.py  (run once on your machine)  │
│                                             │
│  Downloads PDFs → extracts text (pdfplumber)│
│  → segments articles → builds index        │
│  → outputs  search_index.js                │
└─────────────┬───────────────────────────────┘
              │  commit search_index.js to repo
              ▼
┌─────────────────────────────────────────────┐
│  index.html  (GitHub Pages static site)     │
│                                             │
│  Loads search_index.js on page open         │
│  MiniSearch builds in-memory index (< 1s)  │
│  User searches → instant results           │
│  PDF viewer → page-accurate reading        │
│  Learn tab → Claude API (user's key)       │
└─────────────────────────────────────────────┘
```

**No server. No API calls for search. No cost per query.**
Search runs entirely in the visitor's browser using [MiniSearch](https://github.com/lucaong/minisearch).

---

## Quick Start

### 1. Install Python dependencies

```bash
pip install pdfplumber requests tqdm
```

### 2. Build the search index

**Option A — Full index (all 41 volumes, ~4–6 hours, ~600 MB PDFs)**
```bash
python preprocess.py
```

**Option B — Sample index (first 40 pages per volume, ~15 minutes, tests everything)**
```bash
python preprocess.py --sample
```

**Option C — Specific volumes only**
```bash
python preprocess.py --volumes v11,v12,v13,v14,v15a,v15b
```

**Option D — PDFs already downloaded**
```bash
# Put PDFs in ./pdfs/ folder manually, then:
python preprocess.py --skip-download
```

This produces:
- `search_index.js` — JavaScript module loaded by `index.html` (~5–25 MB for full corpus)
- `search_index.json` — plain JSON version for reference

### 3. Test locally

```bash
# Python's built-in server (required — file:// won't load the .js module)
python -m http.server 8000
# Open http://localhost:8000
```

### 4. Deploy to GitHub Pages

```bash
# Initialise repo (if not already done)
git init
git remote add origin https://github.com/YOUR_USERNAME/silalipi.git

# Commit everything
git add index.html preprocess.py search_index.js README.md
git commit -m "Add Silalipi portal with search index"
git push -u origin main

# Enable GitHub Pages:
# → Go to your repo on github.com
# → Settings → Pages
# → Source: Deploy from a branch
# → Branch: main  /  (root)
# → Save
```

Your site will be live at: `https://YOUR_USERNAME.github.io/silalipi/`

---

## File structure

```
silalipi/
├── index.html          ← The portal (all HTML/CSS/JS in one file)
├── preprocess.py       ← Index builder (run locally, not on server)
├── search_index.js     ← Pre-built index (generated, committed to repo)
├── search_index.json   ← Plain JSON version (for reference/debugging)
├── pdfs/               ← Downloaded PDFs (gitignore these — too large)
└── README.md
```

**Important:** Add `pdfs/` to `.gitignore` — PDFs are hundreds of MB each
and shouldn't be committed. Only `search_index.js` goes in the repo.

```bash
echo "pdfs/" >> .gitignore
echo "*.pdf" >> .gitignore
```

---

## Updating the index

When you want to re-index (e.g. to add more volumes or improve extraction):

```bash
python preprocess.py          # regenerate
git add search_index.js
git commit -m "Rebuild search index"
git push
```

GitHub Pages redeploys automatically within ~1 minute.

---

## Index size estimates

| Scope | Articles | Index size | Build time |
|-------|----------|------------|------------|
| Sample (40 pages/vol) | ~400–800 | ~0.5 MB | 15 min |
| 5 volumes | ~300–600 | ~2 MB | 30 min |
| All 41 volumes | ~3,000–6,000 | ~10–25 MB | 4–6 hours |

The index is loaded once when the page opens and held in memory.
Even 25 MB loads in ~2–3 seconds on a typical connection.

---

## Search features

- **Full-text search** across title, snippet, body text, era, place, dynasty, religion, script
- **Fuzzy matching** (handles typos: "Chalukya" ≈ "Chalukyas", "Vishnu" ≈ "Visnhu")
- **Prefix matching** (type "Rash" → finds Rashtrakuta)
- **Field-boosted filters**: click Era / Place / Dynasty / Religion / Script filter pills
  to boost relevance for that field
- **Year range filter**: filter results to a CE year range
- **Volume filter**: restrict to a specific EI volume using the chip strip
- **Sort by**: relevance (MiniSearch score), era (ascending CE), volume (alphabetical)
- **Pagination**: 10 results per page
- **Highlighted terms**: matched query words highlighted in result snippets
- **PDF viewer**: inline page-accurate reading with zoom, keyboard nav, page pills

---

## Learn tab (Claude API)

The Learn & Explore tab uses the Anthropic Claude API for scholarly explanations.
Visitors bring their own API key (entered in the tab, stored only in their browser tab).

Get a free key at: https://console.anthropic.com

The system prompt enforces strict EI/EC sourcing — all claims must cite
specific EI volume/page numbers and epigraphic dates.

---

## Drawbacks of this approach vs a vector search backend

| | This portal | Vector search backend |
|--|--|--|
| Server required | ❌ No | ✅ Yes |
| Search accuracy | BM25 + fuzzy | Semantic similarity |
| Handles typos | ✅ Fuzzy | ✅ Better |
| Understands meaning | Limited | ✅ Yes ("temple grants" ≠ "temple taxes") |
| Setup complexity | Low | High (embeddings API, vector DB) |
| Running cost | $0 | ~$20–50 to embed full corpus |
| Index rebuild | Minutes | Hours + API cost |
| Works offline | ✅ Yes | ❌ No |

For most historical research use cases, BM25 + fuzzy is excellent.
A vector backend would help for queries like "inscriptions about water management"
where no keyword matches but semantic meaning does.

---

## Sources

- **Epigraphia Indica**, Vols. 1–36, Archaeological Survey of India (1892–1965)
  https://library.bjp.org/jspui/handle/123456789/1910
- **Epigraphia Carnatica**, B.L. Rice (1886–1912)

These publications are in the public domain.
