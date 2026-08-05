# -*- coding: utf-8 -*-
# ruff: noqa: F401  [F3] split-base re-export shim — re-export ชื่อขึ้น chain (unused-internally โดยเจตนา)
"""reporting.py — reporting layer for ปุ้มปุ้ย 03 (module split pass 1).

Extracted VERBATIM from the monolith. NO logic changed. Contains: clean-report
sheet builders (_clean_sheet_*), full-export sheet builders (_xlsx_sheet_*),
export_excel/build_clean_report, dashboard (plotly/html), styling helpers.

Leaf module: nothing in core imports reporting; reporting imports a tiny surface
from the main module. _SYSTEM_ISSUES/RULES are imported by-reference (bound once,
mutated in place) so this module observes the same objects main mutates.
"""
import re
import math
import os
import traceback
from datetime import datetime
from collections import defaultdict, Counter
import pandas as pd
import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
try:
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
except Exception:
    plt = None

# notebook / plotly shims — match the main module's optional-import behavior
try:
    import plotly.graph_objects as go
    import plotly.express as px
except Exception:
    go = None; px = None
try:
    from IPython.display import display, HTML
except Exception:
    def display(*a, **k):
        pass
    def HTML(x=''):
        return x

from config import (APP_VERSION, CLEAN, COLORS, FIELD_CODES, REVIEW_CODES,  # [F3] explicit — config ที่ reporting_p0 ใช้
                    SEVERITY_ORDER, _STY_BORDER, _STY_HEADER_ALIGN, _STY_HEADER_FILL,
                    _STY_HEADER_FONT, _STY_SEV_FILLS, _STY_ZEBRA, bottom_only, thin)
# [P-DAG พาส3b] นำเข้า dependency จาก "โมดูลต้นทางจริง" (leaf) แทนการวิ่งกลับ main
#   → ตัด circular dependency reporting -> main
#   - predict_category / PYTHAINLP_AVAILABLE  ← thai_text
#   - RULES (object เดียว mutate in-place)     ← rules_engine
#   - _SYSTEM_ISSUES (object เดียว mutate)      ← state
#   - sort_bills_by_date                        ← core_utils
#   - thin / bottom_only (style)                ← config (ผ่าน `from config import *` ด้านบนแล้ว)
from thai_text import predict_category, PYTHAINLP_AVAILABLE
from rules_engine import RULES
from state import _SYSTEM_ISSUES
from core_utils import sort_bills_by_date, _df_safe, _bill_date_key   # [L4] _df_safe อยู่ leaf core_utils (คง reporting_p0 ≤600 LOC) · [ADR-173] _bill_date_key


def export_verification_to_excel(results, excel_path):
    if not results: return False
    try:
        rows = []
        for r in results:
            rows.append({
                'ชื่อสินค้าเดิม': r['original_name'],
                'หน่วยเดิม': r['original_unit'] or '-',
                'หมวดที่คาด': r['predicted_category'],
                'Tier1 Match': r.get('tier1_match') or '-',
                'Tier1 Conf %': r.get('tier1_confidence') or 0,
                'Conf Tier': r.get('tier1_tier') or 'LOW',
                'OCR สงสัย': '✓' if r.get('ocr_suspected') else '-',
                'Formal Score': round(r.get('formal_score', 0.0), 2),
                'หน่วย Tier1': '✓' if r.get('tier1_unit_ok')==True
                              else '✗' if r.get('tier1_unit_ok')==False else '-',
                'แนะนำหน่วย': r.get('tier1_unit_suggest') or '-',
                'Tier2 State': r.get('tier2_state') or '-',
                'Tier2 Source': (r.get('tier2_source') or '-')[:60],
                'Tier2 Trust': r.get('tier2_trust') or 0,
                'Final State': r['final_state'],
                'Risk': r['risk_level'],
                'พบกี่ครั้ง': r.get('occurrences', 1),
                'คำอธิบาย': r.get('explanation') or '-',
            })
        df = pd.DataFrame(rows)
        df['_sort'] = df['Final State'].map({'CONFLICTED':0,'UNVERIFIABLE':1,'NEEDS_REVIEW':2,'VERIFIED':3,'ERROR':0})
        df = df.sort_values(['_sort','Risk']).drop('_sort', axis=1)
        with pd.ExcelWriter(excel_path, engine='openpyxl', mode='a', if_sheet_exists='replace') as writer:
            df.to_excel(writer, sheet_name='Product Verification', index=False)
        wb = load_workbook(excel_path)
        ws = wb['Product Verification']
        state_col = None
        for cell in ws[1]:
            if cell.value == 'Final State': state_col = cell.column; break
        state_fills = {
            'CONFLICTED': PatternFill('solid', fgColor='FECACA'),
            'UNVERIFIABLE': PatternFill('solid', fgColor='FED7AA'),
            'NEEDS_REVIEW': PatternFill('solid', fgColor='FEF3C7'),
            'VERIFIED': PatternFill('solid', fgColor='BBF7D0'),
            'ERROR': PatternFill('solid', fgColor='FECACA'),
        }
        if state_col:
            for ri in range(2, ws.max_row+1):
                sv = ws.cell(row=ri, column=state_col).value
                if sv in state_fills:
                    for cell in ws[ri]: cell.fill = state_fills[sv]
        wb.save(excel_path)
        return True
    except Exception as e:
        print(f'⚠️ Verification export ล้มเหลว: {e}')
        return False

