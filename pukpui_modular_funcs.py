# -*- coding: utf-8 -*-
"""pukpui_modular_funcs — [SPLIT #3 slice-2] ฟังก์ชัน orchestration (ยกเว้น main)
verbatim จาก monolith เดิม; ดึง shared scope จาก pukpui_modular_base แบบ explicit.
"""

from pukpui_modular_base import (   # [SPLIT #3] shared scope (explicit)
    ANALYTICS_CFG, APP_VERSION, CFG, CONSTRUCTION_DICT,
    Counter, HTML, PYTHAINLP_AVAILABLE, RULES,
    SEVERITY_ICON, THAI_TYPO_PATTERNS, VERIFY_CFG, _CAPTURED_HTML,
    _FUZZY_DICT_CACHE, _IN_NOTEBOOK, _PYTHAINLP_CACHE, _trim_cache,
    apply_abbrev_invoice_check, apply_bad_date_check,
    apply_iv_period_crosscheck, apply_missing_date_check, apply_missing_iv_check, apply_sheet_date_crosscheck, audit_text_num_reset, build_dashboard_figs,
    build_unit_index, check_duplicate_items, check_filename_consistency, check_invoice_sequence,
    check_iv_date_sequence, check_product_typos, clean_tax_id, cluster_products,
    datetime, detect_price_outliers, detect_unit_anomalies, display,
    file_guard, gc, load_audit_excel, log_system_issue,
    os, parse_file, parse_filename, render_dashboard_html,
    run_rules, state, summarize_by_company, system_issues_reset,
    tqdm, web_state_reset,
)


def run_analytics(excel_path=None, sheets=None):
    if not ANALYTICS_CFG['ENABLE']:
        print('⏭️ Analytics Module ปิดอยู่')
        return None
    print('\n' + '='*70)
    print('📊 ANALYTICS MODULE v1.0 — Pattern Clustering + Plotly Dashboard')
    print('='*70)
    if sheets is None:
        if not excel_path:
            print('❌ ต้องระบุ excel_path หรือ sheets')
            return None
        sheets = load_audit_excel(excel_path)
        if not sheets: return None
    items = sheets.get('รายการสินค้า')
    if items is None or len(items) == 0:
        print('⚠️ ไม่พบชีต "รายการสินค้า"')
        return None
    print(f'\n🔬 Clustering ({ANALYTICS_CFG["CLUSTERING_METHOD"]}): {len(items)} items')
    df_clustered = cluster_products(items)
    n_clusters = df_clustered['_cluster_id'].nunique()
    print(f'   พบ {n_clusters} clusters | unique categories: {df_clustered["_category"].nunique()}')
    print('🔍 Anomaly detection...')
    df_clustered = detect_price_outliers(df_clustered)
    df_clustered = detect_unit_anomalies(df_clustered)
    price_out = df_clustered['_price_outlier'].sum() if '_price_outlier' in df_clustered else 0
    unit_out = df_clustered['_unit_rare'].sum() if '_unit_rare' in df_clustered else 0
    print(f'   ราคาผิดปกติ: {price_out} | หน่วยผิดปกติ: {unit_out}')
    print('🎨 สร้าง Plotly figures...')
    figs = build_dashboard_figs(sheets, df_clustered)
    print(f'   สร้าง {len(figs)} charts')
    out_html = ANALYTICS_CFG['DASHBOARD_HTML']
    if '/' not in out_html and excel_path:
        out_html = os.path.join(os.path.dirname(excel_path) or '.', out_html)
    stats = {
        'รายการทั้งหมด': len(items),
        'Clusters': n_clusters,
        'หมวด': df_clustered['_category'].nunique(),
        'ราคาผิดปกติ': int(price_out),
        'หน่วยผิดปกติ': int(unit_out),
    }
    if render_dashboard_html(figs, out_html, stats):
        print(f'\n✅ Dashboard: {out_html}')
        try:
            display(HTML(f'<div style="padding:14px;background:#16A34A;color:white;'
                        f'border-radius:8px;text-align:center;font-weight:600;">'
                        f'📊 Dashboard พร้อมแล้ว: {out_html} ({len(figs)} charts)</div>'))
            print(f'📊 Dashboard บันทึกแล้ว → {os.path.abspath(out_html)}')
        except Exception: pass
        return {'sheets':sheets,'clusters':df_clustered,'figs':figs,'output':out_html}
    return None


def run_self_check(master):
    """v6 SELF-CHECK (ตอนเปิดโปรแกรม): ตรวจ Master JSON ว่าคีย์ครบ/เลขภาษีถูก
    ก่อนเริ่มตรวจบิล — เตือนล่วงหน้า กันผลออกผิดเพราะ master พัง/แก้มือคีย์หาย
    ห่อ try/except ทั้งหมด → พังไม่ได้ ไม่บล็อกการทำงาน
    """
    print('\n' + '─'*70)
    print('🩺 SELF-CHECK: ตรวจความสมบูรณ์ของ Master ก่อนเริ่ม')
    try:
        if not isinstance(master, dict) or not master:
            print('   ⚠️ master ว่าง/ไม่ใช่ dict — ข้ามการตรวจ')
            return
        need = ('name', 'tax_id', 'address_full', 'address_parts')
        miss = {k: [] for k in need}
        bad_tax = []
        for key, m in master.items():
            if not isinstance(m, dict):
                for k in need: miss[k].append(str(key))
                continue
            for k in need:
                if not m.get(k):
                    miss[k].append(str(key))
            tid = clean_tax_id(m.get('tax_id', ''))
            if len(tid) != 13:
                bad_tax.append(f"{key} ({len(tid)} หลัก)")
        n = len(master)
        problems = sum(len(v) for v in miss.values()) + len(bad_tax)
        if problems == 0:
            print(f'   ✅ Master {n} บริษัท — คีย์ครบทุกตัว เลขภาษี 13 หลักทุกราย')
            return
        for k in need:
            if miss[k]:
                ex = ', '.join(miss[k][:3]) + (f' ...(+{len(miss[k])-3})' if len(miss[k]) > 3 else '')
                print(f"   ⚠️ ขาดคีย์ '{k}': {len(miss[k])}/{n} ราย → {ex}")
        if bad_tax:
            ex = ', '.join(bad_tax[:3]) + (f' ...(+{len(bad_tax)-3})' if len(bad_tax) > 3 else '')
            print(f"   ⚠️ เลขภาษีไม่ครบ 13 หลัก: {len(bad_tax)} ราย → {ex}")
        print('   ℹ️ บริษัทที่คีย์หายจะถูกข้ามบางกฎ (โปรแกรมไม่ล้ม) — แนะนำแก้ master ให้ครบ')
    except Exception as e:
        print(f'   ⚠️ self-check ทำงานไม่ครบ ({type(e).__name__}) — ข้ามไป ไม่กระทบการตรวจบิล')


