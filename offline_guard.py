# -*- coding: utf-8 -*-
"""offline_guard.py — นโยบาย "ออฟไลน์ล้วน" จุดเดียวของทั้งระบบ (OBJ-OFFLINE / กฎเหล็กข้อ 1)

แหล่งความจริงเดียว (single source of truth) ว่า "อนุญาตให้ออกอินเทอร์เน็ตไหม":
  • ค่าตั้งต้น = ห้ามออกเน็ต (ข้อมูลใบกำกับไม่ออกจากเครื่อง)
  • เปิดได้เฉพาะ "ตั้งใจ" ผ่าน env  PUOPUY_ALLOW_NETWORK=1  (ต้องอยู่นอกเส้น audit/CI เสมอ)
  • localhost / 127.0.0.1 ถือเป็น "ในเครื่อง" (เช่น Ollama) → ไม่ใช่การออกเน็ต อนุญาตได้แม้ออฟไลน์

ใช้ร่วมกันโดย webverify (live-fetch) และ llm_provider (กัน LLM ปลายทาง remote).
ไม่มี dependency กับ engine/agents → import ได้ทุกที่ ไม่ circular.
"""

from __future__ import annotations

import os
from urllib.parse import urlparse

_TRUE = ("1", "true", "TRUE", "yes", "on")
_LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1", "0.0.0.0")


def network_allowed() -> bool:
    """True เฉพาะเมื่อผู้ใช้ตั้งใจเปิดผ่าน env PUOPUY_ALLOW_NETWORK (default: False = ออฟไลน์)."""
    return os.environ.get("PUOPUY_ALLOW_NETWORK", "").strip() in _TRUE


def is_local_url(url: str) -> bool:
    """True ถ้า URL ชี้ไปเครื่องตัวเอง (localhost/127.0.0.1) — ทราฟฟิกไม่ออกนอกเครื่อง."""
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return host in _LOCAL_HOSTS


def egress_allowed(url: str) -> bool:
    """อนุญาตให้ "ยิง" URL นี้ไหม: ในเครื่องอนุญาตเสมอ ; ออกเน็ตต้อง opt-in."""
    return is_local_url(url) or network_allowed()