def section_header(title, emoji=''):
    display(HTML(f'''<div style="background:#FFFFFF;border:1px solid #E7E5E4;border-left:3px solid #1E293B;color:#1C1917;padding:20px 28px;border-radius:12px;margin:32px 0 20px 0;box-shadow:0 1px 3px rgba(0,0,0,0.04),0 1px 2px rgba(0,0,0,0.06);font-family:'Inter','Noto Sans Thai',-apple-system,sans-serif;"><h2 style="margin:0;font-size:17px;font-weight:600;letter-spacing:-0.01em;color:#1C1917;">{emoji} {title}</h2></div>'''))

def kpi_cards(stats):
    cards = [
        ('ไฟล์', stats['files'], '#1E293B'),
        ('บิล', stats['bills'], '#1E293B'),
        ('ปกติ', stats['clean'], '#166534'),
        ('ผิดปกติ', stats['abnormal'], '#9A3412'),
        ('Critical', stats['critical'], '#991B1B'),
        ('Error', stats['error'], '#9A3412'),
        ('Warning', stats['warning'], '#854D0E'),
        ('Info', stats['info'], '#1E40AF'),
    ]
    html = '<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0;font-family:\'Inter\',\'Noto Sans Thai\',-apple-system,sans-serif;">'
    for label, value, color in cards:
        html += f'<div style="background:#FFFFFF;border:1px solid #E7E5E4;padding:22px 24px;border-radius:12px;box-shadow:0 1px 3px rgba(0,0,0,0.04),0 1px 2px rgba(0,0,0,0.06);"><div style="color:#78716C;font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.06em;margin-bottom:10px;">{label}</div><div style="color:{color};font-size:32px;font-weight:600;line-height:1;letter-spacing:-0.02em;font-variant-numeric:tabular-nums;">{value:,}</div></div>'
    html += '</div>'
    display(HTML(html))

def money_cards(stats):
    cards = [('ยอดก่อน VAT', stats['subtotal']), ('VAT รวม', stats['vat']), ('ยอดสุทธิ', stats['total'])]
    html = '<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:20px 0;font-family:\'Inter\',\'Noto Sans Thai\',-apple-system,sans-serif;">'
    for label, value in cards:
        html += f'<div style="background:#1C1917;color:#FAFAF9;padding:26px 28px;border-radius:12px;box-shadow:0 4px 6px rgba(0,0,0,0.04),0 10px 15px rgba(0,0,0,0.06);"><div style="font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.06em;opacity:0.6;margin-bottom:12px;">{label}</div><div style="font-size:30px;font-weight:600;letter-spacing:-0.02em;font-variant-numeric:tabular-nums;line-height:1;">{value:,.2f}</div><div style="font-size:11px;opacity:0.45;margin-top:8px;font-weight:400;">บาท</div></div>'
    html += '</div>'
    display(HTML(html))

def risk_score_card(stats):
    score = stats['critical']*10 + stats['error']*3 + stats['warning']
    if score < 10: level, color, bg = 'LOW', '#166534', '#F0FDF4'
    elif score < 50: level, color, bg = 'MEDIUM', '#854D0E', '#FEFCE8'
    else: level, color, bg = 'HIGH', '#991B1B', '#FEF2F2'
    display(HTML(f'''<div style="background:{bg};border:1px solid #E7E5E4;padding:36px;border-radius:12px;text-align:center;margin:20px 0;box-shadow:0 1px 3px rgba(0,0,0,0.04),0 1px 2px rgba(0,0,0,0.06);font-family:'Inter','Noto Sans Thai',-apple-system,sans-serif;"><div style="color:#78716C;font-size:11px;font-weight:500;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:14px;">Overall Risk Score</div><div style="color:{color};font-size:60px;font-weight:700;letter-spacing:-0.03em;line-height:1;font-variant-numeric:tabular-nums;">{score}</div><div style="color:{color};font-size:14px;font-weight:500;margin-top:10px;letter-spacing:0.02em;">{level}</div><div style="color:#A8A29E;font-size:11px;margin-top:16px;font-weight:400;">Critical × 10 + Error × 3 + Warning × 1</div></div>'''))

def style_severity(val):
    cm = {'CRITICAL':'#FECACA','ERROR':'#FED7AA','WARNING':'#FEF08A','INFO':'#BAE6FD','CLEAN':'#BBF7D0'}
    color = cm.get(val, '')
    return f'background-color:{color};font-weight:600;' if color else ''

def style_count(val):
    if isinstance(val, (int, float)) and val > 0:
        return 'background-color:#FECACA;font-weight:600;color:#991B1B;'
    return ''

