import math
import re
from dataclasses import dataclass

# Opportunity scoring is intentionally deterministic (spec section 12): an LLM may
# inform individual signals (e.g. via SubredditAnalysis), but must never be the sole
# scoring mechanism, and the combination formula itself must be reproducible.

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return set(_WORD_RE.findall(text.lower()))


def keyword_overlap_score(keywords: list[str], text: str) -> float:
    """0-100 score for how many of ``keywords`` appear in ``text`` (token overlap)."""
    keyword_tokens = {token for kw in keywords for token in _tokenize(kw)}
    if not keyword_tokens:
        return 0.0
    text_tokens = _tokenize(text)
    matched = keyword_tokens & text_tokens
    return round(100 * len(matched) / len(keyword_tokens), 2)


def activity_score(subscribers: int, score: int = 0, num_comments: int = 0) -> float:
    """0-100 score from subscriber count and/or post engagement, log-scaled.

    Log scaling keeps a single viral post or mega-subreddit from saturating the
    score while still rewarding genuine activity over dead communities.
    """
    raw = math.log1p(max(subscribers, 0)) + math.log1p(max(score, 0)) + math.log1p(
        max(num_comments, 0)
    )
    # log1p(2_000_000) ~= 14.5; treat that as a practical ceiling for normalization.
    normalized = min(raw / 14.5, 1.0) * 100
    return round(normalized, 2)


def promotion_risk_from_rules(rule_texts: list[str]) -> float:
    """0-100 risk score from subreddit rule text, independent of any LLM judgment."""
    risk_keywords = (
        "no self promotion",
        "no self-promotion",
        "no advertising",
        "no promotion",
        "spam",
        "no soliciting",
        "no marketing",
        "9:1",
        "90/10",
        "self-promo",
    )
    combined = " ".join(rule_texts).lower()
    hits = sum(1 for kw in risk_keywords if kw in combined)
    return round(min(hits / 3, 1.0) * 100, 2)


def contribution_potential_score(post_age_hours: float, num_comments: int) -> float:
    """0-100 score: fresher discussions with fewer existing replies have more room
    for a genuinely useful contribution to stand out."""
    if post_age_hours < 0:
        raise ValueError("post_age_hours must be >= 0")
    freshness = max(0.0, 1.0 - post_age_hours / 72.0)  # decays to 0 over 3 days
    room = max(0.0, 1.0 - min(num_comments, 50) / 50.0)
    return round(((freshness + room) / 2) * 100, 2)


@dataclass
class OpportunityScoreComponents:
    relevance: float
    audience_fit: float
    discussion_activity: float
    topical_fit: float
    contribution_potential: float
    promotion_risk: float

    def __post_init__(self) -> None:
        for field_name in (
            "relevance",
            "audience_fit",
            "discussion_activity",
            "topical_fit",
            "contribution_potential",
            "promotion_risk",
        ):
            value = getattr(self, field_name)
            if not 0.0 <= value <= 100.0:
                raise ValueError(f"{field_name} must be within 0-100, got {value}")


def compute_opportunity_score(components: OpportunityScoreComponents) -> float:
    """spec section 12's weighted formula, clamped to 0-100."""
    raw = (
        components.relevance * 0.30
        + components.audience_fit * 0.20
        + components.discussion_activity * 0.15
        + components.topical_fit * 0.15
        + components.contribution_potential * 0.10
        - components.promotion_risk * 0.10
    )
    return round(max(0.0, min(100.0, raw)), 2)
