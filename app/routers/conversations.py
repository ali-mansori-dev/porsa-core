import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.conversation import (
    count_conversations_by_business,
    delete_conversation,
    get_conversation_by_id,
    get_conversations_by_business,
    get_messages_by_conversation,
)
from app.database import get_db
from app.dependencies import require_admin
from app.models import MessageRole

router = APIRouter(prefix="/conversations", tags=["conversations"], dependencies=[Depends(require_admin)])


class MessageOut(BaseModel):
    id: uuid.UUID
    role: MessageRole
    content: str
    created_at: str

    @classmethod
    def from_model(cls, msg):
        return cls(
            id=msg.id,
            role=msg.role,
            content=msg.content,
            created_at=msg.created_at.isoformat(),
        )


class ConversationOut(BaseModel):
    id: uuid.UUID
    session_id: str
    business_id: uuid.UUID
    created_at: str
    message_count: int = 0

    @classmethod
    def from_model(cls, conv, message_count: int = 0):
        return cls(
            id=conv.id,
            session_id=conv.session_id,
            business_id=conv.business_id,
            created_at=conv.created_at.isoformat(),
            message_count=message_count,
        )


class ConversationWithMessages(ConversationOut):
    messages: list[MessageOut]


@router.get("/business/{business_id}")
async def list_business_conversations(
    business_id: uuid.UUID,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
):
    conversations = await get_conversations_by_business(db, business_id, skip=skip, limit=limit)
    total = await count_conversations_by_business(db, business_id)

    items = []
    for conv in conversations:
        messages = await get_messages_by_conversation(db, conv.id)
        items.append(ConversationOut.from_model(conv, message_count=len(messages)))

    return {"total": total, "skip": skip, "limit": limit, "items": items}


@router.get("/{conversation_id}", response_model=ConversationWithMessages)
async def get_conversation_detail(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    conversation = await get_conversation_by_id(db, conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="مکالمه یافت نشد")

    messages = await get_messages_by_conversation(db, conversation_id)
    return ConversationWithMessages(
        id=conversation.id,
        session_id=conversation.session_id,
        business_id=conversation.business_id,
        created_at=conversation.created_at.isoformat(),
        message_count=len(messages),
        messages=[MessageOut.from_model(m) for m in messages],
    )


@router.delete("/{conversation_id}", status_code=204)
async def remove_conversation(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    success = await delete_conversation(db, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="مکالمه یافت نشد")
