# Local dashboard reference

`dashboard/app.py` contains the Streamlit presentation. `src/trendscout/dashboard/data.py` handles discovery and validation without importing Streamlit. Install the `dashboard` optional extra; pandas and chart support arrive through Streamlit. The CLI needs no dashboard packages. Run from the repository root after editable installation.

## Input contract

Only immediate subdirectories whose names parse as `YYYY-MM-DD_HHMMSS_microsecondsZ` are runs. They sort by the encoded UTC timestamp, not modification time. Empty or interrupted directories remain selectable, with explicit file errors. A directory name identifies export time, not historical collection time. Arbitrarily named directories are not silently treated as runs.

`ranked_posts.csv` requires rank, identity, platform, title, URL, aware created-at timestamp and all four scores. Source fields validate through `ContentPost`; rank and scores through `AnalyzedPost`. Missing/empty optional body, author and community become null; missing engagement and comment counts use the existing model's zero convention. Required scores are never imputed. Invalid URLs, nonfinite/out-of-range scores, duplicate identities/ranks and malformed rows are excluded with row-number warnings. CSV spreadsheet-protection apostrophes remain visible because removing them can alter legitimate source text.

`content_ideas.json` must contain a list of existing `VideoIdea` records with all exported fields, including mode, method and fact-check labels. Missing fields are reported rather than filled by model defaults. Invalid ideas are excluded with their original one-based position. Files use UTF-8, optionally with a BOM. File-level errors leave that dataset unavailable; a valid empty export has zero records. Metrics explicitly describe validated records when any exclusions occur. No metric is inferred from `scripts.md`.

## Provenance and quality

Exported idea `mode=demo` with consistent demo source labels identifies synthetic demo output. A `live` label is displayed as **Live-labeled export — collection verification unknown**. Mixed, missing or unrecognized mode labels are unknown. Neither filenames nor URLs establish verified collection. Existing exports contain no trusted verification manifest; this dashboard never claims verified live collection. Demo source links are placeholders.

The checked-out dashboard branch starts from V1, without `generation/quality.py`. V1.1's technical reference and content-quality documentation were inspected on `origin/feature/v1.1-content-quality` without switching branches or merging. No V1.1 generator, CLI or evaluator was replaced. The UI reports quality unavailable on this checkout. If the existing V1.1 evaluator is later integrated separately, the loader calls its `evaluate_quality` on the complete validated idea batch and displays its warning objects and affected idea numbers. Evaluation is disabled for a missing or partly invalid idea export to preserve batch numbering and comparisons. Recomputed results are labeled as current evaluation, not historical persisted warnings. Fact-check labels are displayed directly from exports and are not counted as editorial warnings.

The dashboard provides no quality score, factual verification, publishing, historical analytics or virality forecast. Scores are relative research heuristics for one candidate set. Source text is displayed as data, without HTML execution. Keep the server local; it has no authentication and can browse output directories readable by its process.

## Verification

Run `python -m pytest -q` for all tests. Parsing, malformed records, empty files, missing files, run discovery, provenance and evaluator integration tests require only the existing development dependencies. UI interaction tests use Streamlit's AppTest and skip when the optional extra is absent. With `.[dev,dashboard]` installed, these tests exercise demo metrics, filtering and the empty state.