def generate_visual_dashboard(all_bills, summary, cat_counts):
    try:
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))
        plt.subplots_adjust(hspace=0.35, wspace=0.3)
        sev_counts = {sev: sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']==sev) for sev in ['CRITICAL','ERROR','WARNING','INFO']}   # [ADR-173] or []
        sev_f = [(s,c) for s,c in sev_counts.items() if c > 0]
        if sev_f:
            labels = [s for s,_ in sev_f]; sizes = [c for _,c in sev_f]
            axes[0,0].pie(sizes, labels=labels, colors=[COLORS[s] for s in labels],
                         autopct='%1.1f%%', startangle=90, wedgeprops={'edgecolor':'white','linewidth':2})
            axes[0,0].set_title('Severity Distribution', fontsize=13, fontweight='bold', pad=15)
        else:
            axes[0,0].text(0.5,0.5,'No Issues',ha='center',va='center',fontsize=14,color='#16A34A')
            axes[0,0].axis('off')
        if cat_counts:
            cats = sorted(cat_counts.keys(), key=lambda c: -sum(cat_counts[c].values()))
            totals = [sum(cat_counts[c].values()) for c in cats]
            axes[0,1].barh(cats, totals, color='#3B82F6', edgecolor='white', linewidth=1.5)
            axes[0,1].set_title('Issues by Category', fontsize=13, fontweight='bold', pad=15)
            axes[0,1].invert_yaxis()
            for i, v in enumerate(totals): axes[0,1].text(v+max(totals)*0.01, i, str(v), va='center', fontsize=10)
        else: axes[0,1].axis('off')
        comp = sorted([(s['key'], sum(len(b.get('issues') or []) for b in s['bills'])) for s in summary], key=lambda x: -x[1])   # [ADR-173] or []
        top10 = [c for c in comp if c[1] > 0][:10]
        if top10:
            names = [c[0][:25] for c in top10]; vals = [c[1] for c in top10]
            axes[1,0].barh(names, vals, color='#DC2626', edgecolor='white', linewidth=1.5)
            axes[1,0].set_title('Top 10 Companies by Issues', fontsize=13, fontweight='bold', pad=15)
            axes[1,0].invert_yaxis()
            for i, v in enumerate(vals): axes[1,0].text(v+max(vals)*0.01, i, str(v), va='center', fontsize=10)
        else:
            axes[1,0].text(0.5,0.5,'No Issues',ha='center',va='center',fontsize=14,color='#16A34A')
            axes[1,0].axis('off')
        amt = sorted([(s['key'][:25], s['subtotal']) for s in summary if s['subtotal']>0], key=lambda x: -x[1])[:10]
        if amt:
            names = [c[0] for c in amt]; vals = [c[1] for c in amt]
            axes[1,1].barh(names, vals, color='#16A34A', edgecolor='white', linewidth=1.5)
            axes[1,1].set_title('Top 10 Companies by Amount', fontsize=13, fontweight='bold', pad=15)
            axes[1,1].set_xlabel('บาท'); axes[1,1].invert_yaxis()
            for i, v in enumerate(vals): axes[1,1].text(v+max(vals)*0.01, i, f'{v:,.0f}', va='center', fontsize=9)
        else: axes[1,1].axis('off')
        plt.tight_layout()
        try:
            _chart_png = 'audit_charts.png'
            plt.savefig(_chart_png, dpi=120, bbox_inches='tight')
            plt.close('all')
            print(f'🖼️  กราฟสรุปบันทึกแล้ว → {os.path.abspath(_chart_png)}')
        except Exception as _e:
            print(f'⚠️ บันทึกกราฟไม่ได้: {_e}')
    except Exception as e:
        print(f'⚠️ Chart error: {e}')
    finally:
        # [M3] กัน matplotlib figure รั่วทุก path (เดิมถ้า error ก่อน close → figure ค้างใน registry, RAM โตเมื่อรันวน)
        try: plt.close('all')
        except Exception: pass

def field_status(bills, codes):
    affected = sum(1 for b in bills if any(i['code'] in codes for i in (b.get('issues') or [])))   # [ADR-173] or []
    return 'ตรง' if affected == 0 else f"ไม่ตรง ({affected}/{len(bills)} บิล)"

def display_low_confidence_bills(all_bills):
    """แสดงตารางบิลที่ parse_confidence == 'LOW' — ต้องเช็คด้วยมือ"""
    low = [b for b in all_bills if b.get('parse_confidence') == 'LOW']
    section_header('บิลที่ต้องเช็คมือ (Low Confidence)', '✋')
    if not low:
        display(HTML('<div style="padding:18px;background:#D1FAE5;color:#065F46;'
                     'border-radius:8px;font-weight:600;">'
                     '✅ ไม่มีบิลที่ระบบไม่มั่นใจ</div>'))
        return
    rows = []
    for b in low:
        rows.append({
            'ไฟล์': b.get('file', ''),
            'ชีต': b.get('sheet', ''),
            'IV': (b.get('iv_number_raw') or b.get('iv_number') or '-'),
            'วันที่': b.get('iv_date_str') or '-',
            'บริษัท': str(b.get('company') or '')[:40],   # [ADR-173] str() — company non-str เดิม [:40] ครัช
            'เหตุผลที่ confidence ต่ำ': ' | '.join(b.get('parse_confidence_reasons') or []),
        })
    display(HTML(f'<div style="padding:12px;background:#FEF3C7;color:#854D0E;'
                 f'border-radius:8px;font-weight:600;margin-bottom:8px;">'
                 f'⚠️ พบ {len(low)} บิล ที่ระบบอ่านได้ไม่ชัด — ควรเปิดไฟล์จริงตรวจซ้ำ</div>'))
    display(pd.DataFrame(rows))

def display_executive_dashboard(all_bills, summary, iv_issues, typos, filename_issues, file_count):
    # [ADR-173/BUGHUNT] (b.get('issues') or []) + _fin0 — เดิม issues=None/เงินเป็น str ครัชทั้ง run
    #   หลังตรวจเสร็จ ก่อนได้รายงานใด ๆ (จุดเรียกใน main เดิมไม่ถูกห่อ). บิลปกติผลเท่าเดิมเป๊ะ.
    crit = sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='CRITICAL')
    err = sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='ERROR')
    warn = sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='WARNING')
    info = sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='INFO')
    clean = sum(1 for b in all_bills if not b.get('issues'))
    stats = {'files':file_count,'bills':len(all_bills),'clean':clean,
             'abnormal':len(all_bills)-clean,'critical':crit,'error':err,'warning':warn,'info':info,
             'subtotal':sum(_fin0(b.get('subtotal')) for b in all_bills),
             'vat':sum(_fin0(b.get('vat')) for b in all_bills),
             'total':sum(_fin0(b.get('total')) for b in all_bills)}
    pn_badge = ' • PyThaiNLP ✅' if PYTHAINLP_AVAILABLE else ''
    display(HTML(f'''<div style="background:#0F172A;color:#FAFAF9;padding:40px;border-radius:12px;margin-bottom:24px;box-shadow:0 4px 6px rgba(0,0,0,0.04),0 10px 15px rgba(0,0,0,0.06);font-family:'Inter','Noto Sans Thai',-apple-system,sans-serif;"><h1 style="margin:0;font-size:26px;font-weight:600;letter-spacing:-0.02em;">Invoice Audit Report</h1><p style="margin:10px 0 0 0;font-size:12px;opacity:0.55;font-weight:400;letter-spacing:0.02em;">v{APP_VERSION} · {datetime.now().strftime("%d/%m/%Y %H:%M")} · {len(RULES)} Rules{pn_badge}</p></div>'''))
    section_header('EXECUTIVE SUMMARY', '📊')
    kpi_cards(stats); money_cards(stats); risk_score_card(stats)

    section_header('COMPANY BREAKDOWN', '🏢')
    rows = []
    for i, s in enumerate(sorted(summary, key=lambda x: -x['subtotal']), 1):
        rows.append({'อันดับ':i,'บริษัท':s['key'],'งวด':s['period'],'บิล':s['bill_count'],
            'ยอดก่อน VAT':s['subtotal'],'VAT':s['vat'],'ยอดสุทธิ':s['total'],
            'Issues':sum(len((b.get('issues') or [])) for b in s['bills']),
            'Critical':sum(1 for b in s['bills'] for i in (b.get('issues') or []) if i['severity']=='CRITICAL')})
    if rows:
        df = pd.DataFrame(rows)
        try:
            styled = (df.style.background_gradient(subset=['ยอดก่อน VAT','VAT','ยอดสุทธิ'], cmap='Blues')
                      .background_gradient(subset=['Issues','Critical'], cmap='Reds')
                      .format({'ยอดก่อน VAT':'{:,.2f}','VAT':'{:,.2f}','ยอดสุทธิ':'{:,.2f}'}))
            display(styled)
        except Exception: display(df)

    section_header('HIGH RISK BILLS', '🚨')
    hr = [b for b in all_bills if any(i['severity']=='CRITICAL' for i in (b.get('issues') or []))]
    if hr:
        rows = []
        for b in hr[:30]:
            rows.append({'ไฟล์':b['file'],'ชีต':b['sheet'],'IV':(b.get('iv_number_raw') or b.get('iv_number') or '-'),
                'วันที่':b['iv_date_str'],'บริษัท':b.get('master_key') or bill_company_label(b),'ยอด':b['subtotal'] or 0,   # [L] กัน KeyError master_key (dashboard ไม่ถูกห่อใน main)
                '🔴':sum(1 for i in (b.get('issues') or []) if i['severity']=='CRITICAL'),
                '🟠':sum(1 for i in (b.get('issues') or []) if i['severity']=='ERROR'),
                'หมายเหตุ':' | '.join([f"[{i['code']}] {(i.get('detail') or '')[:50]}" for i in (b.get('issues') or []) if i['severity']=='CRITICAL'][:2])})   # [M4] None-safe
        df = pd.DataFrame(rows)
        try:
            styled = df.style.applymap(style_count, subset=['🔴','🟠']).format({'ยอด':'{:,.2f}'})
            display(styled)
        except Exception: display(df)
    else:
        display(HTML('<div style="padding:18px;background:#D1FAE5;color:#065F46;border-radius:8px;font-weight:600;">✅ ไม่พบบิล High Risk</div>'))

    section_header('ERROR BREAKDOWN BY CATEGORY', '📈')
    cat_counts = defaultdict(lambda: defaultdict(int))
    for b in all_bills:
        for i in (b.get('issues') or []): cat_counts[i['category']][i['severity']] += 1
    if cat_counts:
        rows = []
        for cat in cat_counts:
            row = {'หมวด':cat}
            for sev in ['CRITICAL','ERROR','WARNING','INFO']: row[sev] = cat_counts[cat][sev]
            row['รวม'] = sum(cat_counts[cat].values())
            rows.append(row)
        df = pd.DataFrame(rows).sort_values('รวม', ascending=False)
        try: display(df.style.background_gradient(subset=['CRITICAL','ERROR','WARNING','INFO','รวม'], cmap='Reds'))
        except Exception: display(df)

    section_header('VISUAL ANALYTICS', '📊')
    generate_visual_dashboard(all_bills, summary, cat_counts)

    if iv_issues:
        section_header('IV SEQUENCE ISSUES', '🔗')
        df = pd.DataFrame(iv_issues)
        try: display(df.style.applymap(style_severity, subset=['severity']))
        except Exception: display(df)

    if typos:
        section_header('PRODUCT TYPO DETECTION', '🔍')
        df = pd.DataFrame(typos[:30])
        try: display(df.style.background_gradient(subset=['score'], cmap='Oranges'))
        except Exception: display(df)

    if filename_issues:
        section_header('FILENAME ISSUES', '📁')
        display(pd.DataFrame(filename_issues))

    section_header('DETAILED REPORT BY COMPANY', '📋')
    for idx, s in enumerate(summary, 1):
        # [ADR-173] _bill_date_key + str(sheet) — เดิม iv_date เป็น str ทำ '<' str vs datetime ครัชทั้ง display
        bills_s = sorted(s['bills'], key=lambda b: (_bill_date_key(b.get('iv_date')), str(b.get('sheet') or '')))
        display(HTML(f'<div style="background:#F3F4F6;border-left:6px solid {COLORS["HEADER"]};padding:14px 18px;margin-top:16px;border-radius:6px;"><h3 style="margin:0;color:#1E40AF;font-size:18px;">{idx}. {s["key"]} {s["period"]}</h3><div style="margin-top:6px;color:#374151;font-size:13px;">💵 PreVAT: <b>{s["subtotal"]:,.2f}</b> | 💰 VAT: <b>{s["vat"]:,.2f}</b> | 🎯 Total: <b>{s["total"]:,.2f}</b> | 🧾 <b>{s["bill_count"]}</b> บิล</div></div>'))
        status_rows = [{'Field':label,'Status':field_status(bills_s, codes)} for label, codes in FIELD_CODES]
        try:
            df_st = pd.DataFrame(status_rows)
            styled = df_st.style.applymap(lambda v: 'background-color:#FECACA;color:#991B1B;' if 'ไม่ตรง' in str(v)
                                          else 'background-color:#D1FAE5;color:#065F46;' if v=='ตรง' else '',
                                          subset=['Status'])
            display(styled)
        except Exception: display(pd.DataFrame(status_rows))
        timeline = []
        for b in bills_s:
            sev = ('CRITICAL' if any(i['severity']=='CRITICAL' for i in (b.get('issues') or []))
                   else 'ERROR' if any(i['severity']=='ERROR' for i in (b.get('issues') or []))
                   else 'WARNING' if any(i['severity']=='WARNING' for i in (b.get('issues') or []))
                   else 'INFO' if any(i['severity']=='INFO' for i in (b.get('issues') or []))
                   else 'CLEAN')
            timeline.append({'วันที่':b['iv_date_str'] or '-','IV':(b.get('iv_number_raw') or b.get('iv_number') or '-'),
                            'ชีต':b['sheet'],'ยอด':b['subtotal'] or 0,
                            'Issues':len((b.get('issues') or [])),'Severity':sev})
        df_t = pd.DataFrame(timeline)
        try:
            styled = df_t.style.applymap(style_severity, subset=['Severity']).format({'ยอด':'{:,.2f}'})
            display(styled)
        except Exception: display(df_t)

