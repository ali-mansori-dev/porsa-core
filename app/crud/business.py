import secrets
import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Business, BusinessDetail


async def get_business(db: AsyncSession, business_id: uuid.UUID) -> Business | None:
    result = await db.exec(
        select(Business).where(Business.id == business_id, Business.is_active == True)  # noqa: E712
    )
    return result.first()


async def get_business_details(db: AsyncSession, business_id: uuid.UUID) -> dict[str, str]:
    result = await db.exec(
        select(BusinessDetail).where(BusinessDetail.business_id == business_id)
    )
    return {row.key: row.value for row in result.all()}


async def get_all_businesses(db: AsyncSession, skip: int = 0, limit: int = 50) -> list[Business]:
    result = await db.exec(
        select(Business).where(Business.is_active == True).offset(skip).limit(limit)  # noqa: E712
    )
    return list(result.all())


async def get_business_by_api_key(db: AsyncSession, api_key: str) -> Business | None:
    result = await db.exec(
        select(Business).where(Business.api_key == api_key, Business.is_active == True)  # noqa: E712
    )
    return result.first()


async def get_business_by_owner_phone(db: AsyncSession, phone: str) -> Business | None:
    result = await db.exec(
        select(Business).where(Business.owner_phone == phone, Business.is_active == True)  # noqa: E712
    )
    return result.first()


async def create_business(db: AsyncSession, data: dict) -> Business:
    details_data: dict[str, str] = data.pop("details", {})
    business = Business(**data)
    db.add(business)
    await db.flush()

    for key, value in details_data.items():
        db.add(BusinessDetail(business_id=business.id, key=key, value=value))

    await db.commit()
    await db.refresh(business)
    return business


async def update_business(db: AsyncSession, business_id: uuid.UUID, data: dict) -> Business | None:
    business = await get_business(db, business_id)
    if not business:
        return None

    details_data: dict[str, str] = data.pop("details", None)
    for key, value in data.items():
        setattr(business, key, value)

    if details_data is not None:
        existing = await db.exec(
            select(BusinessDetail).where(BusinessDetail.business_id == business_id)
        )
        for row in existing.all():
            await db.delete(row)
        for key, value in details_data.items():
            db.add(BusinessDetail(business_id=business_id, key=key, value=value))

    await db.commit()
    await db.refresh(business)
    return business


async def delete_business(db: AsyncSession, business_id: uuid.UUID) -> bool:
    business = await get_business(db, business_id)
    if not business:
        return False
    business.is_active = False
    await db.commit()
    return True


async def regenerate_api_key(db: AsyncSession, business_id: uuid.UUID) -> str | None:
    business = await get_business(db, business_id)
    if not business:
        return None
    new_key = secrets.token_urlsafe(32)
    business.api_key = new_key
    await db.commit()
    return new_key
