---
name: corpus-reference
description: Treasury Bulletin table/navigation reference for locating financial figures in /app/corpus (treasury_bulletin_YYYY_MM.txt, 1939–2025). Maps table codes to the data they hold and the row/column traps for each, so the right table is picked fast. Use whenever a question must be grounded in a specific Bulletin table.
---

# Treasury Bulletin — Table Navigation Cheat Sheet

Corpus: `/app/corpus/treasury_bulletin_YYYY_MM.txt`, monthly, 1939–2025. **Navigation only — no
data values.** Goal: pick the RIGHT table and avoid evidence-selection mistakes. **Match a table
by its printed title and section header, never by code number alone** — codes are reused and
renumbered across eras.

## Era / label drift (read first)
- Lettered codes (`FFO-x`, `AY-1`, `CM-I-x`, `FCP-VII`, `FD-x`, `OFS-x`, `PDO-x`) are a LATER
  convention. Pre-~1950s bulletins use prose / plain "Table 1, Table 2…".
- The SAME code can name a different table in a different decade, and the SAME data can move to a
  different code. Always confirm the printed title and section header.

## Table families

| Code(s) (+ era forms) | What it holds | Key row/column gotcha |
|---|---|---|
| FFO-1 | Summary of fiscal operations (receipts, outlays, deficit) | Top-line only; drop to FFO-2/3 for detail. **In Sept bulletins the "Est." column is the bulletin's own estimate, NOT the Mid-Session Review** — for an MSR figure read the prose. |
| FFO-2 | On-budget & off-budget **receipts by source** | On/off-budget are separate column groups; spills onto "…continued" pages. |
| FFO-3 | On-budget & off-budget **outlays by agency** | Outlays only; agency rows; "…continued" pages. Laid out by FISCAL year. |
| FFO-5 (era-split) | ~1980s: "Budget Outlays by Functions" (1982_01). ~late-1990s+: "Internal Revenue Collections/Receipts by States…" (1999_03) | SAME code, **different table by era** — confirm the title. 1980s monthly columns are a FISCAL year (header months Oct→Sept, some start Nov). |
| AY-1 (≈1970+; earlier = prose) | "Average Yields of Long-Term Treasury, Corporate and Municipal Bonds by Periods" (1970_06, 1979_01) | Treasury column = yields on **OUTSTANDING** long-term bonds; "New Aa corporate bonds" = **NEW** issues. Years are side-by-side column groups. |
| SBN / SB / SN (era prefixes) | Savings-bond **sales & redemptions** — SBN = Savings Bonds & Notes (2000_03); SB = Series E–K (1982_10); SN = Savings Notes (1982_02) | Pick the prefix matching the era/series. Sales vs redemptions are distinct rows. |
| CM-I-x | **Liabilities to foreigners** (capital movements), CM-I-1/2/3 (1997_03) | Reported by holder type / area; choose the correct sub-table. A "Canadian dollar liabilities" share must take numerator AND denominator from the same CM-I table — the "Canadian dollars" line in Foreign Currency Positions is a DIFFERENT series. |
| FCP-VII (monthly = FCP-VII-2) | **Euro positions** — "SECTION VII.—Euro Positions" (2001_06) | Foreign-currency positions (a stock), not flows; confirm the section header. |
| ESF-1 | Exchange Stabilization Fund **balance sheet** | **"Total capital" = Capital account + Net income** — not a single line. |
| ESF-2 | ESF **income and expense** | Quarterly; lags ~1–2 bulletins after quarter-end. |
| PDO-1 | **Maturity schedule** of interest-bearing marketable public debt, issue-by-issue, excl. regular weekly & 52-week bills (1972_02, 1975_02, 1983_03) | **Point-in-time snapshot** — only issues still outstanding at that date. PDO numbering drifts: recently PDO-1/PDO-2 are bill/marketable OFFERINGS (1973_02) — match by title. |
| FD-1 | Summary of federal debt | Gross debt vs debt held by the public — different rows. |
| FD-2 | Debt held by the public | Distinct from total/gross public debt. |
| FD-5 / FD-7 (drifts) | "Maturity Distribution and Average Length of Marketable Interest-Bearing Public Debt Held by Private Investors" (1983_06) | Distribution buckets + average remaining length, NOT the issue-by-issue PDO-1 schedule. |
| OFS-1 | "Distribution of Federal Securities by Class of Investors and Type of Issues" | Investor-class × issue-type grid — read row and column together. |
| OFS-2 | "Estimated Ownership of U.S. Treasury Securities" | **Estimated** basis; do not mix with OFS-1. |

## Reporting lag
- Full-year / fiscal-year figures usually appear in the **next year's early issues**, not the
  issue matching the period end.
- ESF quarterly tables lag the quarter by ~1–2 bulletins.

## How to read these tables
- Page numbers sit alone on a line — a bare number on its own line is pagination, not data.
- Multi-period tables lay periods out as column groups — match each column to its own period
  header; never assume left-to-right chronological order.
- Check a row's parent section header before trusting its label; the same row label can appear
  under different section headings.
- PDO-1 is a point-in-time snapshot — absence of an issue means it matured/was excluded, not zero.
- In 1940s "Summary by Months and Calendar Years" (Table 6) each calendar year has TWO monthly
  rows sharing the year label — Receipts and Expenditures. Anchor by the section header.
- When code and title disagree across eras, trust the printed title and section header.