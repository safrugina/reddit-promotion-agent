import uuid

import pytest
from sqlalchemy import delete, select

from app.approval.service import approve_candidate
from app.db.models import AuditLog, ContentCandidate, Project, RedditOpportunity, Subreddit
from app.db.models.enums import (
    ApprovalStatus,
    ContentAngle,
    ContentType,
    OpportunityStatus,
    ValidationStatus,
)
from app.db.session import session_scope
from app.errors import PublishError, RateLimitError, ValidationError
from app.publishing.service import publish_candidate
from app.reddit.models import (
    PostInfo,
    SubmissionMetrics,
    SubmissionResult,
    SubredditInfo,
    SubredditRule,
)


class FakeRedditClient:
    def __init__(self) -> None:
        self.submit_comment_calls: list[tuple[str, str]] = []

    async def search_subreddits(self, query: str, limit: int = 10) -> list[SubredditInfo]:
        raise NotImplementedError

    async def search_posts(
        self, query: str, subreddit: str | None = None, limit: int = 25
    ) -> list[PostInfo]:
        raise NotImplementedError

    async def get_subreddit(self, name: str) -> SubredditInfo:
        raise NotImplementedError

    async def get_rules(self, subreddit: str) -> list[SubredditRule]:
        raise NotImplementedError

    async def get_post(self, post_id: str) -> PostInfo:
        raise NotImplementedError

    async def submit_post(self, subreddit: str, title: str, body: str) -> SubmissionResult:
        raise NotImplementedError

    async def submit_comment(self, post_id: str, body: str) -> SubmissionResult:
        self.submit_comment_calls.append((post_id, body))
        return SubmissionResult(
            id="c_abc", url="https://reddit.com/comments/c_abc", permalink="/comments/c_abc"
        )

    async def get_submission_metrics(self, post_id: str) -> SubmissionMetrics:
        raise NotImplementedError

    async def close(self) -> None:
        pass


async def _clear_publish_audit_log(session) -> None:
    """Rate limiting is deliberately global (spec section 23), so tests that need to
    control it must reset prior PUBLISHED audit rows left by other test runs first."""
    await session.execute(delete(AuditLog).where(AuditLog.event_type == "PUBLISHED"))
    await session.commit()


async def _make_candidate(
    session,
    *,
    approval_status: ApprovalStatus,
    validation_status: ValidationStatus,
) -> ContentCandidate:
    project = Project(name=f"Publish Test {uuid.uuid4().hex[:8]}", slug=uuid.uuid4().hex[:12])
    session.add(project)
    await session.flush()

    subreddit = Subreddit(name=f"pubsub_{uuid.uuid4().hex[:8]}", display_name="r/pubsub")
    session.add(subreddit)
    await session.flush()

    opportunity = RedditOpportunity(
        project_id=project.id,
        subreddit_id=subreddit.id,
        reddit_post_id=f"post_{uuid.uuid4().hex[:8]}",
        title="Discussion",
        status=OpportunityStatus.READY,
    )
    session.add(opportunity)
    await session.flush()

    candidate = ContentCandidate(
        project_id=project.id,
        opportunity_id=opportunity.id,
        content_type=ContentType.COMMENT,
        body="A genuinely useful reply.",
        angle=ContentAngle.EDUCATIONAL,
        approval_status=approval_status,
        validation_status=validation_status,
    )
    session.add(candidate)
    await session.commit()
    return candidate


@pytest.mark.requires_db
async def test_publish_requires_confirm_flag():
    async with session_scope() as session:
        candidate = await _make_candidate(
            session,
            approval_status=ApprovalStatus.APPROVED,
            validation_status=ValidationStatus.PASS,
        )
        reddit = FakeRedditClient()

        with pytest.raises(PublishError, match="confirm"):
            await publish_candidate(session, reddit, candidate.id, confirm=False)
        assert reddit.submit_comment_calls == []


@pytest.mark.requires_db
async def test_publish_requires_approved_status():
    async with session_scope() as session:
        candidate = await _make_candidate(
            session,
            approval_status=ApprovalStatus.PENDING,
            validation_status=ValidationStatus.PASS,
        )
        reddit = FakeRedditClient()

        with pytest.raises(PublishError, match="APPROVED"):
            await publish_candidate(session, reddit, candidate.id, confirm=True)
        assert reddit.submit_comment_calls == []


@pytest.mark.requires_db
async def test_publish_requires_validation_pass():
    async with session_scope() as session:
        candidate = await _make_candidate(
            session,
            approval_status=ApprovalStatus.APPROVED,
            validation_status=ValidationStatus.REGENERATE,
        )
        reddit = FakeRedditClient()

        with pytest.raises(PublishError, match="PASS"):
            await publish_candidate(session, reddit, candidate.id, confirm=True)
        assert reddit.submit_comment_calls == []


@pytest.mark.requires_db
async def test_publish_succeeds_and_writes_audit_log():
    async with session_scope() as session:
        await _clear_publish_audit_log(session)
        candidate = await _make_candidate(
            session,
            approval_status=ApprovalStatus.APPROVED,
            validation_status=ValidationStatus.PASS,
        )
        reddit = FakeRedditClient()

        result = await publish_candidate(session, reddit, candidate.id, confirm=True)
        await session.commit()
        await session.refresh(candidate)

        assert result.id == "c_abc"
        assert candidate.approval_status == ApprovalStatus.PUBLISHED
        assert len(reddit.submit_comment_calls) == 1

        audit_result = await session.execute(
            select(AuditLog)
            .where(AuditLog.event_type == "PUBLISHED")
            .order_by(AuditLog.created_at.desc())
            .limit(1)
        )
        audit_entry = audit_result.scalar_one_or_none()
        assert audit_entry is not None
        assert audit_entry.payload["candidate_id"] == str(candidate.id)


@pytest.mark.requires_db
async def test_publish_enforces_minimum_interval_between_publications():
    async with session_scope() as session:
        await _clear_publish_audit_log(session)
        first = await _make_candidate(
            session,
            approval_status=ApprovalStatus.APPROVED,
            validation_status=ValidationStatus.PASS,
        )
        second = await _make_candidate(
            session,
            approval_status=ApprovalStatus.APPROVED,
            validation_status=ValidationStatus.PASS,
        )
        reddit = FakeRedditClient()

        await publish_candidate(session, reddit, first.id, confirm=True)
        await session.commit()

        with pytest.raises(RateLimitError):
            await publish_candidate(session, reddit, second.id, confirm=True)
        assert len(reddit.submit_comment_calls) == 1


@pytest.mark.requires_db
async def test_approve_rejects_candidate_that_has_not_passed_validation():
    async with session_scope() as session:
        candidate = await _make_candidate(
            session,
            approval_status=ApprovalStatus.PENDING,
            validation_status=ValidationStatus.REGENERATE,
        )

        with pytest.raises(ValidationError):
            await approve_candidate(session, candidate.id)
