# TrendScout V1

TrendScout turns content research leads into ranked, traceable short-form video concepts. It addresses a creator's recurring problem: sorting through discussions and deciding what is worth investigating before spending time on production.

V1 implements **Discover → Analyze → Rank → Generate → Export** as a Python CLI. It requires no paid AI API. Templates produce research-oriented drafts and practical visual suggestions; a creator must verify claims and complete the proposed demonstrations before publishing.

## Features and stack

- Explicit offline demo with 25 synthetic AI-workflow records.
- Reddit OAuth source adapter for approved application-only access, with validation, deduplication, timeouts, bounded retries and clear access errors.
- Transparent opportunity scoring, stable rankings and source attribution.
- Template concepts with hooks, angles, approximately 30–60 seconds of spoken text, visual suggestions and calls to action.
- Timestamped CSV, JSON and Markdown exports in UTF-8.
- Offline tests for sources, scoring, generation, exports, pipeline and CLI.

Python 3.12+, requests, Pydantic, Typer, Rich and python-dotenv form the core application stack. Pytest is the development dependency. The optional V1.2 dashboard adds a local Streamlit server; no database is used.

## Architecture

```text
src/trendscout/
  __main__.py / cli.py       command handling and terminal output
  config.py / models.py     environment settings and validated records
  pipeline.py               orchestration
  sources/                  ContentSource protocol, Reddit, explicit demo
  analysis/                 normalization, recency and ranking
  generation/               IdeaGenerator protocol and template provider
  exporters/                CSV, JSON and Markdown writers
  data/sample_posts.json    installed package demo fixture
tests/                      offline fixtures, mocks and integration tests
examples/sample_posts.json human-readable copy of the synthetic fixture
```

The modular pipeline isolates collection from scoring and generation. New source adapters can supply the same validated `ContentPost` model, while a future LLM adapter can implement `IdeaGenerator` without changing ranking or exports. The two demo fixture copies should be kept synchronized when edited.

## Quick start — Windows PowerShell

From the project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m trendscout run --niche "AI tools" --limit 5 --demo
```

The demo ranks 25 **synthetic AI-workflow records** and exports five concepts. It does not collect real posts or measure current demand. `--limit` sets the final idea count (1–20); `--output-dir` overrides the default `output/` folder.

```powershell
.\.venv\Scripts\python.exe -m trendscout --help
.\.venv\Scripts\python.exe -m pytest -q
```

Using the virtual environment's executable avoids PowerShell activation-policy changes.

## Live Reddit setup

Obtain approved Reddit Data API access for your intended use, then copy `.env.example` to `.env` and configure it locally:

```dotenv
CONTENT_SOURCE=reddit
REDDIT_CLIENT_ID=your-approved-client-id
REDDIT_CLIENT_SECRET=your-secret
REDDIT_USER_AGENT=windows:trendscout:v0.1 (by /u/YOUR_USERNAME)
OUTPUT_DIR=output
```

```powershell
Copy-Item .env.example .env
# Edit .env before running the command below. Never commit credentials.
.\.venv\Scripts\python.exe -m trendscout run --niche "Python automation" --limit 10
```

Live Reddit collection is implemented and mock-tested but remains **unverified with real credentials**. Missing credentials or access errors fail explicitly; the app never substitutes demo data for a live result. See [API setup and technical reference](docs/technical-reference.md) for authorization references, request behavior, scoring, and export details.

## Example output

```text
output/<YYYY-MM-DD_HHMMSS_microsecondsZ>/
  ranked_posts.csv
  content_ideas.json
  scripts.md
