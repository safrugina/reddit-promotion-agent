import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, SourceDocument
from app.knowledge.embeddings import EmbeddingProvider


async def retrieve_relevant_chunks(
    session: AsyncSession,
    embeddings: EmbeddingProvider,
    project_id: uuid.UUID,
    query: str,
    top_k: int = 5,
) -> list[DocumentChunk]:
    """Return the top-k document chunks for a project, ranked by cosine similarity to query."""
    vectors = await embeddings.embed([query])
    query_vector = vectors[0]

    result = await session.execute(
        select(DocumentChunk)
        .join(SourceDocument, DocumentChunk.document_id == SourceDocument.id)
        .where(SourceDocument.project_id == project_id)
        .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
        .limit(top_k)
    )
    return list(result.scalars().all())
