from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, SourceDocument
from app.knowledge.chunking import chunk_text
from app.knowledge.embeddings import EmbeddingProvider


async def chunk_document(
    session: AsyncSession, embeddings: EmbeddingProvider, document: SourceDocument
) -> list[DocumentChunk]:
    """Chunk a document's extracted text, embed the chunks, and persist them."""
    if document.chunked_at is not None or not document.extracted_text:
        return []

    texts = chunk_text(document.extracted_text)
    if not texts:
        document.chunked_at = datetime.now(UTC)
        await session.flush()
        return []

    vectors = await embeddings.embed(texts)

    chunks = [
        DocumentChunk(
            document_id=document.id,
            chunk_index=index,
            text=text,
            embedding=vector,
        )
        for index, (text, vector) in enumerate(zip(texts, vectors, strict=True))
    ]
    session.add_all(chunks)
    document.chunked_at = datetime.now(UTC)
    await session.flush()
    return chunks
