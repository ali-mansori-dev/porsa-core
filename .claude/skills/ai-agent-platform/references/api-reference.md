# API reference

Base URL in development: `http://127.0.0.1:8000`. Interactive docs at `/docs`.

## Auth

- **Public endpoints** — no auth.
- **Admin endpoints** — header `X-Admin-Key: <ADMIN_API_KEY>` (value from `.env`).
  Enforced via `require_admin` as a router-level dependency. Wrong/missing key → 401.
- **Business key** — `require_business_key` resolves header `X-Business-Key` to a
  `Business` via `get_business_by_api_key`. Provided for customer-facing/widget auth;
  wire it into routes that should be scoped to a single tenant.
- **User bearer token (phone/OTP login)** — header `Authorization: Bearer <token>`.
  The token is an opaque server-side session (`auth_sessions` table) issued by
  `POST /auth/verify-otp`. `get_current_user` resolves it to a `User`;
  `require_user_business` goes one step further to the `Business` the user owns
  (linked via `Business.owner_phone`). Use these deps for owner-facing routes that
  should be scoped to "the business of the logged-in user" rather than an admin key.

## Auth: /auth  (phone-number login via OTP)

Lets a **business owner** log in with their phone number and receive a bearer token;
the token identifies their business on subsequent calls. SMS delivery is pluggable
(`SMS_PROVIDER`): `log` (dev — code printed to the app log) or `kavenegar`.

### POST /auth/request-otp
Generates a one-time code, stores its **hash** (`otp_codes`), and sends it by SMS.
**Rate-limited: 5/minute per IP** (slowapi) **and** `OTP_MAX_PER_HOUR` per phone (429).
Phone input is normalized (Persian/Arabic digits → ASCII, separators stripped); invalid
shape → 422.
```json
{ "phone": "09120000001" }
```
Response: `{ "detail": "...", "expires_in": 120 }`. In dev (`SMS_PROVIDER=log` or
`DEBUG=true`) the response also includes `"dev_code": "<code>"` so the flow is testable.

### POST /auth/verify-otp
Validates the latest live code for the phone (single-use, expires after
`OTP_EXPIRY_MINUTES`, ≥5 wrong attempts invalidates it), creates the `User` on first
login, links it to the business whose `owner_phone` matches, and issues a token.
```json
{ "phone": "09120000001", "code": "29111" }
```
Response:
```json
{ "token": "<opaque>", "token_type": "bearer",
  "expires_at": "ISO", "business_id": "<uuid|null>", "business_name": "<str|null>" }
```
401 if the code is wrong/expired/already used.

### GET /auth/me  (Bearer)
Returns the logged-in user and their business:
```json
{ "id":"<uuid>", "phone":"...", "last_login_at":"ISO",
  "business": {"id":"<uuid>","name":"...","type":"shop"} }   // business null if unlinked
```

### POST /auth/logout  (Bearer)
Revokes the current token (deletes its `auth_sessions` row). 204.

## Health / public

### GET /
Returns `{"status": "ok", "app": "<APP_NAME>"}`.

### GET /health
Returns `{"status": "ok"}`.

### GET /chat/businesses
Public list for a chooser UI.
Response: `[{"id": "<uuid>", "name": "...", "type": "shop"}, ...]`

### POST /chat/
The customer chat endpoint. **Rate-limited: 20 requests/minute per IP** (slowapi).

Request body:
```json
{
  "message": "سلام، گوشی میخوام",
  "session_id": "optional-string",     // omitted → server generates a UUID
  "business_id": "<uuid>"
}
```
Response:
```json
{
  "response": "<assistant reply in Persian>",
  "session_id": "<same or newly generated>",
  "business_id": "<uuid>"
}
```
404 if the business doesn't exist or is inactive. The handler signature is
`chat(request: Request, body: ChatRequest, ...)` — the `Request` arg is required by
slowapi's limiter.

**Escalation (human handoff):** the agent answers only from the business profile +
its `faq_entries`. When a question isn't covered, the LLM emits the `[NEED_HUMAN]`
marker; `ai_service` then creates an `escalations` row, SMSes the owner (`owner_phone`),
and returns a Persian handoff message to the customer instead of the marker. The owner
reviews/answers via `/me/escalations`.

