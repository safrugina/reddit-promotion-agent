import uuid
from typing import Any

import pytest
from pydantic import BaseModel

from app.db.models import Project, RedditOpportunity, Subreddit
from app.db.models.enums import OpportunityStatus
from app.db.session import session_scope
from app.generation.content_generator import ContentGenerationResult, GeneratedCandidate
from app.generation.export import export_top_candidates


class FakeLLMProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        self.calls += 1
        assert schema is ContentGenerationResult
        return ContentGenerationResult(
            candidates=[
                GeneratedCandidate(
                    angle="EDUCATIONAL",
                    body="A genuinely useful reply for this discussion.",
                    cta=None,
                    rationale="Fits the thread.",
                    source_fact_ids=[],
                )
            ]
        )


@pytest.mark.requires_db
async def test_export_top_candidates_returns_one_entry_per_subreddit():
    async with session_scope() as session:
        project = Project(name=f"Export Test {uuid.uuid4().hex[:8]}", slug=uuid.uuid4().hex[:12])
        session.add(project)
        await session.flush()

        sub_a = Subreddit(name=f"expa_{uuid.uuid4().hex[:8]}", display_name="r/expa")
        sub_b = Subreddit(name=f"expb_{uuid.uuid4().hex[:8]}", display_name="r/expb")
        session.add_all([sub_a, sub_b])
        await session.flush()

        # Two opportunities in sub_a (only the higher-scoring one should be exported
        # by default), one in sub_b.
        opp_a_high = RedditOpportunity(
            project_id=project.id,
            subreddit_id=sub_a.id,
            reddit_post_id="a_high",
            title="High score discussion",
            url="https://reddit.com/a_high",
            opportunity_score=90.0,
            status=OpportunityStatus.READY,
        )
        opp_a_low = RedditOpportunity(
            project_id=project.id,
            subreddit_id=sub_a.id,
            reddit_post_id="a_low",
            title="Low score discussion",
            url="https://reddit.com/a_low",
            opportunity_score=10.0,
            status=OpportunityStatus.READY,
        )
        opp_b = RedditOpportunity(
            project_id=project.id,
            subreddit_id=sub_b.id,
            reddit_post_id="b_only",
            title="Only discussion in b",
            url="https://reddit.com/b_only",
            opportunity_score=50.0,
            status=OpportunityStatus.READY,
        )
        session.add_all([opp_a_high, opp_a_low, opp_b])
        await session.commit()

        llm = FakeLLMProvider()

        entries = await export_top_candidates(session, llm, project.id, top_per_subreddit=1)
        await session.commit()

        assert len(entries) == 2
        by_subreddit = {e.subreddit: e for e in entries}
        assert by_subreddit[sub_a.name].opportunity_title == "High score discussion"
        assert by_subreddit[sub_b.name].opportunity_title == "Only discussion in b"
        assert all(e.body for e in entries)
        assert llm.calls == 2  # one generation call per exported opportunity

        # Re-running should reuse the already-generated candidates, not call the LLM again.
        entries_again = await export_top_candidates(session, llm, project.id, top_per_subreddit=1)
        assert len(entries_again) == 2
        assert llm.calls == 2
