# 🛠️ รายงานแก้บั๊กตัวร้าย — "เงินไม่เข้าตลอด / ระบบหยุดเทรดเอง"

วันที่: 2026-06-13 · ตรวจตั้งแต่เปิดโปรแกรมจนจบสายงาน (startup → signal → decision → execution → trade → treasury)

---

## TL;DR (สรุปสั้น)

**เจอบั๊กตัวร้ายแล้ว** อยู่ที่ `ExecutionAgent` (ด่านอนุมัติคำสั่ง):
ระบบกันคำสั่งซ้ำ (idempotency) ใช้ `id(data)` — ซึ่งคือ **เลขที่อยู่หน่วยความจำ (memory address)** ของ dict ที่เพิ่งแปลงจาก JSON มาเป็นตัวกันซ้ำ
แต่ Python จะ **นำที่อยู่หน่วยความจำเดิมกลับมาใช้ซ้ำทันที** หลัง dict ตัวเก่าถูกลบทิ้ง → คำสั่งใหม่ที่ "คนละคำสั่งกันจริง ๆ" กลับได้ `id()` ตรงกับคำสั่งก่อนหน้า → ระบบเข้าใจผิดว่าเป็น "คำสั่งซ้ำ" แล้ว **ทิ้งเงียบ ๆ**

ผลคือ **หลังเปิดออเดอร์แรกได้สำเร็จเพียงไม้เดียว คำสั่งเทรดถัด ๆ ไปแทบทั้งหมดโดนทิ้ง** → บอทหยุดเทรดเอง → **เงิน/กำไรไม่ไหลเข้าต่อ** (ตรงกับอาการที่ถาม "ยอดเงินของเหรียญเข้าตลอดมั้ย")

> ทำไมชุดทดสอบเดิม 531 เคสไม่จับ? เพราะ **ทุกเทสต์ใส่ `decision_id` มาเองเสมอ** แต่ `SupremeAgent` ตัวจริง (โปรดักชัน) **ไม่เคยใส่ `decision_id`** → โค้ดจริงจึงตกไปใช้ `id(data)` ที่มีบั๊ก ส่วนเทสต์ไม่เคยวิ่งเข้าเส้นทางนั้นเลย

---

## 🔬 หลักฐาน (ทำซ้ำได้จริง)

ยิงคำสั่ง EXECUTE ที่ **ต่างกันจริง 300 คำสั่ง** (รูปแบบเดียวกับที่ `SupremeAgent` ส่งออกมา คือไม่มี `decision_id`) เข้า `ExecutionAgent`:

| | คำสั่งที่ส่ง | ผ่านไปถึง PaperTrader | โดนทิ้ง (เข้าใจผิดว่าซ้ำ) |
|---|---|---|---|
| **ก่อนแก้** | 300 | **1** ❌ | 299 |
| **หลังแก้** | 300 | **300** ✅ | 0 |

ทดสอบ end-to-end ทั้งสาย (Supreme → Execution → PaperTrader → Treasury) หลังแก้:
- ตัดสินใจ 148 ครั้ง → **เปิดไม้ 54 / ปิดไม้ 54** (เงินหมุนเวียนเข้า-ออกต่อเนื่อง)
- ตรวจ "เงินคงตัว" (conservation): `cash − (ทุนตั้งต้น + กำไรสะสม)` = **0** เป๊ะทุกจุด

---

## 🐞 จุดที่ผิด (root cause)

`src/orchestration/agents/execution_agent.py` — เดิม:

```python
raw_id = str(data.get("decision_id") or data.get("event_id") or id(data))
client_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
if client_id in self._seen_ids:
    return  # ← ทิ้งคำสั่งเพราะคิดว่าซ้ำ (แต่จริง ๆ ไม่ซ้ำ)
```

`id(data)` ของ object อายุสั้น **ไม่การันตีว่าไม่ซ้ำข้ามเวลา** — CPython รีไซเคิลที่อยู่ทันที ทำให้ค่าชนกันรัว ๆ

---

## ✅ การแก้ (2 ชั้น — กันพลาดซ้อน)

**ชั้นที่ 1 — ต้นเหตุที่ `ExecutionAgent`:** เลิกใช้ `id(data)`. ถ้าคำสั่งไม่มี `decision_id`/`event_id` ให้สร้าง id ใหม่จาก **ตัวนับเดินหน้า (monotonic counter)** เพื่อให้ทุกคำสั่งที่ต่างกันถูกนับเป็น "ไม่ซ้ำ" เสมอ (จะกันซ้ำเฉพาะเมื่อมี id ชัดเจนเท่านั้น):

```python
explicit_id = data.get("decision_id") or data.get("event_id")
if explicit_id:
    raw_id = str(explicit_id)
else:
    self._noid_seq += 1
    raw_id = f"_noid:{self._noid_seq}"
client_id = hashlib.sha256(raw_id.encode()).hexdigest()[:16]
```

**ชั้นที่ 2 — ที่ต้นทาง `SupremeAgent`:** ติด `decision_id` ที่ไม่ซ้ำให้ทุกคำสั่ง เพื่อให้ระบบกันคำสั่งซ้ำทำงานได้จริงและตามรอย (audit) ได้:

```python
decision_id = f"sup-{self.decision_count}-{int(time.time() * 1000)}"
out = orjson.dumps({"decision": decision, "signal": signal, "decision_id": decision_id})
```

> ความปลอดภัยหลังแก้: ถึงคำสั่งจะไหลครบทุกอัน บอทก็ยัง **ไม่เทรดเกินตัว** เพราะยังมีด่านเดิมครบ — กฎ 1 โพซิชัน (`POSITION_CAP_REACHED`), เพดานเงินสดของ Treasury, circuit breaker, daily-loss limit. การแก้นี้แค่ "คืนพฤติกรรมที่ควรเป็น" ไม่ได้ปลดเซฟตี้ใด ๆ

---

## 🧪 เทสต์ที่เพิ่ม (กันบั๊กกลับมา)

- `tests/orchestration/test_execution_agent.py::test_distinct_decisions_without_id_are_not_falsely_suppressed`
  — ยิงคำสั่งไม่มี id 50 อัน ต้องไหลครบ 50 (เดิมจะเหลือ 1)
- `tests/orchestration/test_department_agents.py::test_supreme_agent_stamps_unique_decision_id`
  — ยืนยัน `SupremeAgent` แปะ `decision_id` ที่ไม่ซ้ำทุกคำสั่ง

**ผลรวม:** `pytest` ✅ 533 ผ่าน / 1 skip · `ruff` ✅ · `mypy` ✅
