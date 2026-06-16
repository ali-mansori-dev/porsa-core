"""CRUD for escalations — customer questions the agent couldn't answer."""

import uuid
from datetime import datetime

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Escalation, EscalationStatus


async def create_escalation(
    db: AsyncSession,
    business_id: uuid.UUID,
    question: str,
    conversation_id: uuid.UUID | None = None,
) -> Escalation:
    escalation = Escalation(
        business_id=business_id,
        conversation_id=conversation_id,
        question=question,
    )
    db.add(escalation)
    await db.commit()
    await db.refresh(escalation)
    return escalation


async def get_escalations_by_business(
    db: AsyncSession,
    business_id: uuid.UUID,
    status: EscalationStatus | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[Escalation]:
    query = select(Escalation).where(Escalation.business_id == business_id)
    if status is not None:
        query = query.where(Escalation.status == status)
    query = query.order_by(Escalation.created_at.desc()).offset(skip).limit(limit)
    result = await db.exec(query)
    return list(result.all())


async def count_escalations_by_business(
    db: AsyncSession, business_id: uuid.UUID, status: EscalationStatus | None = None
) -> int:
    query = select(func.count()).select_from(Escalation).where(
        Escalation.business_id == business_id
    )
    if status is not None:
        query = query.where(Escalation.status == status)
    result = await db.exec(query)
    return result.one()


async def answer_escalation(
    db: AsyncSession, business_id: uuid.UUID, escalation_id: uuid.UUID, answer: str
) -> Escalation | None:
    result = await db.exec(
        select(Escalation).where(
            Escalation.id == escalation_id, Escalation.business_id == business_id
        )
    )
    escalation = result.first()
    if not escalation:
        return None
    escalation.answer = answer
    escalation.status = EscalationStatus.ANSWERED
    escalation.answered_at = datetime.utcnow()
    await db.commit()
    await db.refresh(escalation)
    return escalation
