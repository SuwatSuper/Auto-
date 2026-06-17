# scripts/ws_probe.py — read-only WS diagnostic (no API keys required)
"""Connect to Bitkub public ticker stream for 30 s and report price updates."""
from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

# Make src importable when run as a standalone script
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from domain.trading.market_data import PriceUpdate, normalize_bitkub_ticker
from infrastructure.config import get_settings
from infrastructure.gateway.bitkub_ws import iter_json_objects

_PROBE_SECS = 30
_MAX_FRAME_DISPLAY = 300
_LOG_DIR = Path(__file__).parent.parent / "logs"


async def _probe() -> bool:
    import websockets

    _LOG_DIR.mkdir(exist_ok=True)
    log_path = _LOG_DIR / "ws_probe.txt"

    settings = get_settings()
    url = settings.bitkub_ws_url

    price_received = False
    lines: list[str] = []

    def _emit(line: str) -> None:
        print(line)
        lines.append(line)

    _emit(f"Connecting to {url} for {_PROBE_SECS}s …")

    try:
        async with websockets.connect(url) as ws:
            deadline = asyncio.get_event_loop().time() + _PROBE_SECS
            while asyncio.get_event_loop().time() < deadline:
                try:
                    remaining = deadline - asyncio.get_event_loop().time()
                    raw_message = await asyncio.wait_for(ws.recv(), timeout=min(remaining, 5.0))
                except TimeoutError:
                    continue

                frame_str = (
                    raw_message.decode("utf-8", errors="replace")
                    if isinstance(raw_message, bytes)
                    else str(raw_message)
                )
                truncated = frame_str[:_MAX_FRAME_DISPLAY]
                objects = iter_json_objects(frame_str)
                _emit(f"FRAME({len(frame_str)} bytes, {len(objects)} obj): {truncated!r}")

                now_ms = int(time.time() * 1000)
                for obj in objects:
                    result = normalize_bitkub_ticker(obj, now_ms=now_ms)
                    _emit(f"  normalize → {result!r}")
                    if isinstance(result, PriceUpdate):
                        price_received = True
    except Exception as exc:
        _emit(f"ERROR: {exc}")

    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _emit(f"Log written to {log_path}")
    return price_received


def main() -> None:
    got_price = asyncio.run(_probe())
    if got_price:
        print("SUCCESS — at least one PriceUpdate received.")
        sys.exit(0)
    else:
        print("NO PRICES RECEIVED — check internet connection / bitkub_ws_url")
        log_path = _LOG_DIR / "ws_probe.txt"
        if log_path.exists():
            tail = log_path.read_text(encoding="utf-8").splitlines()[-20:]
            print("\n".join(tail))
        sys.exit(1)


if __name__ == "__main__":
    main()
