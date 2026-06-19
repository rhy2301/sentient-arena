---
name: table-reading-rules
description: How to read Treasury Bulletin tables safely so every value is correctly grounded in document, table, row, column, and cell; use whenever extracting a number from a corpus table.
---

# Table Reading Rules for Treasury Bulletin Evidence

Every final number must be grounded in a specific **document, table, row, column, and cell**. If any of those is uncertain, keep reading context before using the value.

## Units
- Read units from table headers or footnotes — never assume.
- Common units: dollars, thousands, millions, billions, percent.
- Normalize units before doing any arithmetic.

## Date / period traps
- calendar year vs fiscal year
- calendar month vs month-end value
- exact date vs bulletin issue month
- a table may lag one or more bulletin issues
- pre-FY1977 federal fiscal year is July 1 – June 30
- FY1977 onward is October 1 – September 30
- the transition quarter is July – September 1976

## Table structure traps
- total vs subtotal
- gross vs net
- receipts vs expenditures / outlays
- public debt vs debt held by the public
- marketable vs nonmarketable securities
- Treasury bills vs certificates vs notes vs bonds
- row label and column label must be read together
- **parentage check:** a row label alone is not enough — confirm which section/category header the row sits under before trusting it. E.g. "individual income taxes" can appear both as a receipts line and as a refunds line; scroll up to find the enclosing section heading to disambiguate.

## Numeric notation rules
- `(1,234)` means negative 1,234.
- Dash, em dash, blank, or `n.a.` usually means unavailable/not applicable — **not** zero.
- Footnote markers (`p`, `r`, `e`, `*`, superscript-like markers) must not be silently ignored.
- Commas are thousands separators.
- Percent signs indicate percent, not decimal fractions.

## Markdown table reading
- Headers may span multiple lines.
- A chunk may start in the middle of a table — inspect surrounding lines.
- If labels are unclear, call `treasury_search.read_file_context` with nearby row/column terms.

## Checklist before using a value
1. Correct document?
2. Correct table?
3. Correct row (and correct parent section for that row)?
4. Correct column?
5. Correct units?
6. Correct period/date?
7. Footnotes understood?