def _sty_header(ws):
    """style แถว header + freeze + autofilter"""
    for cell in ws[1]:
        cell.fill = _STY_HEADER_FILL; cell.font = _STY_HEADER_FONT
        cell.alignment = _STY_HEADER_ALIGN; cell.border = _STY_BORDER
    ws.row_dimensions[1].height = 28
    ws.freeze_panes = 'A2'
    if ws.max_row > 1:
        ws.auto_filter.ref = f'A1:{get_column_letter(ws.max_column)}{ws.max_row}'

def _sty_cell_len(cell, max_len):
    """helper ลด nesting — คืน max_len ที่อัปเดตจาก cell เดียว"""
    if cell.value is None:
        return max_len
    try:
        return max(max_len, min(60, len(str(cell.value))))
    except (TypeError, ValueError):
        return max_len

def _sty_col_widths(ws):
    """ปรับความกว้างคอลัมน์ตามเนื้อหา (สูงสุด 50 แถวแรก)"""
    for col in ws.columns:
        max_len = 10
        col_letter = col[0].column_letter
        for cell in col[:50]:
            max_len = _sty_cell_len(cell, max_len)
        ws.column_dimensions[col_letter].width = max_len + 2

def _sty_find_cols(ws):
    """หา sev_col + currency_cols จาก header"""
    sev_col = None
    for cell in ws[1]:
        if cell.value == 'Severity':
            sev_col = cell.column; break
    currency_kw = ['ยอด','VAT','ราคา','Value','amount']
    currency_cols = [i for i, cell in enumerate(ws[1], 1)
                     if cell.value and any(k in str(cell.value) for k in currency_kw)]
    return sev_col, currency_cols

