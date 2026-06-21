# ADR-023 — ปิดโปรเจค: ตัดสิน roadmap คงค้างทั้งหมด (Final Closure)

สถานะ : ACCEPTED — 11.06.2026
บริบท : โปรเจคเข้าสู่การปิดงาน (certification final) — ทุก item คงค้างต้องมีคำตัดสิน
เป็นลายลักษณ์อักษร ไม่ทิ้ง "เดี๋ยวค่อยว่ากัน" ไว้ให้คนรุ่นหลังเดา

---

## ตัดสินรายข้อ

### 1. Roadmap-3 : Profiling / micro-optimization → **ปิดแบบ "บันทึก baseline ไม่ optimize"**

ผลรันจริง (106 ไฟล์ / 834 บิล, sandbox อ้างอิง) บันทึกใน `PERFORMANCE_BASELINE_TH.md` :
wall = **27.54s** (parse+audit-core) ; hotspot อันดับ 1 = `r_tax008` →
`clean_tax_id` ถูกเรียก 716,095 ครั้ง (6.0s cumulative)

เหตุผลไม่ optimize : (a) 27.5s/เดือน คือต้นทุนที่ผู้ใช้รับได้สบาย (งานรายเดือน ไม่ใช่
real-time) (b) ทุกการแตะ rules layer = เสี่ยง golden ขยับ แลกกับวินาทีที่ไม่มีใครรอ
(c) ถ้าอนาคต corpus โต 10 เท่า ค่อยเปิด ADR ใหม่โดยมี baseline นี้เทียบ — จุดเริ่มชัด

### 2. Roadmap-4 : Calamine engine swap → **ตัดสิน "ไม่ทำ" ถาวร**

xlrd 2.0.1 (pinned) อ่าน corpus ทั้งหมดถูกต้อง พิสูจน์ด้วย golden มาตลอด การ swap
engine = เปลี่ยนผู้ผลิต bytes ต้นน้ำทั้งระบบ → golden ขยับแน่นอน → rebaseline ใหญ่
แลกกับ speed ที่ข้อ 1 สรุปแล้วว่าไม่ใช่ปัญหา **ความเสี่ยงไม่คุ้มศูนย์ประโยชน์**

### 3. state.py thread-safe rewrite → **ปิดเป็น "accepted limitation"**

ข้อจำกัด : global mutable state ไม่ thread-safe — **แต่ระบบไม่ใช้ threads**
โหมดขนานใช้ **process** (ProcessPoolExecutor) ซึ่งแยก memory โดยธรรมชาติ และมี
CI gate พิสูจน์ `parallel == serial` บน corpus จริงทุกรอบ (gate [8c]) จึงไม่มี
เส้นทาง code จริงที่ชน limitation นี้ การ rewrite = ความเสี่ยงสูงแลกการป้องกัน
ปัญหาที่สถาปัตยกรรมปัจจุบันไม่มีทางเกิด

เงื่อนไขเปิดใหม่ : หากวันหนึ่งจะใช้ threading จริง ให้เปิด ADR ใหม่ก่อนเขียนโค้ดเสมอ

### 4. อ้างอิง `ec61907f` (81-file corpus, pre-Decimal) → **ปิดเป็น "superseded"**

baseline ปัจจุบันคือ `d6b23d12…` (106 ไฟล์ / 834 บิล, post-Decimal ADR-021,
path-independent ADR-037) — hash เก่าเป็นบันทึกประวัติศาสตร์ ไม่ใช่เป้าตรวจอีกต่อไป
GOLDEN.md ชี้ baseline.json เป็น single source อยู่แล้ว

### 5. Branch-coverage threshold → **ปิดแล้วก่อนหน้า (บังคับ ≥85 ใน gate [10])**

ผลจริงรอบ certify : parser 85.4 / rules 85.1 / validators 85.2 / units 100 — ผ่านทุกกลุ่ม

### 6. Bisectable per-commit checkout (Tor-local) → **มอบเป็นขั้นตอนปิดท้ายของเจ้าของ repo**

คำสั่งสำเร็จรูป (รันบนเครื่อง Tor ที่มี git history เต็ม) :
```bash
# พิสูจน์ว่าทุก commit ใน chain ล่าสุด build+golden ผ่าน (ย้อน N commit ที่ต้องการ)
for c in $(git rev-list --reverse HEAD~10..HEAD); do
  git checkout -q "$c" && \
  PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 \
    python3 golden_master.py . /tmp/bisect_$c.json "C:\Users\User\Desktop\พร้อมตรวจ" \
    || { echo "FAIL at $c"; break; }
done; git checkout -q -   # กลับ HEAD เดิม
```
ความเสี่ยงต่ำมาก (differential guard เขียวต่อเนื่อง) — ทำครั้งเดียวจบ certification

---

## ผลลัพธ์

Roadmap คงค้าง = **ศูนย์** ทุกข้อมีคำตัดสิน + เหตุผล + เงื่อนไขเปิดใหม่ (ถ้ามี)
โปรเจคปิดได้โดยไม่มีหนี้ความคลุมเครือ
