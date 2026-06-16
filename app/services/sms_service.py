"""SMS delivery. Pluggable provider: ``log`` (dev — writes the code to the app
log so you can test without an account) or ``kavenegar`` (a common Iranian
gateway). Selected by ``SMS_PROVIDER`` in ``.env``."""

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def send_otp(phone: str, code: str) -> None:
    """Deliver a one-time login code to ``phone``. Raises on provider failure so
    the caller can surface a 502 instead of silently dropping the code."""
    provider = settings.sms_provider.lower()
    if provider == "kavenegar":
        await _send_kavenegar(phone, code)
    else:
        # Dev fallback: never send a real SMS, just log the code.
        logger.info("[SMS:log] کد ورود برای %s: %s", phone, code)


async def send_message(phone: str, text: str) -> None:
    """Send a plain SMS (e.g. notifying an owner of an escalated question).

    Unlike OTP, never uses the verify/template API. In dev (``log``) the message
    is written to the app log instead of being sent."""
    if settings.sms_provider.lower() != "kavenegar":
        logger.info("[SMS:log] پیام به %s: %s", phone, text)
        return

    if not settings.kavenegar_api_key:
        raise RuntimeError("KAVENEGAR_API_KEY تنظیم نشده است")
    url = f"https://api.kavenegar.com/v1/{settings.kavenegar_api_key}/sms/send.json"
    params = {"receptor": phone, "message": text, "sender": settings.kavenegar_sender}
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
    logger.info("[SMS:kavenegar] پیام به %s ارسال شد", phone)


async def _send_kavenegar(phone: str, code: str) -> None:
    if not settings.kavenegar_api_key:
        raise RuntimeError("KAVENEGAR_API_KEY تنظیم نشده است")

    api_key = settings.kavenegar_api_key
    if settings.kavenegar_otp_template:
        # Verify/lookup API — recommended for OTP in Iran (bypasses spam filters).
        url = f"https://api.kavenegar.com/v1/{api_key}/verify/lookup.json"
        params = {
            "receptor": phone,
            "token": code,
            "template": settings.kavenegar_otp_template,
        }
    else:
        url = f"https://api.kavenegar.com/v1/{api_key}/sms/send.json"
        params = {
            "receptor": phone,
            "message": f"کد ورود شما: {code}",
            "sender": settings.kavenegar_sender,
        }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
    logger.info("[SMS:kavenegar] کد ورود برای %s ارسال شد", phone)
