"""Deterministic topic extraction and editorial plans; no factual inference."""

import re
from dataclasses import dataclass

from ..models import AnalyzedPost, ContentPost, VideoIdea


@dataclass(frozen=True)
class TopicPlan:
    keywords: tuple[str, ...]
    subject: str
    hook: str
    problem: str
    explanation: str
    demonstration: str
    takeaway: str
    visual: str


# These are proposed experiments, never claims about a product or source outcome.
PLANS = (
    TopicPlan(
        ("caption", "captions", "accessible"), "caption accessibility review",
        "Can you follow this clip with the sound switched off?",
        "Captions need a viewing check as well as a check of the words.",
        "Timing, readability, and meaningful sound cues are separate review questions.",
        "Use a short clip you own and review it muted on a phone-sized preview. Pause where a caption changes, compare it with the audio, and note unclear timing or missing sound cues. Record suggested edits without claiming an accessibility certification.",
        "Review with intended viewers when possible; a solo checklist cannot establish accessibility for everyone.",
        "Muted phone-sized preview beside caption timing and sound-cue annotations",
    ),
    TopicPlan(
        ("transcription", "transcript"), "transcription accuracy",
        "Would your transcript preserve a name, a pause, and a correction?",
        "A readable transcript still needs an accuracy check before you reuse it.",
        "Separate word accuracy from punctuation and speaker attribution in your review.",
        "Record a short clip with a name and a spoken correction. Make a manual reference transcript, then compare a candidate transcript line by line. Highlight differences without hiding failed cases.",
        "Keep a correction checklist; this proposed test does not establish any tool's accuracy.",
        "Split screen: recorded clip, manual reference, and highlighted transcript differences",
    ),
    TopicPlan(
        ("private", "privacy", "uploading", "sensitive", "data access"), "private-file handling",
        "Before uploading a private file, can you trace where it goes?",
        "A file-upload workflow needs a privacy review before any real private data enters it.",
        "Storage, retention, and deletion are separate questions to verify in current documentation.",
        "Draw the proposed file journey using a dummy document. Check the service documentation for each stop, then mark what is documented and what remains unknown. Do not upload sensitive material for this demonstration.",
        "An unanswered data-handling question is a reason to pause and investigate, not proof of safety.",
        "Dummy document beside a data-flow diagram with documented and unknown checkpoints",
    ),
    TopicPlan(
        ("editing", "writing", "draft", "style"), "draft editing effort",
        "How much editing would this draft need before you could use it?",
        "A finished-looking draft is not the same as a draft you have reviewed.",
        "A useful comparison separates factual corrections, structure changes, and style edits.",
        "Choose a short brief and a draft you have permission to show. Mark every required change in three colors, then revise one paragraph on screen. Keep a manual version of the same brief as your comparison.",
        "Judge the revisions your example requires; do not generalize one draft into a product verdict.",
        "Color-coded draft annotations followed by one paragraph revised on screen",
    ),
    TopicPlan(
        ("failures", "failure", "discard", "errors"), "workflow failure records",
        "Could someone reproduce the workflow failure you just found?",
        "An unexplained failure is hard to investigate or turn into a useful lesson.",
        "A failure record should separate the input, expected behavior, observed behavior, and unresolved cause.",
        "Build an empty incident card with those four fields. Use a non-sensitive example only if you can reproduce it, and capture the steps. Leave the cause marked unknown until evidence supports an explanation.",
        "Share reproducible observations rather than guessing why an automation failed.",
        "Four-field incident card with a step-by-step screen recording placeholder",
    ),
    TopicPlan(
        ("citations", "citation", "source verification", "research assistant"), "citation verification",
        "Does that citation support the sentence beside it?",
        "A citation in a generated summary still needs to be opened and checked.",
        "Check that the page exists, that the quoted passage is present, and that it supports the specific claim.",
        "Choose one summary sentence and open its cited source. Put the sentence and relevant passage side by side. Mark the relationship as supported, unsupported, or unresolved, explaining what evidence would change your assessment.",
        "Keep an evidence trail for each checked claim; a link alone is not your conclusion.",
        "Summary sentence beside the cited passage and a three-way evidence label",
    ),
    TopicPlan(
        ("coding", "code", "python", "formulas"), "generated-code review",
        "What test would you run before trusting this generated code?",
        "A plausible code suggestion needs review before it becomes part of a working system.",
        "Expected outputs, edge cases, and permission boundaries are useful review criteria.",
        "Use a disposable example with no secrets or production access. Write down the expected behavior first, inspect the suggestion, and design one normal case and one edge case. Show results only after actually running the tests.",
        "Passing an example is limited evidence, not a guarantee that the code is safe or correct.",
        "Disposable code sample beside expected outputs and a two-case test table",
    ),
    TopicPlan(
        ("meeting", "summary", "summaries", "task list"), "summary review",
        "Could you trace each action item back to the original conversation?",
        "A summary needs checking before anyone treats it as a record of decisions.",
        "Separate decisions, suggested actions, and unresolved questions instead of blending them together.",
        "Write a short fictional conversation and its reference notes. Compare a candidate summary with those notes. Highlight one decision and one open question, checking whether an action owner was explicitly named rather than inferred.",
        "Keep uncertainty visible and verify action items with the original material before sharing.",
        "Fictional conversation beside decision, action, and open-question columns",
    ),
    TopicPlan(
        ("local", "hosted", "comparison", "comparing", "baseline"), "workflow comparison",
        "Would two workflows still look equal on the same input?",
        "A comparison needs a shared task before differences become meaningful.",
        "Choose criteria in advance so the demonstration does not quietly change the goal.",
        "Prepare one non-sensitive input and a blank comparison table. Record setup steps, review effort, and output checks for each workflow. Fill the table only with observations you can reproduce, leaving unavailable evidence clearly marked.",
        "Pick criteria relevant to your task; one comparison does not establish a universal winner.",
        "Shared input feeding two workflow diagrams and an initially blank comparison table",
    ),
)

