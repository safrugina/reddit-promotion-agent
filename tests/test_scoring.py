import pytest

from app.discovery.scoring import (
    OpportunityScoreComponents,
    activity_score,
    compute_opportunity_score,
    contribution_potential_score,
    keyword_overlap_score,
    promotion_risk_from_rules,
)


def test_keyword_overlap_full_match():
    assert keyword_overlap_score(["postgres", "cli"], "A Postgres CLI tool") == 100.0


def test_keyword_overlap_partial_match():
    score = keyword_overlap_score(["postgres", "cli", "migrations"], "A Postgres tool")
    assert 0 < score < 100


def test_keyword_overlap_no_keywords_returns_zero():
    assert keyword_overlap_score([], "anything") == 0.0


def test_keyword_overlap_no_match_returns_zero():
    assert keyword_overlap_score(["kubernetes"], "a completely unrelated cooking blog") == 0.0


def test_activity_score_increases_with_subscribers():
    small = activity_score(subscribers=100)
    large = activity_score(subscribers=500_000)
    assert 0 <= small < large <= 100


def test_activity_score_zero_for_empty_subreddit():
    assert activity_score(subscribers=0, score=0, num_comments=0) == 0.0


def test_promotion_risk_detects_no_self_promotion_rule():
    risk = promotion_risk_from_rules(["No self promotion of any kind is allowed here."])
    assert risk > 0


def test_promotion_risk_zero_for_silent_rules():
    assert promotion_risk_from_rules(["Be civil.", "No hate speech."]) == 0.0


def test_contribution_potential_favors_fresh_low_comment_posts():
    fresh = contribution_potential_score(post_age_hours=1, num_comments=2)
    stale = contribution_potential_score(post_age_hours=100, num_comments=80)
    assert fresh > stale


def test_contribution_potential_rejects_negative_age():
    with pytest.raises(ValueError):
        contribution_potential_score(post_age_hours=-1, num_comments=0)


def test_compute_opportunity_score_matches_weighted_formula():
    components = OpportunityScoreComponents(
        relevance=80,
        audience_fit=60,
        discussion_activity=50,
        topical_fit=70,
        contribution_potential=40,
        promotion_risk=20,
    )
    expected = 80 * 0.30 + 60 * 0.20 + 50 * 0.15 + 70 * 0.15 + 40 * 0.10 - 20 * 0.10
    assert compute_opportunity_score(components) == round(expected, 2)


def test_compute_opportunity_score_clamped_to_zero_when_risk_dominates():
    components = OpportunityScoreComponents(
        relevance=0,
        audience_fit=0,
        discussion_activity=0,
        topical_fit=0,
        contribution_potential=0,
        promotion_risk=100,
    )
    assert compute_opportunity_score(components) == 0.0


def test_component_out_of_range_raises():
    with pytest.raises(ValueError):
        OpportunityScoreComponents(
            relevance=150,
            audience_fit=0,
            discussion_activity=0,
            topical_fit=0,
            contribution_potential=0,
            promotion_risk=0,
        )
