# _evidence — baseline เก่าก่อน re-baseline (append-only ห้ามลบ)

เก็บแบบ `.gz` เพื่อลดขนาดแพ็กเกจ · คลายด้วย `gunzip -k <ไฟล์>.gz`

| ไฟล์ | golden | บริบท |
|---|---|---|
| `baseline.f05358aa.pre-ADR179-186.json.gz` | `f05358aa` | ก่อนรอบแก้ที่ 1 (corpus 152 ไฟล์) |
| `baseline.a213d704.pre-ADR189.json.gz` | `a213d704` | ก่อน ADR-189 (ส่วนลด) |
| `baseline.555a73cc.pre-ADR190-191.json.gz` | `555a73cc` | ก่อน ADR-190/191 (อักขระ + ใบซ้ำ) |
| `baseline_fixture.*.gz` | — | fixture รุ่นก่อน ๆ |

golden ปัจจุบัน = `814c7cf0…` (corpus จริง) · `d05e5de3…` (fixture)
