import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import DocumentChunk, Project, ProjectFact, SourceDocument
from app.db.models.enums import FactType
from app.knowledge.embeddings import EmbeddingProvider
from app.knowledge.pipeline import chunk_document
from app.llm.prompt_safety import wrap_untrusted
from app.llm.provider import LLMProvider

FactTypeLiteral = Literal[
    "feature",
    "claim",
    "metric",
    "use_case",
    "audience",
    "limitation",
    "technical_detail",
    "link",
    "problem",
    "differentiator",
]

EXTRACTION_SYSTEM_PROMPT = (
    "You are ProjectExtractor, an agent that reads a software/product project's own "
    "documentation and extracts a structured, source-grounded profile of the project. "
    "Only report facts that are explicitly stated or directly implied by the supplied "
    "documentation. Never invent metrics, users, customers, endorsements, or capabilities. "
    "If the documentation does not support a claim, do not include it."
)


class ExtractedFact(BaseModel):
    fact: str = Field(description="A single, self-contained factual statement.")
    fact_type: FactTypeLiteral
    confidence: float = Field(ge=0.0, le=1.0)


class ProjectExtraction(BaseModel):
    what_it_is: str = Field(description="One or two sentences describing what the project is.")
    facts: list[ExtractedFact]


class ProjectProfile(BaseModel):
    what_it_is: str
    who_it_is_for: list[str]
    problems: list[str]
    features: list[str]
    use_cases: list[str]
    differentiators: list[str]
    technical_details: list[str]
    links: list[str]
    claims: list[str]
    limitations: list[str]


_FACT_TYPE_TO_PROFILE_FIELD = {
    FactType.AUDIENCE: "who_it_is_for",
    FactType.PROBLEM: "problems",
    FactType.FEATURE: "features",
    FactType.USE_CASE: "use_cases",
    FactType.DIFFERENTIATOR: "differentiators",
    FactType.TECHNICAL_DETAIL: "technical_details",
    FactType.LINK: "links",
    FactType.CLAIM: "claims",
    FactType.LIMITATION: "limitations",
    FactType.METRIC: "claims",
}


async def extract_facts_for_document(
    session: AsyncSession,
    llm: LLMProvider,
    document: SourceDocument,
) -> tuple[str | None, list[ProjectFact]]:
    """Run ProjectExtractor over one document's chunks and persist ProjectFact rows.

    Returns the extracted ``what_it_is`` summary (if any) and the persisted facts.
    """
    chunks_result = await session.execute(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
    )
    chunks = list(chunks_result.scalars().all())
    if not chunks:
        return None, []

    combined_text = "\n\n---\n\n".join(chunk.text for chunk in chunks)
    prompt = (
        "Extract a structured profile from the following project documentation.\n\n"
        + wrap_untrusted(document.filename, combined_text)
    )

    extraction = await llm.generate_structured(
        prompt, ProjectExtraction, system=EXTRACTION_SYSTEM_PROMPT
    )

    chunk_ids = [str(chunk.id) for chunk in chunks]
    facts: list[ProjectFact] = []
    for item in extraction.facts:
        fact = ProjectFact(
            project_id=document.project_id,
            fact=item.fact,
            source_chunk_ids=chunk_ids,
            confidence=item.confidence,
            fact_type=FactType(item.fact_type),
        )
        session.add(fact)
        facts.append(fact)

    document.facts_extracted_at = datetime.now(UTC)
    await session.flush()
    return extraction.what_it_is, facts


async def build_project_profile(session: AsyncSession, project: Project) -> ProjectProfile:
    """Assemble the project profile deterministically from stored ProjectFact rows."""
    result = await session.execute(select(ProjectFact).where(ProjectFact.project_id == project.id))
    facts = list(result.scalars().all())

    grouped: dict[str, list[str]] = {
        field: [] for field in ProjectProfile.model_fields if field != "what_it_is"
    }
    for fact in facts:
        field_name = _FACT_TYPE_TO_PROFILE_FIELD.get(fact.fact_type)
        if field_name is not None:
            grouped[field_name].append(fact.fact)

    return ProjectProfile(
        what_it_is=project.description or "",
        who_it_is_for=grouped["who_it_is_for"],
        problems=grouped["problems"],
        features=grouped["features"],
        use_cases=grouped["use_cases"],
        differentiators=grouped["differentiators"],
        technical_details=grouped["technical_details"],
        links=grouped["links"],
        claims=grouped["claims"],
        limitations=grouped["limitations"],
    )


async def analyze_project(
    session: AsyncSession,
    llm: LLMProvider,
    embeddings: EmbeddingProvider,
    project_id: uuid.UUID,
) -> ProjectProfile:
    """Build (or refresh) the project's knowledge base: chunk + embed + extract facts
    for any document that hasn't been processed yet, then assemble the profile."""
    project = await session.get(Project, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    documents_result = await session.execute(
        select(SourceDocument).where(SourceDocument.project_id == project_id)
    )
    documents = list(documents_result.scalars().all())

    what_it_is_candidates: list[str] = []
    for document in documents:
        if document.chunked_at is None:
            await chunk_document(session, embeddings, document)

        if document.facts_extracted_at is None:
            what_it_is, _facts = await extract_facts_for_document(session, llm, document)
            if what_it_is:
                what_it_is_candidates.append(what_it_is)

    if what_it_is_candidates and not project.description:
        project.description = what_it_is_candidates[0]
        await session.flush()

    return await build_project_profile(session, project)
