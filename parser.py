# -*- coding: utf-8 -*-
"""parser.py — OBJ-MAINT: ซอยเพื่อ maintainability (≲600/ไฟล์) แบบ pure extraction + re-export.
logic/golden ไม่เปลี่ยน. โครง: parser_p0, parser_p1, parser_p2 (cascade import) → ไฟล์นี้ re-export + __all__ เดิม.
ทุก body extract ด้วย AST line-slice (byte-identical). public API เดิมครบ."""
from __future__ import annotations
from parser_p2 import *  # noqa: F401,F403


__all__ = [
    # [P-DAG พาส3a] ฟังก์ชันระดับชื่อไฟล์/รวมหน้า (ย้ายมาจาก main) — public API ของ parser
    'parse_filename', 'merge_continuation_bills', '_declared_period_from_filename',
    'get_files_via_upload', 'get_files_via_drive',   # [P-DAG พาส3g]
    'read_workbook', '_find_unit_col', '_dic_find_seq', '_dic_int_run',
    '_dic_item_rows', '_dic_find_name', '_dic_text_score', '_dic_find_amt',
    '_dic_collect_numeric', '_dic_score_combo', '_dic_pick_qty_price', '_dic_pick_unit',
    'detect_item_columns', 'detect_item_columns_safe', '_pick_best_iv_safe', '_has_suspat_in_iv',
    'check_iv_format', '_addr_parse_confidence', '_detect_vat_rows',
    '_pick_best_iv', '_extract_taxid_safe', '_taxid_from_cell', '_scan_tax_id_block',
    '_scan_branch_block', '_strip_thai_marks', '_row_label_match', '_label_in_text',
    '_rightmost_num', '_cell_to_num', 'audit_text_num_reset', '_record_text_num',
    'audit_text_num_summary', '_label_based_amounts', '_reconcile_amounts', '_looks_like_address',
    '_pb_try_company', '_pb_try_address_line', '_pb_taxid_from_numeric', '_pb_taxid_from_string',
    '_pb_try_taxid', '_pb_try_iv', '_pb_scan_header', '_pb_extract_items',
    '_pb_build_item', '_pb_find_vat_row', '_row_has_vat_marker', '_pb_amounts_from_vatrow',
    '_pb_finalize_amounts', '_parse_block', '_is_tor_format', '_tor_scan_iv_date',
    '_tor_try_date', '_tor_scan_company', '_tor_cell_company', '_tor_numval',
    '_tor_scan_items', '_tor_scan_subtotal', '_tor_scan_vat', '_tor_scan_total',
    '_parse_tor_sheet', 'parse_sheet', 'parse_file', '_raw_iv_form',
]
