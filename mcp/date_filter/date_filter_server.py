"""date_filter MCP server for the OfficeQA / Treasury Bulletin benchmark.

This server owns ALL natural-language date parsing for the MCP setup. It turns
free-text OfficeQA questions into structured date hints and candidate Treasury
Bulletin filenames (``treasury_bulletin_YYYY_MM.txt``).

Responsibilities (see "Role separation" in the project spec):
  - Parse years, months, month names, fiscal years, ranges, quarters, decades.
  - Build candidate filenames for the agent to feed into treasury_search.

The treasury_search server must NEVER reimplement any of this logic; it only
receives already-resolved integers / lists / filenames.

Standard library + fastmcp only. No network calls at runtime. Deterministic.
"""

from __future__ import annotations

import re
from typing import Optional

from fastmcp import FastMCP

date_filter_app = FastMCP("date_filter")

# Corpus spans these calendar years (Treasury Bulletin began 1939).
CORPUS_MIN_YEAR = 1939
CORPUS_MAX_YEAR = 2025

# Month name / abbreviation -> month number. Covers full names and common
# abbreviations (with and without trailing period handled by normalization).
MONTH_LOOKUP: dict[str, int] = {
    "january": 1, "jan": 1,
    "february": 2, "feb": 2,
    "march": 3, "mar": 3,
    "april": 4, "apr": 4,
    "may": 5,
    "june": 6, "jun": 6,
    "july": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10,
    "november": 11, "nov": 11,
    "december": 12, "dec": 12,
}

MONTH_NUMBER_TO_NAME: dict[int, str] = {
    1: "january", 2: "february", 3: "march", 4: "april", 5: "may", 6: "june",
    7: "july", 8: "august", 9: "september", 10: "october", 11: "november",
    12: "december",
}

# Calendar quarter -> months.
CALENDAR_QUARTERS: dict[int, list[int]] = {
    1: [1, 2, 3], 2: [4, 5, 6], 3: [7, 8, 9], 4: [10, 11, 12],
}

# Regex building blocks.
_YEAR_RE = re.compile(r"\b(19[3-9]\d|20[0-2]\d)\b")
_MONTH_TOKEN_RE = re.compile(
    r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t)?(?:ember)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\b",
    re.IGNORECASE,
)


def _valid_year(year: int) -> bool:
    return CORPUS_MIN_YEAR <= year <= CORPUS_MAX_YEAR


def _valid_month(month: int) -> bool:
    return 1 <= month <= 12


def _filename(year: int, month: int) -> str:
    """Build the canonical corpus filename for a year/month."""
    return f"treasury_bulletin_{year:04d}_{month:02d}.txt"


def _build_cartesian_files(years: list[int], months: list[int]) -> list[str]:
    """Cartesian product of years x months -> sorted unique filenames.

    Empty ``months`` means all 12 months for each year.
    """
    use_months = months if months else list(range(1, 13))
    files: set[str] = set()
    for y in years:
        if not _valid_year(y):
            continue
        for m in use_months:
            if _valid_month(m):
                files.add(_filename(y, m))
    return sorted(files)


def _fiscal_year_files(fy: int) -> tuple[list[str], str]:
    """Candidate files + note for one U.S. federal fiscal year.

    The fiscal-year definition changed over the corpus span:
      - FY <= 1976: Jul 1 (fy-1) .. Jun 30 (fy).
      - FY >= 1977: Oct 1 (fy-1) .. Sep 30 (fy).
      - FY 1976 itself is the transition year; include BOTH boundary
        interpretations rather than guessing.
    """
    months_by_year: dict[int, list[int]] = {}

    def add(year: int, month: int) -> None:
        if _valid_year(year) and _valid_month(month):
            months_by_year.setdefault(year, []).append(month)

    if fy <= 1976:
        # Jul (fy-1) .. Dec (fy-1)
        for m in range(7, 13):
            add(fy - 1, m)
        # Jan (fy) .. Jun (fy)
        for m in range(1, 7):
            add(fy, m)
        note = (
            f"pre-1977 FY ran Jul-Jun; spans calendar {fy - 1}-{fy}"
        )
        if fy == 1976:
            # Transition year ambiguity: also include the post-1977 style
            # window plus the Jul-Sep 1976 transition quarter.
            for m in range(10, 13):
                add(fy - 1, m)
            for m in range(1, 10):
                add(fy, m)
            note = (
                "FY1976 is the transition year (one-time Jul-Sep 1976 "
                "transition quarter); including both Jul-Jun and Oct-Sep "
                "boundary interpretations"
            )
    else:
        # Oct (fy-1) .. Dec (fy-1)
        for m in range(10, 13):
            add(fy - 1, m)
        # Jan (fy) .. Sep (fy)
        for m in range(1, 10):
            add(fy, m)
        note = f"1977+ FY ran Oct-Sep; spans calendar {fy - 1}-{fy}"

    files: set[str] = set()
    for year, months in months_by_year.items():
        for m in months:
            files.add(_filename(year, m))
    return sorted(files), note


