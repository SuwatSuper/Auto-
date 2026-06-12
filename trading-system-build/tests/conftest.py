import pytest


@pytest.fixture
def fixed_now_ms() -> int:
    return 1_733_000_000_000


@pytest.fixture
def valid_bitkub_payload(fixed_now_ms: int) -> dict[str, object]:
    return {
        "stream": "market.ticker.thb_btc",
        "last": "1500000.50",
        "ts": fixed_now_ms // 1000,
    }
