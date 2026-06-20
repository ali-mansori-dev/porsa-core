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
from app.crud.usage import record_token_usage
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


def _system_message(content: str) -> dict:
    """Build the system message, marking it for provider-side prompt caching when
    enabled. The array-of-blocks form with `cache_control` is the OpenRouter/
    Anthropic convention; providers that don't support caching ignore it."""
    if settings.enable_prompt_caching:
        return {
            "role": "system",
            "content": [
                {
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
        }
    return {"role": "system", "content": content}


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

    # The system prompt is rebuilt from the business profile + FAQ on every turn
    # (so edits take effect immediately) and is the stable, cacheable prefix.
    system_prompt = get_system_prompt(business, details, faq)
    messages: list[dict] = [_system_message(system_prompt)]

    if not history:
        # First turn: persist the system prompt for the record and greet the user.
        await save_message(db, conversation.id, MessageRole.SYSTEM, system_prompt)
        if business.welcome_message:
            messages.append({"role": "assistant", "content": business.welcome_message})
            await save_message(db, conversation.id, MessageRole.ASSISTANT, business.welcome_message)
    else:
        # Resend only the most recent dialog turns. The system prompt is supplied
        # fresh above, so stored SYSTEM rows are skipped to avoid duplication.
        dialog = [m for m in history if m.role != MessageRole.SYSTEM]
        recent = dialog[-settings.history_window:] if settings.history_window > 0 else dialog
        messages += [{"role": m.role.value, "content": m.content} for m in recent]

    messages.append({"role": "user", "content": message})
    await save_message(db, conversation.id, MessageRole.USER, message)

    response = await client.chat.completions.create(
        model=settings.ai_model,
        messages=messages,
        max_tokens=business.max_tokens,
    )

    await _record_usage(db, response, business_id, conversation.id)

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


async def _record_usage(db, response, business_id, conversation_id) -> None:
    """Log and persist the token usage OpenRouter returns. Best-effort: the usage
    object's shape varies by provider, and a bookkeeping failure must never break
    the customer's chat."""
    try:
        usage = getattr(response, "usage", None)
        if usage is None:
            logger.warning("No usage returned for business %s", business_id)
            return

        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        total_tokens = getattr(usage, "total_tokens", 0) or 0

        # Cached-prompt tokens, when the provider reports them (OpenAI-style).
        cached_tokens = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached_tokens = getattr(details, "cached_tokens", 0) or 0

        logger.info(
            "LLM usage business=%s model=%s prompt=%s completion=%s total=%s cached=%s",
            business_id, settings.ai_model, prompt_tokens, completion_tokens,
            total_tokens, cached_tokens,
        )

        await record_token_usage(
            db,
            business_id=business_id,
            conversation_id=conversation_id,
            model=settings.ai_model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
        )
    except Exception:  # noqa: BLE001 — usage logging must not break chat
        logger.exception("Failed to record token usage for business %s", business_id)


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
