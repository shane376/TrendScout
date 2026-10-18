# TrendScout V1.2

TrendScout turns content research leads into ranked, traceable short-form video concepts. It addresses a creator's recurring problem: sorting through discussions and deciding what is worth investigating before spending time on production.

TrendScout implements **Discover → Analyze → Rank → Generate → Export** as a Python CLI, with a local Streamlit dashboard for exploring saved runs. It requires no paid AI API. Topic-aware templates produce research drafts and visual plans; advisory editorial checks flag common issues. Creators must verify claims and complete proposed demonstrations before publishing.

## Features and stack

- Explicit offline demo with 25 synthetic AI-workflow records.
- Reddit OAuth source adapter for approved application-only access, with validation, deduplication, timeouts, bounded retries and clear access errors.
- Transparent opportunity scoring, stable rankings and source attribution.
- Topic-aware template concepts with hooks, angles, structured scripts, visual plans and calls to action.
- Deterministic editorial checks for repetition, missing sections, script length, filler and verification labels.
- Timestamped CSV, JSON and Markdown exports in UTF-8.
- Optional read-only dashboard with run selection, score charts, candidate filters and expandable ideas.
- Offline tests for sources, scoring, generation, quality, exports, pipeline, CLI and dashboard.

Python 3.12+, requests, Pydantic, Typer, Rich and python-dotenv form the core application stack. Pytest is the development dependency. The optional V1.2 dashboard adds a local Streamlit server. V1.3.1 adds a separate opt-in SQLite ingestion foundation using Python's standard library; the existing CLI and dashboard still read and write file exports.

## Architecture