def reset_run_state():
    """ล้าง global state ต้นรอบ (กัน state bleed ข้ามรอบใน session ยาว). ไม่แตะ logic."""
    # v5.9 FIX-2(state): ล้าง global state ตอนต้น กันรันซ้ำในเซสชันเดียว (Colab/Jupyter) แล้วค่าค้าง
    VERIFY_CFG['TIER1_CHECK_ONLY'] = False   # เดิมถูก set True ค้างถ้ารอบก่อนเลือก offline
    web_state_reset()                        # รีเซ็ตตัวนับ request / circuit breaker
    state._FUZZY_DICT_CACHE.clear()                # ล้าง fuzzy cache (กันผลค้างข้ามรอบ)
    try: state._PYTHAINLP_CACHE.clear()            # v6.1: ล้าง spell-cache ด้วย กันโตข้ามรอบใน session ยาว (Colab)
    except Exception: pass
    # [P1-FIX-STATECACHE] ล้าง lazy caches ใน state.py ด้วย — เดิมไม่ล้าง → ค้างข้ามรอบ
    #   ทั้งหมดเป็น cache ที่ rebuild ได้ (lazy-init guard มีอยู่ทุกจุดใช้งาน) → ล้างแล้วผลตรวจเหมือนเดิม
    #   build จาก CONSTRUCTION_DICT/CFG ที่เป็น static → rebuild ได้ค่าเดิมเป๊ะ (ไม่กระทบ determinism)
    state._CONSTRUCTION_DICT_BY_LEN = None
    state._PYTHAINLP_STEM_BLOCKLIST = None
    state._CAT_KEYWORDS = None
    state._PRODUCT_WHITELIST = None
    system_issues_reset()                    # v6.2: ล้าง audit trail (system issues) ของรอบก่อน กัน state bleed
    audit_text_num_reset()                   # v6: ล้าง log Text→ตัวเลข ของรอบก่อน
    # [ADR-172/BUGHUNT] ล้างดัชนี cross-bill (อยู่นอก state.py เดิมไม่ถูกล้าง): ถือบิล batch เก่า = RAM ค้าง
    #   + list เดิมแก้ in-place ข้ามรอบ → fingerprint ไม่ขยับ → TAX008 ใช้ดัชนีค้าง (probe พิสูจน์).
    #   rebuild อัตโนมัติที่การเรียกแรกของรอบใหม่ (fp=None ≠ ทุก fp) → ผลตรวจเหมือนเดิมเป๊ะ.
    try:
        from rules_engine import _XBILL_IDX_CACHE as _xc
        from rules_engine_rules_c import _BS3_NAME_IDX as _bc
        _xc.update(fp=None, tax={}, file={}); _bc.update(fp=None, idx={})
    except Exception:
        pass
    if not _IN_NOTEBOOK:
        try: _CAPTURED_HTML.clear()          # ล้าง HTML buffer (เฉพาะโหมด VS Code/.py)
        except Exception: pass


def print_audit_banner():
    """พิมพ์ banner สรุป rules/fixes ต้นรอบ (side-effect: print). ไม่แตะ logic."""
    print('='*70)
    print(f'🧾 Invoice Audit System v{APP_VERSION} — {len(RULES)} Rules + Analytics + ITM Upgrade')
    print('='*70)
    print(f'📋 Rules: {len(RULES)} กฎ')
    sev_count = Counter(r['severity'] for r in RULES.values())
    for sev in ['CRITICAL','ERROR','WARNING','INFO']:
        if sev in sev_count: print(f"   {SEVERITY_ICON[sev]} {sev}: {sev_count[sev]}")
    print(f'🔬 Product Verification 2-Tier: {"ON" if VERIFY_CFG["ENABLE"] else "OFF"}')
    print(f'🇹🇭 Thai Typo: {len(THAI_TYPO_PATTERNS)} patterns | Dict: {len(CONSTRUCTION_DICT)} คำ')
    print(f'🔧 PyThaiNLP: {"✅" if PYTHAINLP_AVAILABLE else "❌"}')
    print('─'*70)
    print(f'🆕 v5.8 fixes:')
    print(f'   [FIX-1] TAX001  : wider tax_id scan (no keyword required)')
    print(f'   [FIX-2] ADDR001 : ซอย fuzzy match + ซ. shorthand')
    print(f'   [FIX-3] BR001/2 : สแกนรหัสสาขาทั้ง block')
    print(f'   [FIX-4] NBSP    : อธิบาย NBSP/ZWS/BOM ใน detail')
    print(f'   [FIX-5] PyThaiNLP: partial whitelist + sim guard {CFG["PYTHAINLP_SIM_THRESHOLD"]}%')
    print(f'   [FIX-6] IV gap  : split severity (consecutive≥{CFG["IV_GAP_CRITICAL_RUN"]}=CRITICAL)')
    print(f'   [FIX-7] ITM001  : plausible discount detection ({CFG["DISCOUNT_MIN_PCT"]}-{CFG["DISCOUNT_MAX_PCT"]}%)')
    print(f'   [FIX-8] DT001   : รองรับ filename month range')
    print(f'   [FIX-9] ITM007  : skip ถ้าชื่อสั้นแต่ถูกต้อง (dict/keyword/spec)')


