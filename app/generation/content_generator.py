import uuid

from pydantic import BaseModel, Field

from app.db.models import ContentCandidate, Project, ProjectFact, RedditOpportunity, Subreddit
from app.db.models.enums import ContentAngle, ContentType
from app.llm.prompt_safety import wrap_untrusted
from app.llm.provider import LLMProvider

GENERATOR_SYSTEM_PROMPT = (
    "You are ContentGenerator, an agent that drafts Reddit comments for a real human to "
    "review and (if they choose) post. The product principle is relevance + usefulness + "
    "authenticity over posting volume -- optimize for that, never for maximum promotion.\n\n"
    "Hard rules, no exceptions:\n"
    "- Use ONLY facts explicitly supported by the <project_facts> supplied to you. "
    "Never invent metrics, benchmarks, user counts, testimonials, or endorsements.\n"
    "- Never fabricate a Reddit community's reaction, consensus, or sentiment.\n"
    "- Avoid exaggerated marketing language, superlatives, and hype.\n"
    "- Adapt tone and content to the actual subreddit's culture and stated rules -- do not "
    "write a generic advertisement.\n"
    "- The comment must provide genuine value (a real answer, insight, or resource) "
    "independent of whether the reader ever visits the project's link.\n"
    "- If the project has any obvious affiliation with the author (it always does -- this "
    "is the project's own promotion), the draft must read as a disclosed, first-person "
    "recommendation ('I built/maintain X'), never as a disguised third-party endorsement.\n"
    "- Never write anything intended to manipulate voting or engagement.\n"
    "- For every fact you use, include its id (from <project_facts>) in `source_fact_ids` "
    "on that candidate. If you cannot support a sentence with a supplied fact, cut the "
    "sentence rather than inventing support for it."
)

ANGLE_DESCRIPTIONS = {
    "EDUCATIONAL": "Teach something useful related to the discussion; the project is a footnote.",
    "TECHNICAL": "Go deep on how the project's approach/architecture solves the problem.",
    "PROBLEM_SOLUTION": "Name the pain point in the thread, then show how the project fits.",
    "CASE_STUDY": "Reference a concrete, fact-supported example of the project in use.",
    "OPEN_SOURCE": "Emphasize openness/transparency/community aspects, if genuinely true.",
    "QUESTION": "Ask a genuine clarifying/engaging question that naturally surfaces the project.",
    "DISCUSSION": "Add a substantive opinion to the discussion; mention the project in passing.",
    "DATA": "Lead with a concrete, fact-supported number or comparison.",
    "EXPERIMENT": "Describe something the project author tried/tested, per supplied facts.",
    "ANNOUNCEMENT": "State plainly that this is the author's own project, disclosed up front.",
}


class GeneratedCandidate(BaseModel):
    angle: str = Field(description=f"One of: {', '.join(ANGLE_DESCRIPTIONS)}")
    body: str = Field(description="The full comment text, ready for human review.")
    cta: str | None = Field(default=None, description="Optional single-sentence call to action.")
    rationale: str = Field(description="Why this angle/framing fits this specific discussion.")
    source_fact_ids: list[str] = Field(
        default_factory=list, description="ids of <project_facts> entries actually used."
    )


class ContentGenerationResult(BaseModel):
    candidates: list[GeneratedCandidate] = Field(max_length=3)


def _format_facts(facts: list[ProjectFact]) -> str:
    if not facts:
        return "(no extracted facts are available for this project yet)"
    return "\n".join(f"[{fact.id}] ({fact.fact_type.value}) {fact.fact}" for fact in facts)


async def generate_candidates(
    llm: LLMProvider,
    project: Project,
    opportunity: RedditOpportunity,
    subreddit: Subreddit,
    facts: list[ProjectFact],
) -> ContentGenerationResult:
    """Generate up to 3 grounded comment candidates for a discovered opportunity."""
    facts_block = wrap_untrusted("project_facts", _format_facts(facts))
    discussion_block = wrap_untrusted(
        f"r/{subreddit.name} discussion",
        f"Title: {opportunity.title}\n\n{opportunity.body or ''}",
    )
    subreddit_block = wrap_untrusted(
        f"r/{subreddit.name} culture and rules",
        subreddit.culture_summary or "(no analysis available)",
    )

    prompt = (
        f"Project: {project.name}\n\n{facts_block}\n\n{discussion_block}\n\n{subreddit_block}\n\n"
        "Draft up to 3 distinct comment candidates for this discussion, each using a "
        "different angle from the taxonomy. Every sentence that states a fact about the "
        "project must be traceable to one of the ids in <project_facts>."
    )

    return await llm.generate_structured(
        prompt, ContentGenerationResult, system=GENERATOR_SYSTEM_PROMPT
    )


def to_content_candidates(
    project_id: uuid.UUID, opportunity: RedditOpportunity, result: ContentGenerationResult
) -> list[ContentCandidate]:
    candidates: list[ContentCandidate] = []
    for item in result.candidates:
        try:
            angle = ContentAngle(item.angle)
        except ValueError:
            angle = ContentAngle.DISCUSSION
        candidates.append(
            ContentCandidate(
                project_id=project_id,
                opportunity_id=opportunity.id,
                content_type=ContentType.COMMENT,
                title=None,
                body=item.body,
                cta=item.cta,
                angle=angle,
                rationale=item.rationale,
                source_fact_ids=item.source_fact_ids,
            )
        )
    return candidates
