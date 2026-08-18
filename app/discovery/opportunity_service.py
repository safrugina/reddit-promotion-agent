import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.db.models import Project, ProjectFact, RedditOpportunity, Subreddit
from app.db.models.enums import OpportunityStatus
from app.discovery.scoring import (
    OpportunityScoreComponents,
    activity_score,
    compute_opportunity_score,
    contribution_potential_score,
    keyword_overlap_score,
    promotion_risk_from_rules,
)
from app.discovery.subreddit_analyzer import analyze_subreddit
from app.llm.provider import LLMProvider
from app.reddit.client import RedditClient

DEFAULT_MAX_SUBREDDITS = 5
DEFAULT_MAX_POSTS_PER_SUBREDDIT = 10


async def derive_keywords(session: AsyncSession, project: Project, limit: int = 15) -> list[str]:
    """Pull a keyword list from the project's extracted facts, falling back to its
    name/description when no facts have been extracted yet."""
    result = await session.execute(
        select(ProjectFact.fact).where(ProjectFact.project_id == project.id).limit(200)
    )
    facts = [row[0] for row in result.all()]
    if not facts:
        return [w for w in f"{project.name} {project.description or ''}".split() if len(w) > 2][
            :limit
        ]

    # Keep it simple and deterministic: take the shortest facts as they tend to be
    # feature/technology names rather than full sentences.
    facts_sorted = sorted(set(facts), key=len)
    keywords: list[str] = []
    for fact in facts_sorted:
        keywords.extend(w for w in fact.replace(",", " ").split() if len(w) > 2)
        if len(keywords) >= limit:
            break
    return keywords[:limit]


async def _get_or_create_subreddit(
    session: AsyncSession, reddit: RedditClient, llm: LLMProvider, name: str
) -> Subreddit:
    result = await session.execute(select(Subreddit).where(Subreddit.name == name))
    subreddit_row = result.scalar_one_or_none()
    if subreddit_row is not None and subreddit_row.last_analyzed_at is not None:
        return subreddit_row

    info = await reddit.get_subreddit(name)
    rules = await reddit.get_rules(name)
    analysis = await analyze_subreddit(llm, info, rules)

    if subreddit_row is None:
        subreddit_row = Subreddit(name=info.name)
        session.add(subreddit_row)

    subreddit_row.display_name = info.display_name
    subreddit_row.description = info.description
    subreddit_row.rules = [
        {"short_name": r.short_name, "description": r.description} for r in rules
    ]
    subreddit_row.restrictions = {
        "self_promotion_policy": analysis.self_promotion_policy,
        "external_links_policy": analysis.external_links_policy,
    }
    subreddit_row.culture_summary = (
        f"Audience: {analysis.audience}. Topics: {', '.join(analysis.primary_topics)}. "
        f"Good angles: {', '.join(analysis.likely_good_angles)}. "
        f"Risks: {', '.join(analysis.risks)}."
    )
    subreddit_row.activity_score = activity_score(info.subscribers)
    subreddit_row.last_analyzed_at = datetime.now(UTC)
    await session.flush()
    return subreddit_row


async def discover_opportunities(
    session: AsyncSession,
    reddit: RedditClient,
    llm: LLMProvider,
    project_id: uuid.UUID,
    max_subreddits: int = DEFAULT_MAX_SUBREDDITS,
    max_posts_per_subreddit: int = DEFAULT_MAX_POSTS_PER_SUBREDDIT,
) -> list[RedditOpportunity]:
    """Mode A (subreddit discovery) + Mode B (discussion discovery), spec section 11."""
    project = await session.get(Project, project_id)
    if project is None:
        raise ValueError(f"Project {project_id} not found")

    keywords = await derive_keywords(session, project)
    query = " ".join(keywords[:6]) or project.name

    candidate_infos = await reddit.search_subreddits(query, limit=max_subreddits)
    opportunities: list[RedditOpportunity] = []

    for info in candidate_infos:
        subreddit_row = await _get_or_create_subreddit(session, reddit, llm, info.name)
        rule_texts = [r["description"] for r in subreddit_row.rules]
        risk = promotion_risk_from_rules(rule_texts)
        topical_fit = keyword_overlap_score(keywords, subreddit_row.description or "")

        posts = await reddit.search_posts(
            query, subreddit=subreddit_row.name, limit=max_posts_per_subreddit
        )
        for post in posts:
            existing = await session.execute(
                select(RedditOpportunity).where(
                    RedditOpportunity.project_id == project_id,
                    RedditOpportunity.reddit_post_id == post.id,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue

            post_age_hours = max(
                0.0, (datetime.now(UTC) - post.created_at).total_seconds() / 3600
            )
            components = OpportunityScoreComponents(
                relevance=keyword_overlap_score(keywords, f"{post.title} {post.body}"),
                audience_fit=min(100.0, (subreddit_row.activity_score or 0) + topical_fit) / 2,
                discussion_activity=activity_score(
                    subscribers=0, score=post.score, num_comments=post.num_comments
                ),
                topical_fit=topical_fit,
                contribution_potential=contribution_potential_score(
                    post_age_hours, post.num_comments
                ),
                promotion_risk=risk,
            )
            opportunity = RedditOpportunity(
                project_id=project_id,
                subreddit_id=subreddit_row.id,
                reddit_post_id=post.id,
                title=post.title,
                body=post.body,
                url=post.permalink,
                relevance_score=components.relevance,
                discussion_score=components.discussion_activity,
                fit_score=components.audience_fit,
                risk_score=components.promotion_risk,
                topical_fit_score=components.topical_fit,
                contribution_potential_score=components.contribution_potential,
                opportunity_score=compute_opportunity_score(components),
                status=OpportunityStatus.NEW,
            )
            session.add(opportunity)
            opportunities.append(opportunity)
            await session.flush()
            await log_event(
                session,
                "DISCOVERY",
                project_id=project_id,
                subreddit_name=subreddit_row.name,
                opportunity_id=str(opportunity.id),
                reddit_post_id=post.id,
                opportunity_score=opportunity.opportunity_score,
            )

    await session.flush()
    return opportunities