## Owner self-service: /me  (Authorization: Bearer)

The intended path for a business owner to set up and run their agent — scoped to the
logged-in user's own business (no admin key). Onboarding = answering the create body.

### POST /me/business
Create the caller's business (one per user; 409 if they already have one). `owner_phone`
is set automatically to the user's phone, and the user is linked to the new business.
```json
{ "name":"...", "type":"shop|education|service", "field":"...", "contact":"...",
  "working_hours":"...", "welcome_message":"optional",
  "response_style":"friendly|formal|brief",
  "details": {"products":"..."},
  "faq": [ {"question":"...","answer":"..."} ] }
```
Returns 201 with the business (incl. `api_key`, `details`, `faq`).

### GET /me/business
The caller's business + `details` + `faq`. 403 if the user has no business.

### PATCH /me/business
Partial update of the caller's business (`name`, `field`, `contact`, `working_hours`,
`welcome_message`, `response_style`, `details`).

### GET/PUT/POST /me/business/faq, DELETE /me/business/faq/{entry_id}
Manage the FAQ knowledge base. `PUT` replaces the whole set with a `[{question,answer}]`
list; `POST` adds one; `DELETE` removes one (404 if not the caller's).

### GET /me/escalations?status=pending&skip=0&limit=20
List escalated questions for the caller's business (filter by `pending|answered|closed`).

### POST /me/escalations/{escalation_id}/answer
Owner answers an escalation. Body `{"answer":"..."}`; sets status `answered` +
`answered_at`. 404 if not the caller's escalation.

## Admin: /businesses  (X-Admin-Key)

### GET /businesses/?skip=0&limit=20
List businesses (pagination via `skip`, `limit` 1–100). Each item includes the full
record **plus** its `details` dict and `api_key`.

### POST /businesses/
Create. Body:
```json
{
  "name": "...", "type": "shop|education|service",
  "field": "...", "contact": "...", "working_hours": "...",
  "owner_phone": "optional — links the owner's OTP login to this business",
  "welcome_message": "optional", "max_tokens": 1000,
  "response_style": "friendly|formal|brief",
  "details": {"products": "...", "return_policy": "..."}
}
```
Returns 201 with the created business (including generated `api_key`). **Note:** the
intended creation path is now owner self-service (`POST /me/business`); this admin route
remains for platform-side management/oversight.

### GET /businesses/{id}
Single business + details. 404 if not found/inactive.

### PATCH /businesses/{id}
Partial update. Any subset of: `name`, `field`, `contact`, `working_hours`,
`owner_phone`, `welcome_message`, `max_tokens`, `response_style`, `details`. Only non-null fields are
applied; passing `details` **replaces** all detail rows for that business. 404 if missing.

### DELETE /businesses/{id}
Soft delete (sets `is_active = false`). 204 on success, 404 if missing.

### POST /businesses/{id}/regenerate-key
Issues a new `api_key`. Returns `{"api_key": "<new>"}`. 404 if missing.

## Admin: /conversations  (X-Admin-Key)

### GET /conversations/business/{business_id}?skip=0&limit=20
Paginated conversations for a business. Response:
```json
{ "total": 42, "skip": 0, "limit": 20,
  "items": [ {"id":"...","session_id":"...","business_id":"...",
              "created_at":"ISO","message_count": 7}, ... ] }
```

### GET /conversations/{id}
One conversation with its full ordered message list:
```json
{ "id":"...", "session_id":"...", "business_id":"...", "created_at":"ISO",
  "message_count": 7,
  "messages": [ {"id":"...","role":"user","content":"...","created_at":"ISO"}, ... ] }
```
404 if not found.

### DELETE /conversations/{id}
Deletes the conversation and its messages (hard delete). 204 / 404.

## Admin: /analytics  (X-Admin-Key)

### GET /analytics/overview
```json
{ "total_businesses": 3, "total_conversations": 120, "total_messages": 980 }
```
`total_businesses` counts only active businesses.

### GET /analytics/businesses/{business_id}
```json
{ "business_id":"<uuid>", "total_conversations": 10,
  "total_messages": 84, "user_messages": 40, "ai_responses": 44 }
```
`ai_responses` = total − user (so it includes the persisted system message).
