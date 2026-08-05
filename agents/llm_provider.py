# -*- coding: utf-8 -*-
"""
agents/llm_provider.py — ตัวเชื่อม Local LLM (stdlib เท่านั้น — ไม่เพิ่ม dependency)

รองรับ Local LLM หลายแบบผ่าน interface เดียว:
  • OllamaProvider        : Ollama (default http://localhost:11434) — /api/chat
  • OpenAICompatProvider  : llama.cpp server / LM Studio / Ollama /v1 — /v1/chat/completions
  • NullProvider          : ไม่มี LLM (offline) — คืน available=False เสมอ → agent ข้ามอย่างสุภาพ
  • MockProvider          : สำหรับทดสอบ wiring โดยไม่ต้องมีโมเดลจริง (deterministic)

ออกแบบให้:
  - degrade graceful: ถ้า probe แล้วต่อ LLM ไม่ได้ → available=False (pipeline ไม่สะดุด)
  - timeout สั้น + ไม่ retry ดุดัน (LLM เป็น advisory ห้ามถ่วงงานหลัก)
  - ไม่พึ่ง lib ภายนอก (เคารพ pin dependency ของระบบ) ใช้ urllib ล้วน

เลือก provider อัตโนมัติด้วย make_provider(options):
  options/env:
    LLM_PROVIDER = ollama | openai | mock | null     (default: ollama แล้ว fallback null)
    LLM_BASE_URL = http://localhost:11434            (ollama) / http://localhost:8080 (openai-compat)
    LLM_MODEL    = llama3.1 / qwen2.5 / ฯลฯ
    LLM_TIMEOUT  = 60   (วินาที)
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional

try:
    from offline_guard import egress_allowed   # นโยบายออฟไลน์จุดเดียวทั้งระบบ
except Exception:                               # fallback กัน import พัง (ยังคงนโยบายเดิม)
    from urllib.parse import urlparse as _urlparse

    def egress_allowed(url: str) -> bool:
        host = (_urlparse(url).hostname or "").lower() if url else ""
        local = host in ("localhost", "127.0.0.1", "::1", "0.0.0.0")
        return local or os.environ.get("PUOPUY_ALLOW_NETWORK", "").strip() in ("1", "true", "TRUE", "yes")


class LLMProvider:
    """interface ฐาน. subclass implement available() และ chat()."""
    name = "base"

    def available(self) -> bool:
        """probe ว่าต่อ LLM ได้จริงไหม (เร็ว, ไม่โยน exception)."""
        return False

    def chat(self, system: str, user: str) -> str:
        """ส่ง prompt → คืนข้อความตอบ (str). โยน exception ถ้าพัง (agent จับเอง)."""
        raise NotImplementedError

    def info(self) -> dict:
        return {"provider": self.name}


def _http_post_json(url: str, payload: dict, timeout: float) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_get(url: str, timeout: float) -> Optional[bytes]:
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except Exception:
        return None


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url="http://localhost:11434", model="llama3.1", timeout=60.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = float(timeout)

    def available(self) -> bool:
        # GET /api/tags = list models; ถ้าตอบได้ = Ollama ทำงานอยู่
        raw = _http_get(f"{self.base_url}/api/tags", timeout=min(5.0, self.timeout))
        return raw is not None

    def chat(self, system: str, user: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "options": {"temperature": 0.0},   # advisory → อยากให้ค่อนข้างนิ่ง
        }
        out = _http_post_json(f"{self.base_url}/api/chat", payload, self.timeout)
        # Ollama /api/chat → {"message": {"content": "..."}}
        return ((out or {}).get("message") or {}).get("content", "") or ""

    def info(self) -> dict:
        return {"provider": self.name, "base_url": self.base_url, "model": self.model}


class OpenAICompatProvider(LLMProvider):
    """สำหรับ llama.cpp server / LM Studio / Ollama /v1 (OpenAI-compatible)."""
    name = "openai"

    def __init__(self, base_url="http://localhost:8080", model="local-model",
                 timeout=60.0, api_key="not-needed"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = float(timeout)
        self.api_key = api_key

    def available(self) -> bool:
        raw = _http_get(f"{self.base_url}/v1/models", timeout=min(5.0, self.timeout))
        return raw is not None

    def chat(self, system: str, user: str) -> str:
        data = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.0,
            "stream": False,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/v1/chat/completions", data=data,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            out = json.loads(resp.read().decode("utf-8"))
        choices = (out or {}).get("choices") or [{}]
        return (choices[0].get("message") or {}).get("content", "") or ""

    def info(self) -> dict:
        return {"provider": self.name, "base_url": self.base_url, "model": self.model}


class NullProvider(LLMProvider):
    """ไม่มี LLM. ใช้เป็น fallback — ทำให้ AI agent ข้ามอย่างสุภาพ (SKIPPED)."""
    name = "null"

    def available(self) -> bool:
        return False

    def chat(self, system: str, user: str) -> str:
        raise RuntimeError("NullProvider ไม่มี LLM ให้เรียก")


class MockProvider(LLMProvider):
    """โมเดลจำลองแบบ deterministic — สำหรับทดสอบ integration โดยไม่ต้องมีโมเดลจริง.
    คืน JSON ที่ถูก schema เสมอ (echo จำนวน finding ที่ได้รับ)."""
    name = "mock"

    def available(self) -> bool:
        return True

    def chat(self, system: str, user: str) -> str:
        # นับ candidate คร่าวๆ จาก prompt เพื่อให้ output สมจริง + deterministic
        n = user.count('"file"')
        return json.dumps({
            "summary": f"[MOCK] ตรวจทาน {n} รายการที่ระบบธงไว้ — นี่คือผลจำลองสำหรับทดสอบสายเชื่อม",
            "prioritized": [
                {"file": "(mock)", "iv": "-", "why": "ตัวอย่างผลจำลอง (ไม่มีโมเดลจริง)",
                 "severity": "INFO", "recommended_action": "ตรวจด้วยมือ"}
            ],
        }, ensure_ascii=False)

    def info(self) -> dict:
        return {"provider": self.name, "note": "deterministic test double"}


def make_provider(options: dict) -> LLMProvider:
    """เลือก provider จาก options/env แล้ว fallback ไป Null ถ้าต่อไม่ได้.

    การ probe (available) ทำที่ AiReviewAgent อีกชั้น — ที่นี่แค่ "สร้าง" ตามที่ตั้งค่า.
    """
    def _opt(key, default=None):
        return options.get(key, os.environ.get(key.upper().replace("-", "_"), default))

    kind = (_opt("llm_provider", os.environ.get("LLM_PROVIDER", "ollama")) or "ollama").lower()
    base = _opt("llm_base_url", os.environ.get("LLM_BASE_URL"))
    model = _opt("llm_model", os.environ.get("LLM_MODEL"))
    timeout = float(_opt("llm_timeout", os.environ.get("LLM_TIMEOUT", "60")) or 60)

    if kind == "mock":
        return MockProvider()
    if kind == "null":
        return NullProvider()
    if kind == "openai":
        base = base or "http://localhost:8080"
    else:
        base = base or "http://localhost:11434"   # default: ollama (local)

    # ★ OFFLINE-ONLY (กฎเหล็กข้อ 1): LLM ในเครื่อง (localhost) ใช้ได้ ; ปลายทาง remote
    #   จะต่อได้เฉพาะ opt-in ผ่าน env PUOPUY_ALLOW_NETWORK=1 — มิฉะนั้น fallback Null (ออฟไลน์)
    if not egress_allowed(base):
        return NullProvider()

    if kind == "openai":
        return OpenAICompatProvider(base_url=base, model=model or "local-model", timeout=timeout)
    return OllamaProvider(base_url=base, model=model or "llama3.1", timeout=timeout)
