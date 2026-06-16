import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.business import get_all_businesses, get_business
from app.database import get_db
from app.limiter import limiter
from app.services.ai_service import chat_with_ai

router = APIRouter(prefix="/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    business_id: uuid.UUID


class ChatResponse(BaseModel):
    response: str
    session_id: str
    business_id: uuid.UUID


@router.post("/", response_model=ChatResponse)
@limiter.limit("20/minute")
async def chat(request: Request, body: ChatRequest, db: AsyncSession = Depends(get_db)):
    business = await get_business(db, body.business_id)
    if not business:
        raise HTTPException(status_code=404, detail="کسب‌وکار یافت نشد")

    session_id = body.session_id or str(uuid.uuid4())
    result = await chat_with_ai(db, body.message, session_id, body.business_id)

    return ChatResponse(
        response=result,
        session_id=session_id,
        business_id=body.business_id,
    )


@router.get("/businesses")
async def get_businesses(db: AsyncSession = Depends(get_db)):
    businesses = await get_all_businesses(db)
    return [
        {"id": str(b.id), "name": b.name, "type": b.type}
        for b in businesses
    ]
