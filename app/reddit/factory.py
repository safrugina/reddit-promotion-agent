from functools import lru_cache

from app.config import get_settings
from app.errors import ConfigurationError
from app.reddit.client import RedditClient
from app.reddit.praw_client import PrawRedditClient


@lru_cache
def get_reddit_client() -> RedditClient:
    settings = get_settings()
    if not settings.REDDIT_CLIENT_ID or not settings.REDDIT_CLIENT_SECRET:
        raise ConfigurationError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set to use Reddit features. "
            "Create an app at https://www.reddit.com/prefs/apps and set them in .env."
        )
    if not settings.REDDIT_USER_AGENT:
        raise ConfigurationError(
            "REDDIT_USER_AGENT must be set (Reddit requires a descriptive UA)."
        )

    return PrawRedditClient(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
        username=settings.REDDIT_USERNAME,
        password=settings.REDDIT_PASSWORD,
    )
