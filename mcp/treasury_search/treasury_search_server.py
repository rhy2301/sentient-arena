"""treasury_search MCP server for the OfficeQA / Treasury Bulletin benchmark.

Two-stage retrieval over a local, offline corpus of monthly U.S. Treasury
Bulletin text files (``/app/corpus/treasury_bulletin_YYYY_MM.txt``):

  Stage 1 — candidate selection from ALREADY-RESOLVED structured filters
            (explicit filenames, or plain years/months lists). This server
            NEVER parses a raw natural-language question; that is the job of
            the separate date_filter server. See "Role separation" in the spec.

  Stage 2 — chunk the candidate files, score chunks with a self-contained BM25
            implementation, and return the top_k chunks with grounding
            metadata (page number when detectable, else line offsets).

Standard library + fastmcp only. No external BM25 package. No network calls at
runtime. Deterministic. Returns JSON-serializable dicts/lists only.
"""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP

treasury_search_app = FastMCP("treasury_search")

# --- global constants -------------------------------------------------------
CORPUS_DIR = Path("/app/corpus")
INDEX_FILE = CORPUS_DIR / "index.txt"
DEFAULT_CHUNK_CHARS = 3500
DEFAULT_OVERLAP_CHARS = 500

# Bound how much text we ever read / return to keep responses small.
MAX_FILE_BYTES = 8_000_000          # skip pathologically large files
MAX_RESULT_TEXT_CHARS = 6000        # truncate per-result chunk text
MAX_CANDIDATE_FILES = 2000          # safety cap on Stage 1 file count

# Strict filename validation — prevents path traversal.
_FNAME_RE = re.compile(r"^treasury_bulletin_(\d{4})_(\d{2})\.txt$")
_ALLOWED_EXTRA = {"index.txt"}

MONTH_NUMBER_TO_NAME: dict[int, str] = {
    1: "January", 2: "February", 3: "March", 4: "April", 5: "May", 6: "June",
    7: "July", 8: "August", 9: "September", 10: "October", 11: "November",
    12: "December",
}

