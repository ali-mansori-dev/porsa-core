import logging
import uuid

from openai import AsyncOpenAI
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.crud.business import get_business, get_business_details
from app.crud.conversation import (
    get_conversation_history,
    get_or_create_conversation,
    save_message,
)
from app.crud.escalation import create_escalation
from app.crud.faq import get_faq
from app.models import MessageRole
from app.services.business_service import NEED_HUMAN_MARKER, get_system_prompt
from app.services.sms_service import send_message

logger = logging.getLogger(__name__)

# Shown to the customer when their question is escalated to the business owner.
HANDOFF_MESSAGE = (
    "این سوال رو به همکارمون ارجاع دادم تا دقیق جواب بده. "
    "لطفاً کمی صبر کن، به‌زودی پاسخ می‌گیری."
)

client = AsyncOpenAI(
    base_url=settings.ai_base_url,
    api_key=settings.ai_api_key,
    default_headers={
        "HTTP-Referer": "http://localhost:8000",
        "X-Title": "AI Agent Platform",
    },
)


async def chat_with_ai(
    db: AsyncSession, message: str, session_id: str, business_id: uuid.UUID
) -> str:
    business = await get_business(db, business_id)
    if not business:
        return "کسب‌وکار مورد نظر یافت نشد."

    details = await get_business_details(db, business_id)
    faq = await get_faq(db, business_id)
    conversation = await get_or_create_conversation(db, session_id, business_id)
    history = await get_conversation_history(db, session_id, business_id)

    messages: list[dict] = []

    if not history:
        system_prompt = get_system_prompt(business, details, faq)
        messages.append({"role": "system", "content": system_prompt})
        await save_message(db, conversation.id, MessageRole.SYSTEM, system_prompt)

        if business.welcome_message:
            messages.append({"role": "assistant", "content": business.welcome_message})
            await save_message(db, conversation.id, MessageRole.ASSISTANT, business.welcome_message)
    else:
        messages = [{"role": msg.role.value, "content": msg.content} for msg in history]

    messages.append({"role": "user", "content": message})
    await save_message(db, conversation.id, MessageRole.USER, message)

    response = await client.chat.completions.create(
        model=settings.ai_model,
        messages=messages,
        max_tokens=business.max_tokens,
    )

    assistant_message = response.choices[0].message.content or ""

    # The agent signals it can't answer from the business's knowledge. Escalate to
    # the owner instead of saving/returning the raw marker.
    if NEED_HUMAN_MARKER in assistant_message:
        await create_escalation(db, business_id, message, conversation.id)
        await _notify_owner(business, message)
        await save_message(db, conversation.id, MessageRole.ASSISTANT, HANDOFF_MESSAGE)
        return HANDOFF_MESSAGE

    await save_message(db, conversation.id, MessageRole.ASSISTANT, assistant_message)
    return assistant_message


async def _notify_owner(business, question: str) -> None:
    """SMS the business owner that a customer question needs their answer. Failure
    to send must not break the customer's chat — the escalation is already stored."""
    if not business.owner_phone:
        logger.warning("Business %s has no owner_phone; escalation not SMSed", business.id)
        return
    text = f"سوال جدید از مشتری در {business.name}:\n{question}\nبرای پاسخ وارد پنل شوید."
    try:
        await send_message(business.owner_phone, text)
    except Exception:  # noqa: BLE001 — escalation is persisted regardless
        logger.exception("Failed to SMS owner for business %s", business.id)