def _normalize_month_text(month_text: str) -> str:
    """Lowercase and strip a single trailing period (e.g. 'Mar.' -> 'mar')."""
    return month_text.strip().lower().rstrip(".")


@date_filter_app.tool()
def parse_month_name(month_text: str) -> dict:
    """Resolve a month name or abbreviation to a month number.

    Args:
        month_text: A month name or abbreviation, e.g. "March", "Mar", "mar.".

    Returns:
        ``{"input": <raw>, "month": <int or None>, "normalized": <str>}``.
        ``month`` is None when the text is not a recognized month.
    """
    raw = month_text if isinstance(month_text, str) else str(month_text)
    normalized = _normalize_month_text(raw)
    return {
        "input": raw,
        "month": MONTH_LOOKUP.get(normalized),
        "normalized": normalized,
    }


def _candidate_files_for_years(
    years: list[int], months: Optional[list[int]] = None
) -> dict:
    """Plain (non-tool) implementation shared by the tool + extract_date_hints.

    Keeping the logic in a plain function avoids depending on FastMCP internals
    to invoke a tool from within another tool.
    """
    try:
        clean_years = [int(y) for y in (years or [])]
    except (TypeError, ValueError):
        return {
            "candidate_files": [],
            "count": 0,
            "notes": "years must be a list of integers",
        }

    clean_months: list[int] = []
    if months:
        try:
            clean_months = [int(m) for m in months]
        except (TypeError, ValueError):
            return {
                "candidate_files": [],
                "count": 0,
                "notes": "months must be a list of integers",
            }

    valid_years = [y for y in clean_years if _valid_year(y)]
    dropped_years = [y for y in clean_years if not _valid_year(y)]
    valid_months = [m for m in clean_months if _valid_month(m)]
    dropped_months = [m for m in clean_months if not _valid_month(m)]

    files = _build_cartesian_files(valid_years, valid_months)

    note_parts: list[str] = []
    if not valid_years:
        note_parts.append("no valid years supplied")
    if not clean_months:
        note_parts.append("no months given -> all 12 months per year")
    if dropped_years:
        note_parts.append(f"dropped out-of-range years {dropped_years}")
    if dropped_months:
        note_parts.append(f"dropped out-of-range months {dropped_months}")

    return {
        "candidate_files": files,
        "count": len(files),
        "notes": "; ".join(note_parts) if note_parts else "ok",
    }


@date_filter_app.tool()
def candidate_files_for_years(
    years: list[int], months: Optional[list[int]] = None
) -> dict:
    """Build candidate corpus filenames from explicit years (and months).

    This is the single filename-building helper that extract_date_hints reuses
    for its cartesian-product cases.

    Args:
        years: Calendar years (1939-2025). Out-of-range values are dropped.
        months: Optional month numbers (1-12). When None/empty, all 12 months
            of each year are returned.

    Returns:
        ``{"candidate_files": [...], "count": <int>, "notes": <str>}``.
    """
    return _candidate_files_for_years(years, months)


# --- natural-language parsing helpers for extract_date_hints ----------------


def _find_years(text: str) -> list[int]:
    """All distinct four-digit corpus years mentioned, in first-seen order."""
    seen: list[int] = []
    for match in _YEAR_RE.finditer(text):
        year = int(match.group(1))
        if _valid_year(year) and year not in seen:
            seen.append(year)
    return seen


def _find_decades(text: str) -> list[tuple[int, int]]:
    """Decade shorthand like '1950s' -> (1950, 1959) ranges."""
    ranges: list[tuple[int, int]] = []
    for match in re.finditer(r"\b(19[3-9]0|20[0-2]0)s\b", text, re.IGNORECASE):
        start = int(match.group(1))
        end = min(start + 9, CORPUS_MAX_YEAR)
        if _valid_year(start):
            ranges.append((start, end))
    return ranges


