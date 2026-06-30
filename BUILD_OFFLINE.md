# BUILD_OFFLINE.md — ติดตั้ง/รันระบบแบบ offline (ประกัน 5 ปี)

ระบบนี้ออกแบบให้ rebuild ได้เอง **โดยไม่ต้องพึ่ง internet/PyPI** ถึงปี 2030+
แม้ Python 3.12 จะ EOL ตุลาคม 2028 — เพราะ deps ทั้งหมดถูก freeze เป็น wheel + hash ไว้ในแพ็ก

## องค์ประกอบ (มีในแพ็กแล้ว)
- `vendor/wheels/` — 21 wheel (cp312, linux x86_64) · numpy **2.2.6** · **ไม่มี pythainlp**
- `requirements.lock` — ตรึงทุกแพ็กเกจ + sha256 (สำหรับ `--require-hashes`)
- `Dockerfile` + `.dockerignore` — build image ที่ reproduce golden ได้
- `constraints.txt` / `requirements.txt` — pin เวอร์ชัน (numpy==2.2.6 อยู่ใน constraints)

> golden ที่ผูกกับ environment นี้ = **08e6abfd** (148 ไฟล์ / 1056 บิล)

---

## วิธี A — venv offline (เร็วสุด, ไม่ต้องมี Docker)

```bash
# 1) สร้าง venv ด้วย Python 3.12
python3.12 -m venv .venv && source .venv/bin/activate

# 2) ติดตั้ง offline จาก wheelhouse (ไม่แตะ internet + ตรวจ hash)
pip install --no-index --find-links vendor/wheels --require-hashes -r requirements.lock

# 3) ตั้ง determinism env (จำเป็น — golden ผูกกับค่านี้)
export PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 PUOPUY_OFFLINE=1

# 4) ยืนยัน golden
python regression_full.py . /mnt/project baseline.json     # ต้องได้ 08e6abfd
```

## วิธี B — Docker (พกพาข้ามเครื่อง/ข้าม OS)

```bash
docker build -t puopuy:9.3.4 .                              # build จาก wheelhouse (offline)
docker run --rm -v /path/to/data:/mnt/project puopuy:9.3.4 \
    python regression_full.py . /mnt/project baseline.json  # ยืนยัน golden
```

**offline 100%** (เผื่อ Docker Hub เปลี่ยน): เก็บ base image ไว้ด้วย
```bash
docker pull python:3.12-slim && docker save python:3.12-slim -o python312-slim.tar
# วันหลัง:  docker load -i python312-slim.tar
```

---

## สร้าง wheelhouse ใหม่ (ถ้าต้องอัปเดต — ปกติไม่ต้อง)

```bash
# ⚠️ ต้องใส่ -c constraints.txt เสมอ ไม่งั้นได้ numpy ผิดเวอร์ชัน (จะ golden drift!)
pip download -r requirements.txt -c constraints.txt -d vendor/wheels --only-binary=:all:
# แล้ว regenerate requirements.lock (sha256 ของ wheel ใหม่)
```

## ข้อจำกัด (อ่านก่อนใช้)
- wheelhouse นี้เป็น **linux x86_64 / cp312 เท่านั้น** — ถ้าจะรันบน Windows/macOS native
  ต้อง `pip download` wheelhouse ของ platform นั้นแยก (หรือใช้ Docker ซึ่งเป็น linux อยู่แล้ว = แนะนำ)
- ห้ามติดตั้ง **pythainlp** เข้าสาย production (golden 51 typo มาจาก CONSTRUCTION_DICT — ดู CLAUDE.md landmine #6)
