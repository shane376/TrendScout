# Technical reference

## Installation and configuration

Install Python 3.12+ and run the README's virtual-environment commands from the project directory. Activation is optional: `.\.venv\Scripts\Activate.ps1` enables the shorter `python` command when local PowerShell policy permits it. Do not change global execution policy just to run the app.

`Settings.from_env()` loads `.env` with python-dotenv; existing environment variables take precedence. Supported keys are `CONTENT_SOURCE` (default `reddit`), `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USER_AGENT`, and `OUTPUT_DIR` (default `output`). `.env` is ignored by Git. CLI `--output-dir` overrides the configured output directory.

For authorized Reddit access consult the [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki), [application-only OAuth documentation](https://github.com/reddit-archive/reddit/wiki/OAuth2#application-only-oauth), and [search endpoint reference](https://www.reddit.com/dev/api/#GET_search). Obtain credentials and any necessary approval for the intended use. A client ID alone does not establish approval. Live access remains unverified in this environment.

The adapter obtains a token using the `client_credentials` grant, then calls `https://oauth.reddit.com/search` for relevant links from the past month. It uses one page, capped at 100 records, and excludes adult/stickied records. There is no anonymous endpoint fallback. Missing credentials, denied access, invalid JSON, malformed listings, or an empty valid candidate set produce clear errors.

Connect/read timeouts are 5/20 seconds. Timeouts, connection errors, and transient HTTP 500/502/503/504 responses retry up to three total attempts, with 1- and 2-second delays. Authentication errors stop immediately. HTTP 429 stops collection so the caller can wait for rate limits to reset. Errors do not expose tokens, credentials, or response bodies.

## Candidate handling and ranking

`--limit` accepts 1–20 final ideas. Candidate requests use `min(100, max(25, limit * 5))`. If fewer unique valid candidates remain, the pipeline exports the available ideas and reports the shortfall; it never fabricates additional records.

Pydantic cleans whitespace and HTML entities in text, normalizes aware timestamps to UTC, and validates required fields and HTTP(S) URLs. Missing numeric metrics default to zero. Malformed source records are skipped with warnings. Negative comment counts are rejected. Source identities are deduplicated by platform and ID.

Scoring is unchanged in V1.1:

1. Clamp negative engagement to zero and calculate `log(1 + x)` for engagement and discussion separately.
2. Min-max normalize each metric to 0–100 across the full candidate set. Identical or singleton sets receive zero for that component.
3. Recency is `100 * 2 ** (-age_hours / 72)`, with a 72-hour half-life; future timestamps have age zero.
4. Opportunity is `0.50 * engagement + 0.30 * recency + 0.20 * discussion`.
5. Sort descending; break ties by platform and source ID before selecting final concepts.

Scores are research heuristics, not predictions of views or business outcomes. Scores from different candidate sets are not directly comparable. Reddit search supplies relevance; there is no semantic relevance model.

## Demo and export behavior

The 25 packaged demo records are synthetic AI-workflow questions with fixed dates and `example.com` placeholder URLs. They do not change topic with `--niche`. Runtime rankings change as timestamps age; tests inject a fixed clock. Keep `examples/sample_posts.json` and `src/trendscout/data/sample_posts.json` synchronized when editing fixtures.

Every export folder uses a UTC allocation timestamp with microseconds: `YYYY-MM-DD_HHMMSS_microsecondsZ`. Directories are created automatically. If that timestamp already exists, allocation retries with the later of the current clock or the preceding attempt plus one microsecond, up to 1,000 attempts. Existing runs are never overwritten; other filesystem errors propagate immediately. The timestamp is an export identifier, not a collection-history measurement. CSV contains every ranked candidate with source fields and component scores. Spreadsheet-formula-like text is prefixed with an apostrophe. JSON contains only selected concepts and preserves validated source text. Markdown escapes source text and presents hooks, angles, scripts, visuals, CTAs, and fact-check notes. All three use UTF-8. An interrupted filesystem write may leave a partial directory.

V1.1 preserves CLI options, source adapters, ranking, data models, and export schemas. The only additional terminal behavior is advisory editorial warnings after generation. See [content quality](content-quality.md) for their rules and limitations.

## Testing

V1.2 adds an optional read-only dashboard: install `.[dev,dashboard]` and run `python -m streamlit run dashboard/app.py --server.address localhost` from the repository root. The CLI and export contracts remain unchanged. The dashboard discovers timestamped directories, validates CSV/JSON through the existing models, and recomputes quality warnings from complete idea exports. See [dashboard validation and quality states](dashboard.md).

Run `.\.venv\Scripts\python.exe -m pytest -q`. Tests use fixtures and mocks; they do not require internet access or Reddit credentials. Coverage includes scoring boundaries and recency, deterministic ranking, malformed source records, OAuth request construction, retries, access errors, generation specificity and length, quality warnings, exports, CLI validation, and the end-to-end demo pipeline.
