from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bitkub_ws_url: str = "wss://api.bitkub.com/websocket-api/market.ticker.thb_btc"
    log_level: str = "INFO"
    prices_topic: str = "prices.thb_btc.v1"
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    bitkub_api_key: SecretStr = SecretStr("")
    bitkub_api_secret: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
