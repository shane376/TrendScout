"""Actionable editorial lint, not a creativity, truth, or virality score."""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from itertools import combinations

from ..models import VideoIdea

SECTIONS = ("Problem", "Explanation", "Demonstration", "Takeaway")
FILLER = (
    "game changer", "game-changing", "unlock your potential", "in today's fast-paced world",
    "take it to the next level", "revolutionize your workflow", "you won't believe",
    "a popular discussion is a starting point", "would this actually help your workflow",
)


@dataclass(frozen=True)
class QualityWarning:
    code: str
    idea_numbers: tuple[int, ...]
    message: str


def normalized(text: str) -> str:
    return " ".join(re.findall(r"\w+", text.casefold()))


def similarity(left: str, right: str) -> float:
    """Token-sequence similarity, excluding punctuation and letter case."""
    return SequenceMatcher(None, normalized(left).split(), normalized(right).split(),
                           autojunk=False).ratio()


def script_core(script: str) -> str:
    # Exclude hooks and quoted source titles: changing either should not hide
    # repetition in the actual explanation and proposed demonstration.
    script = script.split("\n\n", 1)[-1]
    return re.sub(r'The source post raises this topic: ".*?"\.', "", script)


def evaluate_quality(ideas: list[VideoIdea]) -> list[QualityWarning]:
    warnings = []
    for number, idea in enumerate(ideas, 1):
        def warn(code: str, message: str) -> None:
            warnings.append(QualityWarning(code, (number,), message))

        missing = [name for name in ("title", "hook", "content_angle", "script", "call_to_action")
                   if not getattr(idea, name).strip()]
        if not idea.suggested_visuals or not any(v.strip() for v in idea.suggested_visuals):
            missing.append("suggested_visuals")
        for section in SECTIONS:
            match = re.search(
                rf"(?:^|\n\s*\n){section}:[ \t]*(.*?)(?=\n\s*\n(?:{'|'.join(SECTIONS)}):|$)",
                idea.script, re.DOTALL | re.IGNORECASE,
            )
            if not match or not match.group(1).strip():
                missing.append(section)
        if missing:
            warn("missing_sections", "Add substantive content for: " + ", ".join(missing) + ".")
        count = len(idea.script.split())
        if count < 80:
            warn("short_script", f"Script has {count} words; add a concrete explanation and demonstration toward 80–160 words.")
        elif count > 160:
            warn("long_script", f"Script has {count} words; trim toward 80–160 words and time a spoken read-through.")
        filler = [phrase for phrase in FILLER if normalized(phrase) in normalized(idea.hook + " " + idea.script)]
        if filler:
            warn("generic_filler", f"Replace vague language ({', '.join(filler)}) with a topic, check, or observable action.")
        if not all(getattr(idea, field) is not None and str(getattr(idea, field)).strip() for field in
                   ("source_id", "source_platform", "source_title", "source_url")):
            warn("missing_attribution", "Restore the source ID, platform, title, and URL before exporting.")
        if not idea.requires_fact_check or not idea.fact_check_note.strip():
            warn("missing_fact_check", "Label this draft for fact-checking and describe what needs verification.")

    for (left_index, left), (right_index, right) in combinations(enumerate(ideas, 1), 2):
        pair = (left_index, right_index)
        if normalized(left.hook) and normalized(right.hook):
            exact = normalized(left.hook) == normalized(right.hook)
            if exact or similarity(left.hook, right.hook) >= .80:
                warnings.append(QualityWarning(
                    "duplicate_hook" if exact else "similar_hooks", pair,
                    "Rewrite one opening around a different topic-specific question or demonstration.",
                ))
        if left.script.strip() and right.script.strip() and similarity(script_core(left.script), script_core(right.script)) >= .78:
            warnings.append(QualityWarning(
                "repetitive_scripts", pair,
                "Change the explanation and demonstration; swapping the title or hook alone is insufficient.",
            ))
    return warnings
