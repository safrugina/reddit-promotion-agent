import uuid
from typing import Any

import pytest
from pydantic import BaseModel

from app.db.models import Project, ProjectFact, RedditOpportunity, Subreddit
from app.db.models.enums import FactType, OpportunityStatus
from app.db.session import session_scope
from app.generation.content_generator import ContentGenerationResult, GeneratedCandidate
from app.generation.service import generate_candidates_for_opportunity


class FakeLLMProvider:
    def __init__(self, fact_id: str) -> None:
        self.calls: list[str] = []
        self._fact_id = fact_id

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError("not used in this test")

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        self.calls.append(prompt)
        assert schema is ContentGenerationResult
        return ContentGenerationResult(
            candidates=[
                GeneratedCandidate(
                    angle="EDUCATIONAL",
                    body="Here's a genuinely useful answer that happens to mention the tool.",
                    cta="Happy to share more details if useful.",
                    rationale="The thread is asking exactly what this project solves.",
                    source_fact_ids=[self._fact_id],
                ),
                GeneratedCandidate(
                    angle="TECHNICAL",
                    body="Under the hood it infers column types from CSV samples.",
                    cta=None,
                    rationale="Adds technical depth for this audience.",
                    source_fact_ids=[self._fact_id],
                ),
            ]
        )


@pytest.mark.requires_db
async def test_generate_candidates_for_opportunity_persists_grounded_candidates():
    async with session_scope() as session:
        project = Project(name=f"Gen Test {uuid.uuid4().hex[:8]}", slug=uuid.uuid4().hex[:12])
        session.add(project)
        await session.flush()

        fact = ProjectFact(
            project_id=project.id,
            fact="Infers column types from CSV samples",
            source_chunk_ids=[],
            confidence=0.9,
            fact_type=FactType.FEATURE,
        )
        session.add(fact)

        subreddit = Subreddit(
            name=f"testsub_{uuid.uuid4().hex[:8]}",
            display_name="r/testsub",
            description="A community for database tooling.",
            culture_summary="Audience: backend engineers. Values technical depth.",
        )
        session.add(subreddit)
        await session.flush()

        opportunity = RedditOpportunity(
            project_id=project.id,
            subreddit_id=subreddit.id,
            reddit_post_id="post123",
            title="How do you handle CSV to SQL migrations?",
            body="Curious what tools people use for this.",
            url="https://reddit.com/r/testsub/post123",
            status=OpportunityStatus.NEW,
        )
        session.add(opportunity)
        await session.commit()

        llm = FakeLLMProvider(fact_id=str(fact.id))

        candidates = await generate_candidates_for_opportunity(session, llm, opportunity.id)
        await session.commit()

        assert len(candidates) == 2
        assert len(llm.calls) == 1
        angles = {c.angle.value for c in candidates}
        assert angles == {"EDUCATIONAL", "TECHNICAL"}
        for candidate in candidates:
            assert candidate.opportunity_id == opportunity.id
            assert candidate.project_id == project.id
            assert candidate.source_fact_ids == [str(fact.id)]
            assert candidate.body
