# -*- coding: utf-8 -*-
"""file_guard.py — กันไฟล์อินพุต "ไม่น่าเชื่อถือ" (untrusted) ก่อน parse (OBJ-OFFLINE/security)

ถือไฟล์ใบกำกับเป็น untrusted: ป้องกัน resource-exhaustion ไม่ให้ parser ค้าง/กิน RAM จนล่ม
  • ไฟล์ใหญ่ผิดปกติบนดิสก์
  • zip-bomb (xlsx = zip): ผลรวมขนาดหลังคลายซิปมหาศาล / อัตราขยายสูงผิดปกติ / จำนวน entry มาก

★ ออกแบบเป็น "guard" บริสุทธิ์: ไฟล์ใบกำกับจริง (เล็ก/สมเหตุผล) ผ่านทั้งหมด → ไม่กระทบผล parse
  (golden hash ไม่ขยับ). ปฏิเสธเฉพาะไฟล์ "พยาธิสภาพ".
★ fail-open เมื่อ guard เองตรวจไม่ได้ (เช่น zip อ่านไม่ออก) → ปล่อยให้ try/except เดิมของ parser
  รับช่วง ไม่ให้ guard กลายเป็นจุดล้มใหม่.

ลิมิตปรับได้ผ่าน env (default กว้างพอสำหรับใบกำกับจริงทุกใบ):
  PUOPUY_MAX_FILE_MB          (default 64)    ขนาดไฟล์บนดิสก์ (MB)
  PUOPUY_MAX_UNCOMPRESSED_MB  (default 1024)  ผลรวมขนาดหลังคลายซิป (MB)
  PUOPUY_MAX_COMPRESS_RATIO   (default 200)   อัตราขยายซิปสูงสุด (เท่า)
  PUOPUY_MAX_ZIP_ENTRIES      (default 5000)  จำนวนไฟล์ใน zip สูงสุด
"""

from __future__ import annotations

import os
import zipfile
from typing import Tuple

_MB = 1024 * 1024


def _env_num(name: str, default: float) -> float:
    raw = os.environ.get(name, "")
    if not raw:
        return default
    try:
        v = float(raw)
        return v if v > 0 else default
    except Exception:
        return default


def limits() -> dict:
    """ลิมิตที่ใช้จริง (อ่านจาก env ทุกครั้ง — ปรับได้โดยไม่ต้องแก้โค้ด)."""
    return {
        "max_file_bytes": _env_num("PUOPUY_MAX_FILE_MB", 64) * _MB,
        "max_uncompressed_bytes": _env_num("PUOPUY_MAX_UNCOMPRESSED_MB", 1024) * _MB,
        "max_compress_ratio": _env_num("PUOPUY_MAX_COMPRESS_RATIO", 200),
        "max_zip_entries": int(_env_num("PUOPUY_MAX_ZIP_ENTRIES", 5000)),
    }


def inspect_file_safety(path: str) -> Tuple[bool, str]:
    """ตรวจไฟล์ก่อน parse. คืน (ok, reason): ok=True = ปลอดภัย ให้ parse ต่อ."""
    lim = limits()
    try:
        if not os.path.isfile(path):
            return False, "ไม่พบไฟล์หรือไม่ใช่ไฟล์ปกติ"
        size = os.path.getsize(path)
        if size <= 0:
            return False, "ไฟล์ว่าง (0 ไบต์)"
        if size > lim["max_file_bytes"]:
            return False, (
                f"ไฟล์ใหญ่เกินกำหนด ({size / _MB:.1f} MB > "
                f"{lim['max_file_bytes'] / _MB:.0f} MB)"
            )
        # xlsx/xlsm = zip-based → ตรวจ zip-bomb ; xls เก่า (OLE) ไม่ใช่ zip → ข้ามส่วนนี้
        if zipfile.is_zipfile(path):
            try:
                with zipfile.ZipFile(path) as z:
                    infos = z.infolist()
                    if len(infos) > lim["max_zip_entries"]:
                        return False, (
                            f"จำนวนไฟล์ใน zip มากผิดปกติ "
                            f"({len(infos)} > {lim['max_zip_entries']})"
                        )
                    total_unc = sum(int(i.file_size) for i in infos)
                    if total_unc > lim["max_uncompressed_bytes"]:
                        return False, (
                            f"ขนาดหลังคลายซิปใหญ่เกินกำหนด "
                            f"({total_unc / _MB:.1f} MB > "
                            f"{lim['max_uncompressed_bytes'] / _MB:.0f} MB) — สงสัย zip-bomb"
                        )
                    if size > 0 and (total_unc / size) > lim["max_compress_ratio"]:
                        return False, (
                            f"อัตราขยายซิปสูงผิดปกติ "
                            f"({total_unc / size:.0f}x > {lim['max_compress_ratio']:.0f}x) "
                            f"— สงสัย zip-bomb"
                        )
            except zipfile.BadZipFile:
                # อ้างเป็น zip แต่พัง → ไม่บล็อกที่นี่ (ปล่อย parser/try-except เดิมจัดการ)
                return True, "ok (zip ตรวจไม่ได้ — ปล่อย parser จัดการ)"
        return True, "ok"
    except Exception as e:
        # guard ต้องไม่กลายเป็นจุดล้มใหม่ → fail-open ให้ของเดิมรับช่วง
        return True, f"ok (guard ข้ามด้วยข้อยกเว้น: {type(e).__name__})"
