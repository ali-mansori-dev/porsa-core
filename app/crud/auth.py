"""CRUD for phone-number / OTP authentication: one-time codes, users, and
server-side bearer tokens (auth sessions)."""

import hashlib
import secrets
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.config import settings
from app.crud.business import get_business_by_owner_phone
from app.models import AuthSession, OtpCode, User


def _hash_code(phone: str, code: str) -> str:
    """Hash an OTP bound to its phone, so a leaked DB can't reveal live codes."""
    return hashlib.sha256(f"{phone}:{code}".encode("utf-8")).hexdigest()


def generate_code() -> str:
    """Generate a numeric OTP of the configured length (e.g. ``04821``)."""
    upper = 10 ** settings.otp_length
    return str(secrets.randbelow(upper)).zfill(settings.otp_length)


async def count_recent_otps(db: AsyncSession, phone: str, since: datetime) -> int:
    result = await db.exec(
        select(OtpCode).where(OtpCode.phone == phone, OtpCode.created_at >= since)
    )
    return len(result.all())


async def create_otp(db: AsyncSession, phone: str, code: str) -> OtpCode:
    otp = OtpCode(
        phone=phone,
        code_hash=_hash_code(phone, code),
        expires_at=datetime.utcnow() + timedelta(minutes=settings.otp_expiry_minutes),
    )
    db.add(otp)
    await db.commit()
    await db.refresh(otp)
    return otp


async def verify_otp(db: AsyncSession, phone: str, code: str) -> bool:
    """Validate the latest live code for a phone and consume it on success.

    Returns False if there is no active code, it has expired, too many wrong
    attempts were made, or the code does not match."""
    result = await db.exec(
        select(OtpCode)
        .where(OtpCode.phone == phone, OtpCode.consumed == False)  # noqa: E712
        .order_by(OtpCode.created_at.desc())
    )
    otp = result.first()
    if not otp:
        return False
    if otp.expires_at < datetime.utcnow() or otp.attempts >= 5:
        return False

    if otp.code_hash != _hash_code(phone, code):
        otp.attempts += 1
        await db.commit()
        return False

    otp.consumed = True
    await db.commit()
    return True


async def get_or_create_user(db: AsyncSession, phone: str) -> User:
    """Fetch the user for a phone, creating one on first login. New users are
    linked to the business whose ``owner_phone`` matches."""
    result = await db.exec(select(User).where(User.phone == phone))
    user = result.first()
    if user is None:
        business = await get_business_by_owner_phone(db, phone)
        user = User(phone=phone, business_id=business.id if business else None)
        db.add(user)

    # Late-link: business may have been created after the user first logged in.
    if user.business_id is None:
        business = await get_business_by_owner_phone(db, phone)
        if business:
            user.business_id = business.id

    user.last_login_at = datetime.utcnow()
    await db.commit()
    await db.refresh(user)
    return user


async def create_session(db: AsyncSession, user: User) -> AuthSession:
    session = AuthSession(
        user_id=user.id,
        expires_at=datetime.utcnow() + timedelta(days=settings.token_expiry_days),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return session


async def get_user_by_token(db: AsyncSession, token: str) -> User | None:
    result = await db.exec(select(AuthSession).where(AuthSession.token == token))
    session = result.first()
    if not session or session.expires_at < datetime.utcnow():
        return None
    user_result = await db.exec(
        select(User).where(User.id == session.user_id, User.is_active == True)  # noqa: E712
    )
    return user_result.first()


async def delete_session(db: AsyncSession, token: str) -> bool:
    result = await db.exec(select(AuthSession).where(AuthSession.token == token))
    session = result.first()
    if not session:
        return False
    await db.delete(session)
    await db.commit()
    return True