# Minimal English stopword set; we deliberately KEEP financial terms and
# numbers (those are signal, not noise, in this corpus).
_STOPWORDS = frozenset(
    {
        "a", "an", "the", "and", "or", "of", "to", "in", "on", "for", "with",
        "at", "by", "from", "as", "is", "are", "was", "were", "be", "been",
        "being", "this", "that", "these", "those", "it", "its", "into", "than",
        "then", "there", "here", "what", "which", "who", "whom", "how", "when",
        "where", "why", "all", "any", "both", "each", "more", "most", "other",
        "some", "such", "no", "not", "only", "own", "same", "so", "too", "very",
        "can", "will", "just", "do", "does", "did", "have", "has", "had", "but",
        "if", "about", "between", "during", "over", "under", "value", "values",
    }
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Number patterns for extract_numbers_near_query (and numeric-boost detection).
_NUMBER_RE = re.compile(
    r"""
    \(?                       # optional opening paren (negative accounting)
    \$?                       # optional dollar sign
    -?                        # optional leading minus
    \d{1,3}(?:,\d{3})+        # grouped thousands: 1,234 / 12,345,678
    (?:\.\d+)?                # optional decimal
    \)?                       # optional closing paren
    %?                        # optional percent
    |
    \(?\$?-?\d+\.\d+\)?%?     # plain decimal: 12.34 / 12.34%
    |
    \(?\$?-?\d+\)?%?          # plain integer: 1234 / (1234) / 1234%
    """,
    re.VERBOSE,
)

# Page-boundary markers left behind by PDF-to-text conversion.
_PAGE_LABEL_RE = re.compile(r"(?:page|p\.?)\s*[#:]?\s*(\d{1,4})", re.IGNORECASE)
_STANDALONE_PAGE_RE = re.compile(r"^\s*(\d{1,4})\s*$")


# --- shared corpus helpers --------------------------------------------------


def _safe_filename(filename: str) -> Optional[str]:
    """Return the basename if it is a permitted corpus file, else None.

    Strips any directory component (defends against path traversal) and only
    accepts ``treasury_bulletin_YYYY_MM.txt`` or ``index.txt``.
    """
    if not isinstance(filename, str) or not filename:
        return None
    base = Path(filename).name  # discards any leading path / .. segments
    if base in _ALLOWED_EXTRA or _FNAME_RE.match(base):
        return base
    return None


def _year_month_from_name(filename: str) -> tuple[Optional[int], Optional[int]]:
    """Extract (year, month) from a corpus filename, or (None, None)."""
    m = _FNAME_RE.match(filename)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def _list_all_corpus_files() -> list[str]:
    """All corpus filenames, preferring index.txt, falling back to a glob.

    Only returns names that pass strict validation, sorted chronologically.
    """
    names: list[str] = []
    try:
        if INDEX_FILE.is_file():
            for line in INDEX_FILE.read_text(
                encoding="utf-8", errors="replace"
            ).splitlines():
                candidate = _safe_filename(line.strip())
                if candidate and candidate != "index.txt":
                    names.append(candidate)
    except OSError:
        names = []

    if not names:
        # Fall back to globbing the confirmed file pattern.
        try:
            if CORPUS_DIR.is_dir():
                for p in CORPUS_DIR.glob("treasury_bulletin_*.txt"):
                    candidate = _safe_filename(p.name)
                    if candidate:
                        names.append(candidate)
        except OSError:
            names = []

    # Dedup + sort chronologically (filename sort == chronological here).
    return sorted(set(names))


def _read_text(filename: str) -> Optional[str]:
    """Read a validated corpus file, or None if missing / unreadable / huge."""
    safe = _safe_filename(filename)
    if not safe:
        return None
    path = CORPUS_DIR / safe
    try:
        if not path.is_file():
            return None
        if path.stat().st_size > MAX_FILE_BYTES:
            # Read only the cap to stay bounded rather than refuse outright.
            with path.open("r", encoding="utf-8", errors="replace") as fh:
                return fh.read(MAX_FILE_BYTES)
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _document_label(filename: str) -> str:
    """Human-readable label, e.g. 'Treasury Bulletin March 1953'."""
    year, month = _year_month_from_name(filename)
    if year and month:
        return f"Treasury Bulletin {MONTH_NUMBER_TO_NAME[month]} {year}"
    return filename


def _candidate_files_from_filters(
    years: Optional[list[int]],
    months: Optional[list[int]],
    candidate_files: Optional[list[str]],
) -> tuple[list[str], list[str]]:
    """Stage 1: resolve candidate files from plain structured filters only.

    Order (per spec):
      1. explicit candidate_files (validated),
      2. years/months (cartesian when both; all 12 months when only years),
      3. every file in the corpus.

    Returns (files, warnings). No natural-language parsing happens here.
    """
    warnings: list[str] = []

    # 1. explicit filenames.
    if candidate_files:
        resolved: list[str] = []
        for name in candidate_files:
            safe = _safe_filename(name)
            if safe and safe != "index.txt":
                resolved.append(safe)
            else:
                warnings.append(f"ignored invalid filename: {name!r}")
        files = sorted(set(resolved))
        if files:
            return files[:MAX_CANDIDATE_FILES], warnings
        warnings.append("no valid candidate_files; falling back to filters")

    # 2. years / months.
    clean_years: list[int] = []
    if years:
        for y in years:
            try:
                yi = int(y)
            except (TypeError, ValueError):
                continue
            if 1939 <= yi <= 2025:
                clean_years.append(yi)

    clean_months: list[int] = []
    if months:
        for mo in months:
            try:
                mi = int(mo)
            except (TypeError, ValueError):
                continue
            if 1 <= mi <= 12:
                clean_months.append(mi)

    if clean_years:
        use_months = clean_months if clean_months else list(range(1, 13))
        built = sorted(
            {
                f"treasury_bulletin_{y:04d}_{m:02d}.txt"
                for y in clean_years
                for m in use_months
            }
        )
        return built[:MAX_CANDIDATE_FILES], warnings

    if clean_months and not clean_years:
        # Months given but no year: narrow the full corpus to those months.
        all_files = _list_all_corpus_files()
        filtered = [
            f
            for f in all_files
            if _year_month_from_name(f)[1] in clean_months
        ]
        warnings.append(
            "months given without years; filtered full corpus by month"
        )
        return filtered[:MAX_CANDIDATE_FILES], warnings

    # 3. everything.
    return _list_all_corpus_files()[:MAX_CANDIDATE_FILES], warnings


# --- BM25 + chunking --------------------------------------------------------


def _tokenize(text: str) -> list[str]:
    """Lowercase, keep alphanumeric tokens, drop common stopwords.

    Financial terms and numbers are intentionally retained.
    """
    return [
        tok
        for tok in _TOKEN_RE.findall(text.lower())
        if tok not in _STOPWORDS
    ]


def _chunk_text(
    text: str, chunk_chars: int, overlap_chars: int
) -> list[tuple[int, int, str]]:
    """Split text into overlapping character windows.

    Returns a list of (char_start, char_end, chunk_text). Overlap is clamped to
    be strictly smaller than the chunk size to guarantee forward progress.
    """
    if chunk_chars <= 0:
        chunk_chars = DEFAULT_CHUNK_CHARS
    if overlap_chars < 0:
        overlap_chars = 0
    if overlap_chars >= chunk_chars:
        overlap_chars = chunk_chars // 4

    chunks: list[tuple[int, int, str]] = []
    n = len(text)
    if n == 0:
        return chunks
    step = chunk_chars - overlap_chars
    start = 0
    while start < n:
        end = min(start + chunk_chars, n)
        chunks.append((start, end, text[start:end]))
        if end >= n:
            break
        start += step
    return chunks


def _line_offsets(text: str) -> list[int]:
    """Character offset at which each line starts (for char->line mapping)."""
    offsets = [0]
    for i, ch in enumerate(text):
        if ch == "\n":
            offsets.append(i + 1)
    return offsets


def _char_to_line(offsets: list[int], char_pos: int) -> int:
    """1-based line number for a character offset (binary search)."""
    import bisect

    idx = bisect.bisect_right(offsets, char_pos) - 1
    return max(1, idx + 1)


def _has_markdown_table(text: str) -> bool:
    """True if the chunk looks like it contains a Markdown table."""
    if "|" not in text:
        return False
    for line in text.splitlines():
        stripped = line.strip()
        if "|" in stripped and set(stripped) <= set("|-: "):
            if "-" in stripped:
                return True
    return False


def _detect_page(text: str, preamble: str) -> Optional[int]:
    """Best-effort source page-number detection for grounding.

    Scans the chunk plus a small window before it for common PDF-to-text page
    markers: 'Page N', form-feed-adjacent standalone numbers, or 'p. N'. Returns
    the LAST such marker at or before the chunk start (closest preceding page
    boundary), or None when nothing convincing is found.
    """
    page: Optional[int] = None

    # 1. Standalone number lines near a form-feed in the preamble/chunk.
    combined = preamble + text
    for raw_line in combined.split("\f"):
        # Look at the first/last non-empty line of each form-feed section.
        for line in raw_line.splitlines():
            m = _STANDALONE_PAGE_RE.match(line)
            if m:
                val = int(m.group(1))
                if 1 <= val <= 5000:
                    page = val

    # 2. Explicit "Page N" / "p. N" labels (prefer the latest in preamble).
    label_matches = list(_PAGE_LABEL_RE.finditer(preamble)) + list(
        _PAGE_LABEL_RE.finditer(text)
    )
    if label_matches:
        val = int(label_matches[-1].group(1))
        if 1 <= val <= 5000:
            page = val

    return page


def _bm25_score_chunks(
    query: str,
    chunks: list[dict],
    years: Optional[list[int]],
) -> None:
    """Compute BM25 (+boosts) for each chunk in place, setting chunk['score'].

    chunks: list of dicts each containing at least 'tokens' (list[str]),
    'text' (str), 'year' (int|None). Scores are written back onto each dict.
    """
    k1 = 1.5
    b = 0.75

    query_terms = _tokenize(query)
    query_term_set = set(query_terms)

    n_docs = len(chunks)
    if n_docs == 0:
        return

    # Document frequency per query term.
    df: dict[str, int] = {}
    total_len = 0
    for ch in chunks:
        tokens = ch["tokens"]
        total_len += len(tokens)
        present = set(tokens)
        for term in query_term_set:
            if term in present:
                df[term] = df.get(term, 0) + 1
    avgdl = (total_len / n_docs) if n_docs else 0.0

    idf: dict[str, float] = {}
    for term in query_term_set:
        d = df.get(term, 0)
        idf[term] = math.log(1 + (n_docs - d + 0.5) / (d + 0.5))

    query_phrase = query.strip().lower()
    year_set = {int(y) for y in years} if years else set()

    for ch in chunks:
        tokens = ch["tokens"]
        dl = len(tokens)
        tf: dict[str, int] = {}
        for tok in tokens:
            if tok in query_term_set:
                tf[tok] = tf.get(tok, 0) + 1

        score = 0.0
        for term in query_term_set:
            f = tf.get(term, 0)
            if f == 0:
                continue
            denom = f + k1 * (1 - b + b * (dl / avgdl if avgdl else 0))
            score += idf[term] * (f * (k1 + 1)) / denom if denom else 0.0

        lowered = ch["text"].lower()

        # Exact full-phrase boost.
        if query_phrase and len(query_phrase) > 2 and query_phrase in lowered:
            score += 5.0

        # Quoted-phrase boosts (any "..." segments in the query).
        for quoted in re.findall(r'"([^"]+)"', query):
            q = quoted.strip().lower()
            if q and q in lowered:
                score += 3.0

        # Markdown-table boost.
        if ch.get("has_table"):
            score += 1.0

        # Numeric-content boost (tables of figures are usually the evidence).
        if _NUMBER_RE.search(ch["text"]):
            score += 0.5

        # Year-preference boost.
        if year_set and ch.get("year") in year_set:
            score += 1.0

        ch["score"] = round(score, 4)


# --- tools ------------------------------------------------------------------


@treasury_search_app.tool()
def corpus_status() -> dict:
    """Report whether the corpus is mounted and how many files are present.

    Useful for verifying at runtime that ``/app/corpus`` is actually populated
    (the path/format is confirmed by the task, but a specific eval run could
    still mount it differently or be missing files).
    """
    exists = CORPUS_DIR.is_dir()
    index_exists = INDEX_FILE.is_file()
    files = _list_all_corpus_files() if exists else []
    return {
        "corpus_dir": str(CORPUS_DIR),
        "exists": exists,
        "index_exists": index_exists,
        "num_txt_files": len(files),
        "sample_files": files[:10],
    }


@treasury_search_app.tool()
def list_corpus_files(
    year: Optional[int] = None,
    month: Optional[int] = None,
    limit: int = 1000,
) -> dict:
    """List corpus filenames, optionally filtered by year and/or month.

    Args:
        year: Optional calendar year filter.
        month: Optional month (1-12) filter.
        limit: Maximum number of filenames to return.

    Returns:
        ``{"files": [...], "count": <int>, "filtered_by": {...}}``.
    """
    files = _list_all_corpus_files()

    if year is not None:
        try:
            year_i = int(year)
            files = [f for f in files if _year_month_from_name(f)[0] == year_i]
        except (TypeError, ValueError):
            pass
    if month is not None:
        try:
            month_i = int(month)
            files = [f for f in files if _year_month_from_name(f)[1] == month_i]
        except (TypeError, ValueError):
            pass

    try:
        lim = max(0, int(limit))
    except (TypeError, ValueError):
        lim = 1000

    sliced = files[:lim]
    return {
        "files": sliced,
        "count": len(sliced),
        "filtered_by": {"year": year, "month": month},
    }


@treasury_search_app.tool()
def read_corpus_index(max_chars: int = 10000) -> dict:
    """Return the first ``max_chars`` of ``/app/corpus/index.txt``.

    Returns ``{"exists": bool, "text": str, "chars_returned": int}``.
    """
    try:
        cap = max(0, int(max_chars))
    except (TypeError, ValueError):
        cap = 10000

    if not INDEX_FILE.is_file():
        return {"exists": False, "text": "", "chars_returned": 0}
    try:
        text = INDEX_FILE.read_text(encoding="utf-8", errors="replace")[:cap]
    except OSError:
        return {"exists": False, "text": "", "chars_returned": 0}
    return {"exists": True, "text": text, "chars_returned": len(text)}


@treasury_search_app.tool()
def read_file_head(filename: str, n_lines: int = 120) -> dict:
    """Return the first ``n_lines`` lines of a corpus file.

    Only basenames matching ``treasury_bulletin_YYYY_MM.txt`` or ``index.txt``
    are allowed (path traversal is rejected).

    Returns ``{"filename", "exists", "text", "lines_returned"}``.
    """
    safe = _safe_filename(filename)
    if not safe:
        return {
            "filename": filename,
            "exists": False,
            "text": "",
            "lines_returned": 0,
        }

    if safe == "index.txt":
        text = INDEX_FILE.read_text(encoding="utf-8", errors="replace") \
            if INDEX_FILE.is_file() else None
    else:
        text = _read_text(safe)

    if text is None:
        return {
            "filename": safe,
            "exists": False,
            "text": "",
            "lines_returned": 0,
        }

    try:
        n = max(0, int(n_lines))
    except (TypeError, ValueError):
        n = 120
    lines = text.splitlines()[:n]
    return {
        "filename": safe,
        "exists": True,
        "text": "\n".join(lines),
        "lines_returned": len(lines),
    }


def _read_file_context(
    filename: str,
    query: str,
    window_lines: int,
    max_matches: int,
) -> dict:
    """Plain implementation of read_file_context (shared with number extract)."""
    safe = _safe_filename(filename)
    if not safe or safe == "index.txt":
        return {"filename": filename, "query": query, "matches": []}

    text = _read_text(safe)
    if text is None:
        return {"filename": safe, "query": query, "matches": []}

    terms = set(_tokenize(query))
    phrase = query.strip().lower()
    lines = text.splitlines()

    try:
        win = max(0, int(window_lines))
    except (TypeError, ValueError):
        win = 25
    try:
        cap = max(0, int(max_matches))
    except (TypeError, ValueError):
        cap = 5

    matches: list[dict] = []
    used_centers: list[int] = []
    for i, line in enumerate(lines):
        low = line.lower()
        hit = (phrase and len(phrase) > 2 and phrase in low) or any(
            t in low for t in terms
        )
        if not hit:
            continue
        # Avoid heavily overlapping windows around adjacent matched lines.
        if any(abs(i - c) < max(1, win // 2) for c in used_centers):
            continue
        start = max(0, i - win)
        end = min(len(lines), i + win + 1)
        matches.append(
            {
                "start_line": start + 1,
                "end_line": end,
                "matched_line": i + 1,
                "text": "\n".join(lines[start:end]),
            }
        )
        used_centers.append(i)
        if len(matches) >= cap:
            break

    return {"filename": safe, "query": query, "matches": matches}


@treasury_search_app.tool()
def read_file_context(
    filename: str,
    query: str,
    window_lines: int = 25,
    max_matches: int = 5,
) -> dict:
    """Return windows of lines around query matches in a corpus file.

    Handy for inspecting tables surrounding relevant terms.

    Args:
        filename: A ``treasury_bulletin_YYYY_MM.txt`` basename.
        query: Free-text terms; matched line-by-line (any token or full phrase).
        window_lines: Context lines to include on each side of a match.
        max_matches: Maximum number of match windows to return.

    Returns:
        ``{"filename", "query", "matches": [{start_line, end_line,
        matched_line, text}]}``.
    """
    return _read_file_context(filename, query, window_lines, max_matches)


@treasury_search_app.tool()
def search_corpus(
    query: str,
    years: Optional[list[int]] = None,
    months: Optional[list[int]] = None,
    candidate_files: Optional[list[str]] = None,
    top_k: int = 10,
    chunk_chars: int = DEFAULT_CHUNK_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> dict:
    """Two-stage BM25 search over the Treasury Bulletin corpus.

    Stage 1 resolves candidate files from ALREADY-RESOLVED structured filters
    only (explicit ``candidate_files``, or plain ``years``/``months`` lists);
    it never parses a raw question. Stage 2 chunks those files and scores the
    chunks with a self-contained BM25 plus light boosts (exact phrase, quoted
    phrase, Markdown tables, numeric content, preferred years).

    Args:
        query: Search terms (NOT a date-bearing natural-language question for
            filtering — resolve dates via the date_filter server first).
        years: Optional already-resolved year filter.
        months: Optional already-resolved month filter.
        candidate_files: Optional explicit list of corpus filenames.
        top_k: Number of top chunks to return.
        chunk_chars: Chunk size in characters.
        overlap_chars: Overlap between consecutive chunks in characters.

    Returns:
        See the spec's return schema (query, num_candidate_files,
        num_chunks_scored, results[...]).
    """
    if not isinstance(query, str) or not query.strip():
        return {
            "error": "query is required and must be a non-empty string",
            "query": query,
            "num_candidate_files": 0,
            "num_chunks_scored": 0,
            "results": [],
        }

    if not _tokenize(query):
        return {
            "error": (
                "query contains no searchable terms after tokenization "
                "(only stopwords/punctuation)"
            ),
            "query": query,
            "num_candidate_files": 0,
            "num_chunks_scored": 0,
            "results": [],
        }

    if not CORPUS_DIR.is_dir():
        return {
            "error": f"corpus directory not found: {CORPUS_DIR}",
            "query": query,
            "num_candidate_files": 0,
            "num_chunks_scored": 0,
            "results": [],
        }

    try:
        k = max(1, int(top_k))
    except (TypeError, ValueError):
        k = 10
    try:
        cc = int(chunk_chars)
    except (TypeError, ValueError):
        cc = DEFAULT_CHUNK_CHARS
    try:
        oc = int(overlap_chars)
    except (TypeError, ValueError):
        oc = DEFAULT_OVERLAP_CHARS

    files, warnings = _candidate_files_from_filters(years, months, candidate_files)

    # Stage 2: build and score chunks.
    all_chunks: list[dict] = []
    for filename in files:
        text = _read_text(filename)
        if text is None:
            continue
        year, month = _year_month_from_name(filename)
        offsets = _line_offsets(text)
        raw_chunks = _chunk_text(text, cc, oc)
        for idx, (cstart, cend, chunk_text) in enumerate(raw_chunks):
            preamble = text[max(0, cstart - 400):cstart]
            all_chunks.append(
                {
                    "filename": filename,
                    "year": year,
                    "month": month,
                    "chunk_id": idx,
                    "char_start": cstart,
                    "char_end": cend,
                    "approx_line_start": _char_to_line(offsets, cstart),
                    "approx_line_end": _char_to_line(offsets, max(cstart, cend - 1)),
                    "text": chunk_text,
                    "tokens": _tokenize(chunk_text),
                    "has_table": _has_markdown_table(chunk_text),
                    "page": _detect_page(chunk_text, preamble),
                    "score": 0.0,
                }
            )

    _bm25_score_chunks(query, all_chunks, years)

    ranked = sorted(all_chunks, key=lambda c: c["score"], reverse=True)
    top = [c for c in ranked if c["score"] > 0][:k]
    if not top:
        # Even with zero positive scores, return the best-effort top_k so the
        # agent still gets candidate passages rather than nothing.
        top = ranked[:k]

    results = []
    for c in top:
        results.append(
            {
                "document": _document_label(c["filename"]),
                "filename": c["filename"],
                "year": c["year"],
                "month": c["month"],
                "page": c["page"],
                "chunk_id": c["chunk_id"],
                "score": c["score"],
                "char_start": c["char_start"],
                "char_end": c["char_end"],
                "approx_line_start": c["approx_line_start"],
                "approx_line_end": c["approx_line_end"],
                "text": c["text"][:MAX_RESULT_TEXT_CHARS],
            }
        )

    out = {
        "query": query,
        "num_candidate_files": len(files),
        "num_chunks_scored": len(all_chunks),
        "results": results,
    }
    if warnings:
        out["warnings"] = warnings
    return out


def _normalize_number(raw: str) -> Optional[float]:
    """Convert a matched numeric string to a float, or None if not possible.

    Handles thousands separators, dollar signs, parentheses-as-negative, and
    trailing percent signs (percent kept as its face value, e.g. 12.34% -> 12.34).
    """
    s = raw.strip()
    negative = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = s.replace("$", "").replace(",", "").replace("%", "").strip()
    if not s or s in {"-", "."}:
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if negative else val


@treasury_search_app.tool()
def extract_numbers_near_query(
    filename: str,
    query: str,
    window_lines: int = 30,
    max_numbers: int = 100,
) -> dict:
    """Extract numeric values from the lines surrounding query matches.

    Reuses read_file_context to locate relevant table regions, then pulls out
    candidate figures (1,234 / 12.34 / (1,234) / $1,234 / 1,234.5 / 12.34%).

    Args:
        filename: A ``treasury_bulletin_YYYY_MM.txt`` basename.
        query: Free-text terms identifying the table/region of interest.
        window_lines: Context lines on each side of a match to scan.
        max_numbers: Maximum number of extracted values to return.

    Returns:
        ``{"filename", "query", "numbers": [{raw, value, line, snippet}]}``.
    """
    safe = _safe_filename(filename)
    if not safe or safe == "index.txt":
        return {"filename": filename, "query": query, "numbers": []}

    try:
        cap = max(0, int(max_numbers))
    except (TypeError, ValueError):
        cap = 100

    context = _read_file_context(safe, query, window_lines, max_matches=10)

    numbers: list[dict] = []
    seen: set[tuple[str, int]] = set()
    for match in context["matches"]:
        start_line = match["start_line"]
        for offset, line in enumerate(match["text"].splitlines()):
            line_no = start_line + offset
            for num_match in _NUMBER_RE.finditer(line):
                raw = num_match.group(0)
                # Skip bare single digits that are unlikely real figures unless
                # they carry a $, %, comma, or decimal.
                if (
                    len(raw.strip("()$%")) <= 1
                    and not any(c in raw for c in ",.%$")
                ):
                    continue
                key = (raw, line_no)
                if key in seen:
                    continue
                seen.add(key)
                snippet = line.strip()
                numbers.append(
                    {
                        "raw": raw,
                        "value": _normalize_number(raw),
                        "line": line_no,
                        "snippet": snippet[:200],
                    }
                )
                if len(numbers) >= cap:
                    return {
                        "filename": safe,
                        "query": query,
                        "numbers": numbers,
                    }

    return {"filename": safe, "query": query, "numbers": numbers}


if __name__ == "__main__":
    treasury_search_app.run()
