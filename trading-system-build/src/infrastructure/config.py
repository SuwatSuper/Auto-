from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bitkub_ws_url: str = "wss://api.bitkub.com/websocket-api/market.ticker.thb_btc"
    log_level: str = "INFO"
    prices_topic: str = "prices.thb_btc.v1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
