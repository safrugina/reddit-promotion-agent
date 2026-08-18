from typing import Literal

from pydantic import BaseModel, Field

from app.db.models import ProjectFact
from app.llm.prompt_safety import wrap_untrusted
from app.llm.provider import LLMProvider

GROUNDING_SYSTEM_PROMPT = (
    "You are GroundingValidator. You check a draft Reddit comment against a project's "
    "verified facts and classify every factual claim in the draft. Do not be lenient: "
    "if a claim about the project (a capability, a number, a comparison, a user/customer, "
    "an endorsement) is not clearly supported by the supplied facts, it is UNSUPPORTED -- "
    "even if it sounds plausible. Statements of the author's own opinion, or generic "
    "advice unrelated to the project, are OPINION, not a factual claim about the project."
)


class ClaimClassification(BaseModel):
    claim: str
    status: Literal["SUPPORTED", "UNSUPPORTED", "AMBIGUOUS", "OPINION"]
    explanation: str = Field(description="One sentence: which fact supports it, or why not.")


class GroundingReview(BaseModel):
    classifications: list[ClaimClassification]


def _format_facts(facts: list[ProjectFact]) -> str:
    if not facts:
        return "(no verified facts are available for this project)"
    return "\n".join(f"[{fact.id}] {fact.fact}" for fact in facts)


async def review_grounding(
    llm: LLMProvider, candidate_body: str, facts: list[ProjectFact]
) -> GroundingReview:
    facts_block = wrap_untrusted("verified_project_facts", _format_facts(facts))
    draft_block = wrap_untrusted("draft_comment", candidate_body)

    prompt = (
        f"{facts_block}\n\n{draft_block}\n\n"
        "List every distinct factual claim about the project made in the draft comment "
        "above, and classify each one."
    )
    return await llm.generate_structured(prompt, GroundingReview, system=GROUNDING_SYSTEM_PROMPT)


def grounding_score(review: GroundingReview) -> float:
    """0-100: share of factual claims that are SUPPORTED (OPINION claims are neutral --
    excluded from the denominator since they carry no grounding burden)."""
    factual = [c for c in review.classifications if c.status != "OPINION"]
    if not factual:
        return 100.0
    supported = sum(1 for c in factual if c.status == "SUPPORTED")
    return round(100 * supported / len(factual), 2)
