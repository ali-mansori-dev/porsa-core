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