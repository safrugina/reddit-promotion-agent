import asyncio
import json
import re
import uuid
from collections.abc import Coroutine
from dataclasses import asdict
from pathlib import Path
from typing import Any

import typer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.metrics import refresh_engagement_metrics
from app.analytics.service import (
    GroupedMetric,
    ProjectAnalytics,
    compute_project_analytics,
    group_by_angle,
    group_by_subreddit,
)
from app.approval.service import approve_candidate, reject_candidate
from app.db.models import ContentCandidate, Project, RedditOpportunity
from app.db.models.validation_result import ValidationResult
from app.db.session import dispose_engine, session_scope
from app.discovery.opportunity_service import discover_opportunities
from app.errors import AppError
from app.generation.export import export_top_candidates
from app.generation.service import generate_candidates_for_opportunity
from app.ingestion.service import ingest_directory, ingest_file
from app.knowledge.embeddings import get_embedding_provider
from app.knowledge.project_profile import analyze_project
from app.llm.factory import get_llm_provider
from app.publishing.service import publish_candidate
from app.reddit.factory import get_reddit_client
from app.reddit.models import SubmissionResult
from app.validation.service import validate_candidate

app = typer.Typer(help="Reddit Promotion Agent CLI")
project_app = typer.Typer(help="Manage projects")
reddit_app = typer.Typer(help="Reddit discovery")
opportunities_app = typer.Typer(help="Reddit opportunities")
candidate_app = typer.Typer(help="Content candidates")

app.add_typer(project_app, name="project")
app.add_typer(reddit_app, name="reddit")
app.add_typer(opportunities_app, name="opportunities")
app.add_typer(candidate_app, name="candidate")


def _run_sync[T](coro: Coroutine[Any, Any, T]) -> T:
    """Run a coroutine in its own event loop and release DB connections.

    Each CLI invocation is normally a fresh process, but this also keeps
    back-to-back invocations within one process (e.g. tests) safe, since
    asyncpg connections are bound to the event loop that created them.
    """
    try:
        return asyncio.run(coro)
    finally:
        asyncio.run(dispose_engine())


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or uuid.uuid4().hex[:8]


async def _get_project_by_slug(session: AsyncSession, slug: str) -> Project:
    result = await session.execute(select(Project).where(Project.slug == slug))
    project = result.scalar_one_or_none()
    if project is None:
        typer.echo(f"No project with slug '{slug}'", err=True)
        raise typer.Exit(code=1)
    return project