def _sty_sev_row(ws, row_idx, sev_col):
    """ใส่สีตาม severity ถ้าแถวนี้มีค่า severity"""
    sv = ws.cell(row=row_idx, column=sev_col).value
    if sv in _STY_SEV_FILLS:
        for cell in ws[row_idx]:
            cell.fill = _STY_SEV_FILLS[sv]

def _sty_zebra_row(ws, row_idx):
    """ใส่ zebra fill ให้ cell ที่ยังไม่มีสี"""
    for cell in ws[row_idx]:
        if not cell.fill.fgColor.value or cell.fill.fgColor.value in ['00000000','FFFFFFFF',None]:
            cell.fill = _STY_ZEBRA

def _sty_row(ws, row_idx, sev_col, currency_cols):
    """style 1 แถว: zebra / severity fill / border / currency format"""
    if row_idx % 2 == 0:
        _sty_zebra_row(ws, row_idx)
    if sev_col:
        _sty_sev_row(ws, row_idx, sev_col)
    for c in ws[row_idx]:
        c.border = _STY_BORDER
    for ci in currency_cols:
        c = ws.cell(row=row_idx, column=ci)
        if isinstance(c.value, (int, float)):
            c.number_format = '#,##0.00'

def _style_one_sheet(ws):
    """style 1 sheet ครบทุกส่วน (depth ตื้น)"""
    if ws.max_row < 1:
        return
    _sty_header(ws)
    _sty_col_widths(ws)
    sev_col, currency_cols = _sty_find_cols(ws)
    for row_idx in range(2, ws.max_row + 1):
        _sty_row(ws, row_idx, sev_col, currency_cols)

