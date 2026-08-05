# -*- coding: utf-8 -*-
"""
backup_kit.py — สำรอง "ทุกอย่างที่ต้องรอด" เป็นไฟล์เดียว + ตรวจความครบถ้วนได้ [ADR-163]

ปิด gap 3-2-1: golden กัน "ผลเพี้ยน" ได้ แต่กัน "ดิสก์พัง" ไม่ได้.
ของที่ถ้าหายแล้วจบ = release.zip (โค้ด+wheels) · corpus (บิลจริง) · master_companies.json ·
INVARIANTS/DECISIONS.md (ledger การตัดสินใจ). tool นี้มัดรวมเป็น bundle เดียว
พร้อม manifest (sha256 ทุกชิ้น) + คู่มือกู้คืน — เหลืองานมนุษย์แค่ "copy ไฟล์เดียวไป ≥2 ที่".

ใช้:
    python3 backup_kit.py build  <release.zip> [corpus_dir=/mnt/project] [out.zip]
    python3 backup_kit.py verify <bundle.zip>

⚠ PRIVATE: bundle มี corpus จริง (tax_id/ที่อยู่ = ข้อมูลของเจ้าของเอง) — เก็บส่วนตัวเท่านั้น
  ห้ามแชร์คนนอก. ถ้าจะแจกจ่ายระบบ ให้ใช้ sanitize_for_sharing.py กับ release แยกต่างหาก.
exit 0 = สำเร็จ/ครบ ; 1 = พัง/ไม่ครบ ; 2 = ใช้ผิดวิธี
"""
import os
import sys
import json
import glob
import hashlib
import zipfile
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN_REAL = "f05358aab0f7502e74b673429c53cc88d26d82b9f6e1842596869f1e18656ea9"
GOLDEN_FIXTURE = "ad0c9dad6fb31bc28251605c1dbad9bf165299d19d11c4752e743477fa6c0749"

RESTORE_TH = """# 🛟 RESTORE — กู้ระบบปุ้มปุ้ยจาก bundle นี้ (ทีละขั้น)

1) เช็คเครื่องปลายทางก่อน:  python3 machine_check.py   (อยู่ใน bundle นี้)
2) แตก release ด้วย Python เท่านั้น (ห้าม unzip — ชื่อไฟล์ไทยเพี้ยน):
     python3 -c "import zipfile; zipfile.ZipFile('release/<ชื่อ release>.zip').extractall('puopuy')"
3) ติดตั้ง offline ตาม QUICKSTART ในแพ็กที่แตกแล้ว (pip --no-index --find-links wheels -c constraints.txt ...)
4) ยืนยันโค้ดถูกต้อง (ไม่ต้องมี corpus):
     python3 regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json
     → ต้องได้ engine_hash = {fx}
5) วาง corpus/ จาก bundle กลับที่ที่ระบบชี้ (เช่น /mnt/project) + วาง master_companies.json
6) ยืนยันกับข้อมูลจริง:  bash run_ci.sh <corpus_dir>  → golden = {rl}
7) python3 doctor.py  → ทุกข้อเขียว = กู้สำเร็จ
""".format(fx=GOLDEN_FIXTURE[:8] + "…", rl=GOLDEN_REAL[:8] + "…")


