import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.db.models import ContentCandidate, RedditOpportunity, Subreddit
from app.db.models.enums import ApprovalStatus
from app.reddit.client import RedditClient
from app.reddit.models import SubmissionMetrics


async def refresh_engagement_metrics(
    session: AsyncSession, reddit: RedditClient, project_id: uuid.UUID
) -> list[SubmissionMetrics]:
    """Fetch current Reddit metrics for discussions with a published candidate
    (spec section 34, step 17) and append them to the audit log."""
    result = await session.execute(
        select(RedditOpportunity, Subreddit.name)
        .join(ContentCandidate, ContentCandidate.opportunity_id == RedditOpportunity.id)
        .join(Subreddit, RedditOpportunity.subreddit_id == Subreddit.id)
        .where(
            RedditOpportunity.project_id == project_id,
            ContentCandidate.approval_status == ApprovalStatus.PUBLISHED,
        )
        .distinct()
    )
    rows = result.all()

    metrics: list[SubmissionMetrics] = []
    for opportunity, subreddit_name in rows:
        if not opportunity.reddit_post_id:
            continue
        submission_metrics = await reddit.get_submission_metrics(opportunity.reddit_post_id)
        await log_event(
            session,
            "METRICS_REFRESHED",
            project_id=project_id,
            subreddit_name=subreddit_name,
            opportunity_id=str(opportunity.id),
            reddit_post_id=opportunity.reddit_post_id,
            score=submission_metrics.score,
            num_comments=submission_metrics.num_comments,
            upvote_ratio=submission_metrics.upvote_ratio,
        )
        metrics.append(submission_metrics)

    await session.flush()
    return metrics