def style_excel_report(filepath):
    """v5.8 refactor: แตกการ style ออกเป็น helper (_sty_*) ลด nesting ≤6"""
    try:
        wb = load_workbook(filepath)
        for sheet_name in wb.sheetnames:
            _style_one_sheet(wb[sheet_name])
        wb.save(filepath)
    except Exception as e:
        print(f'⚠️ Styling ล้มเหลว: {e}')

def file_company_code(filename):
    """ดึงรหัส/ตัวย่อบริษัทจากชื่อไฟล์ เช่น 'SHS 69.04(20).xls' → 'SHS'
    เอาเฉพาะตัวอักษรขึ้นต้น (ก่อนเจอตัวเลข/ช่องว่าง)"""
    base = os.path.basename(str(filename))
    m = re.match(r'\s*([A-Za-zก-๙]+)', base)
    return m.group(1) if m else ''

def bill_company_label(b):
    """ป้ายบริษัทสำหรับ 1 บิล — ใช้ master_key ก่อน, ไม่มีก็ company,
    ไม่มีอีกก็รหัสจากชื่อไฟล์, สุดท้ายขึ้นเตือนให้ตรวจเอง"""
    mk = b.get('master_key')
    # [ADR-173/BUGHUNT] str() — twin ของ _clean_company_label (ADR-168 C3): master_key/company
    #   ชนิดผิด (int/float) เดิม .strip()/sort ครัชล้ม export_excel ทั้งไฟล์ (full mode). ค่าปกติ no-op.
    if mk and mk != '(ไม่พบใน master)':
        return str(mk)
    comp = str(b.get('company') or '').strip()
    if comp:
        return comp
    code = file_company_code(b.get('file',''))
    if code:
        return code
    return '[ต้องตรวจสอบบริษัทเอง]'

def issue_lane(issue):
    """คืน 'FINDING' (ยืนยัน ต้องแก้/ตรวจ) | 'REVIEW' (ข้อสังเกต/ต้องคนยืนยัน).
    ฟังก์ชันบริสุทธิ์ ไม่แก้ค่า issue ไม่ลบอะไร — แค่ตัดสินว่าควรอยู่เลนไหนของรายงาน
    ปลอดภัยเสมอ: ไม่ throw (กันรายงานพังเพราะ issue รูปแบบแปลก)
    """
    try:
        sev = issue.get('severity', 'INFO')
        code = issue.get('code', '') or ''
        # SYSTEM = error ของเครื่องเอง (กฎพัง/parse fail) — ไม่ใช่ผลตรวจบิล
        if code.startswith('SYS') or issue.get('category') in ('SYSTEM', 'ระบบ'):
            return 'REVIEW'
        # CRITICAL/ERROR = ข้อสรุปยืนยัน (ตัวเลข/นิติบุคคล/เลขภาษีผิด) → เป็น finding เสมอ
        if sev in ('CRITICAL', 'ERROR'):
            return 'FINDING'
        # รหัสกฎกลุ่มแนะนำ → review
        if code in REVIEW_CODES:
            return 'REVIEW'
        # ITM011 เฉพาะ tier ความเชื่อมั่นต่ำ ("ใกล้เคียง (ตรวจสอบ)") → review; tier สูงคงเป็น finding
        if code == 'ITM011' and 'ใกล้เคียง (ตรวจสอบ)' in (issue.get('detail', '') or ''):
            return 'REVIEW'
        # INFO ที่เหลือ = ข้อสังเกต → review; WARNING ที่ยืนยันได้ (เช่น VAT004 rounding) = finding
        return 'REVIEW' if sev == 'INFO' else 'FINDING'
    except Exception:
        return 'FINDING'   # ถ้าตัดสินไม่ได้ → ปลอดภัยไว้ก่อน เก็บเป็น finding (ไม่ทำให้ของหาย)

