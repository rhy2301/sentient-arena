---
name: search-strategy
description: How to locate the correct Treasury Bulletin evidence in full-corpus mode using the date_filter and treasury_search MCP tools; use whenever a question must be grounded in a corpus file.
---

# Search Strategy for Treasury Bulletin OfficeQA

Do not guess filenames by hand when the MCP tools are available. Let `date_filter` and `treasury_search` do the locating.

## 1. Extract search anchors from the question
Before searching, pull out every anchor you can:
- dates, years, months, fiscal years
- financial terms (the quantity being asked about)
- likely table titles
- row labels and column labels
- qualifiers: "marketable", "public", "held by the public", "net", "gross", "total", "individual calendar months"

## 2. Default MCP search workflow
1. `date_filter.extract_date_hints(question)` to get years/months/fiscal years and `candidate_files`.
2. Use the returned `candidate_files` when available to scope the search.
3. Search those candidate files with `treasury_search.search_corpus`.
4. Inspect promising hits with `treasury_search.read_file_context`.
5. Use `treasury_search.extract_numbers_near_query` only as an aid — never as automatic truth. Always confirm the value in context.

## 3. Staged search expansion
Escalate only as needed; stop once you have a confident, verified match:
1. Exact phrase from the question.
2. Financial term + qualifier.
3. Financial term + table-title guess.
4. Row label / column label.
5. Synonyms and historical wording (see below).
6. Adjacent issue months if the expected issue lacks the relevant table.

## 4. Fallback rule (do not loop)
If staged expansion (steps 1–6) still produces no confident match, **stop repeating the same MCP calls**. Looping on the same unproductive tool call wastes turns and is a known failure pattern. Change strategy instead: directly list or inspect candidate files in the corpus directory (e.g. a shell `ls /app/corpus` / read of specific `treasury_bulletin_YYYY_MM.txt` files) for the relevant year/month range. An unproductive search should change strategy, not repeat itself.

## 5. Fiscal-year compilation timing
Full fiscal-year annual tables are often compiled in a later issue than the FY-end month:
- FY1977 onward: usually the **December** issue.
- Pre-FY1977 years: usually the **September** issue.
- The fiscal year ends in September (FY1977+) or June (pre-FY1977), but the annual figure may not appear in the issue matching that month.
- "Bulletin issue month" and "fiscal year" are not the same year — e.g. a bulletin published in early 1941 may report FY1940 data. If an FY annual figure isn't in the issue matching the FY end, check the December (or September, pre-1977) issue.

## 6. Treasury synonyms (try alternates)
- "public debt" ↔ "debt outstanding"
- "marketable Treasury bills" ↔ "Treasury bills"
- "held by the public" ↔ "public holdings"
- "receipts" ↔ "revenue"
- "expenditures" ↔ "outlays"
- "national defense and associated activities" ↔ "national defense"

## 7. Avoid false positives
- A similar table name is **not** enough.
- Before using any value, verify: document date, table title, row label, column label, and units.
- Do not use a value from a plausible chunk unless the table context matches the question exactly.
- Wide tables (yield curves, bill auction results, security-type breakdowns) are prone to column-misalignment errors — confirm column headers explicitly via `read_file_context` rather than assuming column order from memory.
