# Dockerfile — ปุ้มปุ้ย (Puopuy) · offline reproducible build (ประกัน 5 ปี)
# golden 08e6abfd · Python 3.12 · ติดตั้ง deps จาก wheelhouse (offline + hash-pinned)
#
# build:  docker build -t puopuy:9.3.4 .
# run  :  docker run --rm -v /path/to/data:/mnt/project puopuy:9.3.4 \
#             python regression_full.py . /mnt/project baseline.json
#
# หมายเหตุ 5 ปี: base image python:3.12-slim ดึงจาก Docker Hub.
#   ถ้าต้องการ offline 100% (เผื่อ Hub เปลี่ยน/หาย) ให้เก็บ base image ไว้ด้วย:
#       docker pull python:3.12-slim && docker save python:3.12-slim -o python312-slim.tar
#   แล้วโหลดกลับ:  docker load -i python312-slim.tar

FROM python:3.12-slim

# determinism env — golden ผูกกับค่านี้ (ต้องตั้งเสมอ)
ENV PYTHONHASHSEED=0 \
    PUOPUY_AUDIT_DATE=2026-06-02 \
    PUOPUY_OFFLINE=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUTF8=1

WORKDIR /app
COPY . /app

# ติดตั้ง offline จาก wheelhouse เท่านั้น (--no-index = ไม่แตะ internet,
# --require-hashes = ตรวจ sha256 ทุก wheel กันไฟล์เพี้ยน). ไม่มี pythainlp (landmine #6).
RUN pip install --no-index --find-links vendor/wheels --require-hashes -r requirements.lock \
    && rm -rf /root/.cache/pip

# smoke test ตอน build: fixture invariant (ไม่ต้องใช้ corpus) — build จะ fail ถ้า env เพี้ยน
RUN python INVARIANTS/check_invariants.py

# default: เปิด shell ให้เจ้าของ mount corpus แล้วรันรายงาน/gate เอง
#   เช่น:  bash run_ci.sh /mnt/project
#          python super_ultra_viewer.py /mnt/project /out
CMD ["/bin/bash"]
