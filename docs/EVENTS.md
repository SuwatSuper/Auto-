# Events

## Topics

| Topic | Producer | Consumer | Schema |
|-------|----------|----------|--------|
| `prices.thb_btc.v1` | PriceSupervisor | SampleAgent, WebSocket | PriceUpdate |

## PriceUpdate Schema

```json
{
  "event_id": "uuid",
  "symbol": "THB_BTC",
  "price": "1500000.00",
  "ts_ms": 1700000000000,
  "source": "bitkub",
  "version": 1
}
```
