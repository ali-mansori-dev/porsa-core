---
name: ai-agent-platform
description: >
  Complete reference for the AI Agent Platform — a multi-tenant AI customer-support
  backend (FastAPI + PostgreSQL + SQLModel + Alembic, LLM via OpenRouter). Use this
  skill whenever working anywhere in this repo: understanding the project, adding or
  changing API endpoints, models, migrations, CRUD, services, auth, rate limiting, or
  the chat/AI flow; debugging runtime errors (enum errors, AsyncSession.exec, asyncpg
  driver/DATABASE_URL issues, alembic enum-type failures); onboarding a fresh session
  that knows nothing about the project; or answering "how does X work here / where is Y".
  Consult it before editing models, writing migrations, or touching the LLM pipeline,
  even if the request doesn't name the platform explicitly.
---

# AI Agent Platform

A multi-tenant AI customer-support backend. Each **business** gets its own AI agent
that talks to its customers **in Persian**, driven by a business-type-specific system
prompt plus the business's own knowledge (products / courses / services, hours, contact,
return policy, etc.). Conversations are stored per `session_id` so the agent has memory.


## How it fits together (the 30-second model)

```
customer ──POST /chat/──► chat router ──► ai_service.chat_with_ai()
                                              │
        ┌─────────────────────────────────────┼───────────────────────────┐
        ▼                                     ▼                           ▼
  load Business +                     build message list             call OpenRouter
  business_details              (system prompt on first turn,        (OpenAI client)
  (crud/business)               else full history from DB)                │
        │                              │                                  ▼
        ▼                              ▼                          save assistant msg,
  get_system_prompt()         save user msg (crud/conversation)   return response text
  (services/business_service)
```

A business owner / admin manages businesses, reads conversations, and views analytics
through admin-only REST endpoints. Customers only ever hit `/chat`.

## Tech stack

| Concern        | Choice |
|----------------|--------|
| Web framework  | FastAPI (fully async) + Uvicorn |
| ORM / models   | SQLModel (SQLAlchemy core + Pydantic) |
| DB             | PostgreSQL via **asyncpg** |
| Migrations     | Alembic |
| LLM            | OpenRouter (OpenAI-compatible `AsyncOpenAI` client), model set by `AI_MODEL` |
| Rate limiting  | slowapi |
| Config         | pydantic-settings reading `.env` |

## Repository map

```
app/
├── main.py            FastAPI app: lifespan(create_tables), CORS, rate-limit handler,
│                      includes routers: chat, businesses, conversations, analytics.
│                      Health: GET / and GET /health.
├── config.py          Settings (env): ai_base_url, ai_model, ai_api_key, database_url,
│                      app_name, debug, admin_api_key, cors_origins, plus OTP/auth:
│                      otp_length, otp_expiry_minutes, otp_max_per_hour, token_expiry_days,
│                      sms_provider (log|kavenegar), kavenegar_api_key/sender/otp_template.
├── database.py        Async engine + AsyncSessionLocal. IMPORTANT: AsyncSession is
│                      imported from sqlmodel.ext.asyncio.session (so db.exec works).
│                      get_db() is the FastAPI dependency; create_tables() runs on startup.
├── limiter.py         Shared `limiter = Limiter(key_func=get_remote_address)`.
│                      Lives in its own module to avoid a circular import with main.
├── dependencies.py    require_admin (checks X-Admin-Key == ADMIN_API_KEY),
│                      require_business_key (resolves X-Business-Key → Business),
│                      get_current_user (Bearer token → User),
│                      require_user_business (User → the Business they own).
├── seed.py            `python -m app.seed`: creates 3 demo businesses (shop/edu/service).
├── models/__init__.py All tables + enums + the _enum_column helper. SEE references/database.md
├── crud/
│   ├── business.py        get/create/update/delete (soft), get_business_by_api_key,
│   │                      get_business_by_owner_phone, regenerate_api_key, details, all.
│   ├── conversation.py    get_or_create_conversation, save_message, history, counts,
│   │                      per-business listing, delete_conversation.
│   ├── auth.py            OTP create/verify (hashed, single-use), get_or_create_user
│   │                      (links business by owner_phone), session create/lookup/delete.
│   ├── faq.py             FAQ entries: get/add/replace/delete per business.
│   └── escalation.py      create/list/count/answer escalated customer questions.
├── routers/
│   ├── chat.py            POST /chat/ (rate-limited 20/min), GET /chat/businesses (public list)
│   ├── auth.py            POST /auth/request-otp (5/min), /verify-otp, GET /me, POST /logout
│   ├── me.py              Owner self-service (Bearer): /me/business (create/get/patch),
│   │                      /me/business/faq, /me/escalations (list + answer).
│   ├── businesses.py      Admin CRUD under /businesses (+ /{id}/regenerate-key)
│   ├── conversations.py   Admin read/delete under /conversations
│   └── analytics.py       Admin stats under /analytics
└── services/
    ├── ai_service.py        chat_with_ai(): load → prompt → LLM → persist. Detects the
    │                        [NEED_HUMAN] marker → escalates + SMSes owner + handoff reply.
    ├── business_service.py  get_system_prompt(): per-type Persian prompt + style + FAQ +
    │                        the [NEED_HUMAN] escalation rule.
    └── sms_service.py       send_otp() / send_message(): pluggable SMS (log | kavenegar).
alembic/versions/
├── 0001_initial.py               businesses, business_details, conversations, messages
├── 0002_business_enhancements.py adds api_key, welcome_message, max_tokens, response_style
├── 0003_phone_auth.py            adds businesses.owner_phone; users, otp_codes, auth_sessions
└── 0004_faq_and_escalations.py   faq_entries, escalations (+ escalationstatus enum)
```