def parse_all_files(file_list):
    """parse ทุกไฟล์ (ห่อ try/except ต่อไฟล์ + gc/cache-trim เป็นช่วง). behavior 100% เดิม.
    Returns: (all_bills, filename_issues)."""
    print(f'\n📂 Parsing {len(file_list)} ไฟล์...')
    all_bills = []
    filename_issues = []
    _failed_files = []   # v6.1 FAILSAFE: เก็บรายชื่อไฟล์ที่อ่านไม่สำเร็จ เพื่อสรุปท้ายงาน
    _gc_every = max(1, int(CFG.get('GC_EVERY_N_FILES', 50)))   # v6.2 MEMORY: รอบ flush หน่วยความจำ
    for _fidx, fp in enumerate(tqdm(file_list, desc='Parsing'), 1):
        # [OBJ-OFFLINE/untrusted-input] กันไฟล์อันตราย (zip-bomb/ใหญ่ผิดปกติ) ก่อนแตะ parser
        #   ไฟล์ใบกำกับจริงผ่านทั้งหมด (limit กว้างพอ) → ไม่กระทบผล/golden hash ;
        #   ปฏิเสธเฉพาะไฟล์พยาธิสภาพ → บันทึก SYS001 + ข้าม (เหมือนไฟล์อ่านไม่สำเร็จ)
        _safe, _why = file_guard.inspect_file_safety(fp)
        if not _safe:
            _failed_files.append((os.path.basename(fp), _why))
            print(f'   ⛔ ข้ามไฟล์ {os.path.basename(fp)} (untrusted/ไม่ปลอดภัย): {_why}')
            log_system_issue('SYS001', 'Unsafe File Skipped', _why,
                             severity='ERROR', file=os.path.basename(fp), echo=False)
            continue
        # v6.1 FAILSAFE: ห่อการประมวลผล "ทั้งไฟล์" ไว้ใน try — ไฟล์เดียวพัง = ข้ามไฟล์นั้น
        #   ไม่ใช่ทำให้ทั้ง batch ล้ม (เดิม parse_filename / merge_continuation_bills /
        #   check_iv_format / check_filename_consistency อยู่นอก try → 1 ไฟล์เพี้ยน = เสียงานทั้งหมด)
        try:
            finfo = parse_filename(fp)
            bills = parse_file(fp)
            for b in bills: b['file_info'] = finfo
            all_bills.extend(bills)
            filename_issues.extend(check_filename_consistency(os.path.basename(fp), bills, finfo))
        except Exception as _fe:
            _failed_files.append((os.path.basename(fp), f'{type(_fe).__name__}: {str(_fe)[:120]}'))
            print(f'   ⚠️ ข้ามไฟล์ {os.path.basename(fp)} (อ่านไม่สำเร็จ): {type(_fe).__name__}: {str(_fe)[:120]}')
            # v6.2 OBSERVABILITY (TARGET 2): บันทึก file-level failure ลง audit trail ด้วย
            log_system_issue('SYS001', 'File Processing Failure',
                             'ประมวลผลไฟล์ล้มเหลว — ทั้งไฟล์ถูกข้าม',
                             severity='ERROR', file=os.path.basename(fp), exc=_fe, echo=False)
            continue
        finally:
            # v6.2 MEMORY (TARGET 1): คุม RAM ให้ "แบนราบ" ระหว่าง parse ไฟล์จำนวนมาก
            #   - ตัด cache ที่อาจโตไม่จำกัด (สะกดคำ/fuzzy-dict)
            #   - บังคับ gc เป็นช่วง ๆ → คืน DataFrame ชั่วคราว/ลด memory fragmentation
            #   ทั้งหมดนี้ "ผลตรวจเหมือนเดิม" (cache ตัดแล้ว recompute ได้, gc ไม่กระทบข้อมูล)
            if (_fidx % _gc_every) == 0:
                _trim_cache(_PYTHAINLP_CACHE, CFG.get('MAX_PYTHAINLP_CACHE', 50000))
                _trim_cache(_FUZZY_DICT_CACHE, CFG.get('MAX_FUZZY_DICT_CACHE', 50000))
                gc.collect()
    gc.collect()   # v6.2: เก็บกวาดรอบสุดท้ายหลัง parse ครบทุกไฟล์
    # [ADR-174/BUGHUNT] นับ "เปิดไฟล์ไม่ได้" (File Open Failure) เข้าสรุปท้ายรันด้วย — เดิม exception
    #   ถูกกลืนใน parse_file (คืน bills=[] ปกติ) → ไม่เคยเข้า _failed_files → สรุป "มี N ไฟล์อ่านไม่สำเร็จ"
    #   นับขาด ทั้งที่มีเตือน 1 บรรทัดกลาง progress bar (เลื่อนหายง่าย) — operator เข้าใจผิดว่าอ่านครบ.
    #   print/summary-only → ผลตรวจ/golden ไม่ขยับ.
    try:
        _seen = {fn for fn, _ in _failed_files}
        for _iss in list(state._SYSTEM_ISSUES):
            if _iss.get('name') == 'File Open Failure' and _iss.get('file') and _iss['file'] not in _seen:
                _failed_files.append((_iss['file'], (_iss.get('detail') or 'เปิด/อ่านไฟล์ไม่ได้')[:120]))
                _seen.add(_iss['file'])
    except Exception:
        pass
    if _failed_files:
        print(f'\n⚠️ มี {len(_failed_files)} ไฟล์อ่านไม่สำเร็จ ถูกข้าม (บิลจากไฟล์อื่นยังประมวลผลครบ):')
        for _fn, _er in _failed_files[:20]:
            print(f'   • {_fn} — {_er}')
        if len(_failed_files) > 20:
            print(f'   ... และอีก {len(_failed_files)-20} ไฟล์')
    return all_bills, filename_issues


