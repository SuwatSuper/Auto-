# -*- coding: utf-8 -*-
"""ปุ้มปุ้ย_ultimate_v9_modular — [SPLIT #3] entry/orchestration top (main + public surface).
shared scope → pukpui_modular_base ; ฟังก์ชันอื่น → pukpui_modular_funcs (re-export ครบ).
"""

from pukpui_modular_base import (   # [SPLIT #3] shared scope (explicit; contract re-export ผ่าน __all__)
    ANALYTICS_CFG, Counter, HTML, LEAN_REPORT,
    RULES, VERIFY_CFG, _D,
    _SYSTEM_ISSUES, _taxid_checksum_ok, _vat_tolerance, addon_check_withholding,
    apply_iv_period_crosscheck, apply_sheet_date_crosscheck, audit_text_num_summary, audit_today,
    build_clean_report, build_unit_index, check_duplicate_items, check_invoice_sequence,
    check_iv_date_sequence, check_product_typos, clean_tax_id, compute_bill_confidence,
    datetime, detect_iv_period_mismatch, display, display_executive_dashboard,
    display_low_confidence_bills, export_excel, export_verification_to_excel, flush_system_issues_to_disk, format_sys_summary,
    get_files_via_drive, get_files_via_upload, input_master_data, load_master,
    match_company, os, run_product_verification, state,
    summarize_by_company, sys, traceback,
)

from pukpui_modular_funcs import (   # [SPLIT #3] orchestration fns (re-export contract + main calls)
    _audit_core_crosschecks, _audit_core_rules, _emit_agent_notepad, _emit_company_summary,
    _is_real_master, _move_processed_files, _prune_old_reports, parse_all_files, print_audit_banner,
    reset_run_state, run_all_rules, run_analytics, run_audit_core,
    run_self_check,
)


def _ensure_utf8_console():
    """[M-4/ADR-063] กัน UnicodeEncodeError ตอน print ภาษาไทยใต้ locale ascii (เช่น LANG=C,
    บาง cron/systemd ที่ไม่ตั้ง locale) — รันยาวหลายปีบนเครื่อง/สภาพแวดล้อมต่างกัน เจอบ่อย.
    reconfigure stdout/stderr เป็น utf-8 (Python 3.7+). golden-neutral: เปลี่ยนแค่ encoding ขาออก
    ไม่แตะค่าใด ๆ ที่เข้า hash ; ถ้า reconfigure ไม่ได้ก็เงียบ (พฤติกรรมเดิม)."""
    for _s in (sys.stdout, sys.stderr):
        try:
            if hasattr(_s, 'reconfigure') and (getattr(_s, 'encoding', '') or '').lower().replace('-', '') != 'utf8':
                _s.reconfigure(encoding='utf-8')
        except Exception:
            pass


