"""Read-only collection: python -m trendscout.ingestion.youtube_demo --fixture."""

import argparse

from pydantic import ValidationError

from .base import CollectionError
from .models import CollectionRequest
from .youtube import YouTubeSource


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect bounded YouTube metadata in memory; no database or file exports.")
    parser.add_argument("--query", required=True, help="Niche or keyword (1–200 characters).")
    parser.add_argument("--limit", type=int, default=10, help="Maximum candidate count, 1–100.")
    parser.add_argument("--fixture", action="store_true", help="Explicit synthetic offline mode; no key or network required.")
    args = parser.parse_args(argv)
    try:
        # Validate arguments before configuring credentials or constructing a transport.
        source_id = "youtube.fixture" if args.fixture else "youtube.data-api-v3"
        request = CollectionRequest(source_id=source_id, query=args.query, limit=args.limit)
        with YouTubeSource(fixture=args.fixture) as source:
            result = source.collect(request)
    except ValidationError:
        print("Invalid query/limit or YouTube environment configuration. Check documented bounds.")
        return 2
    except CollectionError as error:
        print(f"Collection error [{error.code}]: {error}")
        return 1
    print("SYNTHETIC FIXTURE — not live YouTube evidence." if args.fixture else "LIVE — YouTube Data API v3 collection.")
    print(f"Source: {result.run.source_id}; status: {result.run.status}; accepted: {result.run.item_count}; rejected: {result.run.rejected_count}")
    print(f"UTC collection: {result.run.started_at.isoformat()} to {result.run.completed_at.isoformat()}")
    for item in result.items[:3]:
        # JSON quotes terminal control characters in untrusted source text.
        print(item.model_dump_json(include={"external_id", "title", "creator", "url", "metrics"}))
    if result.run.error_codes:
        print("Collection issues: " + ", ".join(result.run.error_codes))
        explanations = {
            "rate_limited": "Quota or rate limit reached; no automatic retry was performed for that response.",
            "access_denied": "Access denied; check the API key, enabled API and application restrictions.",
            "unavailable": "Transport or server failure after bounded attempts.",
            "invalid_response": "Malformed or unexpected API response; no fixture fallback was used.",
            "page_limit": "The configured search page cap was reached before the candidate budget.",
            "pagination_cycle": "A repeated page token stopped pagination.",
            "invalid_record": "Malformed records were excluded.",
            "missing_video": "Some discovered videos had no usable details; availability is unknown.",
        }
        for code in result.run.error_codes:
            print(explanations[code])
    print("No source data written to disk. Live retention is not enabled by this command.")
    return 0 if result.run.status == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