def _find_year_ranges(text: str) -> list[tuple[int, int]]:
    """Detect year ranges: 'from X to Y', 'between X and Y', 'X-Y', 'X–Y'.

    Returns normalized (start, end) tuples with start <= end.
    """
    ranges: list[tuple[int, int]] = []
    year = r"(19[3-9]\d|20[0-2]\d)"

    patterns = [
        rf"\bfrom\s+{year}\s+(?:to|through|thru|till|until|-|–|—)\s+{year}\b",
        rf"\bbetween\s+{year}\s+and\s+{year}\b",
        rf"\b{year}\s*(?:-|–|—|/)\s*{year}\b",
        rf"\b{year}\s+(?:to|through|thru|till|until)\s+{year}\b",
    ]
    for pat in patterns:
        for match in re.finditer(pat, text, re.IGNORECASE):
            a, b = int(match.group(1)), int(match.group(2))
            if _valid_year(a) and _valid_year(b):
                lo, hi = (a, b) if a <= b else (b, a)
                if (lo, hi) not in ranges:
                    ranges.append((lo, hi))
    return ranges


def _find_fiscal_years(text: str) -> list[int]:
    """Detect 'fiscal year YYYY', 'FY YYYY', 'FYYYYY'."""
    fys: list[int] = []
    pat = re.compile(
        r"\b(?:fiscal\s+year|fiscal|fy)\s*[-:]?\s*(19[3-9]\d|20[0-2]\d)\b",
        re.IGNORECASE,
    )
    for match in pat.finditer(text):
        fy = int(match.group(1))
        if _valid_year(fy) and fy not in fys:
            fys.append(fy)
    return fys


def _find_quarters(text: str) -> list[tuple[int, int, bool]]:
    """Detect quarter mentions tied to a year.

    Returns (quarter_number, year, is_fiscal) tuples. Only quarters that can be
    associated with a nearby year are returned (a bare 'Q1' with no year is
    ambiguous and skipped here; the broader year/month logic still applies).
    """
    results: list[tuple[int, int, bool]] = []
    ordinal = {
        "first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3,
        "fourth": 4, "4th": 4,
    }
    year = r"(19[3-9]\d|20[0-2]\d)"

    # "Q1 1953", "Q1 of 1953", "fiscal Q1 1953"
    for match in re.finditer(
        rf"\b(fiscal\s+)?q([1-4])\s+(?:of\s+)?{year}\b", text, re.IGNORECASE
    ):
        is_fiscal = bool(match.group(1))
        results.append((int(match.group(2)), int(match.group(3)), is_fiscal))

    # "first quarter of 1953", "the fiscal first quarter of 1953"
    for match in re.finditer(
        rf"\b(fiscal\s+)?(first|second|third|fourth|1st|2nd|3rd|4th)\s+"
        rf"quarter\s+(?:of\s+)?{year}\b",
        text,
        re.IGNORECASE,
    ):
        is_fiscal = bool(match.group(1))
        q = ordinal.get(match.group(2).lower())
        if q:
            results.append((q, int(match.group(3)), is_fiscal))

    return results


def _quarter_to_year_months(
    quarter: int, year: int, is_fiscal: bool
) -> list[tuple[int, int]]:
    """Map a quarter+year to concrete (calendar_year, month) pairs.

    Calendar quarters stay within the given year. Fiscal quarters use the
    pre-1977 Jul-start convention (the dominant case across this corpus): the
    first two fiscal quarters fall in the PRIOR calendar year (fy-1).
    """
    if not is_fiscal:
        return [(year, m) for m in CALENDAR_QUARTERS[quarter]]
    fiscal_quarter_months = {
        1: [(year - 1, 7), (year - 1, 8), (year - 1, 9)],
        2: [(year - 1, 10), (year - 1, 11), (year - 1, 12)],
        3: [(year, 1), (year, 2), (year, 3)],
        4: [(year, 4), (year, 5), (year, 6)],
    }
    return fiscal_quarter_months[quarter]


