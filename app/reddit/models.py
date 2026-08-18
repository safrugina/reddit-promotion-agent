from dataclasses import dataclass
from datetime import datetime


@dataclass
class SubredditRule:
    short_name: str
    description: str


@dataclass
class SubredditInfo:
    name: str
    display_name: str
    description: str
    subscribers: int
    over18: bool
    submission_type: str


@dataclass
class PostInfo:
    id: str
    subreddit: str
    title: str
    body: str
    author: str | None
    url: str
    permalink: str
    score: int
    num_comments: int
    created_at: datetime
    is_self: bool


@dataclass
class SubmissionMetrics:
    id: str
    score: int
    upvote_ratio: float
    num_comments: int
    permalink: str


@dataclass
class SubmissionResult:
    id: str
    url: str
    permalink: str
