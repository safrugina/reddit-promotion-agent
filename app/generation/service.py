import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.db.models import ContentCandidate, Project, ProjectFact, RedditOpportunity, Subreddit
from app.discovery.scoring import keyword_overlap_score
from app.generation.content_generator import generate_candidates, to_content_candidates
from app.llm.provider import LLMProvider

MAX_FACTS_IN_PROMPT = 20


async def _select_relevant_facts(
    session: AsyncSession, project_id: uuid.UUID, opportunity: RedditOpportunity
) -> list[ProjectFact]:
    result = await session.execute(select(ProjectFact).where(ProjectFact.project_id == project_id))
    facts = list(result.scalars().all())
    if len(facts) <= MAX_FACTS_IN_PROMPT:
        return facts

    text = f"{opportunity.title or ''} {opportunity.body or ''}"
    facts.sort(
        key=lambda f: keyword_overlap_score(f.fact.split(), text),
        reverse=True,
    )
    return facts[:MAX_FACTS_IN_PROMPT]


async def generate_candidates_for_opportunity(
    session: AsyncSession, llm: LLMProvider, opportunity_id: uuid.UUID
) -> list[ContentCandidate]:
    opportunity = await session.get(RedditOpportunity, opportunity_id)
    if opportunity is None:
        raise ValueError(f"Opportunity {opportunity_id} not found")

    project = await session.get(Project, opportunity.project_id)
    subreddit = await session.get(Subreddit, opportunity.subreddit_id)
    if project is None or subreddit is None:
        raise ValueError("Opportunity is missing its project or subreddit")

    facts = await _select_relevant_facts(session, project.id, opportunity)

    result = await generate_candidates(llm, project, opportunity, subreddit, facts)
    candidates = to_content_candidates(project.id, opportunity, result)

    session.add_all(candidates)
    await session.flush()
    for candidate in candidates:
        await log_event(
            session,
            "GENERATED",
            project_id=project.id,
            subreddit_name=subreddit.name,
            candidate_id=str(candidate.id),
            opportunity_id=str(opportunity.id),
            angle=candidate.angle.value,
        )
    return candidates