## Data model (summary)

Four tables; full DDL and field notes in `references/database.md`.

- **businesses** — the tenant. Has `type` (shop/education/service), descriptive fields,
  and per-tenant settings: `api_key`, `welcome_message`, `max_tokens`, `response_style`.
- **business_details** — flexible key/value rows (e.g. `products`, `courses`,
  `return_policy`) used to enrich the system prompt.
- **conversations** — one per (`session_id`, `business_id`); the unit of chat memory.
- **messages** — `role` (user/assistant/system) + `content`, ordered by `created_at`.
- **users** — a business owner who logs in by phone (OTP); linked to their business via
  `Business.owner_phone`.
- **otp_codes** — one-time login codes, stored hashed, single-use, short expiry.
- **auth_sessions** — opaque, revocable bearer tokens resolved to a user per request.
- **faq_entries** — owner-defined Q&A; the agent's source of truth, injected into the prompt.
- **escalations** — customer questions the agent couldn't answer (`[NEED_HUMAN]`), with
  `status` (pending/answered/closed); the owner is SMSed and answers via `/me/escalations`.

## API surface (summary)

Full request/response shapes in `references/api-reference.md`.

- **Public:** `GET /`, `GET /health`, `GET /chat/businesses`, `POST /chat/` (20/min/IP).
- **Auth (phone/OTP):** `POST /auth/request-otp` (5/min/IP), `POST /auth/verify-otp` →
  bearer token, `GET /auth/me`, `POST /auth/logout`. Token (`Authorization: Bearer`)
  resolves to the user and their business.
- **Owner self-service (`Authorization: Bearer`):** `/me/business` (create/get/patch —
  the intended way to create a business, one per user), `/me/business/faq` (manage FAQ),
  `/me/escalations` (list + answer escalated questions).
- **Admin (header `X-Admin-Key`):** `/businesses` CRUD + regenerate-key,
  `/conversations` (list per business, detail, delete), `/analytics` (overview, per-business).

## Conventions that bite if ignored

These are real bugs that were already hit and fixed — keep them in mind:

1. **SQLModel's AsyncSession, not SQLAlchemy's.** All CRUD uses `db.exec(...)`, which
   only exists on `sqlmodel.ext.asyncio.session.AsyncSession`. `database.py` imports it
   from there. SQLAlchemy's own `AsyncSession` has `.execute()` but no `.exec()`, so
   swapping it back breaks every query at runtime.

2. **Native enum columns must store the lowercase value.** SQLAlchemy by default stores
   a Python enum's *member name* (`SHOP`), but the PG enum types hold the *values*
   (`shop`). The `_enum_column(...)` helper in `models/__init__.py` sets
   `values_callable=lambda e: [m.value for m in e]` to fix this. Any new enum column
   (or new enum) must go through that helper, else inserts raise
   `invalid input value for enum`.

3. **`DATABASE_URL` uses `postgresql+asyncpg://...`** with no `?schema=public` query
   param (asyncpg rejects unknown params). Example:
   `postgresql+asyncpg://user:pass@localhost:5432/ai_platform`.

4. **Migrations adding an enum column** must create the PG type first:
   `postgresql.ENUM("a","b", name="myenum").create(op.get_bind(), checkfirst=True)` and
   then use `sa.Enum(..., create_type=False)` on the column. `create_table` auto-creates
   enum types but `add_column` does not. Pattern lives in `0002_business_enhancements.py`.

5. **Persian everywhere customer-facing.** System prompts, welcome messages, and error
   strings returned to customers are in Persian by design. Keep new user-facing copy Persian.

6. **Windows console encoding.** Printing Persian via `python -c` can throw
   `UnicodeEncodeError` (cp1252). Set `PYTHONIOENCODING=utf-8` for ad-hoc scripts; it's a
   display issue, not a data issue.

## Workflow conventions

- **After every change, write the commit message in English for the user.** Once you
  finish a change (or a coherent set of changes), provide a ready-to-use Git commit
  message in English — a concise imperative subject line plus a short body explaining
  what changed and why. This is for the user to copy; do not run `git commit` unless
  explicitly asked.

## Common tasks

For step-by-step recipes (add an endpoint, add a model field + migration, change the
LLM behavior, add a new business type), read `references/common-tasks.md`.

## Running locally

```bash
pip install -r requirements.txt
alembic upgrade head            # apply migrations (DB must exist & be reachable)
python -m app.seed              # optional sample data
uvicorn app.main:app --reload   # serves http://127.0.0.1:8000, Swagger at /docs
```

Quick smoke test (admin key from `.env`):
```bash
curl -H "X-Admin-Key: <ADMIN_API_KEY>" http://127.0.0.1:8000/analytics/overview
```

## Reference files

- `references/database.md` — full table DDL, enums, the `_enum_column` helper, relationships.
- `references/api-reference.md` — every endpoint with method, auth, request body, response.
- `references/common-tasks.md` — recipes for the changes you'll most often make here.