def _parse_uuid_or_exit(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        typer.echo(f"Invalid id: {value}", err=True)
        raise typer.Exit(code=1) from exc


@project_app.command("create")
def project_create(name: str) -> None:
    """Create a new project."""

    async def _run() -> Project:
        async with session_scope() as session:
            project = Project(name=name, slug=_slugify(name))
            session.add(project)
            await session.commit()
            await session.refresh(project)
            return project

    project = _run_sync(_run())
    typer.echo(f"Created project '{project.name}' (id={project.id}, slug={project.slug})")


@project_app.command("list")
def project_list() -> None:
    """List existing projects."""

    async def _run() -> list[Project]:
        async with session_scope() as session:
            result = await session.execute(select(Project))
            return list(result.scalars().all())

    projects = _run_sync(_run())
    if not projects:
        typer.echo("No projects yet.")
        return
    for project in projects:
        typer.echo(f"{project.slug}\t{project.id}\t{project.status.value}")


@project_app.command("ingest")
def project_ingest(project_slug: str, path: str) -> None:
    """Ingest a documentation file or directory for a project."""
    source = Path(path)
    if not source.exists():
        typer.echo(f"Path does not exist: {path}", err=True)
        raise typer.Exit(code=1)

    async def _run() -> tuple[int, int, int]:
        async with session_scope() as session:
            project = await _get_project_by_slug(session, project_slug)
            if source.is_dir():
                results = await ingest_directory(session, project.id, source)
            else:
                result = await ingest_file(session, project.id, source)
                results = [result] if result is not None else []
            await session.commit()
            ingested = sum(1 for r in results if not r.was_duplicate)
            duplicates = sum(1 for r in results if r.was_duplicate)
            return len(results), ingested, duplicates

    total, ingested, duplicates = _run_sync(_run())
    typer.echo(
        f"Processed {total} file(s): {ingested} newly ingested, {duplicates} already present."
    )


@project_app.command("analyze")
def project_analyze(project_slug: str) -> None:
    """Build/refresh the project knowledge base (chunk, embed, extract facts)."""

    async def _run() -> None:
        async with session_scope() as session:
            project = await _get_project_by_slug(session, project_slug)
            llm = get_llm_provider()
            embeddings = get_embedding_provider()
            profile = await analyze_project(session, llm, embeddings, project.id)
            await session.commit()
            typer.echo(f"what_it_is: {profile.what_it_is or '(not yet known)'}")
            for field_name in (
                "who_it_is_for",
                "problems",
                "features",
                "use_cases",
                "differentiators",
                "technical_details",
                "links",
                "claims",
                "limitations",
            ):
                values = getattr(profile, field_name)
                typer.echo(f"{field_name} ({len(values)}):")
                for value in values:
                    typer.echo(f"  - {value}")

    _run_sync(_run())


@reddit_app.command("discover")
def reddit_discover(project_slug: str) -> None:
    """Discover Reddit subreddits and discussions relevant to a project."""

    async def _run() -> int:
        try:
            reddit = get_reddit_client()
        except AppError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        try:
            async with session_scope() as session:
                project = await _get_project_by_slug(session, project_slug)
                llm = get_llm_provider()
                opportunities = await discover_opportunities(session, reddit, llm, project.id)
                await session.commit()
                return len(opportunities)
        finally:
            await reddit.close()

    count = _run_sync(_run())
    typer.echo(f"Discovered {count} new opportunity(ies). Run 'opportunities list' to view them.")


@opportunities_app.command("list")
def opportunities_list(project_slug: str) -> None:
    """List discovered opportunities, ranked by opportunity_score."""

    async def _run() -> list[RedditOpportunity]:
        async with session_scope() as session:
            project = await _get_project_by_slug(session, project_slug)
            result = await session.execute(
                select(RedditOpportunity)
                .where(RedditOpportunity.project_id == project.id)
                .order_by(RedditOpportunity.opportunity_score.desc())
            )
            return list(result.scalars().all())

    opportunities = _run_sync(_run())
    if not opportunities:
        typer.echo("No opportunities yet. Run 'reddit discover' first.")
        return
    for opp in opportunities:
        typer.echo(
            f"{opp.id}\tscore={opp.opportunity_score:.1f}\trisk={opp.risk_score:.1f}\t"
            f"status={opp.status.value}\t{opp.title}"
        )


@opportunities_app.command("refresh-metrics")
def opportunities_refresh_metrics(project_slug: str) -> None:
    """Fetch current Reddit metrics for discussions with a published candidate."""

    async def _run() -> int:
        try:
            reddit = get_reddit_client()
        except AppError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        try:
            async with session_scope() as session:
                project = await _get_project_by_slug(session, project_slug)
                metrics = await refresh_engagement_metrics(session, reddit, project.id)
                await session.commit()
                return len(metrics)
        finally:
            await reddit.close()

    count = _run_sync(_run())
    typer.echo(f"Refreshed metrics for {count} discussion(s). See 'analytics' / audit log.")


@opportunities_app.command("export")
def opportunities_export(
    project_slug: str,
    output: str = typer.Option(
        "", "--output", help="Optional path to also write the results as JSON."
    ),
    top_per_subreddit: int = typer.Option(
        1, "--top-per-subreddit", help="How many discussions to include per subreddit."
    ),
) -> None:
    """Export the top discussion + generated message for each discovered subreddit.

    Does not touch Reddit and never publishes anything -- it only generates
    content (if not already generated) for the best-scoring opportunity per
    subreddit and prints/saves the subreddit -> message pairs. Run
    'reddit discover' first.
    """

    async def _run() -> list[dict[str, Any]]:
        async with session_scope() as session:
            project = await _get_project_by_slug(session, project_slug)
            llm = get_llm_provider()
            entries = await export_top_candidates(
                session, llm, project.id, top_per_subreddit=top_per_subreddit
            )
            await session.commit()
            return [asdict(e) for e in entries]

    entries = _run_sync(_run())
    if not entries:
        typer.echo("No opportunities yet. Run 'reddit discover' first.")
        return

    for entry in entries:
        typer.echo(f"=== r/{entry['subreddit']} ({entry['angle']}) ===")
        typer.echo(f"discussion: {entry['opportunity_title']}")
        typer.echo(f"url: {entry['opportunity_url']}")
        typer.echo("")
        typer.echo(entry["body"])
        if entry["cta"]:
            typer.echo(f"\nCTA: {entry['cta']}")
        typer.echo("")

    if output:
        Path(output).write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
        typer.echo(f"Saved {len(entries)} entries to {output}")


@candidate_app.command("generate")
def candidate_generate(opportunity_id: str) -> None:
    """Generate up to 3 grounded content candidates for a discovered opportunity."""
    opportunity_uuid = _parse_uuid_or_exit(opportunity_id)

    async def _run() -> list[ContentCandidate]:
        async with session_scope() as session:
            llm = get_llm_provider()
            candidates = await generate_candidates_for_opportunity(session, llm, opportunity_uuid)
            await session.commit()
            return candidates

    candidates = _run_sync(_run())
    for candidate in candidates:
        typer.echo(f"--- {candidate.id} [{candidate.angle.value}] ---")
        typer.echo(candidate.body)
        if candidate.cta:
            typer.echo(f"CTA: {candidate.cta}")
        typer.echo(f"rationale: {candidate.rationale}")
        typer.echo(f"source_fact_ids: {candidate.source_fact_ids}")
        typer.echo("")


@candidate_app.command("validate")
def candidate_validate(candidate_id: str) -> None:
    """Run grounding/rule/duplication/promotion-risk checks on a candidate."""
    candidate_uuid = _parse_uuid_or_exit(candidate_id)

    async def _run() -> tuple[ValidationResult, str]:
        async with session_scope() as session:
            llm = get_llm_provider()
            embeddings = get_embedding_provider()
            result = await validate_candidate(session, llm, embeddings, candidate_uuid)
            candidate = await session.get(ContentCandidate, candidate_uuid)
            await session.commit()
            assert candidate is not None
            return result, candidate.validation_status.value

    result, status = _run_sync(_run())
    typer.echo(f"validation_status: {status}")
    typer.echo(
        f"rule_compliance={result.rule_compliance_score:.1f} "
        f"grounding={result.grounding_score:.1f} originality={result.originality_score:.1f} "
        f"promotion_risk={result.promotion_score:.1f} overall_risk={result.risk_score:.1f}"
    )
    for issue in result.issues:
        typer.echo(f"ISSUE: {issue}")
    for warning in result.warnings:
        typer.echo(f"WARNING: {warning}")


@candidate_app.command("approve")
def candidate_approve(candidate_id: str) -> None:
    """Approve a validated content candidate for publishing."""
    candidate_uuid = _parse_uuid_or_exit(candidate_id)

    async def _run() -> None:
        async with session_scope() as session:
            try:
                await approve_candidate(session, candidate_uuid)
            except AppError as exc:
                typer.echo(str(exc), err=True)
                raise typer.Exit(code=1) from exc
            await session.commit()

    _run_sync(_run())
    typer.echo(f"Approved candidate {candidate_id}.")


@candidate_app.command("reject")
def candidate_reject(
    candidate_id: str,
    reason: str = typer.Option("", "--reason", help="Optional reason for the record."),
) -> None:
    """Reject a content candidate."""
    candidate_uuid = _parse_uuid_or_exit(candidate_id)

    async def _run() -> None:
        async with session_scope() as session:
            await reject_candidate(session, candidate_uuid, reason or None)
            await session.commit()

    _run_sync(_run())
    typer.echo(f"Rejected candidate {candidate_id}.")


@candidate_app.command("publish")
def candidate_publish(
    candidate_id: str,
    confirm: bool = typer.Option(False, "--confirm", help="Required to actually publish."),
) -> None:
    """Publish an approved, validated content candidate to Reddit."""
    candidate_uuid = _parse_uuid_or_exit(candidate_id)

    async def _run() -> SubmissionResult:
        try:
            reddit = get_reddit_client()
        except AppError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(code=1) from exc

        try:
            async with session_scope() as session:
                try:
                    result = await publish_candidate(
                        session, reddit, candidate_uuid, confirm=confirm
                    )
                except AppError as exc:
                    await session.commit()  # persist the FAILED status if one was set
                    typer.echo(str(exc), err=True)
                    raise typer.Exit(code=1) from exc
                await session.commit()
                return result
        finally:
            await reddit.close()

    result = _run_sync(_run())
    typer.echo(f"Published: {result.url}")


@app.command("analytics")
def analytics(project_slug: str) -> None:
    """Show dashboard metrics for a project, grouped by subreddit and angle."""

    async def _run() -> tuple[ProjectAnalytics, list[GroupedMetric], list[GroupedMetric]]:
        async with session_scope() as session:
            project = await _get_project_by_slug(session, project_slug)
            summary = await compute_project_analytics(session, project.id)
            by_subreddit = await group_by_subreddit(session, project.id)
            by_angle = await group_by_angle(session, project.id)
            return summary, by_subreddit, by_angle

    summary, by_subreddit, by_angle = _run_sync(_run())

    typer.echo(f"opportunities_discovered: {summary.opportunities_discovered}")
    typer.echo(f"candidates_generated:     {summary.candidates_generated}")
    typer.echo(f"candidates_approved:      {summary.candidates_approved}")
    typer.echo(f"candidates_rejected:      {summary.candidates_rejected}")
    typer.echo(f"candidates_published:     {summary.candidates_published}")
    typer.echo(f"publication_failures:     {summary.publication_failures}")
    typer.echo(f"average_relevance_score:  {summary.average_relevance_score}")
    typer.echo(f"average_validation_score: {summary.average_validation_score}")

    typer.echo("\nBy subreddit (generated/published):")
    for metric in by_subreddit:
        typer.echo(
            f"  r/{metric.label}: {metric.candidates_generated}/{metric.candidates_published}"
        )

    typer.echo("\nBy angle (generated/published):")
    for metric in by_angle:
        typer.echo(f"  {metric.label}: {metric.candidates_generated}/{metric.candidates_published}")


if __name__ == "__main__":
    app()