def _split_year_month_segments(text: str) -> list[tuple[list[int], list[int]]]:
    """Detect case 7: each year carrying its OWN distinct month(s).

    Strategy: walk the text token-by-token over month/year matches in order.
    Group consecutive month tokens, then attach them to the next year token(s)
    that immediately follow (e.g. "March 1940, and June and December 1953").

    Returns a list of (months, years) groupings. Only returns a non-empty,
    "non-uniform" result when at least two groups exist with DIFFERENT month
    sets — otherwise the caller should fall back to the uniform cartesian
    cases. This keeps cases 3/5/6 out of the year_month_pairs path.
    """
    # Collect month and year matches with positions.
    tokens: list[tuple[int, str, int]] = []  # (pos, kind, value)
    for m in _MONTH_TOKEN_RE.finditer(text):
        month = MONTH_LOOKUP.get(_normalize_month_text(m.group(0)))
        if month:
            tokens.append((m.start(), "month", month))
    for m in _YEAR_RE.finditer(text):
        year = int(m.group(1))
        if _valid_year(year):
            tokens.append((m.start(), "year", year))
    tokens.sort(key=lambda t: t[0])

    # Build groups: a run of months followed by a run of years.
    groups: list[tuple[list[int], list[int]]] = []
    cur_months: list[int] = []
    cur_years: list[int] = []
    state = "months"  # collecting months, then years

    def flush() -> None:
        if cur_months and cur_years:
            groups.append((sorted(set(cur_months)), list(dict.fromkeys(cur_years))))

    for _pos, kind, value in tokens:
        if kind == "month":
            if state == "years":
                # New group begins; flush the previous month->year group.
                flush()
                cur_months.clear()
                cur_years.clear()
                state = "months"
            cur_months.append(value)
        else:  # year
            state = "years"
            cur_years.append(value)
    flush()

    # Only treat as non-uniform (case 7) if there are >=2 groups whose month
    # sets are not all identical.
    if len(groups) >= 2:
        month_sets = {tuple(g[0]) for g in groups}
        if len(month_sets) > 1:
            return groups
    return []


