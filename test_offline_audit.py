# -*- coding: utf-8 -*-
"""test_offline_audit.py — พิสูจน์ "ZERO OUTBOUND ในเส้น audit" (OBJ-OFFLINE / กฎเหล็กข้อ 1)

ตรวจสามอย่าง:
  [A] รัน audit เต็มเส้น (parse → run_audit_core เหมือน golden_master) "โดยบล็อก network ทั้งเครื่อง"
      ต้องสำเร็จและ "ไม่มีการพยายามเปิด socket/urlopen แม้แต่ครั้งเดียว".
  [B] web_request() ออฟไลน์เป็นค่าตั้งต้น: คืน None โดยไม่เรียก urlopen ; ต่อเมื่อ
      ตั้งใจเปิด env PUOPUY_ALLOW_NETWORK=1 เท่านั้น จึงจะ "เรียก" urlopen (เกตคุมได้จริง).
  [C] ออฟไลน์แล้วยังทำงานได้: tier1_verify (dict/fuzzy) + อ่าน sqlite cache (local) ไม่พึ่งเน็ต ;
      run_product_verification(enable_online=True) ออฟไลน์ → web requests = 0.

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_offline_audit.py
exit 0 = ผ่าน, 1 = ไม่ผ่าน
"""

import os, sys, io, glob, socket, sqlite3, tempfile, contextlib, warnings
import urllib.request

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
os.environ.pop("PUOPUY_ALLOW_NETWORK", None)  # เริ่มจาก "ออฟไลน์" เสมอ

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


# ── ตัวดักจับการออกเน็ต (global) ──────────────────────────────────────────
URLOPEN_CALLS = []
_real_urlopen = urllib.request.urlopen


def _spy_urlopen(*a, **k):
    URLOPEN_CALLS.append(a[0] if a else None)
    raise RuntimeError("network blocked by test (urlopen)")


class _BlockedSocket(socket.socket):
    def connect(self, *a, **k):
        raise AssertionError(f"network blocked by test (socket.connect {a})")

    def connect_ex(self, *a, **k):
        raise AssertionError(f"network blocked by test (socket.connect_ex {a})")


def _blocked_getaddrinfo(*a, **k):
    raise AssertionError(f"network blocked by test (getaddrinfo {a[:2]})")


urllib.request.urlopen = _spy_urlopen
_real_socket, _real_gai = socket.socket, socket.getaddrinfo
socket.socket = _BlockedSocket
socket.getaddrinfo = _blocked_getaddrinfo

print("=" * 64)
print("OFFLINE AUDIT — ZERO OUTBOUND ในเส้น audit")
print("=" * 64)

# โหลด engine "ขณะ network ถูกบล็อก" (import เองต้องไม่ยิงเน็ต)
import_ok = True
try:
    with contextlib.redirect_stdout(io.StringIO()):
        import importlib

        app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
        import webverify
except Exception as e:
    import_ok = False
    print(f"  ❌ import engine ขณะบล็อกเน็ต ล้มเหลว: {type(e).__name__}: {e}")

print("\n[A] รัน audit เต็มเส้น (parse → run_audit_core) โดยบล็อกเน็ตทั้งเครื่อง")
audit_ok, n_bills = False, 0
if import_ok:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            app.reset_run_state()
            fl = sorted(glob.glob("tests/fixtures/*.xlsx"))
            bills, _ = app.parse_all_files(fl)
            for b in bills:
                app.compute_bill_confidence(b)
            MASTER = {}
            mp = os.path.join(HERE, "master_companies.json")
            if os.path.exists(mp):
                import json

                MASTER = json.load(open(mp, encoding="utf-8"))
            app.run_audit_core(bills, MASTER, isolate=True)
        audit_ok, n_bills = True, len(bills)
    except AssertionError as e:
        print(f"  ❌ เส้น audit พยายามต่อ network: {e}")
    except Exception as e:
        print(f"  ❌ audit ล้มเหลว (ไม่ใช่เรื่อง network): {type(e).__name__}: {e}")
