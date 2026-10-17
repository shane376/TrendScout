# Content quality in V1.1

## Generation

`TemplateGenerator` keeps the existing `IdeaGenerator` interface and returns the existing `VideoIdea` model. It uses only local, deterministic rules; there is no LLM or network call during generation.

Title and available body text are tokenized for keyword matching. Title matches carry three times the weight of body matches. The highest-scoring topic plan supplies a proposed problem, review criteria, demonstration, takeaway, and shot plan. Ties follow the fixed plan order. Whole-word matching avoids accidental substring matches such as “code” inside “decode.” Only the first 4,000 body characters are considered.

Plans cover transcription, captions, private files, draft editing, failure records, citations, code review, summaries, and workflow comparisons. These contain editorial suggestions, not facts extracted from the source. A request about citations might produce a side-by-side sentence/passage check; a privacy question might produce a dummy-file data-flow diagram. They do not assert product capabilities or test outcomes.

For an unfamiliar topic, a bounded keyword label drawn from the title (or body when the title is sparse) anchors an evidence-gathering plan. This fallback is deliberately cautious and less specific than a supported topic plan. Source text is always data: it can influence keyword matching or appear in a quote but cannot execute instructions. Matching is not a factual verification or a prompt-injection classifier.

Six editorial approaches rotate by batch position: evidence walkthrough, preflight checklist, controlled demonstration, failure investigation, decision guide, and viewer challenge. Identical inputs in the same order produce identical ideas. Reordering inputs can change their editorial approach. No randomness, clock, or Python hash is used by generation.

Scripts have explicit `Problem:`, `Explanation:`, `Demonstration:`, and `Takeaway:` sections after the opening hook. Source title quotations are bounded to 18 words / 150 characters to keep narration concise; full titles and source identity remain in the existing metadata fields. A fact-check requirement remains attached to every generated concept. A template may recommend a test but cannot state it has been performed.

## Editorial evaluator

`generation.quality.evaluate_quality(ideas)` returns deterministic `QualityWarning` objects with a code, one-based idea numbers, and an actionable message. The CLI runs it on the generated batch and prints warnings. Exports and data models are unchanged; warnings are advisory and are not persisted in the three export files. Python callers can run the evaluator directly.

V1.2's dashboard recomputes these warnings from a complete, valid `content_ideas.json` batch. It labels them as current evaluation rather than recorded run history, and distinguishes zero warnings from unavailable, incomplete or failed evaluation. See [dashboard quality states](dashboard.md#provenance-and-quality).

| Check | Rule | Suggested response |
| --- | --- | --- |
| Duplicate hooks | Equal after case/punctuation normalization | Choose a different opening question. |
| Near-identical hooks | Token-sequence similarity ≥ 0.80 | Change the question or proposed demonstration. |
| Repetitive scripts | Core script similarity ≥ 0.78 | Rewrite explanation and demonstration, not just source title. |
| Missing sections | Blank idea fields, no nonblank visuals, or missing/empty labeled script sections | Add substantive content to the named fields. |
| Length | Fewer than 80 or more than 160 whitespace-delimited words | Expand concrete steps or trim; time narration. |
| Generic filler | Match against a small explicit phrase list | Replace phrases with a topic or observable action. |
| Attribution | Missing source ID, platform, title, or URL | Restore source metadata. |
| Fact-check label | Missing note or disabled requirement | Restore verification instructions. |

Pairwise similarity uses standard-library `SequenceMatcher` on normalized tokens with autojunk disabled. Script comparison removes the opening paragraph and the generator's quoted source-title sentence, so changing the hook or quoted title does not mask repeated script bodies. A maximum normal CLI batch of 20 ideas yields at most 190 pair comparisons.

These thresholds and word counts are editorial heuristics, not objective creativity, originality, factuality, accessibility, or virality scores. Related topics can legitimately trigger warnings. Paraphrased repetition, absent reasoning behind nonempty section labels, or filler outside the small phrase list can go undetected. Alternative future providers must use the section-label convention to avoid missing-section warnings, or adapt the evaluator. Review generated text manually.
