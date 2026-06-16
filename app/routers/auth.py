"""Phone-number login via OTP.

Flow: ``POST /auth/request-otp`` → SMS code → ``POST /auth/verify-otp`` → bearer
token. Authenticated calls send ``Authorization: Bearer <token>``; the token
resolves to the user and, from there, to the business they manage."""

import re
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud.auth import (
    count_recent_otps,
    create_otp,
    create_session,
    delete_session,
    generate_code,
    get_or_create_user,
    verify_otp,
)
from app.database import get_db
from app.dependencies import get_current_user
from app.limiter import limiter
from app.models import User
from app.services.sms_service import send_otp

router = APIRouter(prefix="/auth", tags=["auth"])

# Persian/Arabic-Indic digits → ASCII, so "۰۹۱۲" normalizes like "0912".
_DIGIT_MAP = {ord(c): str(i % 10) for i, c in enumerate("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩")}


def normalize_phone(raw: str) -> str:
    phone = raw.translate(_DIGIT_MAP)
    phone = re.sub(r"[\s\-()]", "", phone)
    if not re.fullmatch(r"\+?\d{10,15}", phone):
        raise HTTPException(status_code=422, detail="شماره تلفن نامعتبر است")
    return phone


class RequestOtpBody(BaseModel):
    phone: str


class VerifyOtpBody(BaseModel):
    phone: str
    code: str


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_at: datetime
    business_id: str | None
    business_name: str | None


@router.post("/request-otp")
@limiter.limit("5/minute")
async def request_otp(request: Request, body: RequestOtpBody, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone(body.phone)

    since = datetime.utcnow() - timedelta(hours=1)
    if await count_recent_otps(db, phone, since) >= settings.otp_max_per_hour:
        raise HTTPException(status_code=429, detail="تعداد درخواست‌ها زیاد است؛ بعداً تلاش کنید")

    code = generate_code()
    await create_otp(db, phone, code)
    try:
        await send_otp(phone, code)
    except Exception:  # noqa: BLE001 — don't leak provider internals to the client
        raise HTTPException(status_code=502, detail="ارسال پیامک ناموفق بود")

    resp = {"detail": "کد ورود ارسال شد", "expires_in": settings.otp_expiry_minutes * 60}
    # In dev (no real SMS), surface the code so the flow is testable.
    if settings.sms_provider.lower() == "log" or settings.debug:
        resp["dev_code"] = code
    return resp


@router.post("/verify-otp", response_model=TokenResponse)
async def verify_otp_endpoint(body: VerifyOtpBody, db: AsyncSession = Depends(get_db)):
    phone = normalize_phone(body.phone)

    if not await verify_otp(db, phone, body.code.strip()):
        raise HTTPException(status_code=401, detail="کد نامعتبر یا منقضی شده است")

    user = await get_or_create_user(db, phone)
    session = await create_session(db, user)

    business_name = None
    if user.business_id is not None:
        from app.crud.business import get_business

        business = await get_business(db, user.business_id)
        business_name = business.name if business else None

    return TokenResponse(
        token=session.token,
        expires_at=session.expires_at,
        business_id=str(user.business_id) if user.business_id else None,
        business_name=business_name,
    )


@router.get("/me")
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    business = None
    if user.business_id is not None:
        from app.crud.business import get_business

        b = await get_business(db, user.business_id)
        if b:
            business = {"id": str(b.id), "name": b.name, "type": b.type}

    return {
        "id": str(user.id),
        "phone": user.phone,
        "last_login_at": user.last_login_at,
        "business": business,
    }


@router.post("/logout", status_code=204)
async def logout(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    # Revoke whatever token authenticated this request.
    _scheme, _, token = authorization.partition(" ")
    if token.strip():
        await delete_session(db, token.strip())
