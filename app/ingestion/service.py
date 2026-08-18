import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import SourceDocument
from app.ingestion.code import GenericTextFallbackParser, SourceCodeParser
from app.ingestion.docx import DocxParser
from app.ingestion.markdown import MarkdownTextParser
from app.ingestion.parser import DocumentParser
from app.ingestion.pdf import PdfParser
from app.ingestion.structured import JsonYamlParser

# Order matters: more specific parsers first, GenericTextFallbackParser last.
DEFAULT_PARSERS: Sequence[DocumentParser] = (
    MarkdownTextParser(),
    PdfParser(),
    DocxParser(),
    JsonYamlParser(),
    SourceCodeParser(),
    GenericTextFallbackParser(),
)


def find_parser(
    path: Path, parsers: Sequence[DocumentParser] = DEFAULT_PARSERS
) -> DocumentParser | None:
    for parser in parsers:
        if parser.supports(path):
            return parser
    return None


def hash_content(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


@dataclass
class IngestResult:
    document: SourceDocument
    was_duplicate: bool


async def ingest_file(
    session: AsyncSession,
    project_id: uuid.UUID,
    path: Path,
    parsers: Sequence[DocumentParser] = DEFAULT_PARSERS,
) -> IngestResult | None:
    """Parse and store a single file. Returns None if no parser supports it."""
    parser = find_parser(path, parsers)
    if parser is None:
        return None

    content_hash = hash_content(path.read_bytes())

    existing = await session.execute(
        select(SourceDocument).where(
            SourceDocument.project_id == project_id,
            SourceDocument.content_hash == content_hash,
        )
    )
    duplicate = existing.scalar_one_or_none()
    if duplicate is not None:
        return IngestResult(document=duplicate, was_duplicate=True)

    parsed = parser.parse(path)
    document = SourceDocument(
        project_id=project_id,
        filename=path.name,
        source_type=parsed.source_type,
        path=str(path),
        content_hash=content_hash,
        extracted_text=parsed.text,
        doc_metadata=parsed.metadata,
    )
    session.add(document)
    await session.flush()
    return IngestResult(document=document, was_duplicate=False)


async def ingest_directory(
    session: AsyncSession,
    project_id: uuid.UUID,
    directory: Path,
    parsers: Sequence[DocumentParser] = DEFAULT_PARSERS,
) -> list[IngestResult]:
    results: list[IngestResult] = []
    for path in sorted(p for p in directory.rglob("*") if p.is_file()):
        result = await ingest_file(session, project_id, path, parsers)
        if result is not None:
            results.append(result)
    return results