```text
src/trendscout/
  __main__.py / cli.py       command handling and terminal output
  config.py / models.py     environment settings and validated records
  pipeline.py               orchestration
  sources/                  ContentSource protocol, Reddit, explicit demo
  analysis/                 normalization, recency and ranking
  generation/               IdeaGenerator protocol, topic plans and quality evaluator
  exporters/                CSV, JSON and Markdown writers
  dashboard/                run discovery and export validation (no Streamlit import)
  ingestion/                V1.3 contracts, synthetic adapter and opt-in SQLite repository
  data/sample_posts.json    installed package demo fixture
dashboard/app.py            optional Streamlit presentation
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

For example, a transcription concept can open with “Would your transcript preserve a name, a pause, and a correction?” Its script proposes a comparison with a manual reference transcript; it does not claim that a tool has been tested. Scores depend on the candidate set and runtime.

## Content quality

The V1.1 generator uses source title/body keywords to choose a local topic plan, then rotates six editorial approaches. Scripts contain `Problem:`, `Explanation:`, `Demonstration:` and `Takeaway:` sections, targeting 80–160 words. Metadata retains the full source title while narration uses a bounded quote.

After generation and export, the CLI runs `generation.quality.evaluate_quality` and prints actionable warnings. The Python pipeline returns ideas for callers to evaluate; it does not persist warning results. The dashboard runs the same evaluator on complete idea exports. **Zero warnings** means evaluation completed without a matching rule; **Unavailable** means it could not be evaluated. Dashboard warnings are labeled as recomputed, not historical run results. A failed evaluation is reported explicitly.

Checks are advisory heuristics, not factual verification or objective creativity scores. See [content-quality rules and limitations](docs/content-quality.md).

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

See [dashboard details and limitations](docs/dashboard.md) for validation, provenance and quality states. Missing or invalid idea exports disable batch evaluation; valid records remain inspectable with their original idea numbers. Existing export formats are unchanged. Demo runs are labeled synthetic; live-labeled exports do not establish verified collection.

## V1.3.2 YouTube ingestion

The separate [YouTube Data API v3 adapter](docs/v1.3-youtube-ingestion.md) searches for videos and normalizes metadata and native counters through the ingestion foundation. It provides bounded pagination/retries and explicit collection errors. Missing statistics remain unavailable. No new ranking, generation or dashboard behavior is added, and the command writes no source data to disk.

```powershell
.\.venv\Scripts\python.exe -m trendscout.ingestion.youtube_demo --query "AI automation" --limit 10 --fixture
```

Fixture mode is explicitly synthetic and needs no key or network. For an intentionally authorized live collection, configure `YOUTUBE_API_KEY` locally and omit `--fixture`. The V1.3.2 live smoke test succeeded on **October 17, 2026**, as reported by the maintainer. Production readiness and live-data retention remain unverified. See the adapter guide for environment bounds, officially verified quota references and retention restrictions. Live persistence remains disabled by default; configuration is not permission to store API data or derive analytics.

## V1.3.3 YouTube research intelligence

The [read-only intelligence report](docs/v1.3-youtube-intelligence.md) adds deterministic research priorities, lifetime-average views/day, engagement ratios, component availability, source evidence and separate creator/business hypotheses. Missing metrics stay unavailable. Scores are exploratory heuristics; business hypotheses are not validated market demand. The existing ingestion contracts, CLI, dashboard, SQLite repository and legacy scoring remain unchanged.

```powershell
.\.venv\Scripts\python.exe -m trendscout.ingestion.youtube_intelligence --query "AI automation" --limit 10 --fixture
```

Live analysis requires `--authorized-live-analysis` after applicable analytics permissions have been established, in addition to `YOUTUBE_API_KEY`. API access alone does not establish that permission. The command writes no metadata or derived reports to disk and never substitutes fixtures after a live failure. See the guide for formulas, configuration, caveats and authorization requirements.

## Tests and verification

V1.3.1's [ingestion foundation](docs/v1.3-ingestion-foundation.md) provides source-neutral models, an adapter protocol, transactional SQLite persistence and per-source expiration. It does not add live providers, new scoring or dashboard features. To run its disposable offline workflow:

```powershell
.\.venv\Scripts\python.exe -m trendscout.ingestion.demo
```

No API keys, network access or new dependencies are required. Persistent live-data storage remains disabled unless explicitly configured for a source after its policy requirements are resolved.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

All automated tests run without network access or API credentials. They cover sources, scoring, topic-aware generation, editorial checks, exports, CLI behavior and the demo pipeline, plus dashboard parsing, provenance, quality states and UI interactions. Streamlit UI tests skip when the optional dashboard dependency is absent; install `.[dev,dashboard]` to run them.

## Current limitations

- Scripts are template-generated research drafts. Verify source claims, permissions, current documentation, and any demonstration results before production.
- Keyword matching covers a small set of topics. Unfamiliar topics receive a source-anchored research plan; ambiguous titles and bodies can be misclassified.
- Six editorial approaches cycle across a batch. Related topics may still repeat; quality warnings help identify these cases but cannot judge factual accuracy or semantic completeness.
- Scripts target 80–160 whitespace-delimited words. Time a read-through: speaking pace and section labels affect duration.
- Demo topics remain fixed even when the niche changes. Fixture timestamps age naturally, so runtime rankings can change.
- Reddit uses one search page, up to 100 candidates. There is no persistent cache, historical trend detection, publishing, video rendering, or analytics.
- Opportunity scores are research heuristics, not predictions of views, virality, or profitability.
- Live Reddit access remains unverified with real credentials. Export labels cannot independently verify collection provenance.
- The dashboard reads local files without authentication. Keep its server local. Partial exports are reported; quality warnings are recomputed with the current evaluator and are not persisted history.

## Roadmap

| Milestone | Scope |
| --- | --- |
| V1 / V1.1 | Discover, rank, generate, export; topic plans and editorial checks. |
| V1.2 | Local Streamlit exploration of exported runs, ranked candidates, ideas and recomputed editorial warnings. |
| V1.3.1 | Source-neutral ingestion contracts, synthetic adapter, opt-in SQLite storage and retention; no new live integration. |
| V1.3.2 | Official YouTube adapter; live ingestion smoke test succeeded October 17, 2026; production and retention remain unverified. |
| V1.3.3 | Explainable read-only video research priorities and separate creator/business hypotheses; offline tested. |
| Next | Review production analytics authorization and retention; validate research usefulness on broader topics. |
| V2 | Optional configurable LLM providers and content planning. |
| V3 | Broader supported platform research APIs and integration with research workflows. |
| V4 | Voiceovers, captions, visual assets, and video drafts. |
| V5 | Published-content analytics and performance tracking. |
| V6 | Scheduling, review workflows, calendars, and client reporting. |
