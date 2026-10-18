"""Read-only report: python -m trendscout.ingestion.youtube_intelligence --fixture."""

import argparse
import json

from pydantic import ValidationError

from trendscout.intelligence.models import RankingConfig
from trendscout.intelligence.youtube import IntelligenceInputError, analyze_collection

from .base import CollectionError
from .models import CollectionRequest
from .youtube import YouTubeSource


def _display(value):
    return "Unavailable" if value is None else json.dumps(value, ensure_ascii=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Read-only YouTube research priority report; no persistence or measured growth.")
    parser.add_argument("--query", required=True)
    parser.add_argument("--limit", type=int, default=10, help="Candidate budget, 1–100.")
    parser.add_argument("--fixture", action="store_true", help="Explicit synthetic offline analysis.")
    parser.add_argument("--authorized-live-analysis", action="store_true",
                        help="Confirm applicable authorization for derived analytics, distinct from API-key access; does not authorize storage.")
    for name, default in (("freshness", .30), ("views", .35), ("likes", .20), ("comments", .15)):
        parser.add_argument(f"--{name}-weight", type=float, default=default)
    parser.add_argument("--half-life-days", type=float, default=30)
    args = parser.parse_args(argv)
    if not args.fixture and not args.authorized_live_analysis:
        print("Live analysis requires --authorized-live-analysis after reviewing applicable YouTube analytics permissions. No API request made.")
        return 2
    try:
        config = RankingConfig(
            freshness_weight=args.freshness_weight, views_weight=args.views_weight,
            likes_weight=args.likes_weight, comments_weight=args.comments_weight,
            freshness_half_life_days=args.half_life_days,
        )
        source_id = "youtube.fixture" if args.fixture else "youtube.data-api-v3"
        request = CollectionRequest(source_id=source_id, query=args.query, limit=args.limit)
        with YouTubeSource(fixture=args.fixture) as source:
            result = source.collect(request)
        report = analyze_collection(result, config, authorized_live_analysis=args.authorized_live_analysis)
    except ValidationError:
        print("Invalid query, limit, ranking weights or environment configuration. No report produced.")
        return 2
    except (IntelligenceInputError, PermissionError) as error:
        print(str(error))
        return 2
    except CollectionError as error:
        print(f"Collection error [{error.code}]: {error}")
        return 1
    print("SYNTHETIC FIXTURE - not live trends or market evidence." if args.fixture else "LIVE - third-party research analysis; not YouTube metrics.")
    print(f"Collection: {report.collection_status}; ranked: {len(report.videos)}; excluded: {report.excluded_count}; as of {report.as_of.isoformat()}")
    print("Method configuration: " + config.model_dump_json())
    for warning in report.warnings:
        print("Caveat: " + warning)
    for video in report.videos:
        score = f"{video.research_priority_score:.2f}/100" if video.research_priority_score is not None else "Unavailable"
        print(f"\n#{video.rank} Research priority: {score}; title: {_display(video.title)}")
        print(f"Source: {_display(video.source_id)} / {_display(video.external_id)}; URL: {_display(video.source_url)}")
        print(f"Publication: {_display(video.published_at.isoformat() if video.published_at else None)}; observation: {_display(video.observed_at.isoformat() if video.observed_at else None)}")
        print("Signals (views/day is a lifetime average, not measured recent velocity): " + video.signals.model_dump_json())
        print("Components: " + "; ".join(
            f"{name}={component.score:.2f}/100 (weight {component.weight:.3f})" if component.available
            else f"{name}=Unavailable (weight {component.weight:.3f})"
            for name, component in video.components.items()
        ))
        print("Explanation: " + video.explanation)
        print("Completeness: " + video.completeness.model_dump_json())
        for label, opportunity in (("Creator intelligence", video.creator), ("Business intelligence", video.business)):
            print(label + ": " + _display(opportunity.interpretation if opportunity else None))
            if opportunity:
                print("Evidence: " + json.dumps(opportunity.evidence, ensure_ascii=True))
                print("Lens limitation: " + opportunity.limitation)
        print("Caveats: " + " ".join(video.warnings))
    print("Read-only: no API metadata, derived per-video reports or raw responses written to disk.")
    return 0 if report.collection_status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