def run_all_rules(all_bills, master):
    """รัน 56 rules ต่อบิล (กันชนชั้นสุดท้ายต่อบิล). mutates all_bills in place. ไม่แตะ logic."""
    print(f'\n🛡️ Running {len(RULES)} rules...')
    unit_index = build_unit_index(all_bills)

    # v5.9 FIX-2: ส่ง all_bills ตรง ๆ เข้า run_rules แทนการฝังใน bill dict
    # (ลบ circular reference: เดิม bill แต่ละตัวแบก _all_bills_ref ซึ่งชี้กลับมาที่ list ตัวเอง)
    for b in tqdm(all_bills, desc='Validating'):
        try:
            run_rules(b, master, b.get('file_info', {}), unit_index=unit_index, all_bills_ref=all_bills)
        except Exception as _re:
            # v6: กันชนชั้นสุดท้าย — บิลเดียวพังต้องไม่ล้มทั้ง batch (match_company อยู่นอก try ภายใน run_rules)
            # v8.4 STABILITY: บิลที่ run_rules พังกลางคันจะยังไม่มี master_key/match_score → เติม default
            #   กัน KeyError ภายหลังตอน summarize/dashboard (ซึ่งอ่าน b['master_key'] ตรงๆ) = ไม่ให้ล้มทั้งรอบ
            b.setdefault('master_key', '(ไม่พบใน master)')
            b.setdefault('match_score', 0)
            log_system_issue('SYS001', 'Rule Engine Failure',
                             'run_rules ล้มทั้งบิล — ข้ามบิลนี้ (ไม่ล้มทั้ง batch)',
                             severity='ERROR', file=b.get('file',''), sheet=str(b.get('sheet','')),
                             exc=_re, echo=False)


def _audit_core_rules(all_bills, master, isolate=True, log=None):
    """เฟส 1 ของ audit core (ก่อนการแสดงผลใน main): ตรวจรายการซ้ำ → 56 rules →
    ลำดับ IV → คำสะกด → สรุปต่อบริษัท. mutate all_bills ในที่ (run_all_rules เติม issue).

    Args:
        all_bills:  list บิลที่ parse แล้ว (จะถูก mutate โดย run_all_rules)
        master:     master data ของบริษัท
        isolate:    True = ห่อ iv/typos/summary ด้วย try/except (P1-FIX-ISOLATION) แล้ว log SYS003
                    ถ้าพัง — งานที่เหลือยังออกครบ. False = ปล่อย exception ลอยขึ้น (ใช้ตอน debug).
        log:        callable(str) สำหรับข้อความ console (เช่น print). None = เงียบ.

    Returns:
        dict: {'dup_items','iv_seq','iv_date','iv_issues','typos','summary'}
              (iv_issues = iv_seq + iv_date — ค่าที่รายงานใช้; iv_seq/iv_date แยกไว้ให้ golden hash)
    """
    emit = log if callable(log) else (lambda _m: None)

    # --- ตรวจรายการสินค้าซ้ำ (PATCH4B) + พิมพ์สรุปแบบเดียวกับ main เดิม ---
    dup_items = check_duplicate_items(all_bills)
    if dup_items:
        emit(f'\n⚠️  PATCH4B: พบรายการซ้ำ {len(dup_items)} กลุ่ม (อาจ parse บิลซ้ำ):')
        for d in dup_items[:20]:
            emit(f"   • {d['ไฟล์']}/{d['ชีต']} IV:{d['IV']} — \"{d['รายการ']}\" "
                 f"ยอด {d['ยอด']} ซ้ำ {d['พบซ้ำ']} ครั้ง (ลำดับ {d['ลำดับ']})")
        if len(dup_items) > 20:
            emit(f'   ... และอีก {len(dup_items)-20} กลุ่ม')
    else:
        emit('✅ PATCH4B: ไม่พบรายการสินค้าซ้ำ')

    # --- 56 rules (พิมพ์ banner/tqdm ของตัวเองอยู่แล้ว — ไม่ผ่าน emit, พฤติกรรมเดิม) ---
    run_all_rules(all_bills, master)

    # --- cross-bill checks: ห่อแยกตาม isolate flag (semantics ตรงกับ main เป๊ะ) ---
    if isolate:
        # main ห่อ (check_invoice_sequence + check_iv_date_sequence) ไว้ใน try เดียว →
        # ถ้าตัวใดตัวหนึ่งพัง iv_issues ว่างทั้งคู่. ที่นี่รักษา semantics นั้น (both → []).
        try:
            iv_seq = check_invoice_sequence(all_bills)
            iv_date = check_iv_date_sequence(all_bills)
        except Exception as _ve:
            iv_seq, iv_date = [], []
            emit(f'   ⚠️ IV sequence check ล้มเหลว — ข้ามส่วนนี้: {type(_ve).__name__}: {str(_ve)[:120]}')
            log_system_issue('SYS003', 'IV Sequence Check Failure',
                             'ตรวจลำดับ IV ล้มเหลว — ข้ามผลส่วนนี้ (บิล/กฎอื่นยังครบ)',
                             severity='ERROR', exc=_ve, echo=False)
        try:
            typos = check_product_typos(all_bills)
        except Exception as _ve:
            typos = []
            emit(f'   ⚠️ Product typo check ล้มเหลว — ข้ามส่วนนี้: {type(_ve).__name__}: {str(_ve)[:120]}')
            log_system_issue('SYS003', 'Product Typo Check Failure',
                             'ตรวจคำสะกดสินค้าล้มเหลว — ข้ามผลส่วนนี้ (บิล/กฎอื่นยังครบ)',
                             severity='ERROR', exc=_ve, echo=False)
        try:
            summary = summarize_by_company(all_bills)
        except Exception as _ve:
            summary = {}
            emit(f'   ⚠️ Summary ล้มเหลว — ใช้ค่าว่าง: {type(_ve).__name__}: {str(_ve)[:120]}')
            log_system_issue('SYS003', 'Summary Failure',
                             'สรุปต่อบริษัทล้มเหลว — ใช้ค่าว่าง (บิล/กฎยังครบ)',
                             severity='ERROR', exc=_ve, echo=False)
    else:
        iv_seq = check_invoice_sequence(all_bills)
        iv_date = check_iv_date_sequence(all_bills)
        typos = check_product_typos(all_bills)
        summary = summarize_by_company(all_bills)

    return {
        'dup_items': dup_items,
        'iv_seq': iv_seq,
        'iv_date': iv_date,
        'iv_issues': iv_seq + iv_date,   # ← ค่าที่ Report/dashboard ใช้ (ตรงกับ main เดิม)
        'typos': typos,
        'summary': summary,
    }


