from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Business, User


async def require_admin(x_admin_key: str = Header(default="")):
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="دسترسی غیرمجاز")


async def get_current_user(
    authorization: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the ``Authorization: Bearer <token>`` header to the logged-in user."""
    from app.crud.auth import get_user_by_token

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status_code=401, detail="توکن ارسال نشده است")

    user = await get_user_by_token(db, token.strip())
    if not user:
        raise HTTPException(status_code=401, detail="توکن نامعتبر یا منقضی شده است")
    return user


async def require_user_business(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Business:
    """Resolve the logged-in user to the business they own. 403 if none linked."""
    from app.crud.business import get_business

    if user.business_id is None:
        raise HTTPException(status_code=403, detail="به این کاربر کسب‌وکاری متصل نیست")
    business = await get_business(db, user.business_id)
    if not business:
        raise HTTPException(status_code=403, detail="به این کاربر کسب‌وکاری متصل نیست")
    return business


async def require_business_key(
    x_business_key: str = Header(default=""),
    db: AsyncSession = Depends(get_db),
) -> Business:
    from app.crud.business import get_business_by_api_key

    business = await get_business_by_api_key(db, x_business_key)
    if not business:
        raise HTTPException(status_code=401, detail="کلید API نامعتبر است")
    return business
