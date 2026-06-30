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
import shutil   # [M-1b] สำรอง .bak ก่อนทับ master

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


def _json_dict_len(text):
    """จำนวน key ระดับบนของ JSON dict ในข้อความ (−1 ถ้า parse ไม่ได้/ไม่ใช่ dict)."""
    try:
        d = json.loads(text)
        return len(d) if isinstance(d, dict) else -1
    except Exception:
        return -1


def _text_is_golden_stub(text):
    """[M-2/ADR-061] True ถ้าข้อความ JSON เป็น master "stub ทดสอบ" (มี key `_golden_stub`).
    ใช้กันไม่ให้ stub ที่หลงมาเป็นไฟล์ live ถูกสำรองทับ .bak ของจริง — สมมาตรกับ
    golden_snapshot._file_has_stub_marker (ซึ่ง write_master_file ใช้อยู่แล้ว)."""
    try:
        d = json.loads(text)
        return isinstance(d, dict) and bool(d.get('_golden_stub'))
    except Exception:
        return False


def save_master(master):
    try:
        payload = json.dumps(master, ensure_ascii=False, indent=2)
        mf = CFG['MASTER_FILE']
        # [M-1b FIX 11.06.69] กันพลาดชั้นสุดท้าย: ก่อนทับไฟล์ สำรองของเดิมเป็น .bak
        #   ข้ามสำรองถ้าเนื้อหาไม่เปลี่ยน (กัน save ซ้ำติดกันทับ .bak "ก่อนแก้จริง" ทิ้ง)
        # [BUGHUNT v9.3.1/ADR-040 M2] ห้ามให้ save ที่ "หด" (บริษัทน้อยลง) ทับ .bak ที่สมบูรณ์กว่า
        #   → .bak เก็บสภาพ "ครบที่สุดที่รู้จัก" เสมอ (กู้คืนได้แม้ถูก wipe หลายรอบ)
        try:
            if os.path.exists(mf):
                with open(mf, 'r', encoding='utf-8') as f:
                    current = f.read()
                bak = mf + '.bak'
                if current != payload:
                    keep = True
                    # [M-2/ADR-061] อย่าให้ "stub ทดสอบ" (_golden_stub) ที่หลงเป็นไฟล์ live สำรองทับ
                    #   .bak กู้คืนของจริง. เดิม guard นับ key อย่างเดียว → stub (1 บริษัท + key _golden_stub)
                    #   นับได้ ≥ ของจริง → ทับ .bak ทิ้ง. ทำให้สมมาตรกับ golden_snapshot ที่รู้จัก stub อยู่แล้ว.
                    if _text_is_golden_stub(current):
                        keep = False
                    elif os.path.exists(bak):
                        with open(bak, 'r', encoding='utf-8') as f:
                            keep = _json_dict_len(current) >= _json_dict_len(f.read())
                    if keep:
                        shutil.copy2(mf, bak)
        except Exception:
            pass   # สำรองไม่ได้ (เช่น read-only) → ไม่ขวางการบันทึกหลัก
        # [BUGHUNT v9.3.1/ADR-040 M1] เขียน atomic (temp+fsync+replace) — kill กลาง write
        #   ไม่ทำ master ครึ่ง/ว่าง (เดิม truncate-then-write → load_master กลืน error คืน None เงียบ)
        tmp = mf + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(payload); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, mf)
        print(f'💾 บันทึก master → {mf}')
    except Exception as e:
        print(f'⚠️ บันทึก master ไม่ได้: {e}')


# [STUB-MARKER] ไฟล์ master ที่โหลดล่าสุดมี "_golden_stub": true หรือไม่ —
#   ใช้โดย _is_real_master (pukpui_modular_funcs) เพื่อแยก stub ทดสอบออกจาก master จริง
#   "โดยไม่เดาจากเนื้อหา" (เลขภาษีของ stub อาจตรงกับบริษัทจริง เช่น ฉีอัน)
LAST_LOADED_WAS_STUB = False