def main():
    reset_run_state()
    print_audit_banner()

    # [v9.2] โหมด "กด Run ปุ่มเดียว ไม่ต้องตอบคำถาม" — เปิดด้วย env PUKPUI_AUTO=1 (ตั้งไว้ใน .env แล้ว)
    #   VS Code (Python ext) โหลด .env ของ workspace ให้อัตโนมัติ → กด Run = วิ่งจบเอง
    _AUTO = (os.environ.get('PUKPUI_AUTO', '') or '').strip().lower() in ('1', 'y', 'yes', 'true', 'on')
    _SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

    # [v9.2 งาน A] เลิกสร้าง master stub ปลอมใน AUTO.
    #   เดิม: ไม่มี master → เขียน golden_snapshot.MASTER (บริษัททดสอบ 1 บริษัท) ทับ master_companies.json
    #   ปัญหา (correctness/integrity): (1) ผู้ใช้ใส่ master จริงไม่ได้ (ไฟล์มีของปลอมแล้ว)
    #                                  (2) ช่องชื่อบจ./เลขภาษีขึ้น "ตรง" หลอก ทั้งที่ไม่เคยเทียบ master จริง
    #   ใหม่: ไม่มี master จริง → รันด้วย {} ว่าง (engine ทน {} ได้ — พิสูจน์แล้ว) แล้ว composer
    #         บังคับช่องชื่อบจ./เลขภาษีเป็น "— ไม่มี master ตรวจไม่ได้" (master_present=False).
    #   เพิ่ม master จริง: รัน  เพิ่ม_master.py  (เมนู Run "➕ ใส่ Master") ครั้งเดียว แล้วใช้อัตโนมัติตลอด.
    _is_tty = getattr(sys.stdin, "isatty", lambda: False)()
    if _AUTO:
        master = load_master()
        # [v9.2 งาน A++] งานตรวจหลายพันบริษัท → ต้องสลับบริษัทได้ทุกครั้ง ไม่ใช่ค้างบริษัทเดียวตลอด.
        #   ในเทอร์มินัลจริง (TTY) จึง "ถามทุกครั้ง": ตรวจบริษัทเดิม หรือ ใส่บริษัทใหม่ (แทนที่ของเดิม).
        #   กัน headless/CI/เทส (stdin เป็น pipe/redirect) ค้าง: ถ้าไม่ใช่ TTY → ใช้ master ที่โหลดมาเงียบ ๆ.
        if _is_tty:
            try:
                if _is_real_master(master):
                    _names = list(master.keys())
                    _show = ', '.join(_names[:5]) + ('  ...' if len(_names) > 5 else '')
                    print('\n' + '=' * 70)
                    print(f'📂 Master ปัจจุบัน ({len(_names)} บริษัท): {_show}')
                    print('=' * 70)
                    if input('ตรวจ "บริษัทเดิม" นี้ไหม?  [Enter=เดิม / n=ใส่บริษัทใหม่] : ').strip().lower() == 'n':
                        master = input_master_data(ask_reuse=False)   # ใส่บริษัทใหม่ → แทนที่ของเดิม
                else:
                    print('\n' + '=' * 70)
                    print('📋 ยังไม่มี Master (ภ.พ.20) — จำเป็นต่อการตรวจ "ชื่อบจ. / เลขที่ผู้เสียภาษี"')
                    print('=' * 70)
                    if input('ใส่ Master ตอนนี้เลยไหม? [Y/n]: ').strip().lower() != 'n':
                        master = input_master_data(ask_reuse=False)
            except (EOFError, KeyboardInterrupt):
                print('   (ข้าม — รันต่อด้วย master ที่มี/ว่าง)')
    else:
        master = input_master_data()
    # กัน foot-gun: golden/regression เขียน stub ทดสอบทิ้งไว้ในโฟลเดอร์ได้ → อย่าหยิบมาตรวจจริง
    _master_present = _is_real_master(master)
    if _master_present:
        print(f'\n✅ Master: {len(master)} บริษัท')
    else:
        if master:
            print('ℹ️ master_companies.json ที่พบเป็นชุดทดสอบ (stub) — จะไม่ใช้ตรวจจริง')
        master = {}
        print('ℹ️ ไม่มี master จริง → รันต่อด้วย master ว่าง '
              '(ช่อง "ชื่อบจ." และ "เลขที่ผู้เสียภาษี" จะขึ้น "ไม่มี master ตรวจไม่ได้").')
        print('   เพิ่ม master ภายหลัง: รัน  เพิ่ม_master.py  (หรือเมนู Run "➕ ใส่ Master") ครั้งเดียว.')
    run_self_check(master)                   # v6: ตรวจ master JSON ก่อนเริ่มตรวจบิล (ทน {} ได้)

    print('\n' + '='*70)
    file_list = []
    _data_dir = None                              # [v9.2 งาน B] โฟลเดอร์ต้นทาง (ตั้งใน AUTO; ใช้ตอนย้ายไฟล์ที่ตรวจแล้ว)
    if _AUTO:
        # [v9.2 งาน B] AUTO: อ่าน .xls/.xlsx จากโฟลเดอร์ "พร้อมตรวจ" บนเดสก์ท็อป (ล็อก path) — ไม่ถาม
        #   เปลี่ยนที่เก็บได้ด้วย env PUKPUI_DATA_DIR (ใช้บน Linux/เทส) โดยไม่ต้องแก้โค้ด
        _data_dir = os.environ.get('PUKPUI_DATA_DIR') or r'C:\Users\User\Desktop\พร้อมตรวจ'
        try:
            file_list = get_files_via_drive(_data_dir)
            print(f'📂 [AUTO] พบ {len(file_list)} ไฟล์ใน "{os.path.abspath(_data_dir)}"')
        except Exception as e: print(f'⚠️ {e}'); return
    else:
        print('เลือกวิธีรับไฟล์:\n  1. โฟลเดอร์ปัจจุบัน (โฟลเดอร์ที่รันสคริปต์)\n  2. ระบุ path โฟลเดอร์เอง')
        choice = input('เลือก [1/2] (default=1): ').strip() or '1'
        if choice == '2':
            try:
                file_list = get_files_via_upload()   # จะถาม path ให้พิมพ์เอง
            except Exception as e: print(f'⚠️ {e}'); return
        else:
            try:
                file_list = get_files_via_drive('.')
                print(f'📂 พบ {len(file_list)} ไฟล์ใน "{os.path.abspath(".")}"')
            except Exception as e: print(f'⚠️ {e}'); return

    if not file_list: print('❌ ไม่มีไฟล์'); return

    # [OBJ-PERF / ADR-009] parse แบบขนาน (opt-in): ตั้ง env PUOPUY_PARALLEL=<workers≥2> เพื่อใช้ process pool
    #   ผลเท่า serial เป๊ะ (พิสูจน์ CI [8c] verify_parallel บนข้อมูลจริง). ไม่ตั้ง/0/1 = serial เดิม (default = golden path).
    #   parser กิน ~99% ของเวลา + ขนานข้ามไฟล์ได้ → เร็วขึ้นเกือบเชิงเส้นตามจำนวน core.
    _par_raw = (os.environ.get('PUOPUY_PARALLEL', '0') or '0').strip()
    try:
        _par_workers = int(_par_raw)
    except ValueError:
        _par_workers = 0
    # [L8] เตือนเมื่อตั้งค่าผิด (เช่น -2 / 2.5) แล้วถูกบีบเป็น serial เงียบ ๆ — เดิมไม่มี feedback
    if _par_raw not in ('', '0', '1') and _par_workers < 2:
        print(f'⚠️ PUOPUY_PARALLEL={_par_raw!r} ใช้ไม่ได้ (ต้องเป็นจำนวนเต็ม ≥2) → รัน serial')
    if _par_workers >= 2:
        try:
            from parallel_audit import parse_all_files_parallel
            print(f'⚙️  parse แบบขนาน {_par_workers} workers (ผลเท่า serial เป๊ะ)')
            all_bills, filename_issues = parse_all_files_parallel(file_list, workers=_par_workers)
        except Exception as e:
            print(f'⚠️ parallel ใช้ไม่ได้ ({e}) → ใช้ serial แทน')
            reset_run_state()   # [FIX] กัน state ครึ่ง ๆ ถ้า parallel ล้มกลาง merge ก่อน retry serial
            all_bills, filename_issues = parse_all_files(file_list)
    else:
        all_bills, filename_issues = parse_all_files(file_list)

    # === v6.2 OBSERVABILITY: สรุป + บันทึก audit trail ของ parse failure (sidecar) ===
    if state._SYSTEM_ISSUES:
        _by_code = Counter(i.get('code', 'SYS001') for i in state._SYSTEM_ISSUES)
        print(f'\n🩺 System issues (ตามรอยได้): {len(state._SYSTEM_ISSUES)} รายการ — '
              + ', '.join(f'{c}×{n}' for c, n in _by_code.items()))
        _logp = flush_system_issues_to_disk()
        if _logp:
            print(f'   📝 บันทึก audit trail → {os.path.abspath(_logp)}')
    else:
        print('\n🩺 System issues: ไม่มี (parse ครบทุกไฟล์/ชีตที่อ่านได้)')

    if not all_bills: print('❌ ไม่พบบิล'); return
    print(f'✅ พบ {len(all_bills)} บิล')

    # === คำนวณ parse confidence ทุกบิล (ใช้ในการแสดง low-confidence) ===
    for b in all_bills:
        compute_bill_confidence(b)

    # === PATCH4B (รายการซ้ำ) + 56 rules + IV/typo/summary ===
    #   เรียก "audit core เฟส 1" จุดเดียว (โค้ดจริง + ข้อความ + การ isolate อยู่ใน _audit_core_rules)
    #   log=print → main คงพิมพ์ทุกบรรทัดเหมือนเดิม. เส้น agent/golden ใช้ตัวเดียวกันแต่ log เงียบ.
    _core = _audit_core_rules(all_bills, master, isolate=True, log=print)
    _dup_items = _core['dup_items']
    iv_issues  = _core['iv_issues']
    typos      = _core['typos']
    summary    = _core['summary']

    display_executive_dashboard(all_bills, summary, iv_issues, typos, filename_issues, len(file_list))

    # === แสดงบิลที่ระบบอ่านไม่ชัด ต้องเช็คด้วยมือ ===
    display_low_confidence_bills(all_bills)

    # === v6: สรุป Text→ตัวเลข ที่ระบบกู้คืน (ความโปร่งใส) ===
    audit_text_num_summary(echo=True)

    # 📁 โฟลเดอร์ปลายทางสำหรับเก็บไฟล์รีพอร์ต  ←★ "จุดเดียว" ที่กำหนด path ปลายทางของรีพอร์ตทั้งหมด
    #   ค่าเริ่มต้น (v9): เก็บที่เดสก์ท็อป โฟลเดอร์ "รีพอร์ต" — ถ้ายังไม่มีโฟลเดอร์นี้ ระบบจะสร้างให้อัตโนมัติ
    #   อยากเปลี่ยนที่เก็บ: แก้ path ในเครื่องหมายคำพูดบรรทัด REPORT_DIR ด้านล่าง (ใช้ r'...' เสมอ กัน \ ใน path เพี้ยน)
    #   หรือ (ไม่ต้องแก้โค้ด) ตั้ง environment variable PUKPUI_REPORT_DIR ทับเป็นรายครั้งก็ได้
    REPORT_DIR = os.environ.get('PUKPUI_REPORT_DIR') or r'C:\Users\User\Desktop\รีพอร์ต'
    try:
        os.makedirs(REPORT_DIR, exist_ok=True)   # ถ้ายังไม่มีโฟลเดอร์ จะสร้างให้อัตโนมัติ
    except Exception as _e:                       # v8.4 STABILITY: path เขียนไม่ได้ (คนละ user/OS/สิทธิ์) → อย่าล้มทั้งรอบหลังประมวลผลเสร็จ
        REPORT_DIR = os.getcwd()
        print(f'⚠️ สร้างโฟลเดอร์รายงานไม่ได้ ({type(_e).__name__}) → บันทึกที่โฟลเดอร์ปัจจุบันแทน: {REPORT_DIR}')
    out = os.path.join(REPORT_DIR, f'audit_v58_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx')
    _report_ok = False                            # [v9.2 งาน B] True เมื่อรายงานออกสำเร็จ → ใช้ตัดสินใจย้ายไฟล์

    # PATCH 1+2: cross-checks — เรียก "audit core เฟส 2" จุดเดียว (behavior 100% เดิม)
    _audit_core_crosschecks(all_bills)       # DT004 (วันที่ vs งวดในเลข IV) + DOC001 (วันที่ vs ชื่อชีต)

    if LEAN_REPORT:
        # ---------- โหมดคลีน: 7 ชีต + แดชบอร์ดในตัว ----------
        print('\n📊 สร้างรายงานแบบคลีน (Executive)...')
        if build_clean_report(all_bills, summary, iv_issues, typos, filename_issues, out):
            try:
                display(HTML(f'<div style="background:#1F2A37;color:white;padding:24px;border-radius:10px;text-align:center;margin:20px 0;border-top:2px solid #B08D57;"><div style="font-size:18px;font-weight:600;">✅ รายงาน (คลีน) สำเร็จ</div><div style="font-size:14px;margin-top:8px;opacity:0.85;">{out}</div></div>'))
            except Exception: pass
            print(f'\n✅ ไฟล์รายงาน (คลีน 7 ชีต) บันทึกแล้ว → {os.path.abspath(out)}')
            print('   ชีต: Dashboard | Summary | ทุกบิล | รายการสินค้า | Error Report | High Risk | บิลซ้ำ')
            # [v9.1+] ออกไฟล์รายงานการทำงานของ agent (.txt) ข้าง Excel — advisory, reuse บิลในหน่วยความจำ
            _emit_agent_notepad(master, file_list, all_bills, _core, out, filename_issues)
            _emit_company_summary(all_bills, REPORT_DIR, master_present=_master_present, masters=master)
            _report_ok = True
        else:
            print('❌ สร้างรายงานคลีนไม่สำเร็จ')
    else:
        # ---------- โหมดเต็ม: ทุกชีต + addon + verification + analytics ----------
        if export_excel(all_bills, summary, iv_issues, typos, filename_issues, out):
            # [v9.2 STABILITY] run_addon_pack เป็น "shoulder feature" (ไม่ถูก port มาใน modular)
            #   เดิมเรียกตรง ๆ → NameError ทันทีถ้าโหมดเต็ม (LEAN_REPORT=False) เพราะไม่มี def/ import ใดผูกชื่อนี้
            #   import * บังจาก linter ไว้ (เป็นแค่ F405 ไม่ใช่ F821). ทำให้สอดคล้องกับสัญญาเดียวกับ
            #   agents/report_agent.py:65 (optional + พังไม่ล้มรายงานหลัก). config ปกติ LEAN_REPORT=True
            #   → branch นี้ dead อยู่แล้ว → golden path ไม่กระทบ. โหมดเต็ม: จาก crash → ข้ามอย่างปลอดภัย.
            _run_addon = globals().get('run_addon_pack')
            if _run_addon is not None:
                try:
                    _run_addon(all_bills, out)
                except Exception as _e_addon:
                    print(f'⚠️ addon pack ล้มเหลว ({type(_e_addon).__name__}) → ข้าม (ไม่กระทบรายงานหลัก)')
            if VERIFY_CFG['ENABLE']:
                print('\n' + '='*70)
                # v9 [STABILITY-FIX]: เดิมเรียก input() ตรง ๆ → ค้าง/พังด้วย EOFError
                #   เมื่อรันแบบไม่โต้ตอบ (CI/cron/subprocess/redirect). ทำให้ปลอดภัย:
                #     1) env PUOPUY_ONLINE_VERIFY = 1/0/y/n → ใช้ค่านั้น (ไม่ถาม)
                #     2) ไม่มี TTY (อัตโนมัติ) → default ออฟไลน์ (ไม่ค้าง)
                #     3) มี TTY → ถามตามเดิม; กด Ctrl-D/EOF → ออฟไลน์
                _env_ov = (os.environ.get('PUOPUY_ONLINE_VERIFY', '') or '').strip().lower()
                if _env_ov in ('1', 'y', 'yes', 'true', 'on'):
                    use_online = True
                elif _env_ov in ('0', 'n', 'no', 'false', 'off'):
                    use_online = False
                elif not sys.stdin or not sys.stdin.isatty():
                    print('   (ไม่มี TTY — ข้าม online search อัตโนมัติ; ตั้ง PUOPUY_ONLINE_VERIFY=1 ถ้าต้องการ)')
                    use_online = False
                else:
                    try:
                        use_online = input('ใช้ Tier 2 (online search)? [Y/n]: ').strip().lower() != 'n'
                    except EOFError:
                        use_online = False
                results = run_product_verification(all_bills, enable_online=use_online)
                if results and export_verification_to_excel(results, out):
                    display(HTML(f'<div style="background:linear-gradient(135deg,#7C3AED,#5B21B6);color:white;padding:20px;border-radius:10px;text-align:center;margin:16px 0;"><div style="font-size:16px;font-weight:600;">🔬 Product Verification เสร็จสิ้น</div><div style="font-size:13px;margin-top:6px;opacity:0.9;">{len(results)} รายการ → ดูชีต "Product Verification" ใน Excel</div></div>'))

            display(HTML(f'<div style="background:linear-gradient(135deg,#16A34A,#15803D);color:white;padding:24px;border-radius:10px;text-align:center;margin:20px 0;box-shadow:0 6px 16px rgba(22,163,74,0.25);"><div style="font-size:18px;font-weight:600;">✅ Export สำเร็จ</div><div style="font-size:14px;margin-top:8px;opacity:0.9;">{out}</div></div>'))
            print(f'\n✅ ไฟล์ผลลัพธ์ Excel บันทึกแล้ว → {os.path.abspath(out)}')
            # [v9.1+] ออกไฟล์รายงานการทำงานของ agent (.txt) ข้าง Excel — advisory, reuse บิลในหน่วยความจำ
            _emit_agent_notepad(master, file_list, all_bills, _core, out, filename_issues)
            _emit_company_summary(all_bills, REPORT_DIR, master_present=_master_present, masters=master)
            _report_ok = True

            if ANALYTICS_CFG['ENABLE']:
                print('\n' + '='*70)
                print('📊 ANALYTICS MODULE')
                print('='*70)
                if input('รัน Anomaly Dashboard (Plotly)? [Y/n]: ').strip().lower() != 'n':
                    try:
                        run_analytics(excel_path=out)
                    except Exception as e:
                        print(f'⚠️ Analytics fail: {e}')
                        traceback.print_exc()

    # [A5] สรุป SYS-* "ท้ายการรัน" — รวมกฎที่ crash ระหว่าง run_rules (ไม่เข้า bill['issues'])
    #   → ทำให้ "การข้ามกฎเงียบ" มองเห็นได้เสมอ (ตอนนี้ corpus = 0 SYS แต่อนาคตอาจมี). ไม่เปลี่ยน routing.
    print('\n' + format_sys_summary())
    flush_system_issues_to_disk()                 # re-flush ครบทุกเฟส (รวม rule SYS) — sidecar overwrite

    # [v9.2 งาน B] รายงานออกสำเร็จแล้ว (โหมด AUTO เท่านั้น) → ย้ายไฟล์ที่ตรวจแล้วออกจาก "พร้อมตรวจ"
    #   ไปเก็บใน รีพอร์ต/ตรวจแล้ว_<วันเวลา>/ เพื่อรอบหน้าจะได้ไม่ตรวจซ้ำ (ปลอดภัย: ย้ายเฉพาะตอน report สำเร็จ)
    if _AUTO and _report_ok:
        _move_processed_files(file_list, _data_dir, REPORT_DIR)

    # [M-3/ADR-062] เก็บกวาดรายงานเก่า (กันดิสก์โตไม่จำกัดเมื่อรันยาวหลายปี).
    #   ปิดโดย default — เปิดด้วย env PUKPUI_REPORT_RETENTION_DAYS=N (เช่น 90).
    _prune_old_reports(REPORT_DIR, os.environ.get('PUKPUI_REPORT_RETENTION_DAYS', '0'))

