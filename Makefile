# Makefile — ทางลัดรันด่านต่างๆ ของ ปุ้มปุ้ย v9
# ทุก target ตั้ง PYTHONHASHSEED=0 เพื่อให้ hash reproduce ได้
# ใช้:  make ci   |   make smoke   |   make regression DATA=/path/to/data

export PYTHONHASHSEED := 0
export PUOPUY_AUDIT_DATE ?= 2026-06-02
PY ?= python3
DATA ?= /mnt/project

.PHONY: help ci gate smoke pinned mesh agents agents-real regression regression-real coverage baseline-fixture clean

help:
	@echo "เป้าหมายที่ใช้ได้:"
	@echo "  make gate            - ด่านเวอร์ชัน (FAIL ถ้าเพี้ยนระดับอันตราย)"
	@echo "  make smoke           - smoke test (แพ็กเกจครบ/import ได้)"
	@echo "  make pinned          - ตรึง 3 จุด APPROX"
	@echo "  make mesh            - สัญญา mesh (Tier-2 ไม่เพี้ยนเงียบ)"
	@echo "  make agents          - สัญญา agent บน fixture"
	@echo "  make regression      - regression engine==agent บน fixture (hash ad0c9dad)"
	@echo "  make coverage        - coverage gate (line ≥90% + branch ≥85%; override: BRANCH_MIN=NN)"
	@echo "  make ci              - รันด่านทั้งหมด (gate+smoke+pinned+mesh+agents+regression+coverage)"
	@echo "  make regression-real DATA=<dir> - regression เต็มบนข้อมูลจริง (baseline 23b315e8, 148 ไฟล์)"
	@echo "  make agents-real DATA=<dir>     - สัญญา agent + เช็คเลข baseline (ต้องมี 148 ไฟล์)"
	@echo "  make baseline-fixture - สร้าง baseline ของ fixture ใหม่ (เมื่อแก้ fixture โดยตั้งใจ)"

gate:
	$(PY) version_gate.py

smoke:
	$(PY) smoke_test.py

pinned:
	$(PY) test_pinned_logic.py

mesh:
	$(PY) test_mesh_contract.py

agents:
	$(PY) test_agents.py . tests/fixtures

agents-real:
	$(PY) test_agents.py . $(DATA)

regression:
	$(PY) regression_full.py . tests/fixtures tests/fixtures/baseline_fixture.json

regression-real:
	$(PY) regression_full.py . $(DATA)

coverage:
	PUOPUY_COV_BRANCH_MIN=$(or $(BRANCH_MIN),85) $(PY) coverage_gate.py

ci: gate smoke pinned mesh agents regression coverage
	@echo "✅ CI (fixture) ผ่านทั้งหมด"

baseline-fixture:
	$(PY) golden_master.py . tests/fixtures/baseline_fixture.json tests/fixtures
	$(PY) verify_golden.py . tests/fixtures/baseline_fixture.json tests/fixtures

clean:
	rm -f master_companies.json /tmp/_reg_engine.json
	find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
