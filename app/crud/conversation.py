import uuid

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Conversation, Message, MessageRole


async def get_or_create_conversation(
    db: AsyncSession, session_id: str, business_id: uuid.UUID
) -> Conversation:
    result = await db.exec(
        select(Conversation).where(
            Conversation.session_id == session_id,
            Conversation.business_id == business_id,
        )
    )
    conversation = result.first()
    if conversation is None:
        conversation = Conversation(session_id=session_id, business_id=business_id)
        db.add(conversation)
        await db.commit()
        await db.refresh(conversation)
    return conversation


async def save_message(
    db: AsyncSession, conversation_id: uuid.UUID, role: MessageRole, content: str
) -> Message:
    message = Message(conversation_id=conversation_id, role=role, content=content)
    db.add(message)
    await db.commit()
    return message


async def get_conversation_history(
    db: AsyncSession, session_id: str, business_id: uuid.UUID
) -> list[Message]:
    result = await db.exec(
        select(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(
            Conversation.session_id == session_id,
            Conversation.business_id == business_id,
        )
        .order_by(Message.created_at)
    )
    return list(result.all())


async def get_conversations_by_business(
    db: AsyncSession, business_id: uuid.UUID, skip: int = 0, limit: int = 20
) -> list[Conversation]:
    result = await db.exec(
        select(Conversation)
        .where(Conversation.business_id == business_id)
        .order_by(Conversation.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return list(result.all())


async def count_conversations_by_business(db: AsyncSession, business_id: uuid.UUID) -> int:
    result = await db.exec(
        select(func.count()).where(Conversation.business_id == business_id)
    )
    return result.one()


async def get_conversation_by_id(db: AsyncSession, conversation_id: uuid.UUID) -> Conversation | None:
    result = await db.exec(select(Conversation).where(Conversation.id == conversation_id))
    return result.first()


async def get_messages_by_conversation(
    db: AsyncSession, conversation_id: uuid.UUID
) -> list[Message]:
    result = await db.exec(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at)
    )
    return list(result.all())


async def count_messages_by_business(db: AsyncSession, business_id: uuid.UUID) -> int:
    result = await db.exec(
        select(func.count())
        .select_from(Message)
        .join(Conversation, Message.conversation_id == Conversation.id)
        .where(Conversation.business_id == business_id)
    )
    return result.one()


async def delete_conversation(db: AsyncSession, conversation_id: uuid.UUID) -> bool:
    conversation = await get_conversation_by_id(db, conversation_id)
    if not conversation:
        return False
    messages = await get_messages_by_conversation(db, conversation_id)
    for msg in messages:
        await db.delete(msg)
    await db.delete(conversation)
    await db.commit()
    return True
