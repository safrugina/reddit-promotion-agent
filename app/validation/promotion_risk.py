import re
from dataclasses import dataclass

# Deterministic signal-based risk detector (spec section 17). This is a risk
# detector, not a censorship engine: it flags patterns, it doesn't rewrite content.

URGENCY_PHRASES = (
    "buy now",
    "act now",
    "don't miss out",
    "limited time",
    "limited time only",
    "hurry",
    "once in a lifetime",
    "last chance",
    "sign up now",
    "click here",
    "download now",
    "get rich",
    "guaranteed returns",
    "100% guaranteed",
    "risk-free",
    "moon",
    "to the moon",
)

CTA_PHRASES = (
    "check it out",
    "check us out",
    "visit our",
    "sign up",
    "click the link",
    "link in bio",
    "dm me",
)

SELF_REFERENCE_PATTERN = re.compile(r"\b(my project|my tool|my product|my startup)\b", re.I)
LINK_PATTERN = re.compile(r"https?://\S+")


@dataclass
class PromotionRiskResult:
    score: float  # 0-100, higher = more promotional/risky
    issues: list[str]


def assess_promotion_risk(body: str, cta: str | None = None) -> PromotionRiskResult:
    text = f"{body}\n{cta or ''}"
    lowered = text.lower()
    issues: list[str] = []
    score = 0.0

    for phrase in URGENCY_PHRASES:
        if phrase in lowered:
            issues.append(f"Urgency/hype language: '{phrase}'")
            score += 20

    cta_hits = [phrase for phrase in CTA_PHRASES if phrase in lowered]
    if len(cta_hits) > 1:
        issues.append(f"Multiple promotional CTAs: {', '.join(cta_hits)}")
        score += 15
    elif cta_hits:
        score += 5

    links = LINK_PATTERN.findall(text)
    if len(links) > 1:
        issues.append(f"Repeated links ({len(links)} found)")
        score += 15

    exclamations = text.count("!")
    if exclamations > 2:
        issues.append(f"Excessive exclamation marks ({exclamations})")
        score += 10

    self_references = len(SELF_REFERENCE_PATTERN.findall(text))
    if self_references > 2:
        issues.append(f"Excessive self-reference ({self_references} mentions)")
        score += 10

    return PromotionRiskResult(score=min(100.0, round(score, 2)), issues=issues)
