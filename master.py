# -*- coding: utf-8 -*-
"""master.py — Master-data layer (บริษัทอ้างอิง) — leaf/utility

ชั้นจัดการ "ข้อมูลหลักบริษัท" — ย้ายมาจาก main แบบ **คัดลอกเป๊ะ** (logic เดิม 100%).
ครอบคลุม: validate_master_entry, save/load_master (master_companies.json),
          parse_master_blob (แกะข้อความ ภ.พ.20 ที่วาง), input_master_data (โหมดโต้ตอบ).

ตำแหน่งใน DAG (พึ่งเฉพาะ leaf + core_utils — ไม่พึ่ง main):
    config + puopuy_core + core_utils  →  [master]
"""
from __future__ import annotations

import json
import os
import re

from config import CFG, _ADDR_START_KW  # [F3] explicit (เดิม import *)
from puopuy_core import clean_tax_id
from core_utils import clean_pp20_address, parse_address_input


def validate_master_entry(name, tax_id, address):
    errors = []
    if not name or len(name) < 5: errors.append('ชื่อบริษัทสั้นเกินไป')
    if not re.match(r'^(บริษัท|ห้างหุ้นส่วน|ห้าง|บจก|หจก|บมจ)', name):
        errors.append('ชื่อต้องขึ้นต้นด้วย บริษัท/ห้างหุ้นส่วนจำกัด/บมจ/บจก/หจก')
    tc = clean_tax_id(tax_id)
    if len(tc) != 13: errors.append(f'เลขภาษีต้อง 13 หลัก (ได้ {len(tc)})')
    if not address or len(address) < 20: errors.append('ที่อยู่สั้นเกินไป')
    return errors


def save_master(master):
    try:
        with open(CFG['MASTER_FILE'], 'w', encoding='utf-8') as f:
            json.dump(master, f, ensure_ascii=False, indent=2)
        print(f'💾 บันทึก master → {CFG["MASTER_FILE"]}')
    except Exception as e:
        print(f'⚠️ บันทึก master ไม่ได้: {e}')


def load_master():
    if not os.path.exists(CFG['MASTER_FILE']): return None
    try:
        with open(CFG['MASTER_FILE'],'r',encoding='utf-8') as f:
            return json.load(f)
    except Exception: return None


def parse_master_blob(blob):
    """รับข้อความดิบจาก ภ.พ.20 → แยก field แบบ Section
    หลักการ: หาคำขึ้นต้นที่อยู่ตัวแรก → ก่อนหน้า=บริษัท, หลัง=ที่อยู่
    คืน dict: name, tax_id, branch, address — ดึงจากข้อความจริง ไม่เดา
    """
    out = {'name':'', 'tax_id':'', 'branch':'', 'address':''}
    if not blob:
        return out
    text = re.sub(r'[\r\n\t]+', ' ', str(blob))
    text = re.sub(r'\s+', ' ', text).strip()

    # --- tax_id: เลข 13 หลักทุกรูปแบบ ---
    m = re.search(r'(?<!\d)(\d[\d\-\s]{11,30}\d)(?!\d)', text)
    if m:
        digits = re.sub(r'\D', '', m.group(1))
        if len(digits) == 13:
            out['tax_id'] = digits
        elif len(digits) == 12:
            out['tax_id'] = '0' + digits

    # --- branch ---
    if re.search(r'สำนักงานใหญ่|สนง\.?ใหญ่|สนญ', text):
        out['branch'] = 'สำนักงานใหญ่'
    else:
        mb = re.search(r'สาขา\s*(?:ที่|เลขที่|#|no\.?)?\s*:?\s*(\d{1,5})', text, re.IGNORECASE)
        out['branch'] = ('สาขา ' + mb.group(1).zfill(5)) if mb else 'สำนักงานใหญ่'

    # --- หาเส้นแบ่ง: คำขึ้นต้นที่อยู่ตัวแรก ---
    split_pos = None
    for kw in _ADDR_START_KW:
        p = text.find(kw)
        if p >= 0 and (split_pos is None or p < split_pos):
            split_pos = p
    if split_pos is not None:
        company_section = text[:split_pos]
        addr_section = text[split_pos:]
    else:
        company_section = text
        addr_section = ''

    # --- company_name: ชื่อแรกในส่วนบริษัท ---
    # ตัดเลขภาษี + branch ออกจาก company_section ก่อน
    cs = re.sub(r'(?:เลขประจำตัวผู้เสียภาษี\S*|เลขผู้เสียภาษี)\s*[:：]?\s*', ' ', company_section)
    cs = re.sub(r'(?<!\d)\d[\d\-\s]{11,30}\d(?!\d)', ' ', cs)
    cs = re.sub(r'สำนักงานใหญ่|สนง\.?ใหญ่|สนญ\.?|สาขา\s*(?:ที่)?\s*\d{1,5}', ' ', cs)
    cs = re.sub(r'\s+', ' ', cs).strip()
    # มีหลายชื่อคั่น / | , → เอาตัวแรก
    first_name = re.split(r'\s*[/|,]\s*', cs)[0].strip()
    out['name'] = first_name

    # --- clean_address: ล้างส่วนที่อยู่อย่างเดียว ---
    # ตัด label เปล่า ("ห้องเลขที่ -" ฯลฯ) ด้วย clean_pp20_address
    # ตัดข้อความหลังรหัสไปรษณีย์ทิ้ง (วันที่จดทะเบียน/ดูประวัติ)
    addr = re.sub(r'(\d{5})\s+\S.*$', r'\1', addr_section)
    try:
        out['address'] = clean_pp20_address(addr)
    except Exception:
        # v5.8 FIX: ดักทุก error ไม่ใช่แค่ NameError (clean_pp20_address ประกาศแล้วเสมอ)
        out['address'] = re.sub(r'\s+', ' ', addr).strip()
    return out


