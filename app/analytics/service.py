import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCandidate, RedditOpportunity, Subreddit, ValidationResult
from app.db.models.enums import ApprovalStatus


@dataclass
class ProjectAnalytics:
    opportunities_discovered: int
    candidates_generated: int
    candidates_approved: int
    candidates_rejected: int
    candidates_published: int
    publication_failures: int
    average_relevance_score: float
    average_validation_score: float


@dataclass
class GroupedMetric:
    label: str
    candidates_generated: int
    candidates_published: int


async def compute_project_analytics(
    session: AsyncSession, project_id: uuid.UUID
) -> ProjectAnalytics:
    """spec section 31 dashboard metrics, computed directly from stored records."""
    opportunities_discovered = (
        await session.execute(
            select(func.count())
            .select_from(RedditOpportunity)
            .where(RedditOpportunity.project_id == project_id)
        )
    ).scalar_one()

    async def _count_by_approval(status: ApprovalStatus) -> int:
        result = await session.execute(
            select(func.count())
            .select_from(ContentCandidate)
            .where(
                ContentCandidate.project_id == project_id,
                ContentCandidate.approval_status == status,
            )
        )
        return result.scalar_one()

    candidates_generated = (
        await session.execute(
            select(func.count())
            .select_from(ContentCandidate)
            .where(ContentCandidate.project_id == project_id)
        )
    ).scalar_one()
    candidates_approved = await _count_by_approval(ApprovalStatus.APPROVED)
    candidates_rejected = await _count_by_approval(ApprovalStatus.REJECTED)
    candidates_published = await _count_by_approval(ApprovalStatus.PUBLISHED)
    publication_failures = await _count_by_approval(ApprovalStatus.FAILED)

    avg_relevance = (
        await session.execute(
            select(func.avg(RedditOpportunity.relevance_score)).where(
                RedditOpportunity.project_id == project_id
            )
        )
    ).scalar_one()

    avg_validation = (
        await session.execute(
            select(
                func.avg(
                    (
                        ValidationResult.rule_compliance_score
                        + ValidationResult.grounding_score
                        + ValidationResult.originality_score
                        + (100 - ValidationResult.promotion_score)
                    )
                    / 4
                )
            )
            .select_from(ValidationResult)
            .join(ContentCandidate, ValidationResult.candidate_id == ContentCandidate.id)
            .where(ContentCandidate.project_id == project_id)
        )
    ).scalar_one()

    return ProjectAnalytics(
        opportunities_discovered=opportunities_discovered,
        candidates_generated=candidates_generated,
        candidates_approved=candidates_approved,
        candidates_rejected=candidates_rejected,
        candidates_published=candidates_published,
        publication_failures=publication_failures,
        average_relevance_score=round(float(avg_relevance or 0.0), 2),
        average_validation_score=round(float(avg_validation or 0.0), 2),
    )


async def group_by_subreddit(session: AsyncSession, project_id: uuid.UUID) -> list[GroupedMetric]:
    result = await session.execute(
        select(
            Subreddit.name,
            func.count(ContentCandidate.id),
            func.count(ContentCandidate.id).filter(
                ContentCandidate.approval_status == ApprovalStatus.PUBLISHED
            ),
        )
        .select_from(ContentCandidate)
        .join(RedditOpportunity, ContentCandidate.opportunity_id == RedditOpportunity.id)
        .join(Subreddit, RedditOpportunity.subreddit_id == Subreddit.id)
        .where(ContentCandidate.project_id == project_id)
        .group_by(Subreddit.name)
        .order_by(func.count(ContentCandidate.id).desc())
    )
    return [
        GroupedMetric(label=name, candidates_generated=total, candidates_published=published)
        for name, total, published in result.all()
    ]


async def group_by_angle(session: AsyncSession, project_id: uuid.UUID) -> list[GroupedMetric]:
    """Answers: which content angles work best for this project (spec section 31)."""
    result = await session.execute(
        select(
            ContentCandidate.angle,
            func.count(ContentCandidate.id),
            func.count(ContentCandidate.id).filter(
                ContentCandidate.approval_status == ApprovalStatus.PUBLISHED
            ),
        )
        .where(ContentCandidate.project_id == project_id)
        .group_by(ContentCandidate.angle)
        .order_by(func.count(ContentCandidate.id).desc())
    )
    return [
        GroupedMetric(
            label=angle.value, candidates_generated=total, candidates_published=published
        )
        for angle, total, published in result.all()
    ]
