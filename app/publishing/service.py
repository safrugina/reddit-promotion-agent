import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.db.models import ContentCandidate, RedditOpportunity, Subreddit
from app.db.models.enums import ApprovalStatus, ValidationStatus
from app.errors import PublishError
from app.publishing.rate_limits import enforce_rate_limits
from app.reddit.client import RedditClient
from app.reddit.models import SubmissionResult


async def publish_candidate(
    session: AsyncSession,
    reddit: RedditClient,
    candidate_id: uuid.UUID,
    *,
    confirm: bool,
) -> SubmissionResult:
    """Publish an approved, validated candidate to Reddit (spec section 22).

    All four gates are mandatory and checked in order:
      1. approval_status == APPROVED
      2. validation_status == PASS
      3. no known subreddit-rule violation (covered by gate 2 -- PASS is never set
         when RuleValidator returned BLOCK, see app.validation.service)
      4. explicit human --confirm

    On any submission error we do NOT retry (spec section 25): a timeout or
    ambiguous error may mean the comment was actually posted, and blindly
    retrying risks a duplicate post. The candidate is marked FAILED and the
    user must check Reddit manually before trying again.
    """
    if not confirm:
        raise PublishError(
            "Publishing requires explicit confirmation. Re-run with --confirm."
        )

    candidate = await session.get(ContentCandidate, candidate_id)
    if candidate is None:
        raise ValueError(f"Candidate {candidate_id} not found")

    if candidate.approval_status != ApprovalStatus.APPROVED:
        raise PublishError(
            f"Cannot publish: approval_status is {candidate.approval_status.value}, "
            "not APPROVED."
        )
    if candidate.validation_status != ValidationStatus.PASS:
        raise PublishError(
            f"Cannot publish: validation_status is {candidate.validation_status.value}, "
            "not PASS."
        )

    opportunity = await session.get(RedditOpportunity, candidate.opportunity_id)
    if opportunity is None:
        raise ValueError("Candidate is missing its opportunity")
    subreddit = await session.get(Subreddit, opportunity.subreddit_id)
    if subreddit is None:
        raise ValueError("Opportunity is missing its subreddit")
    if not opportunity.reddit_post_id:
        raise PublishError("Opportunity has no target Reddit post id to reply to.")

    await enforce_rate_limits(session, subreddit.name)

    try:
        result = await reddit.submit_comment(opportunity.reddit_post_id, candidate.body)
    except Exception as exc:
        candidate.approval_status = ApprovalStatus.FAILED
        await session.flush()
        await log_event(
            session,
            "PUBLISH_FAILED",
            project_id=candidate.project_id,
            subreddit_name=subreddit.name,
            candidate_id=str(candidate.id),
            error=str(exc),
        )
        raise PublishError(
            f"Publishing to Reddit failed: {exc}. Do not blindly retry -- check "
            "whether the comment already exists on Reddit before resubmitting."
        ) from exc

    candidate.approval_status = ApprovalStatus.PUBLISHED
    await session.flush()
    await log_event(
        session,
        "PUBLISHED",
        project_id=candidate.project_id,
        subreddit_name=subreddit.name,
        candidate_id=str(candidate.id),
        reddit_id=result.id,
        url=result.url,
    )
    return result
