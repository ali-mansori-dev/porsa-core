from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    ai_base_url: str
    ai_model: str
    ai_api_key: str
    database_url: str
    app_name: str = "AI Agent Platform"
    debug: bool = False
    admin_api_key: str = "change-me-in-production"
    cors_origins: str = "*"

    # Token-cost controls for the LLM call.
    # How many of the most recent dialog messages (user/assistant, excluding the
    # system prompt) to resend on each turn. Older turns are dropped so the prompt
    # doesn't grow unbounded as a conversation gets long.
    history_window: int = 10
    # Mark the (stable) system prompt for provider-side prompt caching. OpenRouter
    # forwards `cache_control` to providers that support it (e.g. Anthropic) and
    # ignores it otherwise, so this is safe to leave on.
    enable_prompt_caching: bool = True

    # Phone-number / OTP authentication
    otp_length: int = 5
    otp_expiry_minutes: int = 2
    otp_max_per_hour: int = 5  # per-phone request cap
    token_expiry_days: int = 30
    # SMS provider: "log" (dev — prints code to the log) or "kavenegar".
    sms_provider: str = "log"
    kavenegar_api_key: str = ""
    kavenegar_sender: str = ""
    # Optional Kavenegar verify/lookup template name. If set, OTP is sent via the
    # verify API (recommended in Iran); otherwise a plain SMS is sent.
    kavenegar_otp_template: str = ""

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = Settings()