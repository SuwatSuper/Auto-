# -*- coding: utf-8 -*-
"""regression_full.py — ตาข่ายนิรภัยเต็มสูตร (engine + agent + baseline ต้องตรงกันหมด)

รัน 2 เส้นทางในโปรเซสแยก (process isolation = deterministic, ไม่มี state ปน):
  • เส้น engine  → golden_master.py  → engine_hash
  • เส้น agent   → verify_golden.py  → agent_hash
แล้วเทียบกับ baseline.json (_sha256). ผ่านเมื่อ:
     engine_hash == agent_hash == baseline_hash
หมายความว่า: โค้ดปัจจุบันให้ผลตรง baseline + ชั้น agent ไม่เปลี่ยนผลตรวจเลย.

วิธีใช้:
    PYTHONHASHSEED=0 python3 regression_full.py [pkg_dir=.] [data_dir=/mnt/project] [baseline=baseline.json]
exit 0 = ผ่านทั้งหมด, 1 = ไม่ตรง, 2 = รันเครื่องมือไม่สำเร็จ

หมายเหตุ: argv[3] (baseline) ใส่ได้เพื่อรันบน fixture ใน CI เช่น
    PYTHONHASHSEED=0 python3 regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json
ถ้าไม่ใส่ จะใช้ baseline.json (golden master ของข้อมูลจริง 81 ไฟล์) ตามเดิม.
"""
import os, re, sys, json, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PKG = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else HERE
DATA = sys.argv[2] if len(sys.argv) > 2 else '/mnt/project'
# argv[3] = baseline path (default baseline.json ใน PKG) — backward compatible
if len(sys.argv) > 3:
    BASELINE = sys.argv[3] if os.path.isabs(sys.argv[3]) else os.path.join(PKG, sys.argv[3])
else:
    BASELINE = os.path.join(PKG, 'baseline.json')

ENV = {**os.environ, 'PYTHONHASHSEED': '0'}
HASH_RE = re.compile(r'\b([0-9a-f]{64})\b')


def _run(script, *args):
    path = os.path.join(PKG, script)
    if not os.path.isfile(path):
        print(f'❌ ไม่พบเครื่องมือ {script}')
        return None
    r = subprocess.run([sys.executable, path, *args],
                       capture_output=True, text=True, env=ENV, cwd=PKG)
    if r.returncode not in (0, 1):   # 0/1 = เทียบผ่าน/ไม่ผ่าน (ปกติ); อื่น = พังจริง
        sys.stderr.write(r.stderr[-800:])
    return r


def _last_hash(text):
    found = HASH_RE.findall(text or '')
    return found[-1] if found else None


def main():
    print('=' * 64)
    print('REGRESSION FULL — engine + agent + baseline')
    print(f'  pkg : {PKG}')
    print(f'  data: {DATA}')
    print('=' * 64)

    if not os.path.isfile(BASELINE):
        print(f'❌ ไม่พบ baseline.json ที่ {BASELINE}')
        print('   สร้างก่อนด้วย:  PYTHONHASHSEED=0 python3 golden_master.py . baseline.json <data>')
        return 2
    baseline_hash = json.load(open(BASELINE, encoding='utf-8')).get('_sha256')

    eng = _run('golden_master.py', '.', '/tmp/_reg_engine.json', DATA)
    if eng is None:
        return 2
    engine_hash = _last_hash(eng.stdout)

    ag = _run('verify_golden.py', '.', BASELINE, DATA)
    if ag is None:
        return 2
    agent_hash = _last_hash(ag.stdout)

    print(f'baseline_hash = {baseline_hash}')
    print(f'engine_hash   = {engine_hash}')
    print(f'agent_hash    = {agent_hash}')
    print('-' * 64)

    ok_engine = (engine_hash == baseline_hash)
    ok_agent = (agent_hash == baseline_hash)
    ok_match = (engine_hash == agent_hash and engine_hash is not None)
    print(f'  engine == baseline : {"✅" if ok_engine else "❌"}')
    print(f'  agent  == baseline : {"✅" if ok_agent else "❌"}')
    print(f'  engine == agent    : {"✅" if ok_match else "❌"}  (ชั้น agent ไม่เปลี่ยนผลตรวจ)')
    print('=' * 64)

    if ok_engine and ok_agent and ok_match:
        print('RESULT: ✅ ผ่านทั้งหมด — ผลตรวจตรง baseline และ agent==engine')
        return 0
    print('RESULT: ❌ พบความต่าง — ตรวจ diff ระหว่าง snapshot กับ baseline.json')
    return 1


if __name__ == '__main__':
    sys.exit(main())
