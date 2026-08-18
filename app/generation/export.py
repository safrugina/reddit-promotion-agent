import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCandidate, RedditOpportunity, Subreddit
from app.generation.service import generate_candidates_for_opportunity
from app.llm.provider import LLMProvider


@dataclass
class ExportEntry:
    subreddit: str
    opportunity_title: str | None
    opportunity_url: str | None
    opportunity_score: float
    angle: str
    body: str
    cta: str | None


async def export_top_candidates(
    session: AsyncSession,
    llm: LLMProvider,
    project_id: uuid.UUID,
    top_per_subreddit: int = 1,
) -> list[ExportEntry]:
    """For each subreddit with discovered opportunities, take the top-scoring
    discussion(s) and return a ready-to-read subreddit -> message list.

    Does not require Reddit write credentials or touch Reddit at all -- it only
    generates content (LLM calls) for opportunities that don't have candidates yet
    and reads what's already in the database.
    """
    result = await session.execute(
        select(RedditOpportunity, Subreddit.name)
        .join(Subreddit, RedditOpportunity.subreddit_id == Subreddit.id)
        .where(RedditOpportunity.project_id == project_id)
        .order_by(Subreddit.name, RedditOpportunity.opportunity_score.desc())
    )
    rows = result.all()

    per_subreddit: dict[str, list[RedditOpportunity]] = {}
    for opportunity, subreddit_name in rows:
        per_subreddit.setdefault(subreddit_name, []).append(opportunity)

    entries: list[ExportEntry] = []
    for subreddit_name, opportunities in per_subreddit.items():
        for opportunity in opportunities[:top_per_subreddit]:
            candidates_result = await session.execute(
                select(ContentCandidate).where(
                    ContentCandidate.opportunity_id == opportunity.id
                )
            )
            candidates = list(candidates_result.scalars().all())
            if not candidates:
                candidates = await generate_candidates_for_opportunity(
                    session, llm, opportunity.id
                )
            if not candidates:
                continue

            best = candidates[0]
            entries.append(
                ExportEntry(
                    subreddit=subreddit_name,
                    opportunity_title=opportunity.title,
                    opportunity_url=opportunity.url,
                    opportunity_score=opportunity.opportunity_score,
                    angle=best.angle.value,
                    body=best.body,
                    cta=best.cta,
                )
            )

    return entries
