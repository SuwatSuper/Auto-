from __future__ import annotations

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bitkub_ws_url: str = "wss://api.bitkub.com/websocket-api/market.ticker.thb_btc"
    # Price feed: "rest" polls the v3 ticker (reliable, firewall-friendly, not
    # deprecated); "ws" uses the public WebSocket (being phased out by Bitkub).
    price_feed_mode: str = "rest"
    bitkub_rest_url: str = "https://api.bitkub.com"
    price_poll_interval_s: float = 3.0
    # News sentiment via public RSS (no API key). Polls headlines, scores them,
    # feeds the News Intelligence agent.
    news_enabled: bool = True
    news_poll_interval_s: float = 120.0
    log_level: str = "INFO"
    prices_topic: str = "prices.thb_btc.v1"
    web_host: str = "127.0.0.1"
    web_port: int = 8000
    bitkub_api_key: SecretStr = SecretStr("")
    bitkub_api_secret: SecretStr = SecretStr("")
    # Control-plane key: when set, all POST /api/* endpoints require X-API-Key.
    dashboard_api_key: SecretStr = SecretStr("")
    # ── TRAINING MODE (agent self-training) ─────────────────────────────
    # ON by default right now: unlocks ALL limits + a 10,000,000 THB paper
    # bankroll so the agents trade freely and train on real prices. It FORCES
    # paper execution, so unlimited loss can never touch real money. When you
    # are confident, set TRAINING_MODE=false to restore the disciplined config
    # (80% entry gate, breaker, survival floor, daily-loss limit).
    training_mode: bool = True
    training_capital: str = "10000000"
    # Paper-trading starting equity (THB). Used when TRAINING_MODE=false.
    initial_capital: str = "1000000"
    risk_per_trade_pct: str = "1.0"
    stop_pct: str = "1.0"
    take_profit_pct: str = "1.5"
    fee_taker_bps: str = "25"
    fee_maker_bps: str = "25"
    slippage_bps: str = "5"
    survival_floor_pct: str = "70"
    # Experiment mode: limits unlocked (profit/loss up to 100%) so agents can
    # trade freely and level up. Tighten these for real-money use.
    max_daily_loss_pct: str = "100"
    # Execution engine (Phase 2) — default must stay "paper"
    execution_engine: str = "paper"
    live_trading_confirm: str = ""
    # Live order type: 'market' (default) guarantees fills for entries AND
    # protective stops; 'limit' rests at the mark and may not fill in fast moves.
    live_order_type: str = "market"
    # Extended risk limits (Phase 1)
    max_weekly_loss_pct: str = "10"
    max_monthly_loss_pct: str = "15"
    max_consecutive_losses: str = "100"
    max_open_positions: str = "3"
    # State persistence (SQLite, default ON — survives restarts)
    persist_state: bool = True
    state_db_path: str = "data/state.db"
    # Agent watchdog / heartbeat
    watchdog_interval_s: float = 2.0
    heartbeat_stale_ms: int = 5000
    # Enabled strategies (Phase 3) — comma-separated names from domain.strategy.registry
    enabled_strategies: str = "trend_following"
    # Adaptive sizing/exits — when ON the advisory agents take REAL effect:
    #   kelly_sizing   → Dynamic Position Sizer drives risk_per_trade_pct
    #                    (clamped to [0.25 .. kelly_max_risk_pct]; needs ≥10 trades)
    #   trailing_stop  → Trailing-Stop Bot ratchets the live position's stop up
    kelly_sizing_enabled: bool = True
    kelly_max_risk_pct: str = "2.0"
    trailing_stop_enabled: bool = True
    # Supreme commander consensus: tally the latest vote per source agent inside
    # a sliding window; EXECUTE only when net agreement meets the thresholds.
    # Defaults (1/1) keep a lone signal acting; raise to 2+ to demand that
    # multiple strategy agents agree before entering (less noise).
    supreme_window_s: float = 8.0
    supreme_buy_votes: int = 1
    supreme_sell_votes: int = 1
    # ── Win-probability entry gate (Timeline Analyst) ───────────────────
    # Only fire an entry when the MEASURED historical win rate of comparable
    # setups (past 50 + recent 50) is ≥ min_p_win. Honest: this is a frequency,
    # not a guarantee. Higher = fewer, higher-odds trades.
    entry_gate_enabled: bool = True
    min_p_win: str = "0.80"
    gate_min_confidence: str = "0.50"
    # ── Daily trade governance ──────────────────────────────────────────
    # Capability cap on entries per day (set high for high-frequency hunting).
    max_trades_per_day: int = 1000
    # Daily profit target (% of initial capital). Tracked + shown on the
    # dashboard. NOT a guarantee — the market decides. stop_at_daily_target,
    # when true, locks the day's gains by halting new entries once reached.
    target_daily_profit_pct: str = "5"
    stop_at_daily_target: bool = False
    # Operator login (optional): password to obtain the control token
    dashboard_password: SecretStr = SecretStr("")
    # Alerts (Phase 1 — Telegram bot or generic webhook)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    alert_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
