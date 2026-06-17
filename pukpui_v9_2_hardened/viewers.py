# -*- coding: utf-8 -*-
"""viewers.py — 10 Super Ultra Viewers (ตัวละ 1 ช่องในบล็อกบริษัท)

แต่ละ viewer "เป็นเจ้าของ" 1 field และตัดสินว่า field นั้นของบริษัท/เดือนนี้ = ตรง หรือผิดอะไร
โดยคัดกรองตามเลน (fix/check/review/master). อ่านอย่างเดียว — ไม่แตะ engine/golden.

10 viewers = 10 field (ตาม code_labels.FIELD_ORDER):
  CompanyViewer ชื่อบจ. · AddressViewer ที่อยู่ · TaxIdViewer เลขภาษี · BranchViewer สาขา ·
  DocNoViewer เลขที่ · DateViewer วันที่ · InvoiceViewer เลขที่ iv · ItemViewer รายการสินค้า ·
  PostVatViewer ยอดหลัง vat · PreVatViewer ยอดก่อน vat
composer (super_ultra_viewer.py) เรียกทั้ง 10 ตัวประกอบเป็นบล็อกต่อบริษัท.
"""
from __future__ import annotations

from code_labels import (FIELD_ORDER, field_of, label_of, lane_of, FIX, CHECK, REVIEW, MASTER, NOTE)

_SEV_RANK = {"CRITICAL": 3, "ERROR": 2, "WARNING": 1, "INFO": 0}


class FieldViewer:
    """viewer 1 field: รับ issue ของกลุ่ม (บริษัท×เดือน) → ตัดสิน verdict ของ field ตัวเอง."""

    def __init__(self, field: str):
        self.field = field

    def collect(self, group_issues):
        """group_issues: list ของ (bill_key, issue) ทั้งกลุ่ม → กรองเฉพาะ field ตัวเอง."""
        return [(bk, i) for (bk, i) in group_issues if field_of(i.get("code", "")) == self.field]

    def verdict(self, group_issues) -> dict:
        mine = self.collect(group_issues)
        # lane → {label: set(bill)} ; NOTE เก็บแยก — ไม่ทำให้ช่องนี้ "ผิด" (ยกขึ้นบรรทัดหมายเหตุแทน)
        buckets = {FIX: {}, CHECK: {}, MASTER: {}, REVIEW: {}, NOTE: {}}
        for bk, i in mine:
            code = i.get("code", "")
            lane = lane_of(code)
            buckets.setdefault(lane, {}).setdefault(label_of(code), set()).add(bk)
        # นับใบต่อเลน
        def _nbills(lane):
            s = set()
            for v in buckets.get(lane, {}).values():
                s |= v
            return len(s)
        out = {"field": self.field, "status": "ตรง", "mark": "ok",
               "fix": sorted(buckets[FIX]), "check": sorted(buckets[CHECK]),
               "master": sorted(buckets[MASTER]), "review": sorted(buckets[REVIEW]),
               "note": sorted(buckets[NOTE]),
               "n_fix": _nbills(FIX), "n_check": _nbills(CHECK)}
        # ลำดับความสำคัญ: fix > check > master(ตรวจไม่ได้) > ตรง  (NOTE ไม่นับเป็นปัญหาของช่อง)
        # [v9.2 งาน C] เอา emoji ❌/⚠️ ออก + ใช้ '-' แทน em-dash (รายงานเหมือนคนเขียน อักษรพื้นฐาน)
        if buckets[FIX]:
            out["status"] = "; ".join(out["fix"]) + f" ({out['n_fix']} ใบ)"
            out["mark"] = "fix"
        elif buckets[CHECK]:
            out["status"] = "; ".join(out["check"]) + f" ({out['n_check']} ใบ)"
            out["mark"] = "check"
        elif buckets[MASTER]:
            out["status"] = "- ไม่มี master ตรวจไม่ได้"
            out["mark"] = "master"
        else:
            out["status"] = "ตรง"
            out["mark"] = "ok"
        return out


# ── 10 viewers (instance ต่อ field) ──────────────────────────────────────────
CompanyViewer = FieldViewer(FIELD_ORDER[0])   # ชื่อบจ.
AddressViewer = FieldViewer(FIELD_ORDER[1])   # ที่อยู่
TaxIdViewer = FieldViewer(FIELD_ORDER[2])     # เลขที่ผู้เสียภาษี
BranchViewer = FieldViewer(FIELD_ORDER[3])    # สาขา/สนญ.
DocNoViewer = FieldViewer(FIELD_ORDER[4])     # เลขที่
DateViewer = FieldViewer(FIELD_ORDER[5])      # วันที่
InvoiceViewer = FieldViewer(FIELD_ORDER[6])   # เลขที่ iv
ItemViewer = FieldViewer(FIELD_ORDER[7])      # รายการสินค้า
PostVatViewer = FieldViewer(FIELD_ORDER[8])   # ยอดหลัง vat
PreVatViewer = FieldViewer(FIELD_ORDER[9])    # ยอดก่อน vat

VIEWERS = [CompanyViewer, AddressViewer, TaxIdViewer, BranchViewer, DocNoViewer,
           DateViewer, InvoiceViewer, ItemViewer, PostVatViewer, PreVatViewer]

assert len(VIEWERS) == 10
