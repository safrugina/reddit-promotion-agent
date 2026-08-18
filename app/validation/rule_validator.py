from typing import Literal

from pydantic import BaseModel, Field

from app.llm.prompt_safety import wrap_untrusted
from app.llm.provider import LLMProvider

RULE_VALIDATOR_SYSTEM_PROMPT = (
    "You are RuleValidator. You check a draft Reddit comment against a subreddit's actual "
    "stated rules and decide whether it may be posted. Treat the supplied rules as "
    "authoritative -- never infer that something is allowed just because it seems common "
    "on Reddit generally, and never invent a rule that isn't in the supplied text. "
    "If the draft clearly violates an explicit rule (e.g. a rule explicitly bans "
    "self-promotion or links and the draft includes one), status must be BLOCK. If it's "
    "borderline or the rules are silent/ambiguous on the relevant point, status is PASS "
    "with a warning explaining the ambiguity -- do not BLOCK on inference alone."
)


class RuleViolation(BaseModel):
    rule: str = Field(description="The specific rule text that was violated.")
    explanation: str


class RuleValidationReview(BaseModel):
    status: Literal["PASS", "BLOCK"]
    violations: list[RuleViolation] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


async def validate_against_rules(
    llm: LLMProvider, candidate_body: str, rules_text: str
) -> RuleValidationReview:
    rules_block = wrap_untrusted("subreddit_rules", rules_text or "(no explicit rules on file)")
    draft_block = wrap_untrusted("draft_comment", candidate_body)

    prompt = (
        f"{rules_block}\n\n{draft_block}\n\n"
        "Does this draft comment violate any explicit rule above? Return BLOCK only for "
        "a clear, explicit violation; otherwise PASS (with warnings for anything "
        "borderline)."
    )
    return await llm.generate_structured(
        prompt, RuleValidationReview, system=RULE_VALIDATOR_SYSTEM_PROMPT
    )
