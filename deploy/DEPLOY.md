# Kingdom Prime — Deployment Guide

## Requirements

- Ubuntu 22.04 LTS (หรือ Debian 12+)
- Python 3.12+
- systemd

## 1. Clone and Install

```bash
git clone <repo-url> /home/ubuntu/Auto-
cd /home/ubuntu/Auto-
python3.12 -m venv .venv
.venv/bin/pip install -e .[dev]
```

## 2. Configure

```bash
cp .env.example .env
# แก้ไข .env ตามต้องการ — ห้ามเปิดเผยหรือ commit ไฟล์นี้
nano .env
```

สิ่งที่ต้องตั้งค่า:
| Key | Description |
|-----|-------------|
| `BITKUB_API_KEY` | Bitkub API key (ใช้สำหรับ reconciliation เท่านั้น — ไม่สั่งซื้อขายจริง) |
| `BITKUB_API_SECRET` | Bitkub API secret |
| `DASHBOARD_API_KEY` | รหัสผ่านสำหรับ control endpoints |
| `EXECUTION_ENGINE` | ต้องเป็น `paper` เสมอ (ค่าเริ่มต้น) |

> ⚠ **ระบบนี้เป็น PAPER TRADING เท่านั้น** — ไม่มีการสั่งซื้อขายจริงใด ๆ

## 3. Create Data Directory

```bash
mkdir -p /home/ubuntu/Auto-/data
```

## 4. Install systemd Service

```bash
sudo cp deploy/kingdom_prime.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable kingdom_prime
sudo systemctl start kingdom_prime
```

## 5. Install Log Rotation

```bash
sudo cp deploy/logrotate.conf /etc/logrotate.d/kingdom_prime
sudo logrotate -d /etc/logrotate.d/kingdom_prime   # dry-run ทดสอบก่อน
```

## 6. Verify

```bash
# ดูสถานะ service
sudo systemctl status kingdom_prime

# ดู logs
journalctl -u kingdom_prime -f

# ทดสอบ health endpoint
curl http://127.0.0.1:8000/api/health

# ทดสอบ liveness
curl http://127.0.0.1:8000/healthz
```

## Graceful Shutdown

```bash
# หยุดระบบอย่างปลอดภัย (SIGTERM → รอ 30s → SIGKILL)
sudo systemctl stop kingdom_prime

# หรือส่ง SIGTERM ตรง ๆ
kill -SIGTERM $(pgrep -f "scripts/run.py")
```

## Kill Switch

ถ้าต้องการหยุด live trading ทันทีโดยไม่ต้อง restart:

```bash
mkdir -p /home/ubuntu/Auto-/data
touch /home/ubuntu/Auto-/data/KILL_SWITCH
# ลบออกเพื่อเปิดใช้งานใหม่
rm /home/ubuntu/Auto-/data/KILL_SWITCH
```

## Trade CSV Logs

ทุก trade ที่ปิดจะถูก log ไว้ที่ `data/trades_YYYYMMDD.csv`:

| Column | Description |
|--------|-------------|
| ts_ms | Timestamp (Unix ms) |
| date_utc | วันที่ UTC (YYYYMMDD) |
| symbol | สัญลักษณ์ (เช่น THB_BTC) |
| qty | จำนวน |
| entry_price | ราคาเข้า |
| exit_price | ราคาออก |
| reason | เหตุผลที่ปิด (STOP, TAKE_PROFIT, OPPOSITE_SIGNAL) |
| pnl | กำไร/ขาดทุน (THB) |
| cash | ยอดเงินสด หลังปิด trade |

## Reconciliation

ระบบจะ reconcile กับ Bitkub API ทุก 60 วินาที
- ถ้า `BITKUB_API_KEY` ไม่ถูกตั้ง → ใช้ `NullBalanceSource` (reconcile ทันที)
- จนกว่าจะ reconcile ครั้งแรก → `STARTUP_NOT_RECONCILED` จะ veto decisions ทั้งหมด
- ดูสถานะ reconciliation ได้ที่ `GET /api/health`

## Monitoring

- Dashboard: `http://localhost:8000/`
- Health: `http://localhost:8000/api/health`
- Metrics (Prometheus): `http://localhost:8000/metrics`
- Status: `http://localhost:8000/api/status`
