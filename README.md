# Reddit Promotion Agent

MVP for turning a project's documentation into a searchable knowledge base, discovering
relevant Reddit conversations, generating grounded content candidates, validating them, and
publishing only after explicit human approval. See `REDDIT_PROMOTION_AGENT_MVP_SPEC.md` for the
full specification.

All six phases from the spec are implemented: project ingestion & knowledge base, Reddit
research, content generation, validation, human approval + publishing, and analytics.

## Requirements

- Python 3.12+ (managed via [uv](https://docs.astral.sh/uv/))
- Docker (for PostgreSQL + pgvector)
- An Anthropic API key (`LLM_API_KEY`) — used for fact extraction, subreddit analysis,
  content generation, and validation
- A Voyage AI API key (`VOYAGE_API_KEY`) — used for embeddings (Anthropic has no embeddings
  endpoint; Voyage is Anthropic's recommended partner for this)
- A Reddit API app (`REDDIT_CLIENT_ID`/`REDDIT_CLIENT_SECRET`/`REDDIT_USER_AGENT`) — needed
  for `reddit discover` (search + rules). `REDDIT_USERNAME`/`REDDIT_PASSWORD` are only needed
  if you intend to actually `candidate publish` — leave them blank to use discovery/generation
  only. Create an app at https://www.reddit.com/prefs/apps

## Quickstart

```bash
# Install dependencies
uv sync

# Start PostgreSQL + pgvector
docker compose up -d

# Copy env file and fill in secrets
cp .env.example .env

# Apply database migrations
uv run alembic upgrade head

# Full workflow
uv run reddit-agent project create demo-project
uv run reddit-agent project ingest demo-project ./path/to/docs
uv run reddit-agent project analyze demo-project           # needs LLM_API_KEY + VOYAGE_API_KEY

uv run reddit-agent reddit discover demo-project            # needs Reddit API credentials
uv run reddit-agent opportunities list demo-project

# Quick path: just get subreddit -> message pairs, no publishing, no Reddit write creds
uv run reddit-agent opportunities export demo-project --output results.json

# Full workflow, per-candidate control
uv run reddit-agent candidate generate <opportunity-id>
uv run reddit-agent candidate validate <candidate-id>
uv run reddit-agent candidate approve <candidate-id>        # only if validation_status == PASS
uv run reddit-agent candidate publish <candidate-id> --confirm  # requires human --confirm

uv run reddit-agent opportunities refresh-metrics demo-project
uv run reddit-agent analytics demo-project

# Run the API
uv run uvicorn app.main:app --reload
# -> http://localhost:8000/health

# Run tests / lint / type-check
uv run pytest
uv run ruff check .
uv run mypy app
```

## Project layout

```
app/
├── main.py           # FastAPI app
├── config.py         # environment-based settings (LLM, embeddings, Reddit, rate limits)
├── errors.py          # spec-defined error categories (section 25)
├── audit.py            # immutable audit-log helper (section 24)
├── db/                # SQLAlchemy models, session, Alembic-backing metadata
├── cli/               # Typer CLI (reddit-agent) -- the whole workflow is usable without a UI
├── llm/                # LLMProvider abstraction (Anthropic), prompt-injection defense
├── ingestion/          # document parsers (Markdown/TXT/PDF/DOCX/JSON/YAML/source-code) + hashing/dedup
├── knowledge/           # chunking, Voyage embeddings, pgvector retrieval, fact extraction, project profile
├── reddit/              # RedditClient protocol + Async PRAW implementation
├── discovery/            # deterministic opportunity scoring + SubredditAnalyzer + discovery pipeline
├── generation/            # ContentGenerator: angle taxonomy, grounded/traceable candidates
├── validation/             # GroundingValidator, RuleValidator, PromotionRiskValidator, duplication, FinalReviewer
├── approval/                # human approve/reject workflow (fails closed on validation_status != PASS)
├── publishing/                # publishing safeguards, rate limits, Reddit submission
└── analytics/                  # dashboard metrics, by-subreddit/by-angle breakdowns, engagement refresh
```

## Safety

This is not a mass-posting bot. Nothing is ever published to Reddit without an explicit,
human-approved action and the `--confirm` flag. There is no `campaign run --autopost` and
there never will be in this codebase. See the spec's non-goals (§3) and publishing safeguards
(§22).

Publishing requires, in order: `approval_status == APPROVED`, `validation_status == PASS`,
conservative app-level rate limits (daily/hourly/per-subreddit/min-interval, all configurable),
and the `--confirm` flag. A failed publish is never silently retried -- it's marked `FAILED`
and logged so a human can check Reddit before deciding what to do next.
