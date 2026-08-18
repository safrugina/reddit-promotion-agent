import uuid
from typing import Any

import pytest
from pydantic import BaseModel

from app.db.models import ContentCandidate, Project, ProjectFact, RedditOpportunity, Subreddit
from app.db.models.enums import ContentAngle, ContentType, FactType, OpportunityStatus
from app.db.session import session_scope
from app.validation.grounding import ClaimClassification, GroundingReview
from app.validation.rule_validator import RuleValidationReview, RuleViolation
from app.validation.service import validate_candidate


class FakeEmbeddingProvider:
    """Deterministic hashing-trick embeddings -- no network calls."""

    _dim = 64

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:
            vector = [0.0] * self._dim
            for word in text.lower().split():
                vector[hash(word) % self._dim] += 1.0
            norm = sum(v * v for v in vector) ** 0.5 or 1.0
            vectors.append([v / norm for v in vector])
        return vectors


class ScriptedLLMProvider:
    def __init__(self, grounding: GroundingReview, rules: RuleValidationReview) -> None:
        self._grounding = grounding
        self._rules = rules
        self.calls: list[type[BaseModel]] = []

    async def generate(self, prompt: str, **kwargs: Any) -> str:
        raise NotImplementedError("not used in this test")

    async def generate_structured(
        self, prompt: str, schema: type[BaseModel], **kwargs: Any
    ) -> BaseModel:
        self.calls.append(schema)
        if schema is GroundingReview:
            return self._grounding
        if schema is RuleValidationReview:
            return self._rules
        raise AssertionError(f"unexpected schema {schema}")


async def _make_project_and_candidate(
    session, *, body: str, rules: list[dict[str, str]]
) -> tuple[Project, ContentCandidate, ProjectFact]:
    project = Project(name=f"Validate Test {uuid.uuid4().hex[:8]}", slug=uuid.uuid4().hex[:12])
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
        description="Database tooling community.",
        rules=rules,
    )
    session.add(subreddit)
    await session.flush()

    opportunity = RedditOpportunity(
        project_id=project.id,
        subreddit_id=subreddit.id,
        reddit_post_id=f"post_{uuid.uuid4().hex[:8]}",
        title="How do you handle CSV to SQL migrations?",
        status=OpportunityStatus.NEW,
    )
    session.add(opportunity)
    await session.flush()

    candidate = ContentCandidate(
        project_id=project.id,
        opportunity_id=opportunity.id,
        content_type=ContentType.COMMENT,
        body=body,
        angle=ContentAngle.EDUCATIONAL,
        source_fact_ids=[str(fact.id)],
    )
    session.add(candidate)
    await session.commit()
    return project, candidate, fact


@pytest.mark.requires_db
async def test_validate_candidate_passes_when_all_checks_are_clean():
    async with session_scope() as session:
        _, candidate, fact = await _make_project_and_candidate(
            session,
            body="I built a small CLI that infers column types from CSV samples.",
            rules=[{"short_name": "Be civil", "description": "No hate speech."}],
        )

        llm = ScriptedLLMProvider(
            grounding=GroundingReview(
                classifications=[
                    ClaimClassification(
                        claim="infers column types from CSV samples",
                        status="SUPPORTED",
                        explanation=f"Matches fact {fact.id}",
                    )
                ]
            ),
            rules=RuleValidationReview(status="PASS", violations=[], warnings=[]),
        )
        embeddings = FakeEmbeddingProvider()

        result = await validate_candidate(session, llm, embeddings, candidate.id)
        await session.commit()
        await session.refresh(candidate)

        assert candidate.validation_status.value == "PASS"
        assert result.grounding_score == 100.0
        assert result.rule_compliance_score == 100.0
        assert result.originality_score == 100.0  # no other candidates to compare against


@pytest.mark.requires_db
async def test_validate_candidate_blocks_on_explicit_rule_violation():
    async with session_scope() as session:
        _, candidate, fact = await _make_project_and_candidate(
            session,
            body="Check out my tool at https://example.com, self-promotion is fine here right?",
            rules=[
                {
                    "short_name": "No self-promotion",
                    "description": "No self-promotion or advertising of any kind.",
                }
            ],
        )

        llm = ScriptedLLMProvider(
            grounding=GroundingReview(
                classifications=[
                    ClaimClassification(
                        claim="a tool exists",
                        status="SUPPORTED",
                        explanation=f"Matches fact {fact.id}",
                    )
                ]
            ),
            rules=RuleValidationReview(
                status="BLOCK",
                violations=[
                    RuleViolation(
                        rule="No self-promotion or advertising of any kind.",
                        explanation="Draft links to the author's own project.",
                    )
                ],
                warnings=[],
            ),
        )
        embeddings = FakeEmbeddingProvider()

        result = await validate_candidate(session, llm, embeddings, candidate.id)
        await session.commit()
        await session.refresh(candidate)

        assert candidate.validation_status.value == "BLOCK"
        assert result.rule_compliance_score == 0.0
        assert any("Rule violation" in issue for issue in result.issues)
