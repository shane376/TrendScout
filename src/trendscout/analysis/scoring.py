import math
from datetime import datetime


def normalize(values: list[int]) -> list[float]:
    scaled = [math.log1p(max(0, value)) for value in values]
    if not scaled:
        return []
    low, high = min(scaled), max(scaled)
    # No comparative evidence when every candidate has identical engagement.
    if high == low:
        return [0.0] * len(values)
    return [100 * (value - low) / (high - low) for value in scaled]


def recency(created_at: datetime, now: datetime, half_life_hours: float = 72) -> float:
    if half_life_hours <= 0 or not math.isfinite(half_life_hours):
        raise ValueError("Half-life must be positive and finite")
    if created_at.tzinfo is None or now.tzinfo is None:
        raise ValueError("Scoring requires timezone-aware timestamps")
    age = max(0, (now - created_at).total_seconds() / 3600)
    return 100 * 2 ** (-age / half_life_hours)
