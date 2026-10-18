"""Research priority from one bounded batch, never measured growth or demand."""

import re
from datetime import datetime

from pydantic import ValidationError

from trendscout.ingestion.models import CollectionResult, ContentItem, as_utc

from .models import (
    DataCompleteness, IntelligenceReport, Opportunity, RankedVideo, RankingConfig,
    ScoreComponent, VideoSignals,
)

LIMITATION = "Exploratory research heuristic, not a prediction of virality or profitability."
LIVE_PERMISSION = (
    "Live derived analysis requires explicit analytics authorization, distinct from an API key. "
    "Use authorized_live_analysis=True only after reviewing applicable YouTube permissions."
)


class IntelligenceInputError(ValueError):
    """Invalid canonical input; never include source payloads or secrets in the error."""


def _signals(item: ContentItem, as_of: datetime, config: RankingConfig):
    warnings = []
    age = (as_of - item.published_at).total_seconds() / 86400 if item.published_at else None
    future = age is not None and age < 0
    if future:
        age = None
        warnings.append("Future publication timestamp: age-based signals and derived engagement signals are unavailable.")
    elif age is None:
        warnings.append("Publication timestamp unavailable; age and lifetime average cannot be calculated.")
    metrics = item.metrics
    if metrics is not None and metrics.expires_at is not None and metrics.expires_at <= as_of:
        metrics = None
        warnings.append("Metric observation has expired; counters and engagement signals are unavailable.")
    values = metrics.values if metrics is not None else {}
    views, likes, comments = (values.get(name) for name in ("views", "likes", "comments"))
    observed_age = ((metrics.observed_at - item.published_at).total_seconds() / 86400
                    if metrics is not None and item.published_at else None)
    inconsistent_observation = observed_age is not None and observed_age < 0
    average = None
    if observed_age is not None and observed_age < 0:
        observed_age = None
        warnings.append("Publication follows the metric observation; derived engagement signals are unavailable.")
    if not future and observed_age is not None and observed_age > 0 and views is not None:
        average = views / observed_age
        if observed_age < config.exposure_floor_days:
            warnings.append("Short exposure: lifetime average is unstable; view scoring uses an exposure floor.")
    elif observed_age == 0:
        warnings.append("Zero elapsed exposure at observation; lifetime average is unavailable.")
    like_ratio = likes / views if not future and not inconsistent_observation and views is not None and views > 0 and likes is not None else None
    comment_ratio = comments / views if not future and not inconsistent_observation and views is not None and views > 0 and comments is not None else None
    if views == 0:
        warnings.append("Zero views: like/view and comment/view ratios are unavailable, not zero.")
    if views is None:
        warnings.append("Views unavailable: lifetime average and engagement ratios cannot be inferred.")
    if views is not None and 0 < views < 100:
        warnings.append("Small view denominator: engagement ratios can be unstable and do not establish audience preference.")
    if any(value is not None and value > 1 for value in (like_ratio, comment_ratio)):
        warnings.append("A ratio exceeds one; counters are not synchronized probabilities or viewer intent.")
    if metrics is not None and metrics.observed_at < as_of:
        warnings.append("Counters reflect the stated observation time, not a refreshed measurement at report time.")
    warnings.append("One observation cannot establish recent velocity, growth, sentiment, or demand.")
    return VideoSignals(
        age_days=age, observation_age_days=observed_age, views=views, likes=likes, comments=comments,
        lifetime_average_views_per_day=average, like_to_view_ratio=like_ratio, comment_to_view_ratio=comment_ratio,
        freshness_score=100 * 2 ** (-age / config.freshness_half_life_days) if age is not None else None,
    ), warnings


def _components(signals: VideoSignals, config: RankingConfig):
    def saturate(value, reference):
        return 100 * (value / (value + reference)) if value is not None else None

    view_value = None
    if signals.lifetime_average_views_per_day is not None:
        view_value = signals.views / max(signals.observation_age_days, config.exposure_floor_days)
    raw = {
        "freshness": (signals.freshness_score, config.freshness_weight,
                      "100 × 2^(-age_days / half_life_days); unavailable dates receive no freshness credit."),
        "view_evidence": (saturate(view_value, config.views_per_day_reference), config.views_weight,
                          "100 × stabilized lifetime views/day / (stabilized lifetime views/day + reference); not recent velocity."),
        "like_ratio": (saturate(signals.like_to_view_ratio, config.like_ratio_reference), config.likes_weight,
                       "100 × observed like/view ratio / (ratio + reference); not viewer sentiment."),
        "comment_ratio": (saturate(signals.comment_to_view_ratio, config.comment_ratio_reference), config.comments_weight,
                          "100 × observed comment/view ratio / (ratio + reference); comment topics were not collected."),
    }
    total = sum(value[1] for value in raw.values())
    components = {name: ScoreComponent(score=score, weight=weight / total, available=score is not None, explanation=explanation)
                  for name, (score, weight, explanation) in raw.items()}
    usable = [component for component in components.values() if component.available and component.weight > 0]
    score = min(100.0, sum(component.score * component.weight for component in usable)) if usable else None
    return components, score


