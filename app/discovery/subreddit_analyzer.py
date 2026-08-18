from pydantic import BaseModel, Field

from app.llm.prompt_safety import wrap_untrusted
from app.llm.provider import LLMProvider
from app.reddit.models import SubredditInfo, SubredditRule

ANALYZER_SYSTEM_PROMPT = (
    "You are SubredditAnalyzer, an agent that studies a subreddit's description and "
    "explicit rules to characterize its culture, audience, and content norms. "
    "You must clearly distinguish three kinds of statements: (1) an EXPLICIT RULE is "
    "text taken directly from the subreddit's stated rules -- never invent or paraphrase "
    "a rule that isn't actually present; (2) an OBSERVED PATTERN is something evident "
    "from the description/rules text itself (e.g. tone, topic focus); (3) a MODEL "
    "INFERENCE is your own judgment about likely behavior, not directly stated anywhere. "
    "Only the `explicit_rules` field may contain (1). Never present an inference or "
    "observed pattern as if it were an explicit rule. If Reddit's own rule text is "
    "silent about self-promotion or external links, say so plainly rather than guessing "
    "a policy."
)


class SubredditAnalysis(BaseModel):
    subreddit: str
    audience: str
    primary_topics: list[str]
    content_patterns: list[str]
    self_promotion_policy: str = Field(
        description="Best-available characterization; state explicitly if the rules are silent."
    )
    external_links_policy: str
    likely_good_angles: list[str]
    likely_bad_angles: list[str]
    explicit_rules: list[str] = Field(
        description="Verbatim or closely-paraphrased text of actual subreddit rules only."
    )
    risks: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


async def analyze_subreddit(
    llm: LLMProvider, subreddit: SubredditInfo, rules: list[SubredditRule]
) -> SubredditAnalysis:
    rules_text = (
        "\n".join(f"- {rule.short_name}: {rule.description}" for rule in rules)
        or "(no explicit rules were returned by Reddit for this subreddit)"
    )
    description_block = wrap_untrusted(
        f"r/{subreddit.name} description",
        subreddit.description or "(no public description)",
    )
    rules_block = wrap_untrusted(f"r/{subreddit.name} rules", rules_text)

    prompt = (
        f"Analyze r/{subreddit.name} ({subreddit.subscribers} subscribers).\n\n"
        f"{description_block}\n\n{rules_block}\n\n"
        "Produce a SubredditAnalysis. The `explicit_rules` field must contain only "
        "rules actually present in the rules text above -- if there are none, return "
        "an empty list rather than inventing any."
    )

    return await llm.generate_structured(
        prompt, SubredditAnalysis, system=ANALYZER_SYSTEM_PROMPT
    )