__all__ = [
    # rules / cross-check engine
    'RULES', 'match_company', 'run_all_rules',
    'apply_iv_period_crosscheck', 'apply_sheet_date_crosscheck',
    'check_duplicate_items', 'check_invoice_sequence', 'check_iv_date_sequence',
    'check_product_typos',
    # orchestration (นิยามใน monolith)
    'main', 'parse_all_files', 'reset_run_state', 'run_audit_core',
    # ingest / files
    'get_files_via_drive', 'get_files_via_upload',
    # analytics
    'addon_check_withholding', 'build_unit_index', 'compute_bill_confidence',
    'summarize_by_company',
    # reporting
    'build_clean_report', 'export_excel',
    # leaf-util contract (core_access bind ตรง)
    'clean_tax_id', '_taxid_checksum_ok', '_D', '_vat_tolerance',
    # shared state (by-reference)
    '_SYSTEM_ISSUES',
    # agent dynamic-lookup (core.get ใน verification lenses — สัญญาประเภทที่ 3)
    'audit_today', 'detect_iv_period_mismatch',
]

if __name__ == '__main__':
    _ensure_utf8_console()   # [M-4/ADR-063] กัน print ไทย crash ใต้ locale ascii
    try: main()
    except KeyboardInterrupt: print('\n⏹️ ยกเลิก')
    except Exception as e:
        print(f'\n❌ Error: {e}'); traceback.print_exc()
