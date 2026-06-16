# Common tasks (recipes)

Practical, repo-specific recipes for the changes made most often here. Follow the
existing patterns rather than introducing new ones.

## Add a new admin endpoint to an existing router

1. Add the route function in the relevant file under `app/routers/`. The router already
   carries `dependencies=[Depends(require_admin)]`, so admin auth is automatic.
2. Define request/response shapes as Pydantic `BaseModel`s in that same file (see how
   `businesses.py` does `BusinessCreate` / `BusinessResponse`).
3. Put DB logic in `app/crud/`, not inline in the router — routers stay thin.
4. Use `db: AsyncSession = Depends(get_db)` and call `await crud_fn(db, ...)`.

## Add a CRUD query

Add an `async def` to `app/crud/business.py` or `conversation.py`. Use SQLModel style:
```python
result = await db.exec(select(Model).where(...))
return result.first()      # or .all(), or .one() for a scalar count
```
For counts use `select(func.count())...` and `.one()`. Commit with `await db.commit()`
for writes; use `await db.flush()` when you need the generated PK before committing
(see `create_business`).

## Add a field to a model + migrate it

1. Add the field in `app/models/__init__.py`. For a plain column just annotate it. For an
   **enum** column, define the `(str, Enum)` class and use the `_enum_column` helper:
   ```python
   status: SomeEnum = Field(
       default=SomeEnum.OPEN,
       sa_column=_enum_column(SomeEnum, nullable=False, server_default="open"),
   )
   ```
2. Create a migration file `alembic/versions/000N_description.py` following the existing
   numbering, with `down_revision` pointing at the previous revision id.
3. For a plain column: `op.add_column("businesses", sa.Column("col", <type>, ...))`.
   For an enum column: create the PG type first (see `references/database.md` →
   "Writing a new migration that adds an enum column").
4. If the column is `NOT NULL` on a populated table, add it nullable, backfill, then
   `op.alter_column(..., nullable=False)` — that's the `api_key` pattern in `0002`.
5. Run `alembic upgrade head` and verify.

## Change how the AI behaves

- **System prompt / persona / per-type instructions** → `app/services/business_service.py`,
  `get_system_prompt()`. It branches on `business.type` and appends a `response_style`
  instruction. Keep customer-facing text in Persian.
- **Model, history handling, token cap, welcome message** → `app/services/ai_service.py`,
  `chat_with_ai()`. It loads the business + details, builds the message list (system
  prompt + optional welcome on the first turn, otherwise full stored history), calls the
  OpenRouter client, then persists user and assistant messages. Respects
  `business.max_tokens`.
- **Which model / endpoint** → `.env` (`AI_MODEL`, `AI_BASE_URL`, `AI_API_KEY`); the
  client is constructed once at module load in `ai_service.py`.

## Add a new business type

1. Add the value to `BusinessType` in `models/__init__.py` (e.g. `RESTAURANT = "restaurant"`).
2. Migrate the PG enum: `ALTER TYPE businesstype ADD VALUE 'restaurant';` in a new
   migration (`op.execute(...)`). Note PG can't run `ALTER TYPE ... ADD VALUE` inside a
   transaction block in some versions — if it errors, use a non-transactional migration.
3. Add a branch in `get_system_prompt()` for the new type with its Persian prompt and the
   detail keys it expects.
4. Optionally add a sample to `app/seed.py`.

## Add rate limiting to another endpoint

Import the shared limiter (`from app.limiter import limiter`), decorate the route with
`@limiter.limit("N/minute")`, and ensure the handler takes `request: Request` as a
parameter (slowapi needs it).

## Adjust auth

- Change the admin key check or add new dependencies in `app/dependencies.py`.
- To scope an endpoint to a single tenant by its own key, depend on
  `require_business_key` and use the returned `Business`.

## Troubleshooting (already-seen failures)

| Symptom | Cause / fix |
|---------|-------------|
| `'AsyncSession' object has no attribute 'exec'` | `database.py` must import AsyncSession from `sqlmodel.ext.asyncio.session`, not `sqlalchemy.ext.asyncio`. |
| `invalid input value for enum businesstype: "SHOP"` | Enum column not using `_enum_column` / `values_callable`; SQLAlchemy is sending the member name. |
| `type "responsestyle" does not exist` during migration | `add_column` doesn't create enum types — create the PG type first with `.create(op.get_bind(), checkfirst=True)`. |
| asyncpg rejecting the connection / unknown param | `DATABASE_URL` must be `postgresql+asyncpg://...` with no `?schema=public`. |
| `UnicodeEncodeError` printing Persian in `python -c` | Windows cp1252 console; set `PYTHONIOENCODING=utf-8`. Data is fine. |
| uvicorn `--reload` not picking up model changes | Sometimes the reload is partial; stop and restart the server fresh. |

## Verifying a change end-to-end

```bash
alembic upgrade head
uvicorn app.main:app --reload
# then, with the admin key from .env:
curl -H "X-Admin-Key: <key>" http://127.0.0.1:8000/analytics/overview
curl -X POST -H "X-Admin-Key: <key>" -H "Content-Type: application/json" \
  -d '{"name":"x","type":"shop","field":"y","contact":"z","working_hours":"w","details":{}}' \
  http://127.0.0.1:8000/businesses/
```
