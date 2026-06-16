# Database reference

PostgreSQL accessed asynchronously through asyncpg. Models are SQLModel classes in
`app/models/__init__.py`. Schema is managed by Alembic (`alembic/versions/`). On app
startup `create_tables()` also runs `SQLModel.metadata.create_all` with `checkfirst`,
so existing objects are left alone — but **migrations are the source of truth** for
production schema changes.

## Enums

All enums subclass `(str, Enum)` and are stored as **native PostgreSQL enum types**
holding the lowercase *values*:

| Python enum     | PG type name     | Values |
|-----------------|------------------|--------|
| `BusinessType`     | `businesstype`     | `shop`, `education`, `service` |
| `ResponseStyle`    | `responsestyle`    | `friendly`, `formal`, `brief` |
| `MessageRole`      | `messagerole`      | `user`, `assistant`, `system` |
| `EscalationStatus` | `escalationstatus` | `pending`, `answered`, `closed` |

### The `_enum_column` helper (critical)

```python
def _enum_column(enum_cls, **kwargs) -> Column:
    return Column(
        SAEnum(
            enum_cls,
            name=enum_cls.__name__.lower(),
            values_callable=lambda e: [member.value for member in e],
        ),
        **kwargs,
    )
```

Why it exists: by default SQLAlchemy stores a Python enum's **name** (`SHOP`), but the
PG types hold **values** (`shop`). Without `values_callable`, inserts fail with
`invalid input value for enum businesstype: "SHOP"`. Every enum column routes through
this helper. If you add a new enum or enum column, use it.

## Tables

### businesses
The tenant. One row per business.

| Column           | Type / notes |
|------------------|--------------|
| `id`             | UUID, PK, default `uuid4` |
| `name`           | str |
| `type`           | `BusinessType` enum (via `_enum_column`, not null) |
| `field`          | str — business area, e.g. "فروش لوازم الکترونیکی" |
| `contact`        | str |
| `working_hours`  | str |
| `is_active`      | bool, default true — **soft delete** flips this to false |
| `created_at`     | datetime, default `utcnow` |
| `api_key`        | str, unique, indexed, default `secrets.token_urlsafe(32)` — per-tenant key |
| `welcome_message`| Optional[str] — sent as the first assistant message of a new conversation |
| `max_tokens`     | int, default 1000 — caps the LLM response length for this tenant |
| `response_style` | `ResponseStyle` enum, default `friendly`, server_default `friendly` |
| `owner_phone`    | Optional[str], indexed — owner's phone; links a phone/OTP `User` to this business |

Relationships: `details` (1‑to‑many BusinessDetail), `conversations` (1‑to‑many).

### business_details
Flexible per-business knowledge as key/value rows. Read into a `dict[str,str]` and fed
into the system prompt.

| Column        | Type / notes |
|---------------|--------------|
| `id`          | UUID, PK |
| `business_id` | UUID, FK → businesses.id, indexed |
| `key`         | str — e.g. `products`, `courses`, `services`, `return_policy`, `age_range`, `service_area` |
| `value`       | str |

Which keys matter depends on `business.type` — see `business_service.get_system_prompt`.

### conversations
One per (`session_id`, `business_id`). This is the memory boundary: the same browser
session talking to the same business continues one conversation.

| Column        | Type / notes |
|---------------|--------------|
| `id`          | UUID, PK |
| `session_id`  | str, indexed — supplied by client; auto-generated UUID if omitted |
| `business_id` | UUID, FK → businesses.id, indexed |
| `created_at`  | datetime, default `utcnow` |

Relationships: `business` (many‑to‑one), `messages` (1‑to‑many).

### messages
Ordered chat log.

| Column            | Type / notes |
|-------------------|--------------|
| `id`              | UUID, PK |
| `conversation_id` | UUID, FK → conversations.id, indexed |
| `role`            | `MessageRole` enum (via `_enum_column`) — user / assistant / system |
| `content`         | Text (not null) |
| `created_at`      | datetime, default `utcnow` — ordering key for history |

The system prompt is persisted as a `system` message on the first turn; subsequent
turns rebuild the LLM message list from stored history rather than regenerating it.

### users
A business owner authenticated by phone/OTP. No enum columns.

| Column          | Type / notes |
|-----------------|--------------|
| `id`            | UUID, PK |
| `phone`         | str, **unique**, indexed — normalized (ASCII digits) at login |
| `business_id`   | Optional[UUID], FK → businesses.id, indexed — linked from `Business.owner_phone` |
| `is_active`     | bool, default true |
| `created_at`    | datetime, default `utcnow` |
| `last_login_at` | Optional[datetime] — updated on each successful verify |

### otp_codes
One-time login codes. The plaintext code is **never stored** — only `code_hash`
(`sha256("<phone>:<code>")`). Codes are single-use and short-lived.

