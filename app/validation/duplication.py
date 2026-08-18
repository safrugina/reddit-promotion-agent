import re
import uuid
from dataclasses import dataclass
from difflib import SequenceMatcher

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContentCandidate
from app.knowledge.embeddings import EmbeddingProvider

TEXT_SIMILARITY_THRESHOLD = 0.85
EMBEDDING_SIMILARITY_THRESHOLD = 0.92


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def normalized_text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalize(a), _normalize(b)).ratio()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass
class DuplicationResult:
    originality_score: float  # 0-100, higher = more original
    max_similarity: float
    issues: list[str]


async def check_duplication(
    session: AsyncSession,
    embeddings: EmbeddingProvider,
    project_id: uuid.UUID,
    candidate_id: uuid.UUID,
    body: str,
) -> DuplicationResult:
    """Compare against previously generated candidates for the same project
    (spec section 16): normalized text similarity + embedding similarity."""
    result = await session.execute(
        select(ContentCandidate).where(
            ContentCandidate.project_id == project_id,
            ContentCandidate.id != candidate_id,
        )
    )
    others = list(result.scalars().all())
    if not others:
        return DuplicationResult(originality_score=100.0, max_similarity=0.0, issues=[])

    max_text_sim = max(normalized_text_similarity(body, other.body) for other in others)

    vectors = await embeddings.embed([body, *(other.body for other in others)])
    candidate_vector, other_vectors = vectors[0], vectors[1:]
    max_embedding_sim = (
        max(_cosine_similarity(candidate_vector, v) for v in other_vectors)
        if other_vectors
        else 0.0
    )

    max_similarity = max(max_text_sim, max_embedding_sim)
    issues: list[str] = []
    if max_text_sim >= TEXT_SIMILARITY_THRESHOLD:
        issues.append(f"Near-duplicate text of a prior candidate (similarity={max_text_sim:.2f})")
    if max_embedding_sim >= EMBEDDING_SIMILARITY_THRESHOLD:
        issues.append(
            f"Semantically near-duplicate of a prior candidate (similarity={max_embedding_sim:.2f})"
        )

    originality_score = round(max(0.0, 1.0 - max_similarity) * 100, 2)
    return DuplicationResult(
        originality_score=originality_score, max_similarity=max_similarity, issues=issues
    )
