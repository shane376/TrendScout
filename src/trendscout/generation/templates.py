from ..models import AnalyzedPost, VideoIdea


class TemplateGenerator:
    def generate(self, posts: list[AnalyzedPost], niche: str, mode: str) -> list[VideoIdea]:
        approaches = [
            ("Test the claim", "Would this actually help your workflow?", "Choose one small task you already understand. Record your current approach, then investigate the approach raised in this post. Keep the input and success criteria the same. Show the steps side by side and label anything you could not reproduce. Discuss where a human review is still needed."),
            ("Questions before trying", "Before you try this, ask these three questions.", "Start with the problem: what task would this solve for you? Next, check the evidence: does the original discussion link to documentation or a reproducible example? Finally, consider the tradeoffs: what setup, cost, or data access would your own test require? Put each question on screen and leave space for your findings."),
            ("Build a verification checklist", "A popular discussion is a starting point for a test.", "Turn the topic into a checklist. Find the original documentation, identify one claim you can check, and design a small demonstration. Capture the result on screen, including any failure. Separate what you observed from what the author suggested. Finish by showing which questions remain unanswered, so viewers can decide what to investigate themselves."),
            ("Explain the problem", "What problem is this discussion really trying to solve?", "Begin with a simple diagram of the workflow involved. Mark the step that seems confusing or repetitive. Use the post as a question to investigate, then find a reliable source that explains that step. Show a small example only after checking it. End with the limits of the example and one practical question viewers can apply to their own workflow."),
            ("Compare your options", "How would you decide whether this approach fits?", "Sketch two possible ways to tackle the underlying task: your current workflow and the approach you want to investigate. Do not declare a winner yet. Choose criteria such as effort, clarity, and review needs. Gather evidence for each criterion, then show your findings in a simple table. Flag missing information and explain what you would test next."),
        ]
        ideas = []
        for index, analyzed in enumerate(posts):
            post = analyzed.post
            label, hook, instructions = approaches[index % len(approaches)]
            topic = post.title[:180]
            script = (f"{hook} A source post raises this topic: “{topic}”. "
                      f"For creators exploring {niche}, this is a research lead, and the post alone does not verify its claims. "
                      f"{instructions} What evidence would you need before using this in your own work?")
            ideas.append(VideoIdea(
                title=f"{label}: {post.title[:65]}", target_niche=niche,
                source_id=post.id, source_platform=post.platform, source_title=post.title,
                source_url=post.url, content_angle=f"{label.lower()} around the source question: {topic}",
                hook=hook, script=script,
                suggested_visuals=[f"Title card quoting the source topic: {topic}",
                    f"Screen capture or diagram illustrating: {label.lower()}",
                    "Evidence checklist with verified and unverified items clearly labeled"],
                call_to_action="What would you test first? Share your criteria in the comments.",
                opportunity_score=analyzed.opportunity_score, mode=mode,
            ))
        return ideas