```

CSV includes source fields, rank and all component scores. Cells that could be interpreted as spreadsheet formulas are prefixed with an apostrophe; JSON preserves the original validated text. JSON is a list of concepts with source identity, title, URL, niche, angle, hook, script, visuals, CTA, score, mode, generation method and fact-check labels. Markdown escapes source text and presents the same concepts in a readable format.

An illustrative concept might be titled “Test the claim: How should I evaluate an AI writing assistant?” and open with “Would this actually help your workflow?” Its script proposes a controlled workflow comparison rather than claiming that an untested tool is effective. Scores in actual output depend on the candidate set and runtime.

## Ranking methodology

For each candidate set:

1. Clamp negative engagement to zero, then transform scores and comment counts separately with `log(1 + x)`.
2. Min-max normalize each transformed metric to 0–100. An identical or singleton set receives zero for that component because it supplies no comparative evidence.
3. Calculate recency as `100 × 2 ** (-age_hours / 72)`, a 72-hour half-life. Future timestamps have age zero. Timestamps must be timezone-aware and are normalized to UTC.
4. Calculate `opportunity = 0.50 × engagement + 0.30 × recency + 0.20 × discussion`.
5. Sort descending by score, breaking ties by platform and source ID. Normalization occurs before selecting the requested number of ideas.

All components and final scores are bounded to 0–100. Missing numeric metrics default to zero. Invalid records are skipped with a warning; missing required fields, malformed timestamps, invalid URLs and negative comment counts are rejected. Duplicate source IDs are removed within the same platform. An empty candidate set produces an error and no exports.

The score is a **research heuristic**, not a prediction of views, virality or profitability. Scores from different candidate sets are not directly comparable. Niche relevance is supplied by Reddit search; there is no semantic relevance model in V1.

## V1.2 local intelligence dashboard

Install the optional UI dependency from the repository root (the CLI does not require it):

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev,dashboard]"
.\.venv\Scripts\python.exe -m streamlit run dashboard/app.py --server.address localhost
```

With the virtual environment activated, the launch command is `python -m streamlit run dashboard/app.py --server.address localhost`. Open `http://localhost:8501` and stop the server with Ctrl+C. Streamlit's standard launch command `python -m streamlit run dashboard/app.py` also works.

If no runs exist, first execute `python -m trendscout run --niche "AI tools" --limit 5 --demo`. The dashboard has the same empty-state instructions. It reads `OUTPUT_DIR` (including `.env`) by default; enter another directory in the sidebar for custom CLI output locations. Select a timestamped run, newest first in UTC, and click **Refresh exports** after adding files. The dashboard reads files on each interaction without a stale data cache.

The Overview shows validated candidate/idea counts, average opportunity on the existing 0–100 scale, a score distribution and comparisons of the top 20 ranked candidates. Ranked trends supports source, text and minimum-score filters, sortable columns, source links and individual inspection. Content ideas expands hooks, scripts, visual plans, CTAs, attribution and exported fact-check metadata. It performs no collection, generation, or export writes.

See [dashboard details and limitations](docs/dashboard.md) for schemas, provenance and quality availability. This branch does not contain the V1.1 evaluator: the dashboard explicitly displays **Unavailable**, rather than manufacturing warning counts. Existing pipeline logic and export formats are unchanged.

## Tests and verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

All automated tests run without network access or API credentials. They cover normalization and boundaries, time decay, deterministic tie-breaking, malformed and duplicate records, missing credentials, OAuth request construction, bounded retries, access/rate errors, invalid JSON, template traceability and script lengths, CSV/JSON/Markdown exports, CLI validation, shortfalls and the complete demo pipeline.

## Current limitations

- Scripts are template-generated research drafts. Verify source claims, permissions, current documentation, and any demonstration results before production.
- Keyword matching covers a small set of topics. Unfamiliar topics receive a source-anchored research plan; ambiguous titles and bodies can be misclassified.
- Six editorial approaches cycle across a batch. Related topics may still repeat; quality warnings help identify these cases but cannot judge factual accuracy or semantic completeness.
- Scripts target 80–160 whitespace-delimited words. Time a read-through: speaking pace and section labels affect duration.
- Demo topics remain fixed even when the niche changes. Fixture timestamps age naturally, so runtime rankings can change.
- Reddit uses one search page, up to 100 candidates. There is no persistent cache, historical trend detection, publishing, video rendering, or analytics.
- Opportunity scores are research heuristics, not predictions of views, virality, or profitability.

## Roadmap

| Milestone | Scope |
| --- | --- |
| V1 / V1.1 | Discover, rank, generate, export; topic plans and editorial checks. |
| Next | Verify authorized live collection; evaluate script quality on a broader set of real topics. |
| V2 | Optional configurable LLM providers and content planning. |
| V3 | Supported YouTube and other platform research APIs. |
| V4 | Voiceovers, captions, visual assets, and video drafts. |
| V5 | Published-content analytics and performance tracking. |
| V6 | Scheduling, review workflows, calendars, and client reporting. |
