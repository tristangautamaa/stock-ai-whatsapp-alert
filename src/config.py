from typing import Literal
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # App
    app_env: Literal["dev", "prod"] = "dev"
    dry_run: bool = True
    log_level: str = "INFO"

    # Market Data
    market_data_provider: Literal["yfinance", "sectors", "twelvedata", "finnhub"] = "yfinance"

    # Signal thresholds
    signal_min_confidence: int = Field(default=60, ge=0, le=100)
    signal_alert_threshold: int = Field(default=65, ge=0, le=100)

    # WhatsApp / notification provider
    whatsapp_provider: Literal["meta", "twilio", "pywhatkit", "email"] = "meta"
    whatsapp_recipient: str = ""  # E.164 format, used by pywhatkit
    email_recipient: str = ""
    whatsapp_cloud_api_token: str = ""
    whatsapp_phone_number_id: str = ""
    whatsapp_recipient_number: str = ""
    whatsapp_api_version: str = "v20.0"

    # Twilio
    twilio_account_sid: str = ""
    twilio_auth_token: str = ""
    twilio_whatsapp_from: str = ""
    twilio_whatsapp_to: str = ""

    # TradingView
    tradingview_webhook_secret: str = ""

    # External APIs
    sectors_api_key: str = ""
    timegpt_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env == "dev"

    @property
    def has_whatsapp_meta(self) -> bool:
        return bool(
            self.whatsapp_cloud_api_token
            and self.whatsapp_phone_number_id
            and self.whatsapp_recipient_number
        )

    @property
    def has_whatsapp_twilio(self) -> bool:
        return bool(
            self.twilio_account_sid
            and self.twilio_auth_token
            and self.twilio_whatsapp_from
            and self.twilio_whatsapp_to
        )

    @property
    def has_timegpt(self) -> bool:
        return bool(self.timegpt_api_key)

    @property
    def has_openai(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def has_anthropic(self) -> bool:
        return bool(self.anthropic_api_key)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
