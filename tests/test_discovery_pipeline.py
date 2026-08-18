import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import BaseModel

from app.db.models import Project, ProjectFact, RedditOpportunity, Subreddit
from app.db.models.enums import FactType
from app.db.session import session_scope
from app.discovery.opportunity_service import discover_opportunities
from app.discovery.subreddit_analyzer import SubredditAnalysis
from app.reddit.models import (
    PostInfo,
    SubmissionMetrics,
    SubmissionResult,
    SubredditInfo,
    SubredditRule,
)


class FakeRedditClient:
    """Mocked RedditClient: no network calls, deterministic fixture data.

    Subreddit.name is globally unique in the DB and this test does not roll back,
    so each instance uses a fresh subreddit/post id -- otherwise a second test run
    would find the previous run's already-analyzed Subreddit row and the
    generate_structured_calls assertion below would flake.
    """

    def __init__(self) -> None:
        self.get_subreddit_calls = 0
        suffix = uuid.uuid4().hex[:8]
        self.subreddit_name = f"postgresql_{suffix}"
        self.post_id = f"post_{suffix}"
        self._subreddit = SubredditInfo(
            name=self.subreddit_name,
            display_name=f"r/{self.subreddit_name}",
            description="A community for Postgres users and tooling.",
            subscribers=50_000,
            over18=False,
            submission_type="any",
        )
        self._post = PostInfo(
            id=self.post_id,
            subreddit=self.subreddit_name,
            title="How do you manage schema migrations?",
            body="Looking for a tool to generate migrations from CSV data.",
            author="someuser",
            url=f"https://reddit.com/r/{self.subreddit_name}/{self.post_id}",
            permalink=f"https://reddit.com/r/{self.subreddit_name}/comments/{self.post_id}",
            score=42,
            num_comments=5,
            created_at=datetime.now(UTC),
            is_self=True,
        )

    async def search_subreddits(self, query: str, limit: int = 10) -> list[SubredditInfo]:
        return [self._subreddit]

    async def search_posts(
        self, query: str, subreddit: str | None = None, limit: int = 25
    ) -> list[PostInfo]:
        return [self._post]

    async def get_subreddit(self, name: str) -> SubredditInfo:
        self.get_subreddit_calls += 1
        return self._subreddit

    async def get_rules(self, subreddit: str) -> list[SubredditRule]:
        return [SubredditRule(short_name="Be civil", description="No hate speech.")]

    async def get_post(self, post_id: str) -> PostInfo:
        return self._post

    async def submit_post(self, subreddit: str, title: str, body: str) -> SubmissionResult:
        raise NotImplementedError("not used in this test")

    async def submit_comment(self, post_id: str, body: str) -> SubmissionResult:
        raise NotImplementedError("not used in this test")

    async def get_submission_metrics(self, post_id: str) -> SubmissionMetrics:
        raise NotImplementedError("not used in this test")

    async def close(self) -> None:
        pass


class FakeLLMProvider:
    """Mocked LLMProvider: returns a canned SubredditAnalysis, no API calls."""

    def __init__(self) -> None:
        self.generate_structured_calls = 0

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError("not used in this test")

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        self.generate_structured_calls += 1
        assert schema is SubredditAnalysis
        return SubredditAnalysis(
            subreddit="postgresql",
            audience="Backend engineers using Postgres",
            primary_topics=["postgres", "migrations", "sql"],
            content_patterns=["how-to questions", "tool recommendations"],
            self_promotion_policy="Not explicitly addressed in the rules.",
            external_links_policy="Not explicitly addressed in the rules.",
            likely_good_angles=["Share a genuinely useful open-source tool"],
            likely_bad_angles=["Pure advertisement with no technical substance"],
            explicit_rules=["No hate speech."],
            risks=["Community may be sensitive to promotional content"],
            confidence=0.7,
        )


@pytest.mark.requires_db
async def test_discover_opportunities_creates_subreddit_and_opportunity():
    async with session_scope() as session:
        project = Project(name=f"Discovery Test {uuid.uuid4().hex[:8]}", slug=uuid.uuid4().hex[:12])
        session.add(project)
        await session.flush()
        session.add(
            ProjectFact(
                project_id=project.id,
                fact="postgres migrations cli",
                source_chunk_ids=[],
                confidence=1.0,
                fact_type=FactType.FEATURE,
            )
        )
        await session.commit()

        reddit = FakeRedditClient()
        llm = FakeLLMProvider()

        opportunities = await discover_opportunities(session, reddit, llm, project.id)
        await session.commit()

        assert len(opportunities) == 1
        opp = opportunities[0]
        assert opp.reddit_post_id == reddit.post_id
        assert 0 <= opp.opportunity_score <= 100
        assert llm.generate_structured_calls == 1

        subreddit_result = await session.execute(
            Subreddit.__table__.select().where(Subreddit.name == reddit.subreddit_name)
        )
        assert subreddit_result.first() is not None

        # Re-running should not duplicate the opportunity or re-analyze the subreddit.
        opportunities_again = await discover_opportunities(session, reddit, llm, project.id)
        await session.commit()

        assert opportunities_again == []
        assert llm.generate_structured_calls == 1

        count_result = await session.execute(
            RedditOpportunity.__table__.select().where(
                RedditOpportunity.project_id == project.id
            )
        )
        assert len(count_result.fetchall()) == 1
