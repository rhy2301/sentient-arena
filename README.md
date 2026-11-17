# sentient-arena — OfficeQA grounded-reasoning agent

Agent submitted to **Sentient Arena, Challenge 0 (Grounded Reasoning)**. It answers one precise
numerical question per task from a corpus of 697 U.S. Treasury Bulletin issues spanning 1939–2025.

`Goose harness` · `OpenRouter` · `Python` · `Jinja2` · `FastMCP`

## The problem

Each task gives one question and a text corpus at `/app/corpus/treasury_bulletin_YYYY_MM.txt`. The
answer is a single number (or a list of them), graded against a reference value. Cost and latency
per task are tracked alongside accuracy.

What makes it hard:

- The bulletins are PDF-to-text, so tables arrive as pipe-delimited lines carrying footnote markers
  (`2/`), revision markers (`r47,905`), and occasionally two cells mashed into one.
- The same table code means different tables in different eras — `FFO-5` is "Budget Outlays by
  Functions" in the 1980s and "Internal Revenue Collections by States" in the late 1990s.
- Figures lag their period: annual figures appear in the next year's early issues, and ESF quarterly
  data lags one to two issues.
- Monthly tables such as `FFO-3` and `FFO-5` are laid out by *fiscal* year, so a calendar-year
  question has to stitch columns across issues.

## Layout

```
arena.yaml                     harness, model, prompt and skill wiring
prompts/officeqa_prompt.j2     the agent instruction (85 lines)
skills/corpus_reference/       Treasury Bulletin table-navigation cheat sheet
mcp/treasury_search/           v1 experiment: two-stage BM25 retrieval server (disabled)
mcp/date_filter/               v1 experiment: NL date → candidate filenames (disabled)
```

## Three design decisions

**1. Fabrication is blocked structurally, not asked for politely.**
When multi-column table extraction fails, the model invents values — this was the dominant failure
mode by a wide margin. So every numeric input to a computation must appear in this session's own
stdout first: an indexed-cell dump prints absolute line indices, and the compute script re-reads
those same indices from the file through `cell(line, col)`. Retyping a dumped value into a
`vals=[...]` literal is forbidden, because that "dump, then hand-retype" pattern institutionalises
transcription errors and outright invention.

**2. A provisional answer is written before any verification.**
Putting verification ahead of writing caused loops that burned turns and cost without leaving an
answer at all. The first plausible number now goes to `/app/answer.txt` immediately and is
overwritten by the audited value afterwards, so a loop costs money and latency but never accuracy.

**3. Definitions are locked before any number is read.**
The agent decomposes the question's nouns in one line and commits to each distinction — new vs
outstanding, net vs gross, fiscal vs calendar year, budget vs total, monthly vs cumulative — then
maps each requested period to a fixed column index taken from the header row. Ratios must draw
numerator and denominator from the same table. Re-deriving the same month from a second bulletin to
argue revisions (*reconciling*) is forbidden; taking non-overlapping months from different bulletins
to cover one year (*stitching*) is allowed.

## Version history

Every scored row below is a submission record from the Arena leaderboard. Cost and latency per task
are graded alongside accuracy, so they are listed too.

| Version | Submitted | Score | Solved | $/task | s/task | What changed |
|---|---|---|---|---|---|---|
| v1 | — | 0 | — | — | — | Two MCP servers (BM25 retrieval, date parsing) plus three skills |
| v2 | Jun 19 | 42.1 | 51.1% | 0.37 | 250 | MCP and skills dropped entirely — minimal prompt, shell only (`grep`/`sed`/`python3`), turn limit, write-answer rule |
| v3 | not submitted | — | — | — | — | Chart/figure fallback, senior-analyst verification pass |
| v4 | Jun 20 | 41.0 | 50.0% | 0.35 | 260 | `index.txt` step removed, provisional write introduced |
| v5 | Jun 21 | 41.0 | 50.0% | 0.33 | 264 | local experiment, no branch in this repository |
| v6 | Jun 22 | 42.3 | 52.1% | 0.41 | 302 | local experiment, no branch in this repository |
| v7 | — | **43.4** | **54.3%** | — | — | Prompt rebuilt (145 → 85 lines), three skills replaced by one `corpus_reference` table map |

Scores sat in a 41–42 band from v2 through v6. One point is roughly one question, so most of that
movement is sampling noise: v4 and v5 scored identically, and v6 — the slowest and most expensive
run of the set — beat v2 by 0.2. v7 is the best of the set at 43.4, but by that same argument its
margin over v6 is not large either. The honest read is that prompt wording plateaued early, and the
remaining gains have to come from the extraction path rather than from rephrasing instructions.

## What the iterations taught

- **MCP had close to zero ROI with this harness.** The MCP-only configuration (v1) scored near zero;
  the harness and the model both preferred direct shell and `grep` access. The multi-agent retrieval
  design was dropped for a minimal prompt. `mcp/` is kept as the record of that experiment —
  `treasury_search` implements BM25 from the standard library alone, and `date_filter` owns all
  natural-language date parsing so the search server only ever receives resolved integers.
- **Extraction has to be made reliable before prompting can help.** No amount of instruction fixed
  the answers while cell extraction itself was unreliable.
- **A one- or two-question swing is sampling noise.** v4 and v5 scored the same 41.0, and v2 and v6
  are 0.2 apart; treating that as signal means chasing variance from version to version instead of
  fixing causes.
- **Verify empirically that skills load.** One harness version did not expose them at all, which
  quietly made that iteration's SKILL.md content irrelevant.

## Running it

```bash
arena auth login
arena doctor
arena test --dry-run
arena test --smoke     # one sample task locally; needs Docker
arena submit
```

`arena.yaml` reads `OPENROUTER_API_KEY` from the environment; set it before running.

## Branches

`main` holds the latest submitted version (currently v7). Each experiment keeps its own branch:
`v2-no-mcp-minimal-prompt`, `v3-officeqa-prompt-visual-fix`, `v4-no-index-provisional-write`,
`v7-corpus-reference-skill`.
