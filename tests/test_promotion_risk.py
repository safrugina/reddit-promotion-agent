from app.validation.promotion_risk import URGENCY_PHRASES, assess_promotion_risk


def test_clean_technical_comment_has_low_risk():
    body = (
        "I built a small CLI that infers column types from CSV samples and writes "
        "Alembic-compatible migrations. Happy to answer questions about the approach."
    )
    result = assess_promotion_risk(body)
    assert result.score < 20
    assert result.issues == []


def test_urgency_language_raises_risk():
    result = assess_promotion_risk("Buy now! Limited time offer, don't miss out!!!")
    assert result.score > 0
    assert any("Urgency" in issue for issue in result.issues)


def test_repeated_links_flagged():
    body = "Check https://example.com/a and also https://example.com/b for details."
    result = assess_promotion_risk(body)
    assert any("links" in issue.lower() for issue in result.issues)


def test_excessive_self_reference_flagged():
    body = "My project does X. My tool also does Y. My product is the best at Z."
    result = assess_promotion_risk(body)
    assert any("self-reference" in issue.lower() for issue in result.issues)


def test_score_never_exceeds_100():
    body = " ".join(URGENCY_PHRASES) + " " + " ".join(["https://x.com/a"] * 10) + " !!!!!!!!!!"
    result = assess_promotion_risk(body)
    assert result.score <= 100.0
