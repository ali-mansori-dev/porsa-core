import uuid
from typing import Optional

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import TokenUsage


async def record_token_usage(
    db: AsyncSession,
    business_id: uuid.UUID,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cached_tokens: int = 0,
    conversation_id: Optional[uuid.UUID] = None,
) -> TokenUsage:
    usage = TokenUsage(
        business_id=business_id,
        conversation_id=conversation_id,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_tokens=cached_tokens,
    )
    db.add(usage)
    await db.commit()
    return usage


async def get_usage_totals_by_business(
    db: AsyncSession, business_id: uuid.UUID
) -> dict[str, int]:
    """Aggregate token usage for one business across all calls."""
    row = (
        await db.exec(
            select(
                func.coalesce(func.sum(TokenUsage.prompt_tokens), 0),
                func.coalesce(func.sum(TokenUsage.completion_tokens), 0),
                func.coalesce(func.sum(TokenUsage.total_tokens), 0),
                func.coalesce(func.sum(TokenUsage.cached_tokens), 0),
                func.count(),
            ).where(TokenUsage.business_id == business_id)
        )
    ).one()
    prompt, completion, total, cached, calls = row
    return {
        "calls": calls,
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cached_tokens": cached,
    }
