"""CRUD for owner-defined FAQ entries (question/answer pairs)."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import FaqEntry


async def get_faq(db: AsyncSession, business_id: uuid.UUID) -> list[FaqEntry]:
    result = await db.exec(
        select(FaqEntry)
        .where(FaqEntry.business_id == business_id)
        .order_by(FaqEntry.created_at)
    )
    return list(result.all())


async def add_faq(db: AsyncSession, business_id: uuid.UUID, question: str, answer: str) -> FaqEntry:
    entry = FaqEntry(business_id=business_id, question=question, answer=answer)
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def replace_faq(
    db: AsyncSession, business_id: uuid.UUID, items: list[dict]
) -> list[FaqEntry]:
    """Replace the whole FAQ set for a business with ``items`` (``{question, answer}``)."""
    existing = await db.exec(select(FaqEntry).where(FaqEntry.business_id == business_id))
    for row in existing.all():
        await db.delete(row)
    for item in items:
        db.add(FaqEntry(business_id=business_id, question=item["question"], answer=item["answer"]))
    await db.commit()
    return await get_faq(db, business_id)


async def delete_faq_entry(db: AsyncSession, business_id: uuid.UUID, entry_id: uuid.UUID) -> bool:
    result = await db.exec(
        select(FaqEntry).where(FaqEntry.id == entry_id, FaqEntry.business_id == business_id)
    )
    entry = result.first()
    if not entry:
        return False
    await db.delete(entry)
    await db.commit()
    return True