def _audit_core_crosschecks(all_bills):
    """เฟส 2 ของ audit core (หลังการแสดงผลใน main): cross-check ที่ "เติม issue ลงบิล".
    ต้องรัน *หลัง* summary และ *ครั้งเดียว* (เรียกซ้ำ = issue ซ้ำ → golden hash เปลี่ยน)."""
    # [ARCH] หุ้มแต่ละ crosscheck แยกกัน: เดิมเรียกตรง ๆ ไม่มี try → ถ้าตัวใดตัวหนึ่ง throw จะดึง
    #   crosscheck ที่เหลือร่วงทั้งหมด + ครัชหลุดถึง main. apply_* ปลอดภัยอยู่แล้ววันนี้ → no-op (golden
    #   ไม่ขยับ); กัน regression อนาคต (แก้ตัวใดตัวหนึ่งแล้ว throw จะไม่ทำคลาส crosscheck หายเงียบทั้งชุด).
    for _fn, _name in (
        (apply_iv_period_crosscheck, 'DT004 (วันที่ vs งวดในเลข IV)'),
        (apply_sheet_date_crosscheck, 'DOC001 (วันที่ vs ชื่อชีต)'),
        (apply_missing_date_check, 'DT005 (บิลไม่มีวันที่)'),
        (apply_missing_iv_check, 'IV005 (บิลไม่มีเลขที่ใบกำกับ)'),
        (apply_bad_date_check, 'DT006 (วันที่ไม่มีจริงในปฏิทิน)'),
        (apply_abbrev_invoice_check, 'IV006 (ใบกำกับภาษีอย่างย่อ)'),
    ):
        try:
            _fn(all_bills)
        except Exception as _e:
            try:
                from diagnostics import log_system_issue
                log_system_issue(code='SYS001', severity='WARNING', category='ระบบ',
                                 name=f'crosscheck ล้มเหลว: {_name}',
                                 detail=f'{type(_e).__name__}: {_e}', echo=True)
            except Exception:
                print(f'⚠️ crosscheck {_name} ล้มเหลว ({type(_e).__name__}) — ข้าม')


def run_audit_core(all_bills, master, isolate=True, log=None):
    """ลำดับศักดิ์สิทธิ์เต็ม = เฟส1 + เฟส2 (ไม่มีการแสดงผลคั่น).

    ใช้โดยเส้นที่ไม่ต้องแทรกแดชบอร์ดระหว่างเฟส: agents.orchestrator และ golden_master.
    คืน dict เดียวกับ _audit_core_rules (เพิ่มการันตีว่า crosscheck ถูกรันแล้ว 1 ครั้ง)."""
    result = _audit_core_rules(all_bills, master, isolate=isolate, log=log)
    _audit_core_crosschecks(all_bills)
    return result


