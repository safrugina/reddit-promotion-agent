import uuid

import pytest

from app.analytics.service import compute_project_analytics, group_by_angle, group_by_subreddit
from app.db.models import ContentCandidate, Project, RedditOpportunity, Subreddit, ValidationResult
from app.db.models.enums import (
    ApprovalStatus,
    ContentAngle,
    ContentType,
    OpportunityStatus,
    ValidationStatus,
)
from app.db.session import session_scope


@pytest.mark.requires_db
async def test_compute_project_analytics_counts_and_averages():
    async with session_scope() as session:
        project = Project(name=f"Analytics Test {uuid.uuid4().hex[:8]}", slug=uuid.uuid4().hex[:12])
        session.add(project)
        await session.flush()

        subreddit = Subreddit(name=f"asub_{uuid.uuid4().hex[:8]}", display_name="r/asub")
        session.add(subreddit)
        await session.flush()

        opp1 = RedditOpportunity(
            project_id=project.id,
            subreddit_id=subreddit.id,
            reddit_post_id="p1",
            status=OpportunityStatus.USED,
            relevance_score=80.0,
        )
        opp2 = RedditOpportunity(
            project_id=project.id,
            subreddit_id=subreddit.id,
            reddit_post_id="p2",
            status=OpportunityStatus.NEW,
            relevance_score=60.0,
        )
        session.add_all([opp1, opp2])
        await session.flush()

        published = ContentCandidate(
            project_id=project.id,
            opportunity_id=opp1.id,
            content_type=ContentType.COMMENT,
            body="Published candidate",
            angle=ContentAngle.EDUCATIONAL,
            approval_status=ApprovalStatus.PUBLISHED,
            validation_status=ValidationStatus.PASS,
        )
        rejected = ContentCandidate(
            project_id=project.id,
            opportunity_id=opp2.id,
            content_type=ContentType.COMMENT,
            body="Rejected candidate",
            angle=ContentAngle.TECHNICAL,
            approval_status=ApprovalStatus.REJECTED,
            validation_status=ValidationStatus.REGENERATE,
        )
        session.add_all([published, rejected])
        await session.flush()

        session.add(
            ValidationResult(
                candidate_id=published.id,
                rule_compliance_score=100.0,
                grounding_score=90.0,
                originality_score=80.0,
                promotion_score=10.0,
                risk_score=10.0,
            )
        )
        await session.commit()

        summary = await compute_project_analytics(session, project.id)

        assert summary.opportunities_discovered == 2
        assert summary.candidates_generated == 2
        assert summary.candidates_published == 1
        assert summary.candidates_rejected == 1
        assert summary.candidates_approved == 0
        assert summary.publication_failures == 0
        assert summary.average_relevance_score == 70.0  # (80 + 60) / 2
        # (100 + 90 + 80 + (100 - 10)) / 4 = 90.0
        assert summary.average_validation_score == 90.0

        by_subreddit = await group_by_subreddit(session, project.id)
        assert len(by_subreddit) == 1
        assert by_subreddit[0].label == subreddit.name
        assert by_subreddit[0].candidates_generated == 2
        assert by_subreddit[0].candidates_published == 1

        by_angle = await group_by_angle(session, project.id)
        angle_labels = {m.label for m in by_angle}
        assert angle_labels == {"EDUCATIONAL", "TECHNICAL"}
