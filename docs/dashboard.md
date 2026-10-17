# Local dashboard reference

`dashboard/app.py` contains the Streamlit presentation. `src/trendscout/dashboard/data.py` handles discovery and validation without importing Streamlit. Install the `dashboard` optional extra; pandas and chart support arrive through Streamlit. The CLI needs no dashboard packages. Run from the repository root after editable installation.

## Input contract

Only immediate subdirectories whose names parse as `YYYY-MM-DD_HHMMSS_microsecondsZ` are runs. They sort by the encoded UTC timestamp, not modification time. Empty or interrupted directories remain selectable, with explicit file errors. A directory name identifies export time, not historical collection time. Arbitrarily named directories are not silently treated as runs.

`ranked_posts.csv` requires rank, identity, platform, title, URL, aware created-at timestamp and all four scores. Source fields validate through `ContentPost`; rank and scores through `AnalyzedPost`. Missing/empty optional body, author and community become null; missing engagement and comment counts use the existing model's zero convention. Required scores are never imputed. Invalid URLs, nonfinite/out-of-range scores, duplicate identities/ranks and malformed rows are excluded with row-number warnings. CSV spreadsheet-protection apostrophes remain visible because removing them can alter legitimate source text.

`content_ideas.json` must contain a list of existing `VideoIdea` records with all exported fields, including mode, method and fact-check labels. Missing fields are reported rather than filled by model defaults. Invalid ideas are excluded with their original one-based position. Files use UTF-8, optionally with a BOM. File-level errors leave that dataset unavailable; a valid empty export has zero records. Metrics explicitly describe validated records when any exclusions occur. No metric is inferred from `scripts.md`.

## Provenance and quality

Exported idea `mode=demo` with consistent demo source labels identifies synthetic demo output. A `live` label is displayed as **Live-labeled export — collection verification unknown**. Mixed, missing or unrecognized mode labels are unknown. Neither filenames nor URLs establish verified collection. Existing exports contain no trusted verification manifest; this dashboard never claims verified live collection. Demo source links are placeholders.

V1.2 includes the V1.1 `generation.quality.evaluate_quality` evaluator. The loader evaluates the complete validated idea batch, independently of CSV availability. It returns the same `QualityWarning` objects as a direct Python call, with codes, messages and one-based idea numbers. The overview counts warning objects once; a warning affecting two ideas appears in both expanders.

| Quality state | Dashboard behavior |
| --- | --- |
| Completed, zero warnings | Displays **0** and a recomputation caption. A valid empty idea list also evaluates to zero warnings. |
| Completed, warnings found | Displays the actual warning count and warnings under each affected idea. |
| Evaluator unavailable | Displays **Unavailable**, with an explicit status if the evaluator module is missing from the installation. |
| Missing or invalid idea export | Displays **Unavailable** and file/record errors; batch evaluation is impossible. Valid remaining ideas retain their original exported positions. |
| Evaluator raised an error | Displays **Unavailable**, the failure status and the error; exports remain inspectable. No zero-warning fallback is used. |

Warnings are recomputed using the installed evaluator and labeled **not historical results**. V1.1's CLI evaluates after export; neither the Python pipeline result nor the three export files record warning history. Fact-check labels are displayed directly from exports and are not counted as editorial warnings. The evaluator's advisory rules and limits are documented in [content quality](content-quality.md). No missing fields, invalid records or evaluator failures are silently treated as a clean evaluation.

The dashboard provides no quality score, factual verification, publishing, historical analytics or virality forecast. Scores are relative research heuristics for one candidate set. Source text is displayed as data, without HTML execution. Keep the server local; it has no authentication and can browse output directories readable by its process.

## Verification

Run `python -m pytest -q` for all tests. Parsing, malformed records, empty files, missing files, run discovery, provenance and evaluator integration tests require only the existing development dependencies. UI interaction tests use Streamlit's AppTest and skip when the optional extra is absent. With `.[dev,dashboard]` installed, these tests exercise demo metrics, filtering, candidate inspection, source links, actual warnings, original idea numbers and empty/partial runs.