def _emit_agent_notepad(master, file_list, all_bills, core_result, out_path, filename_issues):
    """[v9.1+ ADVISORY] ออกไฟล์ "รายงานสรุปการทำงานของ agent" (agent_report.txt) ข้าง Excel.

    ★ ทำไมปลอดภัย/เร็ว (เสี่ยงศูนย์ ต่อผลตรวจหลัก):
      - reuse บิลที่ "parse + ตรวจ (rules+crosscheck) เสร็จแล้ว" ในหน่วยความจำ → ไม่ parse ซ้ำ
        (ImportAgent/รันกฎไม่ถูกเรียกอีก) → เพอร์ฟอร์แมนซ์ parse ไม่ตก
      - รันเฉพาะ agent ชั้น "อ่านอย่างเดียว" (review/tier2/ai/synthesis/super) → ไม่ mutate bills,
        ไม่ rerun กฎ/crosscheck (กัน issue ซ้ำ) → ผลตรวจ/Excel/golden hash ไม่เปลี่ยน
      - ห่อ try/except ทุกชั้น: เลเยอร์ agent มีปัญหาใด ๆ → ข้ามเงียบ ไม่ล้มงานหลัก
        (Excel ถูกเขียนเสร็จก่อนเรียกฟังก์ชันนี้เสมอ — ไฟล์ผลลัพธ์หลักจึงปลอดภัย 100%)

    core_result : dict จาก _audit_core_rules/run_audit_core (มี iv_seq/iv_date/iv_issues/typos/
                  summary/dup_items) — เติมลง PipelineContext ให้ตรงกับที่ orchestrator เติมเอง
    out_path    : พาธไฟล์ Excel ที่เพิ่งเขียน (ใช้หา report_dir + อ้างอิงในรายงาน)
    """
    # ให้เลเยอร์ agent ใช้ "โมดูล orchestrator ที่กำลังรันอยู่" เป็น core (กันสำเนาที่ 2 + กัน gate fail)
    #   [FIX] เดิมใช้ __name__ = 'pukpui_modular_funcs' (โมดูลที่ฟังก์ชันนี้อยู่หลังซอย monolith) — ผิด:
    #   โมดูลนี้ไม่มี io symbols (get_files_via_drive ฯลฯ) ที่ core_access._REQUIRED ต้องการ → gate ล้ม →
    #   รายงาน Notepad ถูกข้ามเงียบทุกครั้ง. ที่ถูก: ชี้ไปยังโมดูลที่ "มี run_audit_core" จริง —
    #   รันตรง (python ไฟล์หลัก) = '__main__' ; ถูก import = 'ปุ้มปุ้ย_ultimate_v9_modular'. ทั้งคู่ไม่โหลดซ้ำ.
    import sys as _sys
    for _cand in ('__main__', 'ปุ้มปุ้ย_ultimate_v9_modular'):
        if hasattr(_sys.modules.get(_cand), 'run_audit_core'):
            os.environ.setdefault('PUKPUI_MAIN_MODULE', _cand)
            break
    try:
        from agents.contracts import PipelineContext
        from agents.orchestrator import run_pipeline_advisory
    except Exception as _e:
        print(f'   ℹ️ ข้ามรายงานการทำงาน agent (โหลดเลเยอร์ agent ไม่ได้: '
              f'{type(_e).__name__}: {str(_e)[:120]})')
        return
    try:
        cr = core_result or {}
        report_dir = os.path.dirname(os.path.abspath(out_path))
        ctx = PipelineContext(
            master=master or {},
            file_list=list(file_list or []),
            options={'report_dir': report_dir, 'write_report': False, 'write_note': True},
            bills=all_bills,
            filename_issues=list(filename_issues or []),
            iv_issues=cr.get('iv_issues', []),
            iv_seq=cr.get('iv_seq', []),
            iv_date=cr.get('iv_date', []),
            typos=cr.get('typos', []),
            summary=cr.get('summary', {}),
            dup_items=cr.get('dup_items', []),
            report_path=os.path.abspath(out_path),
        )
        run_pipeline_advisory(ctx, logger=None)   # เงียบ — ไม่รบกวน log หลัก
        _np = ctx.results.get('notepad')
        _path = (_np.summary or {}).get('path') if _np else None
        if _path:
            print(f'📝 รายงานการทำงาน Agent (Notepad) → {os.path.abspath(_path)}')
        else:
            print('   ℹ️ สร้างรายงานการทำงาน agent แล้ว (ไม่ได้เขียนไฟล์)')
    except Exception as _e:                         # ADVISORY: ห้ามล้มงานหลักเด็ดขาด
        print(f'   ⚠️ ข้ามรายงานการทำงาน agent — {type(_e).__name__}: {str(_e)[:140]}')


def _emit_company_summary(all_bills, report_dir, master_present=True, masters=None):
    """[v9.2 ADVISORY] ออกสรุป "ต่อบริษัท × เดือน" ภาษาคน (company_summary.txt/.xlsx) ข้าง Excel.

    ★ ปลอดภัย/เสี่ยงศูนย์ต่อผลตรวจหลัก:
      - อ่าน all_bills ที่ตรวจเสร็จแล้วในหน่วยความจำ (ไม่ parse/ไม่ rerun กฎ → ไม่ mutate)
      - เขียน "ไฟล์ใหม่" คนละไฟล์กับ Excel หลัก → golden Excel/hash ไม่เปลี่ยน
      - try/except: เลเยอร์ viewer พังใด ๆ → ข้ามเงียบ ไม่ล้มงานหลัก
    ใช้ 10 viewers + composer ใน super_ultra_viewer.py (แปลง 59 รหัส → คำภาษาคน + คัดเลน).
    """
    try:
        import super_ultra_viewer as _suv
        _t, _x, _rows = _suv.emit_for_bills(all_bills, report_dir, master_present=master_present, masters=masters)
        # [ADR-180] เดิมพิมพ์ 2 ถัง (fix/clean) แต่ row model มี 3 → check-only หายเงียบ (28+61=89/99)
        _nfix, _nclean = sum(1 for r in _rows if r['fix']), sum(1 for r in _rows if r['clean'])
        print(f'🧾 สรุปต่อบริษัท (ก็อปวางได้) → {os.path.abspath(_t)}')
        print(f'   ตารางสรุปบริษัท (Excel)     → {os.path.abspath(_x)}')
        print(f'   {len(_rows)} บริษัท×เดือน: ต้องแก้ {_nfix} / ควรตรวจ {len(_rows)-_nfix-_nclean} / ตรง {_nclean}')
    except Exception as _e:                         # ADVISORY: ห้ามล้มงานหลัก
        print(f'   ⚠️ ข้ามสรุปต่อบริษัท — {type(_e).__name__}: {str(_e)[:140]}')

    # [Ultra Agent] เวอร์ชัน "ตรวจทานแล้ว" — ยืนยัน finding ด้วยหลักฐานอิสระ (advisory, ข้างของเดิม)
    try:
        import ultra_agent as _ua
        _up = _ua.emit_ultra_summary(all_bills, report_dir, master_present=master_present, masters=masters)
        print(f'🤖 Ultra Agent (ตรวจทานแล้ว)  → {os.path.abspath(_up)}')
    except Exception as _e:                         # ADVISORY: ห้ามล้มงานหลัก
        print(f'   ⚠️ ข้าม Ultra Agent — {type(_e).__name__}: {str(_e)[:140]}')