def input_master_data(ask_reuse=True):
    existing = load_master()
    if ask_reuse and existing:
        print(f'\n📂 พบ master เก่า ({len(existing)} บริษัท): {list(existing.keys())}')
        if input('ใช้ master เดิม? [Y/n]: ').strip().lower() != 'n':
            return existing
    print('\n' + '='*70)
    print('📝 ใส่ Master Data (ภ.พ.20)')
    print('='*70)
    master = {}
    idx = 1
    while True:
        print(f'\n--- บริษัทที่ {idx} ---')
        print('📋 วางข้อความ ภ.พ.20 ทั้งก้อนได้เลย (ก๊อปจากเว็บ/PDF)')
        print('   พิมพ์/วางเสร็จกด Enter — บรรทัดว่าง = จบการกรอก')
        blob_lines = []
        while True:
            line = input('  ')
            if not line.strip():
                break
            blob_lines.append(line)
        blob = ' '.join(blob_lines)
        if not blob.strip():
            if not master: print('⚠️ ต้องใส่อย่างน้อย 1 บริษัท'); continue
            break

        parsed = parse_master_blob(blob)
        print('\n   ── ระบบแยกข้อมูลได้ดังนี้ ──')
        print(f'   ชื่อบริษัท : {parsed["name"] or "(ไม่พบ — ต้องพิมพ์เอง)"}')
        print(f'   เลขภาษี   : {parsed["tax_id"] or "(ไม่พบ — ต้องพิมพ์เอง)"}')
        print(f'   สาขา      : {parsed["branch"]}')
        print(f'   ที่อยู่    : {parsed["address"] or "(ไม่พบ — ต้องพิมพ์เอง)"}')
        print('   ──────────────────────────')

        # ให้แก้ทีละ field ถ้าระบบแยกผิด (Enter = ใช้ค่าที่ระบบแยกได้)
        name = input(f'   ✏️ ชื่อบริษัท [Enter=ใช้ค่าบน] : ').strip() or parsed['name']
        tax_id = input(f'   ✏️ เลขภาษี [Enter=ใช้ค่าบน] : ').strip() or parsed['tax_id']
        branch = input(f'   ✏️ สาขา [Enter=ใช้ค่าบน] : ').strip() or parsed['branch']
        addr_in = input(f'   ✏️ ที่อยู่ [Enter=ใช้ค่าบน] : ').strip()
        full_addr = addr_in or parsed['address']
        iv_prefix = input('   ✏️ IV Prefix (default=IV) : ').strip().upper() or 'IV'

        if not name:
            print('⚠️ ไม่มีชื่อบริษัท ข้าม'); continue

        errors = validate_master_entry(name, tax_id, full_addr)
        if errors:
            print('⚠️ พบปัญหา:')
            for e in errors: print(f'   • {e}')
            if input('บันทึกต่อ? [y/N]: ').strip().lower() != 'y':
                print('ข้าม'); continue
        key_base = re.sub(r'^(บริษัท\s*|ห้างหุ้นส่วนจำกัด\s*|ห้าง\s*|บจก\.?\s*|หจก\.?\s*|บมจ\.?\s*)','',name).strip()
        key_base = re.sub(r'\s*จำกัด(\s*\(มหาชน\))?\s*$','',key_base).strip()
        name_alt = re.sub(r'^(บริษัท|ห้างหุ้นส่วนจำกัด|ห้าง|บจก\.?|หจก\.?|บมจ\.?)\s+',r'\1',name)
        # v5.9 FIX-7: ตรวจ key ซ้ำก่อนบันทึก — กัน master ถูกทับโดยไม่เตือน
        if key_base in master:
            existing_tax = master[key_base].get('tax_id', '')
            print(f'\n⚠️  "{key_base}" มีอยู่แล้วใน master (เลขภาษี: {existing_tax})')
            if input('   เขียนทับ? [y/N]: ').strip().lower() != 'y':
                print('ข้าม — ไม่เขียนทับ')
                idx += 1
                continue
        master[key_base] = {
            'name':name,'name_alt':name_alt,'tax_id':clean_tax_id(tax_id),
            'branch':branch,'branch_no':'00000' if 'สำนัก' in branch else '',
            'iv_prefix':iv_prefix,
            'address_full':full_addr,'address_parts':parse_address_input(full_addr),
        }
        print(f'✅ "{key_base}"')
        idx += 1
    save_master(master)
    return master
