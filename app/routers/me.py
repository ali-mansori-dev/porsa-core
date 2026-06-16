"""Owner self-service: a logged-in user (phone/OTP) creates and manages *their own*
business, its FAQ knowledge, and reviews escalated customer questions. All routes are
scoped to the caller's business via their bearer token — no admin key involved."""

import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.business import (
    create_business,
    get_business,
    get_business_details,
    update_business,
)
from app.crud.escalation import (
    answer_escalation,
    get_escalations_by_business,
)
from app.crud.faq import add_faq, delete_faq_entry, get_faq, replace_faq
from app.database import get_db
from app.dependencies import get_current_user, require_user_business
from app.models import Business, BusinessType, EscalationStatus, ResponseStyle, User

router = APIRouter(prefix="/me", tags=["me"])


# ── schemas ───────────────────────────────────────────────────────────────────
class FaqItem(BaseModel):
    question: str
    answer: str


class OnboardingBody(BaseModel):
    """The questions the owner answers to set up their agent."""

    name: str
    type: BusinessType
    field: str
    contact: str
    working_hours: str
    welcome_message: Optional[str] = None
    response_style: ResponseStyle = ResponseStyle.FRIENDLY
    details: dict[str, str] = {}
    faq: list[FaqItem] = []


class BusinessPatch(BaseModel):
    name: Optional[str] = None
    field: Optional[str] = None
    contact: Optional[str] = None
    working_hours: Optional[str] = None
    welcome_message: Optional[str] = None
    response_style: Optional[ResponseStyle] = None
    details: Optional[dict[str, str]] = None


class AnswerBody(BaseModel):
    answer: str


async def _business_payload(db: AsyncSession, business: Business) -> dict:
    details = await get_business_details(db, business.id)
    faq = await get_faq(db, business.id)
    return {
        "id": str(business.id),
        "name": business.name,
        "type": business.type,
        "field": business.field,
        "contact": business.contact,
        "working_hours": business.working_hours,
        "owner_phone": business.owner_phone,
        "welcome_message": business.welcome_message,
        "response_style": business.response_style,
        "api_key": business.api_key,
        "details": details,
        "faq": [{"id": str(e.id), "question": e.question, "answer": e.answer} for e in faq],
    }


# ── business ──────────────────────────────────────────────────────────────────
@router.post("/business", status_code=201)
async def create_my_business(
    body: OnboardingBody,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if user.business_id is not None:
        raise HTTPException(status_code=409, detail="شما قبلاً یک کسب‌وکار ساخته‌اید")

    data = body.model_dump(exclude={"faq"})
    data["owner_phone"] = user.phone  # the agent's escalation destination
    business = await create_business(db, data)

    if body.faq:
        await replace_faq(db, business.id, [f.model_dump() for f in body.faq])

    # Link the user to the business they just created.
    user.business_id = business.id
    await db.commit()

    return await _business_payload(db, business)


@router.get("/business")
async def get_my_business(
    business: Business = Depends(require_user_business), db: AsyncSession = Depends(get_db)
):
    return await _business_payload(db, business)


@router.patch("/business")
async def update_my_business(
    body: BusinessPatch,
    business: Business = Depends(require_user_business),
    db: AsyncSession = Depends(get_db),
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await update_business(db, business.id, data)
    return await _business_payload(db, updated)


# ── FAQ ───────────────────────────────────────────────────────────────────────
@router.get("/business/faq")
async def list_my_faq(
    business: Business = Depends(require_user_business), db: AsyncSession = Depends(get_db)
):
    faq = await get_faq(db, business.id)
    return [{"id": str(e.id), "question": e.question, "answer": e.answer} for e in faq]


@router.put("/business/faq")
async def replace_my_faq(
    items: list[FaqItem],
    business: Business = Depends(require_user_business),
    db: AsyncSession = Depends(get_db),
):
    faq = await replace_faq(db, business.id, [i.model_dump() for i in items])
    return [{"id": str(e.id), "question": e.question, "answer": e.answer} for e in faq]


@router.post("/business/faq", status_code=201)
async def add_my_faq(
    item: FaqItem,
    business: Business = Depends(require_user_business),
    db: AsyncSession = Depends(get_db),
):
    entry = await add_faq(db, business.id, item.question, item.answer)
    return {"id": str(entry.id), "question": entry.question, "answer": entry.answer}


@router.delete("/business/faq/{entry_id}", status_code=204)
async def delete_my_faq(
    entry_id: uuid.UUID,
    business: Business = Depends(require_user_business),
    db: AsyncSession = Depends(get_db),
):
    if not await delete_faq_entry(db, business.id, entry_id):
        raise HTTPException(status_code=404, detail="سوال یافت نشد")


# ── escalations ───────────────────────────────────────────────────────────────
@router.get("/escalations")
async def list_my_escalations(
    status: Optional[EscalationStatus] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    business: Business = Depends(require_user_business),
    db: AsyncSession = Depends(get_db),
):
    items = await get_escalations_by_business(db, business.id, status, skip, limit)
    return [
        {
            "id": str(e.id),
            "question": e.question,
            "status": e.status,
            "answer": e.answer,
            "created_at": e.created_at,
            "answered_at": e.answered_at,
        }
        for e in items
    ]


@router.post("/escalations/{escalation_id}/answer")
async def answer_my_escalation(
    escalation_id: uuid.UUID,
    body: AnswerBody,
    business: Business = Depends(require_user_business),
    db: AsyncSession = Depends(get_db),
):
    escalation = await answer_escalation(db, business.id, escalation_id, body.answer)
    if not escalation:
        raise HTTPException(status_code=404, detail="سوال ارجاع‌شده یافت نشد")
    return {
        "id": str(escalation.id),
        "question": escalation.question,
        "status": escalation.status,
        "answer": escalation.answer,
        "answered_at": escalation.answered_at,
    }