def _is_real_master(master) -> bool:
    """[v9.2 งาน A] master ที่โหลดมาเป็น 'ของจริง' หรือไม่ (ไม่ใช่ stub ทดสอบ/ว่าง).

    [STUB-MARKER fix] เดิมแยก stub โดย "เดาจากเนื้อหา" (ทุกบริษัทเลขภาษีตรง golden stub → ตีเป็น stub)
    ทำให้ master จริงของบริษัทเดียวกับ stub (เช่น ฉีอัน 0105566206726) ถูกโยนทิ้งทั้งที่ผู้ใช้ใส่เอง.
    ใหม่: เครื่องมือ golden/verify เขียนไฟล์ stub พร้อม key "_golden_stub": true →
      • load_master() ตัด key ออกและจำไว้ใน master_mod.LAST_LOADED_WAS_STUB
      • ที่นี่เช็ค marker เป็นชั้นแรก: ไฟล์ล่าสุดเป็น stub → False, ไม่ใช่ → True (เนื้อหาอะไรก็ได้)
      • fallback เนื้อหา (ตรรกะเดิม) ใช้ "เฉพาะ" เมื่อ marker บอกไม่ได้ (เช่นไฟล์ stub รุ่นเก่าก่อน marker)
    master ที่ผู้ใช้เพิ่งพิมพ์สด (input_master_data — ไม่ผ่านไฟล์) → ไม่ใช่ stub โดยนิยาม.
    errs ไปทาง 'ของจริง' เสมอ — ถ้าเทียบไม่ได้ → True (ไม่บล็อก master จริงของผู้ใช้).
    """
    if not master:
        return False
    # ชั้นที่ 1 — marker จากไฟล์ที่เพิ่งโหลด (ทางเดียวที่ master ใน flow นี้มาจากไฟล์คือ load_master)
    try:
        import master as _master_mod
        if getattr(_master_mod, "LAST_LOADED_WAS_STUB", False):
            return False   # ไฟล์ประกาศตัวเองว่าเป็น stub ทดสอบ → ไม่ใช้ตรวจจริง
    except Exception:
        pass
    # ชั้นที่ 2 (legacy fallback) — ไฟล์ stub รุ่นเก่าที่ "ไม่มี marker": ใช้ heuristic เนื้อหาเดิม
    #   แต่จำกัดเฉพาะกรณี "หน้าตาเหมือน stub เป๊ะทั้ง key และเลขภาษี" เพื่อไม่กิน master จริง
    try:
        from golden_snapshot import MASTER as _STUB
    except Exception:
        return True
    try:
        if set(master.keys()) == set(_STUB.keys()):
            _stub_tax = {(v or {}).get('tax_id') for v in _STUB.values()}
            if all((v or {}).get('tax_id') in _stub_tax for v in master.values()):
                return False   # โครง+เลขภาษีตรง stub เป๊ะ (ไฟล์เก่าก่อน marker) → ถือเป็น stub
    except Exception:
        return True
    return True


