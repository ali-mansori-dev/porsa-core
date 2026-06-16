# AI Agent Platform

A multi-tenant AI customer-support platform. Each business gets its own AI agent
that chats with customers in Persian, using a business-specific system prompt and
knowledge base.

## Stack
- **FastAPI** (async) + **Uvicorn**
- **PostgreSQL** via **asyncpg** + **SQLModel** (SQLAlchemy + Pydantic)
- **Alembic** migrations
- LLM through **OpenRouter** (OpenAI-compatible client), configurable model
- **slowapi** for rate limiting

## Layout
```
app/
├── main.py            # FastAPI app, middleware (CORS, rate limit), router wiring, lifespan
├── config.py          # pydantic-settings, reads .env
├── database.py        # async engine + session (uses SQLModel's AsyncSession)
├── limiter.py         # shared slowapi Limiter instance
├── dependencies.py    # auth deps: require_admin, require_business_key
├── seed.py            # `python -m app.seed` creates 3 sample businesses
├── models/__init__.py # all SQLModel tables + enums
├── crud/              # business.py, conversation.py — DB queries (use db.exec())
├── routers/           # chat.py, businesses.py, conversations.py, analytics.py
└── services/          # ai_service.py (LLM call), business_service.py (system prompts)
alembic/versions/      # 0001 initial schema, 0002 business enhancements
```

## Key conventions (important — easy to get wrong)
- **Use SQLModel's `AsyncSession`** (imported in `database.py` from
  `sqlmodel.ext.asyncio.session`), not SQLAlchemy's. CRUD code calls `db.exec(...)`,
  which only exists on SQLModel's session.
- **Native PG enums store the lowercase *value*** (e.g. `shop`), not the member name
  (`SHOP`). This is enforced by the `_enum_column` helper in `models/__init__.py` via
  `values_callable`. Any new enum column must use that helper or inserts will fail with
  "invalid input value for enum".
- **`DATABASE_URL` must use the `postgresql+asyncpg://` driver prefix** (no `?schema=`
  query param — asyncpg rejects it).
- **Adding an enum column in a migration** requires creating the PG type explicitly
  first (`postgresql.ENUM(...).create(op.get_bind(), checkfirst=True)`); `add_column`
  does not auto-create enum types the way `create_table` does. See `0002` for the pattern.

## Auth model
- **Admin routes** (`/businesses`, `/conversations`, `/analytics`) require header
  `X-Admin-Key` matching `ADMIN_API_KEY` from `.env`.
- **Each business has its own `api_key`** (auto-generated) for widget/customer-facing use;
  validated by `require_business_key`. The public `/chat` endpoint is rate-limited (20/min/IP).
- **Business owners log in by phone (OTP)** under `/auth`: `request-otp` → SMS code →
  `verify-otp` → opaque **bearer token** (stored in `auth_sessions`, revocable). The token
  resolves to a `User` (`get_current_user`) and to the business they own
  (`require_user_business`), linked via `Business.owner_phone`. SMS is pluggable
  (`SMS_PROVIDER=log|kavenegar`); `log` just prints the code for local dev.
- **Owners create/manage their own business via `/me`** (bearer token, not the admin key):
  `POST /me/business` (onboarding, one per user), `/me/business/faq` (the agent's Q&A
  knowledge), `/me/escalations`. The admin `/businesses` CRUD still exists for oversight.
- **Human handoff:** the agent answers only from the business profile + its `faq_entries`.
  When a question isn't covered it emits `[NEED_HUMAN]`; `ai_service` records an
  `escalation`, SMSes the owner, and returns a Persian handoff reply. Owners answer from
  `/me/escalations`.

## Running
```bash
pip install -r requirements.txt
alembic upgrade head          # apply migrations
python -m app.seed            # optional: sample data
uvicorn app.main:app --reload # http://127.0.0.1:8000  (docs at /docs)
```
`.env` is gitignored. Required keys: `AI_BASE_URL`, `AI_MODEL`, `AI_API_KEY`,
`DATABASE_URL`, `ADMIN_API_KEY`, `CORS_ORIGINS`.

## Deeper docs
For full API reference, data model, and request flow, see the **`ai-agent-platform`
skill** in `.claude/skills/ai-agent-platform/` (and its `references/` files).
