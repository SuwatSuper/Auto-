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
    # Paper-trading starting equity (THB). Mandate default: 1,000 THB — fully
    # adjustable live from the dashboard (POST /api/settings/capital); the
    # treasury sizes everything off this.
    initial_capital: str = "1000"
    # Per-trade risk %. Adjustable live in Settings up to 100% (ความเสี่ยงสูงสุด
    # 100%). Default kept conservative; crank it in the dashboard when desired.
    risk_per_trade_pct: str = "1.0"
    # Fee-aware exits. Bitkub taker fee 0.25%/side = 0.50% round-trip, so the
    # take-profit MUST clear that to net positive. Default SL 0.5% / TP 1.5%
    # (net ≈ 1:1 after fees). Tiny-TP scalping would be eaten by fees — honest.
    stop_pct: str = "0.5"
    take_profit_pct: str = "1.5"
    fee_taker_bps: str = "25"
    fee_maker_bps: str = "25"
    slippage_bps: str = "5"
    survival_floor_pct: str = "70"
    # Experiment mode: limits unlocked (profit/loss up to 100%) so agents can
    # trade freely and level up. Tighten these for real-money use.
    max_daily_loss_pct: str = "100"
    # Circuit-breaker consecutive-loss threshold. 0 = UNLIMITED (ปลดลิมิต
    # เบรกเกอร์ 5/5 เป็นไม่จำกัด) — the breaker never auto-trips on losing
    # streaks; the operator can still trip it manually. Adjustable in Settings.
    # Execution engine (Phase 2) — default must stay "paper"
    execution_engine: str = "paper"
    live_trading_confirm: str = ""
    # Live order type: 'market' (default) guarantees fills for entries AND
    # protective stops; 'limit' rests at the mark and may not fill in fast moves.
    live_order_type: str = "market"
    # Bitkub's minimum order notional (THB). Live orders below this are rejected
    # by the exchange, so the runtime refuses to send (or arm live below) it.
    bitkub_min_order_thb: str = "10"
    # Extended risk limits (Phase 1)
    max_weekly_loss_pct: str = "10"
    max_monthly_loss_pct: str = "15"
    max_consecutive_losses: str = "0"
    max_open_positions: str = "3"
    # State persistence (SQLite, default ON — survives restarts)
    persist_state: bool = True
    state_db_path: str = "data/state.db"
    # How often (seconds) to flush every agent's learned memory to disk while
    # running, so a crash keeps most of what they learned (ทยอย ๆ เซฟ).
    memory_persist_interval_s: float = 30.0
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
    # When ON, only fire an entry when the MEASURED historical win rate of
    # comparable setups (past 50 + recent 50) is ≥ min_p_win — fewer, higher-odds
    # trades. Ships OFF so the bot trades on every strategy signal out of the box
    # (in a calm market the gate can measure 0% win and block everything). Set
    # ENTRY_GATE_ENABLED=true once you want the system to be selective.
    entry_gate_enabled: bool = False
    # Win-probability floor. 0.55 = fire when comparable historical setups won
    # ≥55% of the time (better than a coin flip). Lower = more trades / lower
    # odds; raise for fewer, stronger entries. Honest frequency, not a promise.
    min_p_win: str = "0.55"
    gate_min_confidence: str = "0.50"
    # Graded historical setups required before p_win is trusted (was 20; lowered
    # so the system starts trading after a short warm-up instead of never).
    gate_min_samples: int = 8
    # Block longs in a down-trend? OFF by default so mean-reversion can dip-buy
    # (turning this ON makes the system trend-only and trade much less).
    gate_block_regime_mismatch: bool = False
    # ── Daily trade governance ──────────────────────────────────────────
    # Capability cap on entries per day. ~200 supports active intraday hunting;
    # actual count depends on how many real setups the market offers.
    max_trades_per_day: int = 200
    # Daily profit target (% of initial capital). Pursue 5–10%/day; tracked on
    # the dashboard. NOT a guarantee — Bitkub fees + the market decide the real
    # result. stop_at_daily_target locks the day's gains once the target is hit.
    target_daily_profit_pct: str = "5"
    stop_at_daily_target: bool = True
    # Operator login (optional): password to obtain the control token
    dashboard_password: SecretStr = SecretStr("")
    # Alerts (Phase 1 — Telegram bot or generic webhook)
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    alert_webhook_url: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
