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

Python 3.12+, requests, Pydantic, Typer, Rich and python-dotenv form the application stack. Pytest is the development dependency. There is no database or web server.

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

## Install on Windows PowerShell

From this project directory:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m trendscout --help
```

Activation is optional. Using the environment's Python directly avoids PowerShell execution-policy changes. To activate in a shell that permits it, run `.\.venv\Scripts\Activate.ps1`, then use `python` in place of `.\.venv\Scripts\python.exe`.

## Run the offline demo

```powershell
.\.venv\Scripts\python.exe -m trendscout run --niche "AI tools" --limit 5 --demo
```

The terminal explicitly reports demo mode, ranks 25 fixture candidates and generates five concepts. These are **synthetic examples, not collected Reddit posts or current trends**. Their `example.com` URLs are placeholders. The fixture is fixed and remains about AI workflows even if you pass another niche; `--niche` changes the intended audience of the draft, not the fixture topics. Fixed timestamps age naturally, so scores change with runtime. Tests inject a fixed clock for reproducible assertions.

`--limit` accepts 1–20 final ideas. The pipeline requests `min(100, max(25, limit × 5))` candidates. If fewer unique valid candidates are available, it exports the available ideas and reports the shortfall rather than fabricating additional posts. CSV contains all ranked candidates; JSON and Markdown contain only the selected concepts.

Override the output location with `--output-dir .\my-results` or `OUTPUT_DIR`.

## Live Reddit configuration

Live integration is implemented and mock-tested, but **live collection has not been verified**: no authorized credentials were available during implementation.

Reddit requires OAuth and an identifying User-Agent. Consult the [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki), [OAuth application-only documentation](https://github.com/reddit-archive/reddit/wiki/OAuth2#application-only-oauth), and [search endpoint reference](https://www.reddit.com/dev/api/#GET_search). Obtain any necessary approval and credentials for your intended use before configuring the application. Having a client ID does not establish that your use has been approved.

```powershell
Copy-Item .env.example .env
# Edit .env locally with your approved credentials and identifying User-Agent.
.\.venv\Scripts\python.exe -m trendscout run --niche "Python automation" --limit 10
```

```dotenv
CONTENT_SOURCE=reddit
REDDIT_CLIENT_ID=your-approved-client-id
REDDIT_CLIENT_SECRET=your-secret
REDDIT_USER_AGENT=windows:trendscout:v0.1 (by /u/YOUR_USERNAME)
OUTPUT_DIR=output
```

The application uses the `client_credentials` application-only OAuth grant, then requests `https://oauth.reddit.com/search` for relevant links from the past month. It does not use anonymous JSON scraping. Only one search page is requested, capped at 100 results, and adult or stickied records are excluded. Missing credentials fail with a useful message; no live error triggers a demo fallback. Keep `.env` private; it is ignored by Git. Environment variables take precedence over `.env` values.

Connect/read timeouts are 5/20 seconds. Connection failures, timeouts and transient 500/502/503/504 responses retry up to three total attempts with 1- and 2-second backoff. Authentication errors stop immediately. HTTP 429 stops collection so the caller can wait for the rate limit to reset; it never attempts to evade that limit. Response bodies, tokens and credentials are not included in error messages.

## Example output

Each run creates a unique directory using the actual UTC runtime, including microseconds:

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

## Tests and verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

All automated tests run without network access or API credentials. They cover normalization and boundaries, time decay, deterministic tie-breaking, malformed and duplicate records, missing credentials, OAuth request construction, bounded retries, access/rate errors, invalid JSON, template traceability and script lengths, CSV/JSON/Markdown exports, CLI validation, shortfalls and the complete demo pipeline.

## Limitations

- Reddit live access requires approved credentials and remains unverified in this environment.
- Demo records are synthetic and do not measure real demand. Other niches require live collection for meaningful research.
- Templates use five editorial approaches, cycling for larger requests. They are not LLM-generated and may need substantial editorial work.
- Source titles are untrusted quoted data, never executed as instructions. Claims remain unverified. Review quoted text, check authoritative documentation and verify rights before production.
- Scripts are research drafts, not completed product reviews. Speaking duration depends on pace and title length.
- One Reddit search page, no pagination, persistent cache, cross-run deduplication or historical trend detection.
- Outputs are local files; an interrupted or failed filesystem write may leave a partial output directory.
- No publishing, video rendering, account management or analytics are implemented.

## Roadmap

| Version | Scope |
| --- | --- |
| V1 — Content Discovery and Ideation | Retrieve, rank, generate and export (current; live Reddit verification pending). |
| V2 — LLM Integration | Configurable AI providers for improved scripts and content planning. |
| V3 — Multi-Platform Research | Supported YouTube and other platform APIs. |
| V4 — Automated Content Production | Voiceovers, captions, visual assets and video drafts through appropriate services. |
| V5 — Analytics Dashboard | Published content, engagement and performance tracking. |
| V6 — Business Automation | Scheduling, review workflows, content calendars and client reporting. |

The next practical milestone is an authorized live Reddit smoke test, followed by editorial evaluation of generated concepts before adding an optional LLM provider.
