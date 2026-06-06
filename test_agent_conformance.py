# -*- coding: utf-8 -*-
"""
test_agent_conformance.py — META-conformance ของ multi-agent mesh (โครงสร้าง ไม่ใช่พฤติกรรมรายตัว)

ต่างจาก test_agents.py (ทดสอบ "พฤติกรรม" A–I ของ agent เฉพาะตัว เช่น isolation/degrade/mesh):
ไฟล์นี้ "วนทุก agent ที่ค้นพบอัตโนมัติ" แล้วยืนยันว่า *ทุกตัว* ยึดสัญญาคลาสฐาน Agent เดียวกัน
→ เพิ่ม agent ใหม่ = ถูกตรวจทันทีโดยไม่ต้องแก้เทส (กัน contract-drift เชิงสถาบัน)

ทำไมต้องมี (บทเรียนจากงาน de-star: สัญญาชั้น agent อยู่ "นอก golden snapshot" → golden ไม่จับ
การละเมิดสัญญาโครงสร้าง เช่น override run() จนกล่อง error-boundary หาย, ชื่อชนกันจน
ctx.results ทับ, ลืม _run จนคลาส abstract). เทสนี้คือ gate โครงสร้างคู่กับ golden.

สัญญาที่ตรวจ (ต่อ agent ทุกตัว):
  1. เป็น subclass ของ Agent และ instantiate ได้ (ไม่มี abstractmethod ค้าง = implement _run แล้ว)
  2. *ไม่* override `run()` — กล่อง error-boundary/timing/log ต้องสืบทอดจากฐาน (ความสม่ำเสมอ)
  3. override `_run()` จริง (ไม่ใช่ตัวฐานที่ raise NotImplementedError)
  4. คุณสมบัติคลาส: name=str ไม่ว่าง, description=str, critical=bool
  5. ลายเซ็น `_run(self, ctx)` — รับ ctx 1 ตัว
  6. ชื่อ (name) ไม่ซ้ำกันทั้งระบบ (ชนกัน = ctx.results ทับเงียบ ๆ)
และ guard ระดับชุด:
  7. ไม่มีโมดูล agents/*.py ที่ import ไม่ผ่าน (discovery ไม่ถูกข้ามเงียบ ๆ)
  8. จำนวน agent ที่พบ ≥ ขั้นต่ำที่คาด (กันเทส "ผ่านแบบว่างเปล่า" เมื่อ discovery พัง)

ใช้:
    PYTHONHASHSEED=0 python3 test_agent_conformance.py <pkg_dir>
"""
import os
import sys
import inspect
import pkgutil
import importlib

PKG_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
sys.path.insert(0, PKG_DIR)
os.chdir(PKG_DIR)

# จำนวนขั้นต่ำที่คาด — snapshot กัน discovery พังแล้วเทสผ่านแบบว่างเปล่า
# (อัปเดตได้เมื่อ "เพิ่ม" agent จริง; "ลด" ต้องตั้งใจ)
_MIN_EXPECTED_AGENTS = 14

PASS, FAIL = [], []


def check(cond, label):
    (PASS if cond else FAIL).append(label)
    print(f"  {'✅' if cond else '❌'} {label}")


def discover_agents():
    """ค้นหา Agent subclass ทั้งหมดใน package agents/ (auto, ไม่ hardcode รายชื่อ).

    คืน (agent_classes, import_errors) — import_errors = [(module, exc_str)] เพื่อ guard #7.
    """
    import agents
    from agents.base import Agent

    classes = {}
    import_errors = []
    for m in pkgutil.iter_modules(agents.__path__):
        modname = f"agents.{m.name}"
        try:
            mod = importlib.import_module(modname)
        except Exception as e:  # โมดูล agent import ไม่ผ่าน = ปัญหาโครงสร้าง (กัน discovery เงียบ)
            import_errors.append((modname, f"{type(e).__name__}: {e}"))
            continue
        for _, obj in inspect.getmembers(mod, inspect.isclass):
            # เอาเฉพาะคลาสที่ "นิยามในโมดูลนี้เอง" (กันนับซ้ำจาก import ข้ามไฟล์)
            if (issubclass(obj, Agent) and obj is not Agent
                    and obj.__module__ == modname):
                classes[obj.__qualname__] = obj
    return classes, import_errors