def _opportunities(item: ContentItem, signals: VideoSignals):
    evidence = tuple(f"{label} (quoted source text): {value[:180]}" for label, value in
                     (("Title", item.title), ("Description", item.description)) if value and value.strip())
    if not evidence:
        return None, None
    text = " ".join(((item.title or "")[:180], (item.description or "")[:180])).casefold()
    cues = (
        (r"\b(?:automate|automation|workflow)\b", "the workflow mentioned in the source"),
        (r"\b(?:caption|captions|transcription|transcript)\b", "the transcription or caption task mentioned in the source"),
        (r"\b(?:privacy|private|sensitive)\b", "the data-handling question mentioned in the source"),
        (r"\b(?:code|coding|python)\b", "the coding task mentioned in the source"),
    )
    topic = next((label for pattern, label in cues if re.search(pattern, text)), "the topic quoted in the source metadata")
    comment_positive = signals.comment_to_view_ratio is not None and signals.comment_to_view_ratio > 0
    creator_evidence = evidence + tuple(
        f"Observed {name}: {value:.6g}; viewer intent is unknown."
        for name, value in (("like/view ratio", signals.like_to_view_ratio), ("comment/view ratio", signals.comment_to_view_ratio))
        if value is not None
    )
    creator = Opportunity(
        lens="creator", evidence=creator_evidence,
        interpretation=f"Possible content angle: {'a question-and-answer walkthrough' if comment_positive else 'a worked example'} of {topic}. Verify the example before making claims.",
        limitation="Engagement ratios, when available, do not establish audience preference. Comment topics and viewer intent are unknown.",
    )
    business = Opportunity(
        lens="business", evidence=evidence,
        interpretation=f"Unvalidated research hypothesis: people exploring {topic} may have workflow questions. Interview intended users and test whether any recurring problem exists before proposing a solution.",
        limitation="Metadata cannot establish customer pain, willingness to pay, competitive gaps, or validated market demand.",
    )
    return creator, business


def analyze_collection(result: CollectionResult, config: RankingConfig | None = None, *,
                       as_of: datetime | None = None, authorized_live_analysis: bool = False) -> IntelligenceReport:
    try:
        result = CollectionResult.model_validate(result.model_dump(warnings=False))
        config = RankingConfig.model_validate((config or RankingConfig()).model_dump(warnings=False))
    except ValidationError:
        raise IntelligenceInputError("Invalid canonical result or ranking configuration; no intelligence computed.") from None
    if result.run.provenance == "unknown":
        raise IntelligenceInputError("Unknown provenance cannot be analyzed as YouTube evidence.")
    if result.run.provenance == "live" and not authorized_live_analysis:
        raise PermissionError(LIVE_PERMISSION)
    reference = as_utc(as_of) if as_of is not None else result.run.completed_at
    if reference < result.run.completed_at:
        raise IntelligenceInputError("Report time cannot precede collection completion.")
    warnings = [LIMITATION, "Scores are third-party research priorities, not YouTube metrics or business demand scores."]
    if result.run.status != "complete":
        warnings.append(f"Collection is {result.run.status}; this report is not a representative sample. Issues: {', '.join(result.run.error_codes)}.")
    if result.run.provenance == "synthetic":
        warnings.append("Synthetic fixture only; not live trends or market evidence.")
    ranked, excluded = [], 0
    for item in result.items:
        if item.platform != "youtube" or item.content_type != "video" or (item.expires_at is not None and item.expires_at <= reference):
            excluded += 1
            continue
        signals, caveats = _signals(item, reference, config)
        components, score = _components(signals, config)
        fields = {"title": item.title, "description": item.description if item.description and item.description.strip() else None, "creator": item.creator,
                  "published_at": item.published_at, "views": signals.views, "likes": signals.likes, "comments": signals.comments}
        available = tuple(name for name, value in fields.items() if value is not None)
        missing = tuple(name for name, value in fields.items() if value is None)
        completeness = DataCompleteness(available_fields=available, missing_fields=missing, fraction=len(available) / len(fields))
        creator, business = _opportunities(item, signals)
        if creator is None:
            caveats.append("Source text unavailable; grounded opportunity hypotheses cannot be produced.")
        if missing:
            caveats.append("Unavailable evidence: " + ", ".join(missing) + ".")
        explanation = "; ".join(
            f"{name}: {component.weight:.3f} × {component.score:.3f} = {component.weight * component.score:.3f} points"
            if component.available else f"{name}: unavailable; its {component.weight:.3f} weight is not redistributed"
            for name, component in components.items()
        )
        ranked.append(RankedVideo(
            rank=1, external_id=item.external_id, source_id=item.source_id, title=item.title,
            source_url=str(item.url) if item.url else None, published_at=item.published_at,
            observed_at=item.metrics.observed_at if item.metrics else None,
            signals=signals, components=components, research_priority_score=score, completeness=completeness,
            explanation=explanation, warnings=tuple(caveats), creator=creator, business=business,
        ))
    ranked.sort(key=lambda item: (item.research_priority_score is None,
                                  -(item.research_priority_score or 0), item.source_id, item.external_id))
    if excluded:
        warnings.append(f"Excluded {excluded} non-YouTube, non-video, or expired records; no analysis fabricated for them.")
    return IntelligenceReport(
        source_id=result.run.source_id, provenance=result.run.provenance, collection_status=result.run.status,
        as_of=reference, config=config, videos=tuple(item.model_copy(update={"rank": index}) for index, item in enumerate(ranked, 1)),
        excluded_count=excluded, warnings=tuple(warnings),
    )
