from typing import Protocol

from app.reddit.models import (
    PostInfo,
    SubmissionMetrics,
    SubmissionResult,
    SubredditInfo,
    SubredditRule,
)


class RedditClient(Protocol):
    """Abstraction over the official Reddit API.

    Every method must be backed by Reddit's supported API surface. If an
    operation cannot be performed through it, implementations should raise
    rather than fall back to unofficial scraping or browser automation.
    """

    async def search_subreddits(self, query: str, limit: int = 10) -> list[SubredditInfo]: ...

    async def search_posts(
        self, query: str, subreddit: str | None = None, limit: int = 25
    ) -> list[PostInfo]: ...

    async def get_subreddit(self, name: str) -> SubredditInfo: ...

    async def get_rules(self, subreddit: str) -> list[SubredditRule]: ...

    async def get_post(self, post_id: str) -> PostInfo: ...

    async def submit_post(self, subreddit: str, title: str, body: str) -> SubmissionResult: ...

    async def submit_comment(self, post_id: str, body: str) -> SubmissionResult: ...

    async def get_submission_metrics(self, post_id: str) -> SubmissionMetrics: ...

    async def close(self) -> None: ...
