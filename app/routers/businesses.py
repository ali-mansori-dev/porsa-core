import uuid
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.business import (
    create_business,
    delete_business,
    get_all_businesses,
    get_business,
    get_business_details,
    regenerate_api_key,
    update_business,
)
from app.database import get_db
from app.dependencies import require_admin
from app.models import BusinessType, ResponseStyle

router = APIRouter(prefix="/businesses", tags=["businesses"], dependencies=[Depends(require_admin)])


class BusinessDetailItem(BaseModel):
    key: str
    value: str


class BusinessCreate(BaseModel):
    name: str
    type: BusinessType
    field: str
    contact: str
    working_hours: str
    owner_phone: Optional[str] = None
    welcome_message: Optional[str] = None
    max_tokens: int = 1000
    response_style: ResponseStyle = ResponseStyle.FRIENDLY
    details: dict[str, str] = {}


class BusinessUpdate(BaseModel):
    name: Optional[str] = None
    field: Optional[str] = None
    contact: Optional[str] = None
    working_hours: Optional[str] = None
    owner_phone: Optional[str] = None
    welcome_message: Optional[str] = None
    max_tokens: Optional[int] = None
    response_style: Optional[ResponseStyle] = None
    details: Optional[dict[str, str]] = None


class BusinessResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: BusinessType
    field: str
    contact: str
    working_hours: str
    is_active: bool
    owner_phone: Optional[str]
    welcome_message: Optional[str]
    max_tokens: int
    response_style: ResponseStyle
    api_key: str
    details: dict[str, str] = {}


@router.get("/", response_model=list[BusinessResponse])
async def list_businesses(
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_db),
):
    businesses = await get_all_businesses(db, skip=skip, limit=limit)
    result = []
    for b in businesses:
        details = await get_business_details(db, b.id)
        result.append(BusinessResponse(
            id=b.id,
            name=b.name,
            type=b.type,
            field=b.field,
            contact=b.contact,
            working_hours=b.working_hours,
            is_active=b.is_active,
            owner_phone=b.owner_phone,
            welcome_message=b.welcome_message,
            max_tokens=b.max_tokens,
            response_style=b.response_style,
            api_key=b.api_key,
            details=details,
        ))
    return result


@router.post("/", response_model=BusinessResponse, status_code=201)
async def create_new_business(body: BusinessCreate, db: AsyncSession = Depends(get_db)):
    data = body.model_dump()
    business = await create_business(db, data)
    details = await get_business_details(db, business.id)
    return BusinessResponse(
        id=business.id,
        name=business.name,
        type=business.type,
        field=business.field,
        contact=business.contact,
        working_hours=business.working_hours,
        is_active=business.is_active,
        owner_phone=business.owner_phone,
        welcome_message=business.welcome_message,
        max_tokens=business.max_tokens,
        response_style=business.response_style,
        api_key=business.api_key,
        details=details,
    )


@router.get("/{business_id}", response_model=BusinessResponse)
async def get_single_business(business_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    business = await get_business(db, business_id)
    if not business:
        raise HTTPException(status_code=404, detail="کسب‌وکار یافت نشد")
    details = await get_business_details(db, business_id)
    return BusinessResponse(
        id=business.id,
        name=business.name,
        type=business.type,
        field=business.field,
        contact=business.contact,
        working_hours=business.working_hours,
        is_active=business.is_active,
        owner_phone=business.owner_phone,
        welcome_message=business.welcome_message,
        max_tokens=business.max_tokens,
        response_style=business.response_style,
        api_key=business.api_key,
        details=details,
    )


@router.patch("/{business_id}", response_model=BusinessResponse)
async def update_existing_business(
    business_id: uuid.UUID, body: BusinessUpdate, db: AsyncSession = Depends(get_db)
):
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    business = await update_business(db, business_id, data)
    if not business:
        raise HTTPException(status_code=404, detail="کسب‌وکار یافت نشد")
    details = await get_business_details(db, business_id)
    return BusinessResponse(
        id=business.id,
        name=business.name,
        type=business.type,
        field=business.field,
        contact=business.contact,
        working_hours=business.working_hours,
        is_active=business.is_active,
        owner_phone=business.owner_phone,
        welcome_message=business.welcome_message,
        max_tokens=business.max_tokens,
        response_style=business.response_style,
        api_key=business.api_key,
        details=details,
    )


@router.delete("/{business_id}", status_code=204)
async def deactivate_business(business_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    success = await delete_business(db, business_id)
    if not success:
        raise HTTPException(status_code=404, detail="کسب‌وکار یافت نشد")


@router.post("/{business_id}/regenerate-key")
async def regenerate_business_key(business_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    new_key = await regenerate_api_key(db, business_id)
    if new_key is None:
        raise HTTPException(status_code=404, detail="کسب‌وکار یافت نشد")
    return {"api_key": new_key}