check(audit_ok, f"audit ({n_bills} บิล) รันจบโดยไม่แตะ socket แม้แต่ครั้งเดียว")
check(
    len(URLOPEN_CALLS) == 0,
    f"เส้น audit เรียก urlopen 0 ครั้ง (ได้ {len(URLOPEN_CALLS)})",
)

print("\n[B] เกต offline: web_request ปิดเป็นค่าตั้งต้น / เปิดเฉพาะ opt-in")
if import_ok:
    os.environ.pop("PUOPUY_ALLOW_NETWORK", None)
    URLOPEN_CALLS.clear()
    r_off = webverify.web_request("https://example.com/x")
    check(r_off is None, "default (ไม่มี env) → web_request คืน None")
    check(len(URLOPEN_CALLS) == 0, "default → ไม่เรียก urlopen (ไม่แตะ socket)")
    check(
        webverify.network_allowed() is False, "network_allowed() = False เป็นค่าตั้งต้น"
    )

    os.environ["PUOPUY_ALLOW_NETWORK"] = "1"
    URLOPEN_CALLS.clear()
    r_on = webverify.web_request(
        "https://example.com/y"
    )  # เกตเปิด → "พยายาม" urlopen (สปายจับ)
    check(webverify.network_allowed() is True, "env=1 → network_allowed() = True")
    check(
        len(URLOPEN_CALLS) >= 1,
        f"env=1 → web_request เรียก urlopen จริง ({len(URLOPEN_CALLS)} ครั้ง) — เกตคุมได้",
    )
    check(
        r_on is None, "ถูกบล็อกระหว่างทดสอบ → คืน None อย่างนุ่มนวล (มี circuit/except)"
    )
    os.environ.pop("PUOPUY_ALLOW_NETWORK", None)

print("\n[C] ออฟไลน์แล้วยังทำงาน: tier1 + cache (local) ไม่พึ่งเน็ต")
if import_ok:
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            t1 = webverify.tier1_verify("เหล็กเส้น", "เส้น")
        check(
            isinstance(t1, dict) and "tier1_state" in t1,
            "tier1_verify ทำงานออฟไลน์ (dict/fuzzy)",
        )
    except Exception as e:
        check(False, f"tier1_verify ออฟไลน์ล้มเหลว: {e}")
    try:
        tdb = os.path.join(tempfile.gettempdir(), "pp_cache_test.db")
        conn = sqlite3.connect(tdb)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS search_cache (query TEXT PRIMARY KEY, snippet TEXT, source TEXT, trust INTEGER, ts REAL)"
        )
        webverify.set_cached(conn, "ddg:x", "snip", "src", 5)
        got = webverify.get_cached(conn, "ddg:x")
        conn.close()
        os.remove(tdb)
        check(
            got and got.get("snippet") == "snip",
            "อ่าน/เขียน sqlite cache (local) ได้ ไม่พึ่งเน็ต",
        )
    except Exception as e:
        check(False, f"cache local ล้มเหลว: {e}")
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            res = webverify.run_product_verification(
                [
                    {
                        "file": "f",
                        "sheet": "1",
                        "items": [{"name": "เหล็กเส้น", "unit": "เส้น", "seq": 1}],
                    }
                ],
                enable_online=True,
            )  # ขอเปิด แต่ env ปิด → ต้องออฟไลน์
        check(
            webverify._WEB_STATE["total_requests"] == 0,
            f"run_product_verification(online=True) ออฟไลน์ → web req = {webverify._WEB_STATE['total_requests']}",
        )
    except AssertionError as e:
        check(False, f"พยายามต่อเน็ต: {e}")
    except Exception as e:
        check(False, f"run_product_verification ล้มเหลว: {type(e).__name__}: {e}")

# คืน global เดิม
urllib.request.urlopen = _real_urlopen
socket.socket = _real_socket
socket.getaddrinfo = _real_gai

print("\n" + "=" * 64)
print(f"OFFLINE: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ เส้น audit ไม่มี outbound + เกต offline คุมได้ + ออฟไลน์ยังทำงานครบ")
sys.exit(0)
