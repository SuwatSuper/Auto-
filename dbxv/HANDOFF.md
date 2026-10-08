# DBXV — งานปรับค่าพลังจากอนิเมะเข้าเกม (ส่งต่อให้ session บนเครื่องผู้ใช้)

เกม: **Dragon Ball Xenoverse 1** บน Windows ของผู้ใช้
เครื่องมือบนเครื่อง: shortcut **"DBXV FULL STAT EDITOR"** (สคริปต์ Python) บน Desktop

## คำสั่งเดิมของผู้ใช้ (แชท 2026-10-03 เวลาไทย, ถูกหยุดกลางคัน)

> นายทำการสร้างไฟล์สำหรับเปลี่ยนให้หน่อย เพราะว่าเราต้องการ ตัวเลขค่าพลังจากอนิเมะ มาปรับกับในเกมของเราทุกตัว
> และ เราจะส่งให้กับ แชทจีพีที ถ้าหากว่า ข้อมูลไหนไม่มีให้อ้างอิงจาก ฉากต่อสู้ และ ทำการ ใส่มา เราจะมาปรับ

คำสั่งเพิ่ม (2026-10-08): ทำ "3 ข้อที่ยังไม่เสร็จจากแชทเมื่อคืน" ให้เสร็จ ห้ามเดา ตรวจค่าทีละตัวอย่างละเอียด

## สถานะ

- แชทเดิมอ่านไฟล์ได้ 7 นาทีแล้วถูกหยุด **ยังไม่มีผลงานใด ๆ** (ไม่มีไฟล์ผลลัพธ์ ไม่มี commit)
- "3 ข้อที่ยังไม่เสร็จ" มาจากแชทที่ไม่ใช่ Claude Code (claude.ai หรือ ChatGPT) — **ยังไม่ทราบเนื้อหา ต้องถามผู้ใช้**

## ไฟล์ input (ผู้ใช้เคยอัปโหลด 5 ไฟล์)

| ไฟล์ | สถานะ |
|---|---|
| `ค่าพลังในอนิเมะ .txt` | กู้ครบ 851 บรรทัด 108 รายการ → `dbxv/anime_power_xv1.txt` |
| `ALL_CHARACTER_PRESETS.tsv` | อยู่บนเครื่องผู้ใช้ (250 แถว) |
| `PLAYABLE_FORMS_EXPANDED.tsv` | อยู่บนเครื่องผู้ใช้ (292 แถว) |
| `TRANSFORMATION_MODIFIERS.tsv` | อยู่บนเครื่องผู้ใช้ (ยังไม่เคยถูกอ่าน) |
| `README.txt` | อยู่บนเครื่องผู้ใช้ (ยังไม่เคยถูกอ่าน) |

โครงสร้างที่เห็นจากแชทเดิม (ข้อเท็จจริงจากไฟล์ ไม่ใช่การเดา):

- `ALL_CHARACTER_PRESETS.tsv` คอลัมน์: `cid code name record costume category hp ki stamina basic basic_ki strike blast power_index basic_def ki_def strike_def blast_def ground air boost dash skillset_ids transform_skills skills`
  - `category` = `Roster` หรือ `CaC`; `hp` ทุกแถว = 1.0
- `PLAYABLE_FORMS_EXPANDED.tsv` คอลัมน์: `cid code name record costume category form source hp ki stamina basic basic_ki strike blast power_index ground air boost dash`
  - `form`: BASE 250, Super Saiyan 21, Super Saiyan 2 5, Super Saiyan 3 5, Kaioken 4, X3 Kaioken 2, Super Vegeta 2 2, X20 Kaioken 1, Potential Unleashed 1, Super Vegeta 1
  - `source`: `PSC` (ค่าฐาน) หรือ `PSC x PUP <id>` (ค่าฐาน × ตัวคูณร่างแปลง); PUP 2/3/4 = Kaioken/x3/x20, 30/31/32 = SS/SS2/SS3, 33 = Potential Unleashed, 34/35 = Super Vegeta/2

## กติกาของผู้ใช้

- ห้ามเดา ทุกตัวเลขต้องระบุชนิดหลักฐาน: เนื้อเรื่อง / คู่มือ / คำนวณ (แสดงสูตร) / เทียบจากฉากต่อสู้
- ถ้าข้อมูลไม่ครบ ให้ถามก่อน
- ห้ามรวมสเกล Z / GT / ภาพยนตร์ / Super เป็นเลขเดียวกันโดยไม่ระบุ (ดูหลักการในหัวไฟล์ anime_power_xv1.txt)