def main():
    print("=" * 64)
    print("AGENT META-CONFORMANCE — ทุก agent ยึดสัญญาคลาสฐานเดียวกัน")
    print("=" * 64)

    from agents.base import Agent

    classes, import_errors = discover_agents()

    # --- guard ระดับชุด ---
    print(f"\n[ชุด] ค้นพบ Agent subclass {len(classes)} ตัว")
    check(not import_errors,
          f"ทุกโมดูล agents/*.py import ผ่าน (discovery ไม่ถูกข้าม)")
    if import_errors:
        for mod, err in import_errors:
            print(f"      ✗ {mod}: {err}")
    check(len(classes) >= _MIN_EXPECTED_AGENTS,
          f"จำนวน agent ≥ ขั้นต่ำที่คาด ({len(classes)} ≥ {_MIN_EXPECTED_AGENTS})")

    # --- ชื่อไม่ซ้ำ (รวมทั้งระบบ) ---
    names = {}
    collisions = []
    for cls in classes.values():
        nm = getattr(cls, "name", None)
        if nm in names:
            collisions.append((nm, names[nm], cls.__qualname__))
        else:
            names[nm] = cls.__qualname__
    check(not collisions, f"ชื่อ agent ไม่ซ้ำกันทั้งระบบ ({len(names)} ชื่อ)")
    for nm, a, b in collisions:
        print(f"      ✗ ชื่อซ้ำ '{nm}': {a} ↔ {b}")

    # --- ต่อ agent ทุกตัว ---
    for qual, cls in sorted(classes.items()):
        print(f"\n[{qual}]  (name={getattr(cls,'name','?')!r}, critical={getattr(cls,'critical','?')})")

        # 2) ห้าม override run() — error-boundary ต้องมาจากฐาน
        check(cls.run is Agent.run,
              f"{qual}: ไม่ override run() (กล่อง error-boundary/timing สืบทอดจากฐาน)")

        # 3) override _run จริง
        check(cls._run is not Agent._run,
              f"{qual}: override _run() (มีโค้ดจริง ไม่ใช่ฐาน abstract)")

        # 1) instantiate ได้ (ไม่มี abstractmethod ค้าง)
        instok = True
        inst = None
        try:
            inst = cls()
        except TypeError as e:
            instok = False
            print(f"      ✗ instantiate ไม่ได้: {e}")
        check(instok, f"{qual}: instantiate ได้ (implement abstract ครบ)")

        # 4) คุณสมบัติคลาส
        nm = getattr(cls, "name", None)
        check(isinstance(nm, str) and nm.strip() != "",
              f"{qual}: name เป็น str ไม่ว่าง")
        check(isinstance(getattr(cls, "description", None), str),
              f"{qual}: description เป็น str")
        check(isinstance(getattr(cls, "critical", None), bool),
              f"{qual}: critical เป็น bool")

        # 5) ลายเซ็น _run(self, ctx)
        try:
            params = list(inspect.signature(cls._run).parameters)
            # unbound → ['self','ctx'] ; รับ ctx 1 ตัว
            sig_ok = (len(params) == 2)
        except (TypeError, ValueError):
            sig_ok = False
        check(sig_ok, f"{qual}: ลายเซ็น _run(self, ctx) — รับ ctx 1 ตัว")

    print("\n" + "-" * 64)
    total = len(PASS) + len(FAIL)
    if FAIL:
        print(f"RESULT: ❌ ล้มเหลว {len(FAIL)}/{total}")
        for f in FAIL:
            print(f"   - {f}")
        return 1
    print(f"RESULT: ✅ PASS — agent ทุกตัวยึดสัญญาคลาสฐานครบ ({len(PASS)}/{total} เช็ก, {len(classes)} agents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
