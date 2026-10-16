# TrendScout

Turn content discussions into ranked, traceable short-form video concepts — free to run locally, without a paid AI API.

Creators need more than a list of popular posts: they need a specific question to explore and a practical plan for showing it on screen. TrendScout connects **discovery → analysis → ranking → concept generation → export**, keeping the source attached to every idea.

## Key features

- Reddit OAuth collection for approved API access, plus an explicit offline demo.
- Transparent engagement, recency, and discussion scoring.
- Topic-aware hooks and editorial plans for transcription, captions, privacy, editing, citations, code review, summaries, failures, and comparisons.
- Scripts organized into problem, explanation, demonstration, and takeaway, with visuals and calls to action.
- Deterministic editorial warnings for duplicate hooks, repetitive scripts, missing sections, length, filler, and attribution.
- UTF-8 CSV, JSON, and Markdown exports with source URLs and fact-check labels.

Python 3.12+, requests, Pydantic, Typer, Rich, python-dotenv, and pytest. No database or paid AI service.

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
output/<actual-UTC-run-timestamp>/
  ranked_posts.csv       all ranked candidates and component scores
  content_ideas.json    selected concepts with source attribution
  scripts.md            creator-friendly scripts and visual plans
```

For a post about checking citations, a generated hook is **“Does that citation support the sentence beside it?”** The demonstration proposes comparing one summary sentence with its cited passage and labeling the evidence supported, unsupported, or unresolved. It does not invent a verification result.

Quality warnings appear in the terminal with idea numbers and suggested fixes. They do not alter the export schemas, block exports, or measure creativity or virality. Details and thresholds are in [content quality](docs/content-quality.md).

## Architecture

```text
src/trendscout/
  cli.py / pipeline.py       command handling and orchestration
  config.py / models.py      settings and validated records
  sources/                   Reddit adapter and explicit demo fixtures
  analysis/                  scoring and deterministic ranking
  generation/                topic plans, provider protocol, quality evaluator
  exporters/                 CSV, JSON, Markdown
  data/                      packaged synthetic demo records
tests/                       offline unit and pipeline tests
```

Source adapters and generation providers use independent interfaces. This keeps collection, ranking, and exports reusable as providers evolve. V1.1 preserves the existing models, ranking, CLI options, and export formats.

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
