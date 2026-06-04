# -*- coding: utf-8 -*-
"""state.py — shared MUTABLE runtime state for ปุ้มปุ้ย 03 (module split foundation).

Holds lazy caches that are (re)bound at runtime and must be observable across ALL
modules (parser, rules_engine, main). Accessed as `state.X` so every `import state`
sees the same object — unlike module-level `global X` which rebinds per-namespace.

Lifecycle: each is None until its builder runs once (lazy init), then reused.
reset_run_state() in main may clear caches between runs in long sessions.
"""

# lazy caches (None until first build) — see _build_* functions in parser/rules
#
# ⚠️ [P1-NOTE] กฎการใช้งาน: ทุกจุดที่อ่าน cache เหล่านี้ "ต้อง" มี lazy-init guard ก่อนเสมอ:
#       if state._XXX is None: _build_xxx()
#   มิฉะนั้นจะได้ None แล้ว .get()/.append()/iterate → AttributeError/TypeError กลาง runtime
#   (ค่าเริ่มต้น None โดยตั้งใจ เพื่อให้ reset_run_state() ล้างได้ และ rebuild lazy ตอนใช้ครั้งแรก)
#   reset_run_state() ใน main จะ set ทั้งหมดกลับเป็น None ต้นรอบ — build ใหม่ได้ค่าเดิม (build จาก static dict/CFG)
_CONSTRUCTION_DICT_BY_LEN = None   # {len: [words]} bucket index for fuzzy dict match
_PYTHAINLP_STEM_BLOCKLIST = None   # protected stems (skip pythainlp correction)
_CAT_KEYWORDS = None               # union of product-category keywords
_PRODUCT_WHITELIST = None          # known-correct product terms

# ── system-issue audit trail (ย้ายมาจาก main พาส2a) ──────────────────────────
# ⚠️ ใช้ list/set "ตัวเดิมตลอด" (ไม่ rebind) — diagnostics.log_system_issue() append เข้าตัวนี้,
#    reporting อ่านผ่าน state._SYSTEM_ISSUES, main พิมพ์สรุปจากตัวนี้ → ทุกโมดูลเห็น object เดียวกัน
#    system_issues_reset() ใช้ .clear() (ไม่ใช่ = []) เพื่อคง identity ของ reference ทุกที่
_SYSTEM_ISSUES = []          # [{code,severity,category,name,detail,...}]
_SYSTEM_ISSUE_SEEN = set()   # ป้องกัน record ซ้ำ (dedupe key)

# ── Text→ตัวเลข recovery audit (ย้ายมาจาก main พาส2c) ────────────────────────
# parser.audit_text_num_reset() ใช้ .clear() คง identity ; main alias ชี้ตัวเดียวกัน
_TEXT_NUM_RECOVERIES = []                  # list ของ dict (cap กันโต)
_AUDIT_CTX = {'file': '-', 'sheet': '-'}   # parser ตั้ง context ก่อนดึงแต่ละชีต

# ── thai_text caches (ย้ายมาจาก main พาส2b) ──────────────────────────────────
# ⚠️ ใช้ dict "ตัวเดิมตลอด" (ไม่ rebind) — thai_text เขียน/อ่าน, main alias ชี้ตัวเดียวกัน
#    reset ใช้ .clear() เพื่อคง identity (เหมือน _SYSTEM_ISSUES). rebuild ได้ค่าเดิม (deterministic)
_FUZZY_DICT_CACHE = {}       # {(word,threshold): (match,score)} fuzzy dict cache (v5.7)
_PYTHAINLP_CACHE = {}        # {word: correction|None} pythainlp spell cache (v6.1)
