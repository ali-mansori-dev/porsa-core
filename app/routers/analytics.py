import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.crud.conversation import count_conversations_by_business, count_messages_by_business
from app.database import get_db
from app.dependencies import require_admin
from app.models import Business, Conversation, Message

router = APIRouter(prefix="/analytics", tags=["analytics"], dependencies=[Depends(require_admin)])


@router.get("/overview")
async def platform_overview(db: AsyncSession = Depends(get_db)):
    total_businesses = (await db.exec(select(func.count()).select_from(Business).where(Business.is_active == True))).one()  # noqa: E712
    total_conversations = (await db.exec(select(func.count()).select_from(Conversation))).one()
    total_messages = (await db.exec(select(func.count()).select_from(Message))).one()

    return {
        "total_businesses": total_businesses,
        "total_conversations": total_conversations,
        "total_messages": total_messages,
    }


@router.get("/businesses/{business_id}")
async def business_stats(business_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    total_conversations = await count_conversations_by_business(db, business_id)
    total_messages = await count_messages_by_business(db, business_id)

    user_messages = (
        await db.exec(
            select(func.count())
            .select_from(Message)
            .join(Conversation, Message.conversation_id == Conversation.id)
            .where(Conversation.business_id == business_id, Message.role == "user")
        )
    ).one()

    return {
        "business_id": str(business_id),
        "total_conversations": total_conversations,
        "total_messages": total_messages,
        "user_messages": user_messages,
        "ai_responses": total_messages - user_messages,
    }
