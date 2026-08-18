import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.db.models import ContentCandidate, Project, ProjectFact, RedditOpportunity, Subreddit
from app.db.models.enums import ValidationStatus
from app.db.models.validation_result import ValidationResult
from app.knowledge.embeddings import EmbeddingProvider
from app.llm.provider import LLMProvider
from app.validation.duplication import check_duplication
from app.validation.grounding import grounding_score, review_grounding
from app.validation.promotion_risk import assess_promotion_risk
from app.validation.rule_validator import validate_against_rules

# Grounding/promotion/originality thresholds are conservative on purpose (spec
# section 36 #11: fail closed on safety/rule validation failures).
GROUNDING_REGENERATE_THRESHOLD = 50.0
PROMOTION_REGENERATE_THRESHOLD = 80.0
ORIGINALITY_REGENERATE_THRESHOLD = 30.0


def determine_validation_status(
    rule_status: str,
    grounding: float,
    promotion: float,
    originality: float,
) -> ValidationStatus:
    """Pure combination of the four validator outputs (spec sections 15-18)."""
    if rule_status == "BLOCK":
        return ValidationStatus.BLOCK
    if (
        grounding < GROUNDING_REGENERATE_THRESHOLD
        or promotion >= PROMOTION_REGENERATE_THRESHOLD
        or originality < ORIGINALITY_REGENERATE_THRESHOLD
    ):
        return ValidationStatus.REGENERATE
    return ValidationStatus.PASS


def _rule_compliance_score(rule_review_status: str, warning_count: int) -> float:
    if rule_review_status == "BLOCK":
        return 0.0
    return 80.0 if warning_count else 100.0


async def validate_candidate(
    session: AsyncSession,
    llm: LLMProvider,
    embeddings: EmbeddingProvider,
    candidate_id: uuid.UUID,
) -> ValidationResult:
    candidate = await session.get(ContentCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")

    opportunity = await session.get(RedditOpportunity, candidate.opportunity_id)
    if opportunity is None:
        raise ValueError("Candidate is missing its opportunity")
    subreddit = await session.get(Subreddit, opportunity.subreddit_id)
    project = await session.get(Project, candidate.project_id)
    if subreddit is None or project is None:
        raise ValueError("Candidate is missing its subreddit or project")

    facts: list[ProjectFact] = []
    if candidate.source_fact_ids:
        for fact_id in candidate.source_fact_ids:
            fact = await session.get(ProjectFact, uuid.UUID(fact_id))
            if fact is not None:
                facts.append(fact)

    rules_text = "\n".join(f"- {r['short_name']}: {r['description']}" for r in subreddit.rules)

    grounding_review = await review_grounding(llm, candidate.body, facts)
    grounding = grounding_score(grounding_review)

    rule_review = await validate_against_rules(llm, candidate.body, rules_text)

    promotion = assess_promotion_risk(candidate.body, candidate.cta)

    duplication = await check_duplication(
        session, embeddings, candidate.project_id, candidate.id, candidate.body
    )

    status = determine_validation_status(
        rule_status=rule_review.status,
        grounding=grounding,
        promotion=promotion.score,
        originality=duplication.originality_score,
    )

    issues: list[str] = [
        f"Rule violation: {v.rule} -- {v.explanation}" for v in rule_review.violations
    ]
    issues.extend(promotion.issues)
    issues.extend(duplication.issues)
    issues.extend(
        f"Unsupported claim: {c.claim} -- {c.explanation}"
        for c in grounding_review.classifications
        if c.status == "UNSUPPORTED"
    )
    warnings = list(rule_review.warnings)
    warnings.extend(
        f"Ambiguous claim: {c.claim} -- {c.explanation}"
        for c in grounding_review.classifications
        if c.status == "AMBIGUOUS"
    )

    result = ValidationResult(
        candidate_id=candidate.id,
        rule_compliance_score=_rule_compliance_score(rule_review.status, len(rule_review.warnings)),
        grounding_score=grounding,
        originality_score=duplication.originality_score,
        promotion_score=promotion.score,
        risk_score=max(
            promotion.score,
            100 - grounding,
            100 - duplication.originality_score,
            0.0 if rule_review.status == "PASS" else 100.0,
        ),
        issues=issues,
        warnings=warnings,
    )
    session.add(result)
    candidate.validation_status = status
    await session.flush()
    await log_event(
        session,
        "VALIDATED",
        project_id=candidate.project_id,
        subreddit_name=subreddit.name,
        candidate_id=str(candidate.id),
        status=status.value,
        rule_compliance_score=result.rule_compliance_score,
        grounding_score=result.grounding_score,
        originality_score=result.originality_score,
        promotion_score=result.promotion_score,
    )
    return result