def _move_processed_files(file_list, data_dir, report_dir):
    """[v9.2 งาน B] ย้ายไฟล์ที่ตรวจเสร็จแล้วจากโฟลเดอร์ต้นทาง ("พร้อมตรวจ") ไปเก็บใน
    report_dir/ตรวจแล้ว_<วันเวลา>/  — เรียก "เฉพาะเมื่อรายงานออกสำเร็จ" (โหมด AUTO เท่านั้น).
    ปลอดภัย: ห่อ try/except กันไฟล์หาย, ย้ายเฉพาะไฟล์ที่อยู่ใน data_dir จริง (กันย้ายผิดที่),
    ถ้าย้ายไฟล์ใดไม่ได้ก็ข้าม (ไฟล์ยังอยู่ที่เดิม) ไม่ทำให้รอบตรวจล้มหลังประมวลผลเสร็จ.
    """
    import shutil
    if not (file_list and data_dir):
        return
    # [L-T] +PID กันชื่อโฟลเดอร์ชนเมื่อรัน 2 รอบในวินาทีเดียวกัน (วินาทีเดียว+basename ซ้ำ → shutil.move ทับ)
    done_dir = os.path.join(report_dir, f'ตรวจแล้ว_{datetime.now().strftime("%Y%m%d_%H%M%S")}_{os.getpid()}')
    try:
        os.makedirs(done_dir, exist_ok=True)
    except Exception as _e:
        print(f'⚠️ สร้างโฟลเดอร์ "ตรวจแล้ว" ไม่ได้ ({type(_e).__name__}) — ไม่ย้ายไฟล์ (ไฟล์ยังอยู่ที่เดิม)')
        return
    _data_abs = os.path.abspath(data_dir)
    moved = 0
    for src in file_list:
        try:
            if not os.path.isfile(src):
                continue
            _src_abs = os.path.abspath(src)
            # [M2] ย้ายทุกไฟล์ที่อยู่ "ใต้" data_dir จริง (รวมซับโฟลเดอร์) — เดิมเทียบโฟลเดอร์พ่อตรงเป๊ะ
            #   → ไฟล์ในซับโฟลเดอร์ถูกตรวจแต่ไม่เคยถูกย้าย → ตรวจซ้ำทุกครั้ง. คงโครงสร้างซับโฟลเดอร์ใน done_dir.
            _rel = os.path.relpath(_src_abs, _data_abs)
            if _rel.startswith('..') or os.path.isabs(_rel):
                continue                       # อยู่นอก data_dir → ไม่แตะ (กันย้ายไฟล์นอกขอบเขต)
            # [M2] ข้ามไฟล์ที่อยู่ใต้ "ตรวจแล้ว_*" อยู่แล้ว (กันย้ายซ้อนไฟล์ที่ตรวจแล้ว เมื่อ report_dir⊆data_dir)
            if any(part.startswith('ตรวจแล้ว_') for part in _rel.split(os.sep)):
                continue
            dst = os.path.join(done_dir, _rel)
            if os.path.abspath(dst) == _src_abs:
                continue                       # ปลายทาง == ต้นทาง → ไม่ต้องย้าย
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)
            moved += 1
        except Exception as _e:
            print(f'⚠️ ย้ายไฟล์ไม่ได้: {os.path.basename(src)} ({type(_e).__name__}) — ข้ามไฟล์นี้ (ไฟล์ยังอยู่ที่เดิม)')
    print(f'\n📦 ย้ายไฟล์ที่ตรวจแล้ว {moved}/{len(file_list)} ไฟล์ → "{os.path.abspath(done_dir)}"')
    # [ADR-174/BUGHUNT M-F2] เก็บ "สำเนาชื่อซ้ำที่ SYS004 ข้าม" เข้า สำเนาซ้ำ_ข้าม/ ด้วย — เดิมสำเนา
    #   ค้างในโฟลเดอร์ input → รอบถัดไปชื่อไม่ซ้ำแล้ว ถูกตรวจซ้ำเงียบเป็นบิลใหม่ (นับยอดซ้ำข้ามรอบ).
    #   ย้ายเฉพาะที่อยู่ใต้ data_dir (ขอบเขตเดียวกับไฟล์หลัก) — ผลตรวจรอบนี้ไม่กระทบ (ไฟล์ไม่ถูกตรวจอยู่แล้ว).
    try:
        from parser_guards import SYS004_SKIPPED_DUP_PATHS as _dups
        _dmoved = 0
        for src in list(_dups):
            try:
                if not os.path.isfile(src):
                    continue
                _rel = os.path.relpath(os.path.abspath(src), _data_abs)
                if _rel.startswith('..') or os.path.isabs(_rel):
                    continue
                dst = os.path.join(done_dir, 'สำเนาซ้ำ_ข้าม', _rel)
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
                _dmoved += 1
            except Exception as _e:
                print(f'⚠️ ย้ายสำเนาซ้ำไม่ได้: {os.path.basename(src)} ({type(_e).__name__}) — ไฟล์ยังอยู่ที่เดิม')
        if _dmoved:
            print(f'📦 เก็บสำเนาชื่อซ้ำที่ข้ามการตรวจ (SYS004) {_dmoved} ไฟล์ → "สำเนาซ้ำ_ข้าม/" (กันถูกตรวจซ้ำรอบหน้า)')
        _dups.clear()
    except Exception:
        pass


def _prune_old_reports(report_dir, keep_days):
    """[M-3/ADR-062] เก็บกวาดรายงานเก่าในโฟลเดอร์รายงาน — กันดิสก์โตไม่จำกัดเมื่อรันยาวหลายปี.
    ลบเฉพาะ artifact ของระบบ: ไฟล์ `audit_v58_*.xlsx` และโฟลเดอร์ `ตรวจแล้ว_*` ที่ "เก่ากว่า keep_days วัน".

    ★ ปิดโดย default: keep_days<=0 (หรือไม่ตั้ง env) = เก็บทุกไฟล์ = พฤติกรรมเดิมเป๊ะ (golden-neutral).
      เปิดด้วย env PUKPUI_REPORT_RETENTION_DAYS=N (เช่น 90).
    ★ ปลอดภัย: แตะเฉพาะ 2 pattern ข้างบนใน report_dir เท่านั้น (ไม่แตะไฟล์อื่นของผู้ใช้),
      ตัดสินด้วย mtime, ห่อ try/except รายไฟล์, ไม่ขวางงานหลักถ้าลบไม่ได้.
    """
    import time, glob, shutil
    try:
        keep_days = int(str(keep_days).strip() or 0)
    except Exception:
        return
    if keep_days <= 0 or not report_dir or not os.path.isdir(report_dir):
        return
    cutoff = time.time() - keep_days * 86400
    removed = 0
    try:
        for pat in ('audit_v58_*.xlsx', 'ตรวจแล้ว_*'):
            for p in glob.glob(os.path.join(report_dir, pat)):
                try:
                    if os.path.getmtime(p) >= cutoff:
                        continue
                    if os.path.isdir(p):
                        shutil.rmtree(p, ignore_errors=True)
                    else:
                        os.remove(p)
                    removed += 1
                except Exception:
                    continue
    except Exception:
        return
    if removed:
        print(f'🧹 เก็บกวาดรายงานเก่าเกิน {keep_days} วัน: ลบ {removed} รายการ')