def _sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def build(release_zip, corpus_dir="/mnt/project", out=None):
    if not os.path.isfile(release_zip):
        print("❌ ไม่พบ release: %s" % release_zip); return 1
    if not zipfile.is_zipfile(release_zip):
        print("❌ release ไม่ใช่ zip ที่ถูกต้อง (เสียหาย?): %s" % release_zip); return 1
    corpus = sorted(glob.glob(os.path.join(corpus_dir, "*.xls")) +
                    glob.glob(os.path.join(corpus_dir, "*.xlsx")))
    if not os.path.isdir(corpus_dir) or not corpus:
        print("❌ ไม่พบ corpus ใน %s — bundle ที่ไม่มีบิลจริง = สำรองหลอก จึงไม่สร้าง" % corpus_dir)
        print("   ระบุโฟลเดอร์บิล: python3 backup_kit.py build <release.zip> <corpus_dir>")
        return 1
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    out = out or os.path.join(os.getcwd(), "puopuy_PRIVATE_BACKUP_%s.zip" % ts)

    entries = {}  # arcname -> src path
    entries["release/" + os.path.basename(release_zip)] = release_zip
    for p in corpus:
        entries["corpus/" + os.path.basename(p)] = p
    for name, arc in (("master_companies.json", "master_companies.json"),
                      (os.path.join("INVARIANTS", "DECISIONS.md"), "INVARIANTS/DECISIONS.md"),
                      ("corpus_manifest.json", "corpus_manifest.json"),
                      ("machine_check.py", "machine_check.py")):
        src = os.path.join(HERE, name)
        if os.path.isfile(src):
            entries[arc] = src

    man = {"created": ts, "golden_real_corpus": GOLDEN_REAL, "golden_fixture": GOLDEN_FIXTURE,
           "n_corpus_files": len(corpus), "files": {}}
    try:
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
            for arc, src in sorted(entries.items()):
                z.write(src, arc)
                man["files"][arc] = {"sha256": _sha(src), "size": os.path.getsize(src)}
            z.writestr("RESTORE_TH.md", RESTORE_TH)
            z.writestr("manifest.json", json.dumps(man, ensure_ascii=False, sort_keys=True, indent=1))
    except Exception as e:
        try:
            os.remove(out)
        except OSError:
            pass
        print("❌ สร้าง bundle ไม่สำเร็จ (%s: %s) — ลบไฟล์ค้างแล้ว" % (type(e).__name__, str(e)[:60]))
        return 1
    mb = os.path.getsize(out) / (1024 * 1024)
    print("✅ bundle สำรอง: %s  (%.0f MB)" % (out, mb))
    print("   • release 1 · corpus %d · master %s · ledger %s · manifest+RESTORE ✅"
          % (len(corpus),
             "✅" if "master_companies.json" in entries else "— (ยังไม่มีไฟล์)",
             "✅" if "INVARIANTS/DECISIONS.md" in entries else "—"))
    print("   ⚠ PRIVATE: มี corpus จริง — เก็บ ≥2 ที่ (นอกเครื่อง 1) ห้ามแชร์คนนอก")
    print("   ตรวจครบถ้วนภายหลัง: python3 backup_kit.py verify %s" % os.path.basename(out))
    return 0


def verify(bundle):
    if not os.path.isfile(bundle):
        print("❌ ไม่พบไฟล์: %s" % bundle); return 1
    if not zipfile.is_zipfile(bundle):
        print("❌ ไม่ใช่ zip ที่ถูกต้อง (เสียหาย?): %s" % bundle); return 1
    try:
        with zipfile.ZipFile(bundle) as z:
            names = set(z.namelist())
            if "manifest.json" not in names:
                print("❌ ไม่มี manifest.json — ไม่ใช่ bundle ของ backup_kit"); return 1
            man = json.loads(z.read("manifest.json").decode("utf-8"))
            bad = []
            for arc, meta in sorted(man.get("files", {}).items()):
                if arc not in names:
                    bad.append("หาย: " + arc); continue
                h = hashlib.sha256(z.read(arc)).hexdigest()
                if h != meta.get("sha256"):
                    bad.append("เพี้ยน: " + arc)
    except Exception as e:
        print("❌ อ่าน bundle ไม่ได้ (%s: %s)" % (type(e).__name__, str(e)[:60])); return 1
    n = len(man.get("files", {}))
    if bad:
        print("🚨 bundle ไม่ครบ/เพี้ยน %d จาก %d ชิ้น:" % (len(bad), n))
        for b in bad[:10]:
            print("   • " + b)
        print("   → สำเนานี้ใช้กู้ไม่ได้ — ใช้สำเนาอีกที่ / สร้าง bundle ใหม่")
        return 1
    print("✅ bundle ครบถ้วน %d/%d ชิ้น (sha256 ตรง manifest ทุกชิ้น)" % (n, n))
    print("   golden ในนี้: fixture %s… · real %s… · corpus %d ไฟล์"
          % (man.get("golden_fixture", "")[:8], man.get("golden_real_corpus", "")[:8],
             man.get("n_corpus_files", 0)))
    return 0


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] == "build":
        return build(a[1], a[2] if len(a) > 2 else "/mnt/project", a[3] if len(a) > 3 else None)
    if len(a) == 2 and a[0] == "verify":
        return verify(a[1])
    print(__doc__.strip().split("\n\n")[1])  # ส่วน "ใช้:"
    return 2


if __name__ == "__main__":
    sys.exit(main())