def load_master():
    global LAST_LOADED_WAS_STUB
    LAST_LOADED_WAS_STUB = False
    if not os.path.exists(CFG['MASTER_FILE']): return None
    try:
        with open(CFG['MASTER_FILE'],'r',encoding='utf-8') as f:
            data = json.load(f)
        if isinstance(data, dict) and data.pop('_golden_stub', False):
            LAST_LOADED_WAS_STUB = True   # marker อยู่ระดับไฟล์ — ตัดออกก่อนส่งต่อ (กันปนเป็น "บริษัท")
        return data
    except Exception: return None


def _classify_tax_digits(digits):
    """[BUG-2/ADR-149] แปลง digit-run → (tax_id, branch_from_tax). คืน (None,'') ถ้าไม่ใช่ความยาว tax.
    13=tax / 12=tax(เติม0) / 18=tax13+branch5 / 17=tax12+branch5 (กรณีติดกันจริงไม่มี separator)."""
    if not isinstance(digits, str):                         # [ADR-150 CRASH-2] กัน len() ครัชถ้า caller อนาคตส่ง non-str
        return None, ''
    if len(digits) == 13:
        return digits, ''
    if len(digits) == 12:
        return '0' + digits, ''
    if len(digits) == 18:                                   # tax13 + branch5 ติดกัน
        return digits[:13], ('' if digits[13:] == '00000' else 'สาขา ' + digits[13:])
    if len(digits) == 17:                                   # tax12 (0 หาย) + branch5
        return '0' + digits[:12], ('' if digits[12:] == '00000' else 'สาขา ' + digits[12:])
    return None, ''


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
    # [BUG-1 FIX 11.06.69] เดิม re.search ตัวเดียว: ภ.พ.20 layout "เลขภาษี<TAB>เลขสาขา"
    #   (เช่น '0-2055-55015-71-1\t00001') ถูก normalize เป็น space → regex โลภกินรวมเป็น
    #   18 หลัก → tax_id ว่าง + branch หาย. แก้: ไล่ทุก match เลือกตัว 13/12 หลักแรก ;
    #   ถ้าเจอ 18 (=13+5) หรือ 17 (=12+5) หลัก ให้แยก tax กับ branch ออกจากกัน.
    tax_end = None        # ตำแหน่งจบ tax_id ใน text — ใช้หา branch code โดดที่ตามมา
    tax_start = None      # ตำแหน่งเริ่ม tax_id ใน text — ใช้ตัด tax ออกจากชื่อแบบตรงตัว (ADR-149)
    _br_from_tax = ''     # branch ที่ติดมากับ tax (18/17 หลัก) — explicit keyword ชนะได้
    # [BUG-2/ADR-149] 2-pass: Pass1 จับ digit-run "ไม่มีช่องว่าง" (digits+dash) ก่อน → กัน greedy
    #   คร่อม "tax<space>เลขบ้าน/สาขา" (เช่น '0105556000041 99/4' หรือ 'สาขาที่ 7 0105...') ที่ทำ
    #   digit รวม >13 ไม่เข้า 13/12/18/17 → tax หายเงียบ (BUG เดิม). Pass1 หยุดที่ช่องว่าง → ได้ 13 สะอาด.
    #   Pass2 (fallback) ยอมช่องว่างใน tax ('0 1055 56000 04 1' = พิมพ์เว้นวรรค) เฉพาะเมื่อ Pass1 ไม่เจอ.
    #   คง BUG-1 (TAB-glued '…\t00001') — Pass1 ได้ tax13 สะอาด, branch '00001' หาได้จาก post-tax logic.
    # [ADR-150 BUG-1] quantifier {10,30} (เดิม {11,30}) → จับ run 12 หลักเปล่า (Excel ตัด 0 นำหน้า
    #   เลขภาษีไม่มี separator เช่น '105556000041') ที่ _classify เติม 0 เป็น 13 อยู่แล้ว แต่เดิม regex
    #   ยาวขั้นต่ำ 13 ตัว → ไม่ match → tax หาย. (run 10/11 ตัว = เบอร์โทร → _classify คืน None → ข้าม.)
    # [ADR-150 BUG-3] ถ้ามี label 'เลขประจำตัว/เลขผู้เสียภาษี' → ค้น tax จาก "หลัง label" ก่อน → กันคว้า
    #   เลข 13 หลักอื่น (เลขบัญชี/อ้างอิง) ที่มาก่อน label. ไม่มี label / หลัง label ไม่เจอ → ค้นทั้งข้อความ.
    _lbl = re.search(r'เลข(?:ประจำตัว(?:ผู้เสียภาษี|ผู้เสีย|ประชาชน)?|ผู้เสียภาษี)\S*\s*[:：]?\s*', text)
    for _off in ([_lbl.end(), 0] if _lbl else [0]):
        for _pat in (r'(?<!\d)(\d[\d\-]{10,30}\d)(?!\d)',
                     r'(?<!\d)(\d[\d\-\s]{10,30}\d)(?!\d)'):
            for m in re.finditer(_pat, text[_off:]):
                _tid, _brt = _classify_tax_digits(re.sub(r'\D', '', m.group(1)))
                if _tid:
                    out['tax_id'] = _tid; _br_from_tax = _brt
                    tax_start = _off + m.start(1); tax_end = _off + m.end(1); break
            if tax_end is not None:
                break
        if tax_end is not None:
            break

    # --- branch ---
    # [BUG-1 FIX] ลำดับความเชื่อ: explicit "สำนักงานใหญ่" > explicit "สาขา N" >
    #   เลข 5 หลักติด/ตามหลัง tax_id (ภ.พ.20) > default สำนักงานใหญ่.
    #   guard เลขโดด: ภายใน 15 ตัวอักษรหลัง tax_id เท่านั้น + ไม่ใช่ '00000'
    #   (กันรหัสไปรษณีย์ปลายที่อยู่ เช่น 20170 ถูกจับผิด — อยู่ไกล tax_id เสมอ)
    _brcode_end = None    # [ADR-150 BUG-2] ตำแหน่งจบ "รหัสสาขา 5 หลัก" ที่ตามหลัง tax (post-tax) ใน text
    if re.search(r'สำนักงานใหญ่|สนง\.?ใหญ่|สนญ', text):
        out['branch'] = 'สำนักงานใหญ่'
    else:
        mb = re.search(r'สาขา\s*(?:ที่|เลขที่|#|no\.?)?\s*:?\s*(\d{1,5})', text, re.IGNORECASE)
        if mb:
            out['branch'] = 'สาขา ' + mb.group(1).zfill(5)
        elif _br_from_tax:
            out['branch'] = _br_from_tax
        else:
            if tax_end is not None:
                mb2 = re.match(r'\s*(\d{5})(?!\d)', text[tax_end:tax_end + 15])
                if mb2 and mb2.group(1) != '00000':
                    out['branch'] = 'สาขา ' + mb2.group(1)
                    _brcode_end = tax_end + mb2.end()   # รหัสสาขาติด tax → ตัดรวมกับ tax ออกจากชื่อ
            if not out['branch']:
                out['branch'] = 'สำนักงานใหญ่'

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
    # [BUG-2/ADR-149] ตัด tax ออกจากชื่อ "แบบตรงตัว" (สตริง tax ที่ extract ได้จริง รูปแบบใดก็ได้:
    #   ติดกัน/dash/space) แทน regex greedy เดิม [\d\-\s] ที่กิน 'tax<space>เลขบ้าน/สาขา' พ่วงไปด้วย →
    #   เลขบ้าน '99/4' หาย / รหัสสาขาหลุด. ตัดตรงตัว → เลขที่ตามหลังคงไว้ให้ ADR-100/ที่อยู่จัดการถูก.
    # [BUG-2/ADR-149 + ADR-150] ตัด "tax (+ รหัสสาขา post-tax ถ้าติดกัน)" ออกจากชื่อ "แบบตรงตัว".
    #   [ADR-150 BUG-2] เดิมตัดรหัสสาขาด้วย global re.sub(branch_no) → ลบเลข 5 หลักที่บังเอิญอยู่ในชื่อ
    #   จริง (เช่น 'ไทยพาณิชย์ 12345 จำกัด' โดน 12345 หาย). แก้: ขยายช่วงตัด tax ให้ครอบรหัสสาขาที่
    #   "ตามหลัง tax ติดกัน" (_brcode_end) เท่านั้น — รหัสสาขาที่มาจาก keyword 'สาขา N' ตัดด้วย regex
    #   keyword ด้านล่างอยู่แล้ว ; เลข 5 หลักอื่นในชื่อไม่โดนแตะ.
    _strip_end = _brcode_end if _brcode_end is not None else tax_end
    if tax_start is not None and _strip_end is not None:
        cs = cs.replace(text[tax_start:_strip_end], ' ', 1)
    cs = re.sub(r'(?<!\d)\d[\d\-]{10,30}\d(?!\d)', ' ', cs)   # เผื่อ tax-like run อื่นตกค้าง (ไม่กินช่องว่าง)
    cs = re.sub(r'สำนักงานใหญ่|สนง\.?ใหญ่|สนญ\.?|สาขา\s*(?:ที่)?\s*\d{1,5}', ' ', cs)
    cs = re.sub(r'\s+', ' ', cs).strip()
    # [ADR-100] เลขที่บ้านเปล่า (เช่น "88", "99/4", "99 หมู่ 4") ที่ขึ้นต้นที่อยู่แต่ไม่มี "เลขที่" นำ
    #   จะค้างท้าย company_section (มาก่อนคำ keyword เช่น อาคาร/ถนน/ตำบล) → ทำให้เลขหลุดไปติดชื่อ
    #   + หายจากที่อยู่. แก้: ถ้ามีที่อยู่ต่อ (split เกิดที่ keyword) และชื่อลงท้ายด้วยเลขที่บ้านเปล่า
    #   → ย้ายไปต้นที่อยู่. (ชื่อที่มีเลขกลาง เช่น "1000 แอมป์"/"ทีเค 2514" ลงท้าย "จำกัด" ไม่โดน)
    if addr_section:
        _mh = re.search(r'(\d+(?:/\d+)?(?:\s*หมู่\s*(?:ที่)?\s*\d+)?)\s*$', cs)
        if _mh:
            addr_section = (_mh.group(1).strip() + ' ' + addr_section).strip()
            cs = cs[:_mh.start()].strip()
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
        # [M-1 FIX 11.06.69] เดิมตอบ n → master={} เริ่มว่าง → save ทับทั้งไฟล์ →
        #   บริษัทเก่าหายเกลี้ยง (data loss เงียบ). ใหม่: n = "เพิ่ม/แก้ต่อจากเดิม"
        #   (เริ่มจาก existing — dup-check เดิมที่ด้านล่างกันเขียนทับรายบริษัทอยู่แล้ว)
        if input('ใช้ master เดิม? [Y=ใช้เลย / n=เพิ่ม-แก้บริษัท]: ').strip().lower() != 'n':
            return existing
    print('\n' + '='*70)
    print('📝 ใส่ Master Data (ภ.พ.20)')
    print('='*70)
    master = dict(existing) if existing else {}   # [M-1 FIX] ต่อยอดจากของเดิม ไม่เริ่มว่าง
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
        # [BUG-1b FIX 11.06.69] เดิม branch_no ตั้งเฉพาะ HQ ('00000') — สาขาได้ค่าว่าง
        #   (BR004 ยัง fallback parse จาก label ได้ แต่ตั้งตรง ๆ ปลอดภัย/อ่านง่ายกว่า)
        _m_brno = re.search(r'(\d{1,5})\s*$', branch)
        _brno = ('00000' if 'สำนัก' in branch
                 else _m_brno.group(1).zfill(5) if _m_brno else '')
        master[key_base] = {
            'name':name,'name_alt':name_alt,'tax_id':clean_tax_id(tax_id),
            'branch':branch,'branch_no':_brno,
            'iv_prefix':iv_prefix,
            'address_full':full_addr,'address_parts':parse_address_input(full_addr),
        }
        print(f'✅ "{key_base}"')
        idx += 1
    save_master(master)
    return master