@date_filter_app.tool()
def extract_date_hints(question: str) -> dict:
    """Parse an OfficeQA question into structured date hints + candidate files.

    This is the ONLY place natural-language date phrasing is parsed. It handles
    plain years, month names, multi-year/month combinations, non-uniform
    per-year months, year ranges, fiscal years, quarters, and decade shorthand
    (see the project spec's enumerated cases 0-15). When unsure, it errs toward
    the broader (more inclusive) set of candidate files and explains in notes.

    Args:
        question: A natural-language OfficeQA question.

    Returns:
        A structured dict (see schema in the project spec) including
        ``candidate_files`` ready to pass to treasury_search.search_corpus.
    """
    if not isinstance(question, str):
        question = str(question)
    text = question
    notes: list[str] = []

    # --- detection ---------------------------------------------------------
    year_ranges = _find_year_ranges(text)
    decade_ranges = _find_decades(text)
    fiscal_years = _find_fiscal_years(text)
    quarters = _find_quarters(text)

    # Years that participate in ranges/fiscal/quarters should not also be
    # mis-read as standalone years where it would distort results. We keep the
    # flat year list as "all detected years" for transparency, but range
    # expansion drives candidate generation.
    all_years = _find_years(text)

    # Months mentioned anywhere (flat).
    months: list[int] = []
    for m in _MONTH_TOKEN_RE.finditer(text):
        num = MONTH_LOOKUP.get(_normalize_month_text(m.group(0)))
        if num and num not in months:
            months.append(num)

    # Year/month pairing (case 7).
    ym_groups = _split_year_month_segments(text)
    year_month_pairs: list[dict] = []
    if ym_groups:
        for grp_months, grp_years in ym_groups:
            for y in grp_years:
                year_month_pairs.append({"year": y, "months": sorted(grp_months)})
        notes.append("non-uniform per-year months detected (case 7)")

    # Combine explicit + decade ranges.
    combined_ranges = list(year_ranges) + list(decade_ranges)
    date_ranges = [
        {"start_year": lo, "end_year": hi} for lo, hi in combined_ranges
    ]
    if year_ranges:
        notes.append("year range(s) detected")
    if decade_ranges:
        notes.append("decade shorthand expanded to a range")

    # Expand ranges into individual years and merge into the flat year list.
    range_years: list[int] = []
    for lo, hi in combined_ranges:
        for y in range(lo, hi + 1):
            if _valid_year(y):
                range_years.append(y)

    flat_years = list(dict.fromkeys(all_years + range_years))

    # --- emptiness / case 0 ------------------------------------------------
    nothing_detected = (
        not flat_years
        and not months
        and not fiscal_years
        and not date_ranges
        and not quarters
    )
    if nothing_detected:
        return {
            "years": [],
            "months": [],
            "month_names": [],
            "fiscal_years": [],
            "fiscal_year_calendar_months": [],
            "date_ranges": [],
            "year_month_pairs": [],
            "all_individual_calendar_months": False,
            "month_only_no_year": False,
            "no_date_hint_found": True,
            "candidate_files": [],
            "notes": (
                "no date mentioned; downstream retrieval should skip date "
                "filtering and run treasury_search across the full corpus"
            ),
        }

    # --- quarter handling (case 15) ----------------------------------------
    # Quarters map to concrete (calendar_year, month) pairs. Years that appear
    # ONLY because of a quarter mention should be narrowed to the quarter's
    # months, not broad-expanded to all 12 months. Years mentioned outside a
    # quarter context still expand normally.
    quarter_pairs: list[tuple[int, int]] = []  # (calendar_year, month)
    quarter_years: set[int] = set()
    for q, q_year, is_fiscal in quarters:
        quarter_years.add(q_year)
        for eff_year, m in _quarter_to_year_months(q, q_year, is_fiscal):
            if _valid_year(eff_year) and _valid_month(m):
                quarter_pairs.append((eff_year, m))
    if quarters:
        notes.append("quarter mention(s) mapped to months")

    # Years eligible for broad cartesian expansion exclude quarter-only years
    # (when there are no standalone months to cross with).
    if quarter_years and not months:
        expansion_years = [y for y in flat_years if y not in quarter_years]
    else:
        expansion_years = list(flat_years)

    # --- candidate file generation (ordered algorithm) ---------------------
    candidate: set[str] = set()
    month_only_no_year = False
    all_individual_calendar_months = False

    if year_month_pairs:
        # Case 7: build ONLY from the pairs, no blind cartesian product.
        for pair in year_month_pairs:
            for m in pair["months"]:
                if _valid_year(pair["year"]) and _valid_month(m):
                    candidate.add(_filename(pair["year"], m))
    elif months and not expansion_years and not quarters:
        # Cases 8-9: month(s) with no year -> full corpus span.
        month_only_no_year = True
        flat_years = list(range(CORPUS_MIN_YEAR, CORPUS_MAX_YEAR + 1))
        helper = _candidate_files_for_years(flat_years, months)
        candidate.update(helper["candidate_files"])
        notes.append(
            "month(s) given with no year -> defaulted to full corpus span "
            f"{CORPUS_MIN_YEAR}-{CORPUS_MAX_YEAR}"
        )
    elif expansion_years and not months:
        # Cases 1-2/10 (range, no month): all 12 months per year.
        all_individual_calendar_months = True
        helper = _candidate_files_for_years(expansion_years, None)
        candidate.update(helper["candidate_files"])
    elif expansion_years and months:
        # Cases 3-6/11: cartesian product years x months.
        helper = _candidate_files_for_years(expansion_years, months)
        candidate.update(helper["candidate_files"])

    # Quarter pairs union in (they may add files regardless of the branch).
    for y, m in quarter_pairs:
        candidate.add(_filename(y, m))

    # --- fiscal years (case 12): bespoke, unioned in -----------------------
    fiscal_year_calendar_months: list[dict] = []
    for fy in fiscal_years:
        fy_files, fy_note = _fiscal_year_files(fy)
        fiscal_year_calendar_months.append(
            {
                "fiscal_year": fy,
                "candidate_files": fy_files,
                "note": fy_note,
            }
        )
        candidate.update(fy_files)
    if fiscal_years:
        notes.append("fiscal year(s) expanded to calendar months (case 12)")

    candidate_files = sorted(candidate)

    month_names = [MONTH_NUMBER_TO_NAME[m] for m in sorted(set(months))]

    if not notes:
        notes.append("date hints extracted")

    return {
        "years": flat_years if not month_only_no_year else [],
        "months": sorted(set(months)),
        "month_names": month_names,
        "fiscal_years": fiscal_years,
        "fiscal_year_calendar_months": fiscal_year_calendar_months,
        "date_ranges": date_ranges,
        "year_month_pairs": year_month_pairs,
        "all_individual_calendar_months": all_individual_calendar_months,
        "month_only_no_year": month_only_no_year,
        "no_date_hint_found": False,
        "candidate_files": candidate_files,
        "notes": "; ".join(notes),
    }


if __name__ == "__main__":
    date_filter_app.run()