STOP_WORDS = set("a an the how what why when where should would could can do does i you your my to for of in on and or is are with this that help question about please".split())


def words(text: str) -> list[str]:
    return re.findall(r"[^\W_]+(?:[-'][^\W_]+)*", text.lower(), re.UNICODE)


def topic_label(post: ContentPost) -> str:
    """Keep bounded source vocabulary; never promote extracted text to a claim."""
    tokens = [token for token in words(post.title) if token not in STOP_WORDS]
    if len(tokens) < 2:
        tokens += [token for token in words(post.body or "") if token not in STOP_WORDS][:8]
    return " ".join(dict.fromkeys(tokens))[:75].strip() or "the source question"


def extract_plan(post: ContentPost) -> TopicPlan:
    title = " ".join(words(post.title))
    body = " ".join(words((post.body or "")[:4000]))

    def relevance(plan: TopicPlan) -> int:
        # Title evidence wins over incidental body references. Word boundaries
        # avoid matching 'code' inside 'decode', for example.
        return sum(3 * bool(re.search(rf"\b{re.escape(key)}\b", title))
                   + bool(re.search(rf"\b{re.escape(key)}\b", body))
                   for key in plan.keywords)

    plan = max(PLANS, key=relevance)
    if relevance(plan):
        return plan
    topic = topic_label(post)
    return TopicPlan(
        (), topic,
        f"What would count as evidence for {topic}?",
        f"The question around {topic} needs a concrete example before drawing conclusions.",
        "Separate what the source asks from what it actually demonstrates; neither popularity nor a confident title verifies a claim.",
        f"Turn {topic} into one answerable question. Find the original documentation, choose a non-sensitive example, and write the expected observation before testing. Show the example and mark any missing evidence explicitly.",
        "Report only the observation you can verify; if evidence is missing, end with the next research step.",
        f"Question card for {topic}, an evidence checklist, and a blank observation log",
    )


APPROACHES = (
    ("Evidence walkthrough", "Walk through one case and show the evidence at each step."),
    ("Preflight checklist", "Turn these checks into a checklist to complete before trying the workflow."),
    ("Controlled demonstration", "State the expected observation first, then record whether the example matches it."),
    ("Failure investigation", "Focus the example on what could go wrong, keeping unknown causes explicitly unresolved."),
    ("Decision guide", "Use the evidence to explain what you would investigate before deciding to proceed."),
    ("Viewer challenge", "Invite viewers to apply the same checks to a non-sensitive example of their own."),
)


class TemplateGenerator:
    def generate(self, posts: list[AnalyzedPost], niche: str, mode: str) -> list[VideoIdea]:
        ideas = []
        for index, analyzed in enumerate(posts):
            post = analyzed.post
            plan = extract_plan(post)
            approach, direction = APPROACHES[index % len(APPROACHES)]
            # Source titles remain quoted, bounded data. Body text selects a plan
            # but is never followed as instructions or repeated as verified fact.
            excerpt = " ".join(post.title.split()[:18])[:150]
            hook = plan.hook
            script = (
                f'{hook}\n\nProblem: {plan.problem} '
                f'The source post raises this topic: "{excerpt}".\n\n'
                f"Explanation: {plan.explanation}\n\n"
                f"Demonstration: {plan.demonstration} {direction}\n\n"
                f"Takeaway: {plan.takeaway} This is a proposed test, not a verified result."
            )
            ideas.append(VideoIdea(
                title=f"{approach}: {plan.subject}", target_niche=niche,
                source_id=post.id, source_platform=post.platform,
                source_title=post.title, source_url=post.url,
                content_angle=(f'{approach} for {niche}: investigate "{excerpt}" '
                               f"with a practical review of {plan.subject}."),
                hook=hook, script=script,
                suggested_visuals=[plan.visual, f"Source question card: {excerpt}",
                                   f"End card: {plan.takeaway}"],
                call_to_action=f"What would you check first in a review of {plan.subject}?",
                opportunity_score=analyzed.opportunity_score, mode=mode,
                fact_check_note="Proposed demonstration only. Verify source claims, current documentation, permissions, and any recorded results before production.",
            ))
        return ideas
