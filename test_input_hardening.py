# -*- coding: utf-8 -*-
"""test_input_hardening.py — ไฟล์ใบกำกับเป็น untrusted + สวิตช์ออฟไลน์รวม (OBJ-OFFLINE)

[1] file_guard: กัน zip-bomb / ไฟล์ใหญ่ผิดปกติ / ว่าง / หาย — ไฟล์จริงผ่าน, พยาธิสภาพถูกปฏิเสธ
[2] engine integration: parse_all_files "ข้าม" ไฟล์ไม่ปลอดภัย (SYS001) + ไฟล์ดีอื่นยัง parse ได้ ไม่ crash
[3] สวิตช์ออฟไลน์รวม (offline_guard): localhost อนุญาตเสมอ ; remote ต้อง opt-in ;
    make_provider บล็อก LLM ปลายทาง remote เป็น Null เมื่อออฟไลน์

    PYTHONHASHSEED=0 PUOPUY_AUDIT_DATE=2026-06-02 python3 test_input_hardening.py
"""

import os, sys, io, zipfile, tempfile, contextlib, warnings

warnings.filterwarnings("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
os.chdir(HERE)
for _k in (
    "PUOPUY_MAX_FILE_MB",
    "PUOPUY_MAX_UNCOMPRESSED_MB",
    "PUOPUY_MAX_COMPRESS_RATIO",
    "PUOPUY_MAX_ZIP_ENTRIES",
    "PUOPUY_ALLOW_NETWORK",
):
    os.environ.pop(_k, None)

import file_guard
from offline_guard import network_allowed, is_local_url, egress_allowed

PASS, FAIL = 0, []


def check(c, l):
    global PASS
    if c:
        PASS += 1
        print(f"  ✅ {l}")
    else:
        FAIL.append(l)
        print(f"  ❌ {l}")


def setenv(**kw):
    for k, v in kw.items():
        os.environ[str(k)] = str(v)


def clearenv(*keys):
    for k in keys:
        os.environ.pop(k, None)


TMP = tempfile.mkdtemp(prefix="pp_guard_")


def _zip_with(uncompressed_bytes=0, n_entries=1, payload=None):
    p = os.path.join(TMP, f"z_{uncompressed_bytes}_{n_entries}.xlsx")
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        if payload is not None:
            z.writestr("big.bin", payload)
        for i in range(n_entries):
            z.writestr(f"e{i}.txt", b"x")
    return p


print("=" * 64)
print("INPUT HARDENING — untrusted file + offline switch")
print("=" * 64)

print("\n[1] file_guard")
check(
    file_guard.inspect_file_safety(os.path.join(TMP, "nope.xlsx"))[0] is False,
    "ไฟล์หาย → ปฏิเสธ",
)
empty = os.path.join(TMP, "empty.xls")
open(empty, "wb").close()
check(file_guard.inspect_file_safety(empty)[0] is False, "ไฟล์ว่าง (0 ไบต์) → ปฏิเสธ")
ok, why = file_guard.inspect_file_safety("tests/fixtures/fixture_invoices.xlsx")
check(ok is True, f"ไฟล์ใบกำกับจริงผ่าน (limit default) — {why}")

big = os.path.join(TMP, "big.xls")
open(big, "wb").write(b"\0" * (300 * 1024))  # 300KB
setenv(PUOPUY_MAX_FILE_MB="0.1")  # 100KB
ok, why = file_guard.inspect_file_safety(big)
clearenv("PUOPUY_MAX_FILE_MB")
check(ok is False and "ใหญ่เกิน" in why, f"ไฟล์ใหญ่เกิน limit → ปฏิเสธ ({why})")

bomb = _zip_with(uncompressed_bytes=3 * 1024 * 1024, payload=b"\0" * (3 * 1024 * 1024))
setenv(PUOPUY_MAX_UNCOMPRESSED_MB="1")
ok, why = file_guard.inspect_file_safety(bomb)
clearenv("PUOPUY_MAX_UNCOMPRESSED_MB")
check(ok is False and "zip-bomb" in why, f"zip-bomb (ขนาดคลายซิป) → ปฏิเสธ ({why})")

setenv(PUOPUY_MAX_UNCOMPRESSED_MB="100", PUOPUY_MAX_COMPRESS_RATIO="5")
ok, why = file_guard.inspect_file_safety(bomb)
clearenv("PUOPUY_MAX_UNCOMPRESSED_MB", "PUOPUY_MAX_COMPRESS_RATIO")
check(
    ok is False and ("อัตราขยาย" in why or "zip-bomb" in why),
    f"zip-bomb (อัตราขยายสูง) → ปฏิเสธ ({why})",
)

many = _zip_with(n_entries=50)
setenv(PUOPUY_MAX_ZIP_ENTRIES="10")
ok, why = file_guard.inspect_file_safety(many)
clearenv("PUOPUY_MAX_ZIP_ENTRIES")
check(ok is False and "จำนวนไฟล์" in why, f"zip entry มากผิดปกติ → ปฏิเสธ ({why})")

print("\n[2] engine integration — parse_all_files ข้ามไฟล์ไม่ปลอดภัย ไม่ crash")
integ_ok = False
try:
    with contextlib.redirect_stdout(io.StringIO()):
        import importlib

        app = importlib.import_module("ปุ้มปุ้ย_ultimate_v9_modular")
        import state

        garbage = os.path.join(TMP, "garbage.xls")
        open(garbage, "wb").write(b"\0" * (700 * 1024))
        setenv(
            PUOPUY_MAX_FILE_MB="0.5"
        )  # 512KB → garbage(700KB) เกิน, fixture(7KB) ผ่าน
        app.reset_run_state()
        bills, _ = app.parse_all_files(
            ["tests/fixtures/fixture_invoices.xlsx", garbage]
        )
        clearenv("PUOPUY_MAX_FILE_MB")
        sys_issues = list(state._SYSTEM_ISSUES)
    skipped = any(
        "Unsafe File Skipped" == i.get("name")
        or "ไม่ปลอดภัย" in str(i.get("detail", ""))
        for i in sys_issues
    )
    check(
        len(bills) > 0,
        f"ไฟล์ใบกำกับดียัง parse ได้ ({len(bills)} บิล) แม้มีไฟล์อันตรายปน",
    )
    check(skipped, "ไฟล์ไม่ปลอดภัยถูกข้าม + บันทึก SYS001 (ตามรอยได้)")
    integ_ok = True
except Exception as e:
    clearenv("PUOPUY_MAX_FILE_MB")
    check(False, f"parse_all_files crash: {type(e).__name__}: {e}")
if not integ_ok:
    check(False, "engine integration ล้มเหลว")

print("\n[3] สวิตช์ออฟไลน์รวม (offline_guard + llm_provider)")
clearenv("PUOPUY_ALLOW_NETWORK")
check(is_local_url("http://localhost:11434") is True, "localhost = ในเครื่อง")
check(is_local_url("http://127.0.0.1:8080") is True, "127.0.0.1 = ในเครื่อง")
check(
    egress_allowed("http://localhost:11434") is True,
    "ออฟไลน์: localhost ยังอนุญาต (Ollama)",
)
check(egress_allowed("https://api.openai.com/v1") is False, "ออฟไลน์: remote ถูกบล็อก")
check(network_allowed() is False, "network_allowed=False เป็นค่าตั้งต้น")
setenv(PUOPUY_ALLOW_NETWORK="1")
check(egress_allowed("https://api.openai.com/v1") is True, "opt-in: remote อนุญาตได้")
clearenv("PUOPUY_ALLOW_NETWORK")
try:
    with contextlib.redirect_stdout(io.StringIO()):
        from agents.llm_provider import (
            make_provider,
            NullProvider,
            OllamaProvider,
            OpenAICompatProvider,
        )
    p_remote = make_provider(
        {"llm_provider": "openai", "llm_base_url": "https://remote.example:8080"}
    )
    check(
        isinstance(p_remote, NullProvider),
        "make_provider: remote LLM ออฟไลน์ → Null (บล็อก)",
    )
    p_local = make_provider(
        {"llm_provider": "ollama", "llm_base_url": "http://localhost:11434"}
    )
    check(
        isinstance(p_local, OllamaProvider), "make_provider: Ollama localhost → ใช้ได้"
    )
    setenv(PUOPUY_ALLOW_NETWORK="1")
    p_remote2 = make_provider(
        {"llm_provider": "openai", "llm_base_url": "https://remote.example:8080"}
    )
    check(
        isinstance(p_remote2, OpenAICompatProvider),
        "make_provider: remote + opt-in → ใช้ได้",
    )
    clearenv("PUOPUY_ALLOW_NETWORK")
except Exception as e:
    clearenv("PUOPUY_ALLOW_NETWORK")
    check(False, f"make_provider ทดสอบล้มเหลว: {type(e).__name__}: {e}")

print("\n" + "=" * 64)
print(f"INPUT HARDENING: ผ่าน {PASS} / ล้มเหลว {len(FAIL)}")
print("=" * 64)
if FAIL:
    for x in FAIL:
        print(f"  • {x}")
    print("RESULT: ❌")
    sys.exit(1)
print("RESULT: ✅ untrusted-file guard + สวิตช์ออฟไลน์รวม ครบ")
sys.exit(0)