| Column       | Type / notes |
|--------------|--------------|
| `id`         | UUID, PK |
| `phone`      | str, indexed |
| `code_hash`  | str — `sha256` of phone+code |
| `expires_at` | datetime — `OTP_EXPIRY_MINUTES` after creation |
| `consumed`   | bool, default false — flipped on successful verify |
| `attempts`   | int, default 0 — ≥5 wrong tries invalidates the code |
| `created_at` | datetime, default `utcnow` |

### auth_sessions
Server-side bearer tokens (opaque, revocable). Resolved to a `User` on each
authenticated request by `get_user_by_token`.

| Column       | Type / notes |
|--------------|--------------|
| `id`         | UUID, PK |
| `user_id`    | UUID, FK → users.id, indexed |
| `token`      | str, **unique**, indexed, default `secrets.token_urlsafe(32)` |
| `expires_at` | datetime — `TOKEN_EXPIRY_DAYS` after creation |
| `created_at` | datetime, default `utcnow` |

CRUD for all three lives in `crud/auth.py`; SMS delivery in `services/sms_service.py`.

### faq_entries
Owner-defined question/answer pairs — the agent's source of truth. Injected into the
system prompt; CRUD in `crud/faq.py`.

| Column        | Type / notes |
|---------------|--------------|
| `id`          | UUID, PK |
| `business_id` | UUID, FK → businesses.id, indexed |
| `question`    | Text |
| `answer`      | Text |
| `created_at`  | datetime, default `utcnow` |

### escalations
A customer question the agent couldn't answer from the business's knowledge. Created
when the LLM emits the `[NEED_HUMAN]` marker (see `ai_service` / `business_service`);
the owner is SMSed and can answer it from `/me/escalations`. CRUD in `crud/escalation.py`.

| Column            | Type / notes |
|-------------------|--------------|
| `id`              | UUID, PK |
| `business_id`     | UUID, FK → businesses.id, indexed |
| `conversation_id` | Optional[UUID], FK → conversations.id, indexed |
| `question`        | Text — the customer's unanswered question |
| `status`          | `EscalationStatus` enum (via `_enum_column`), default `pending`, server_default `pending` |
| `answer`          | Optional[Text] — the owner's answer |
| `created_at`      | datetime, default `utcnow` |
| `answered_at`     | Optional[datetime] |

## Migrations

- `0001_initial.py` — creates the four tables; enum types `businesstype`, `messagerole`
  are created implicitly by `create_table`.
- `0002_business_enhancements.py` — adds `api_key`, `welcome_message`, `max_tokens`,
  `response_style` to businesses; backfills `api_key` for existing rows; adds unique
  constraint + index on `api_key`. Note it **explicitly creates** the `responsestyle`
  PG type before `add_column` (with `checkfirst=True`) and uses `create_type=False` on
  the column — because `add_column` does not auto-create enum types.
- `0003_phone_auth.py` — adds `owner_phone` to businesses; creates `users`,
  `otp_codes`, `auth_sessions` for phone/OTP login. No enum columns, so no PG-type
  juggling. Note: because startup `create_all` may have already created these tables
  on a dev DB (it creates missing tables but never alters existing ones), run
  `alembic upgrade head` on a DB where they don't yet exist — or drop the auto-created
  copies first so the migration owns them and `owner_phone` actually gets added.
- `0004_faq_and_escalations.py` — creates `faq_entries` and `escalations`. Adds an enum
  **column** (`status`), so it follows the `0002` pattern: creates the `escalationstatus`
  PG type with `checkfirst=True` before the table, and uses `create_type=False` on the
  column. Same `create_all` caveat as `0003` applies (on a dev DB where a `--reload`
  server already ran `create_all`, the type/tables exist — `alembic stamp 0004` rather
  than fighting the race; the migration SQL itself is correct for a clean DB).

### Writing a new migration that adds an enum column
```python
from sqlalchemy.dialects import postgresql

my_enum = postgresql.ENUM("a", "b", "c", name="myenum")

def upgrade():
    my_enum.create(op.get_bind(), checkfirst=True)
    op.add_column("t", sa.Column("col",
        sa.Enum("a", "b", "c", name="myenum", create_type=False), nullable=False))

def downgrade():
    op.drop_column("t", "col")
    op.execute("DROP TYPE IF EXISTS myenum")
```

## Connection / session

- `DATABASE_URL` must use the async driver: `postgresql+asyncpg://user:pass@host:port/db`.
  Do **not** append `?schema=public` — asyncpg rejects unknown query params.
- `database.py` imports `AsyncSession` from `sqlmodel.ext.asyncio.session` so CRUD can
  call `db.exec(select(...))`. Results: `.first()`, `.all()`, `.one()` (for scalar counts).
