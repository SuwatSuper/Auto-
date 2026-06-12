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
    # Control-plane key: when set, all POST /api/* endpoints require X-API-Key.
    dashboard_api_key: SecretStr = SecretStr("")
    # Paper-trading starting equity (THB). No live order execution exists.
    initial_capital: str = "1000"
    risk_per_trade_pct: str = "1.0"
    stop_pct: str = "1.0"
    take_profit_pct: str = "1.5"
    fee_taker_bps: str = "25"
    slippage_bps: str = "5"
    survival_floor_pct: str = "70"
    max_daily_loss_pct: str = "5"
    # Extended risk limits (Phase 1)
    max_weekly_loss_pct: str = "10"
    max_monthly_loss_pct: str = "15"
    max_consecutive_losses: str = "5"
    max_open_positions: str = "3"
    # State persistence (SQLite, default ON — survives restarts)
    persist_state: bool = True
    state_db_path: str = "data/state.db"
    # Agent watchdog / heartbeat
    watchdog_interval_s: float = 2.0
    heartbeat_stale_ms: int = 5000


@lru_cache
def get_settings() -> Settings:
    return Settings()
