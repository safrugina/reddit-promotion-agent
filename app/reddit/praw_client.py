from datetime import UTC, datetime

import asyncpraw
from asyncpraw.models import Submission, Subreddit

from app.reddit.models import (
    PostInfo,
    SubmissionMetrics,
    SubmissionResult,
    SubredditInfo,
    SubredditRule,
)

REDDIT_BASE_URL = "https://www.reddit.com"


def _to_subreddit_info(subreddit: Subreddit) -> SubredditInfo:
    return SubredditInfo(
        name=str(subreddit.display_name),
        display_name=str(getattr(subreddit, "display_name_prefixed", subreddit.display_name)),
        description=str(getattr(subreddit, "public_description", "") or ""),
        subscribers=int(getattr(subreddit, "subscribers", 0) or 0),
        over18=bool(getattr(subreddit, "over18", False)),
        submission_type=str(getattr(subreddit, "submission_type", "any")),
    )


def _to_post_info(submission: Submission) -> PostInfo:
    author = getattr(submission, "author", None)
    return PostInfo(
        id=str(submission.id),
        subreddit=str(submission.subreddit.display_name),
        title=str(submission.title),
        body=str(getattr(submission, "selftext", "") or ""),
        author=str(author) if author is not None else None,
        url=str(submission.url),
        permalink=f"{REDDIT_BASE_URL}{submission.permalink}",
        score=int(submission.score),
        num_comments=int(submission.num_comments),
        created_at=datetime.fromtimestamp(submission.created_utc, tz=UTC),
        is_self=bool(submission.is_self),
    )


class PrawRedditClient:
    """RedditClient implementation backed by the official Reddit API via Async PRAW."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        user_agent: str,
        username: str = "",
        password: str = "",
    ) -> None:
        if username and password:
            self._reddit = asyncpraw.Reddit(
                client_id=client_id,
                client_secret=client_secret,
                user_agent=user_agent,
                username=username,
                password=password,
            )
        else:
            self._reddit = asyncpraw.Reddit(
                client_id=client_id, client_secret=client_secret, user_agent=user_agent
            )

    async def close(self) -> None:
        await self._reddit.close()

    async def search_subreddits(self, query: str, limit: int = 10) -> list[SubredditInfo]:
        results: list[SubredditInfo] = []
        async for subreddit in self._reddit.subreddits.search(query, limit=limit):
            results.append(_to_subreddit_info(subreddit))
        return results

    async def search_posts(
        self, query: str, subreddit: str | None = None, limit: int = 25
    ) -> list[PostInfo]:
        target = await self._reddit.subreddit(subreddit or "all")
        results: list[PostInfo] = []
        async for submission in target.search(query, limit=limit):
            results.append(_to_post_info(submission))
        return results

    async def get_subreddit(self, name: str) -> SubredditInfo:
        subreddit = await self._reddit.subreddit(name, fetch=True)
        return _to_subreddit_info(subreddit)

    async def get_rules(self, subreddit: str) -> list[SubredditRule]:
        sr = await self._reddit.subreddit(subreddit)
        rules: list[SubredditRule] = []
        async for rule in sr.rules:
            rules.append(
                SubredditRule(
                    short_name=str(rule.short_name),
                    description=str(getattr(rule, "description", "") or ""),
                )
            )
        return rules

    async def get_post(self, post_id: str) -> PostInfo:
        submission = await self._reddit.submission(post_id)
        return _to_post_info(submission)

    async def submit_post(self, subreddit: str, title: str, body: str) -> SubmissionResult:
        sr = await self._reddit.subreddit(subreddit)
        submission = await sr.submit(title=title, selftext=body)
        if submission is None:
            raise RuntimeError("Reddit did not return a submission for this post")
        return SubmissionResult(
            id=str(submission.id),
            url=str(submission.url),
            permalink=f"{REDDIT_BASE_URL}{submission.permalink}",
        )

    async def submit_comment(self, post_id: str, body: str) -> SubmissionResult:
        submission = await self._reddit.submission(post_id)
        comment = await submission.reply(body)
        if comment is None:
            raise RuntimeError("Reddit did not return a comment for this reply")
        return SubmissionResult(
            id=str(comment.id),
            url=f"{REDDIT_BASE_URL}{comment.permalink}",
            permalink=f"{REDDIT_BASE_URL}{comment.permalink}",
        )

    async def get_submission_metrics(self, post_id: str) -> SubmissionMetrics:
        submission = await self._reddit.submission(post_id)
        return SubmissionMetrics(
            id=str(submission.id),
            score=int(submission.score),
            upvote_ratio=float(submission.upvote_ratio),
            num_comments=int(submission.num_comments),
            permalink=f"{REDDIT_BASE_URL}{submission.permalink}",
        )