def _get_p(d):
    if not d: return '-'
    # [ADR-173/BUGHUNT] twin ของ _clean_period (ADR-168 C2 + ADR-170): iv_date ชนิดผิด/NaT เดิม d.year
    #   ครัชล้ม export_excel ทั้งไฟล์ (full mode). date ปกติผลเท่าเดิมเป๊ะ.
    try: yr = int(getattr(d, 'year', None)); mo = int(getattr(d, 'month', None))
    except (TypeError, ValueError): return '-'
    be = yr + 543 if yr < 2500 else yr
    return f"{(be % 100):02d}.{mo:02d}"

def _fin0(v):
    """[ADR-173/BUGHUNT] twin ของ reporting_p1._fin ([REP-C2]) ฝั่ง p0 (import ย้อน chain ไม่ได้) —
    ยอดเงินปลอดภัยสำหรับ sum: None/NaN/±inf/str → 0. float ปกติค่าเท่าเดิม (ผลรวมไม่ขยับ)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0
    return f if (f == f and f not in (float('inf'), float('-inf'))) else 0

def _xlsx_sheet_dashboard(writer, all_bills):
    """ชีต Executive Dashboard (KPI). คำนวณ crit/err/warn ในตัว (เหมือนเดิม)."""
    crit = sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='CRITICAL')
    err = sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='ERROR')
    warn = sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='WARNING')
    kpi = [
        {'Metric':'จำนวนไฟล์','Value':len(set(b['file'] for b in all_bills))},
        {'Metric':'จำนวนบิล','Value':len(all_bills)},
        {'Metric':'บิลปกติ','Value':sum(1 for b in all_bills if not (b.get('issues') or []))},
        {'Metric':'บิลผิดปกติ','Value':sum(1 for b in all_bills if (b.get('issues') or []))},
        {'Metric':'CRITICAL','Value':crit},
        {'Metric':'ERROR','Value':err},
        {'Metric':'WARNING','Value':warn},
        {'Metric':'INFO','Value':sum(1 for b in all_bills for i in (b.get('issues') or []) if i['severity']=='INFO')},
        {'Metric':'ยอดก่อน VAT','Value':sum(_fin0(b.get('subtotal')) for b in all_bills)},   # [ADR-173] _fin0 กัน str/NaN
        {'Metric':'VAT รวม','Value':sum(_fin0(b.get('vat')) for b in all_bills)},
        {'Metric':'ยอดสุทธิ','Value':sum(_fin0(b.get('total')) for b in all_bills)},
        {'Metric':'RISK SCORE','Value':crit*10+err*3+warn},
    ]
    _df_safe(pd.DataFrame(kpi)).to_excel(writer, sheet_name='Executive Dashboard', index=False)

def _xlsx_sheet_summary(writer, summary):
    """ชีต Summary (สรุปต่อบริษัท×งวด)."""
    _df_safe(pd.DataFrame([{'บริษัท':s['key'],'งวด':s['period'],'จำนวนบิล':s['bill_count'],
        'ยอดก่อน VAT':s['subtotal'],'VAT':s['vat'],'ยอดสุทธิ':s['total']}
        for s in summary])).to_excel(writer, sheet_name='Summary', index=False)

def _xlsx_sheet_allbills(writer, all_bills_s):
    """ชีต ทุกบิล (+คอลัมน์ งวดบัญชี)."""
    # [UPDATE] 2. ยัดคอลัมน์ 'งวดบัญชี' ลงชีต 'ทุกบิล'
    _df_safe(pd.DataFrame([{'งวดบัญชี': _get_p(b['iv_date']), 'วันที่':b['iv_date_str'],'ไฟล์':b['file'],'ชีต':b['sheet'],
        'บริษัท':b['company'],'เลขภาษี':b['tax_id'],
        'IV': (b.get('iv_number_raw') or b.get('iv_number') or '-'),
        'ยอดก่อน VAT':b['subtotal'],'VAT':b['vat'],'ยอดสุทธิ':b['total'],
        'รายการ':len(b['items']),'Issues':len((b.get('issues') or [])),
        'Critical':sum(1 for i in (b.get('issues') or []) if i['severity']=='CRITICAL'),
        'Error':sum(1 for i in (b.get('issues') or []) if i['severity']=='ERROR'),
        'Warning':sum(1 for i in (b.get('issues') or []) if i['severity']=='WARNING')}
        for b in all_bills_s])).to_excel(writer, sheet_name='ทุกบิล', index=False)

def _xlsx_sheet_highrisk(writer, all_bills_s):
    """ชีต High Risk (เฉพาะบิลที่มี CRITICAL)."""
    hr = [b for b in all_bills_s if any(i['severity']=='CRITICAL' for i in (b.get('issues') or []))]
    if hr:
        _df_safe(pd.DataFrame([{'งวดบัญชี': _get_p(b['iv_date']), 'วันที่':b['iv_date_str'],'ไฟล์':b['file'],'ชีต':b['sheet'],
            'IV': (b.get('iv_number_raw') or b.get('iv_number') or '-'),
            'บริษัท':b.get('master_key') or bill_company_label(b),'ยอด':b['subtotal'] or 0,   # [L] กัน KeyError master_key
            'Critical':sum(1 for i in (b.get('issues') or []) if i['severity']=='CRITICAL'),
            'หมายเหตุ':' | '.join([f"[{i['code']}] {(i.get('detail') or '')[:80]}" for i in (b.get('issues') or []) if i['severity']=='CRITICAL'])}   # [M4] None-safe
            for b in hr])).to_excel(writer, sheet_name='High Risk', index=False)

def _xlsx_sheet_ranking(writer, summary):
    """ชีต Company Ranking (เรียงตามยอดก่อน VAT)."""
    ranking = []
    for i, s in enumerate(sorted(summary, key=lambda x: -x['subtotal']), 1):
        ranking.append({'อันดับ':i,'บริษัท':s['key'],'จำนวนบิล':s['bill_count'],
            'ยอดก่อน VAT':s['subtotal'],'VAT':s['vat'],'ยอดสุทธิ':s['total'],
            'Issues':sum(len((b.get('issues') or [])) for b in s['bills']),
            'Critical':sum(1 for b in s['bills'] for i in (b.get('issues') or []) if i['severity']=='CRITICAL')})
    if ranking:
        _df_safe(pd.DataFrame(ranking)).to_excel(writer, sheet_name='Company Ranking', index=False)

def _xlsx_sheet_error_report(writer, all_bills_s):
    """ชีต Error Report + ข้อควรตรวจสอบ (แยกเลน FINDING/REVIEW)."""
    err_rows = []
    for b in all_bills_s:
        for i in (b.get('issues') or []):
            # [UPDATE] 3. ยัดคอลัมน์ 'งวดบัญชี' ลงชีต 'Error Report'
            # v8.5 [FIX-LANE]: ติดป้าย 'เลน' แยก finding (ยืนยัน) / review (ต้องคนตรวจ)
            err_rows.append({'งวดบัญชี': _get_p(b['iv_date']), 'บริษัท':bill_company_label(b),
                'รหัสไฟล์':file_company_code(b['file']),
                'เลน': issue_lane(i),
                'Severity':i['severity'],'Code':i['code'],
                'หมวด':i['category'],'กฎ':i['name'],'ไฟล์':b['file'],'ชีต':b['sheet'],
                'วันที่':b['iv_date_str'],
                'IV': (b.get('iv_number_raw') or b.get('iv_number') or '-'),
                'รายละเอียด':i['detail']})
    if err_rows:
        df_e = pd.DataFrame(err_rows)
        df_e['_s'] = df_e['Severity'].map(SEVERITY_ORDER)
        df_e = df_e.sort_values(['_s','Code']).drop('_s', axis=1)
        # v8.5 [FIX-LANE]: Error Report = เฉพาะ "ต้องแก้/ตรวจ" (finding); review แยกชีต
        #   ของทุกชิ้นยังอยู่ในรายงาน (ไม่ลบ) — แค่จัดเลน → ลด FP ที่ตาเห็น โดย recall ไม่หาย
        df_find = df_e[df_e['เลน'] == 'FINDING'].drop('เลน', axis=1)
        df_rev  = df_e[df_e['เลน'] == 'REVIEW'].drop('เลน', axis=1)
        _df_safe(df_find).to_excel(writer, sheet_name='Error Report', index=False)
        if not df_rev.empty:
            _df_safe(df_rev).to_excel(writer, sheet_name='ข้อควรตรวจสอบ', index=False)

def _xlsx_sheet_system_issues(writer):
    """ชีต System Issues (กฎพัง/parse fail — แยกจากผลตรวจบิล)."""
    # v8.5 [FIX-SYS]: system-issue (กฎพัง/parse fail) แยกชีตของตัวเอง — ไม่ปนผลตรวจบิล
    if _SYSTEM_ISSUES:
        pd.DataFrame([{'Severity':s.get('severity','INFO'),'Code':s.get('code','SYS'),
            'หมวด':s.get('category','SYSTEM'),'รายการ':s.get('name',''),
            'ไฟล์':s.get('file',''),'ชีต':s.get('sheet',''),
            'รายละเอียด':s.get('detail','')} for s in _SYSTEM_ISSUES]
            ).to_excel(writer, sheet_name='System Issues', index=False)


# OBJ-MAINT: auto-export ทุกชื่อ (รวม _ และ import) → from-import * cascade ครบ
__all__=[n for n in list(globals().keys()) if not n.startswith('__') and n!='annotations']
