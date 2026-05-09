# ============================================================
# Gunicorn 설정 — 라즈베리파이 최적화
# ============================================================
# 실행: gunicorn -c gunicorn_config.py app:app
# ============================================================

import multiprocessing
import os

# ── 바인딩 ──
bind = os.environ.get("BIND", "0.0.0.0:5000")

# ── 워커 수 ──
# 라즈베리파이 4: 코어 4개 → 워커 2~3개 권장 (메모리 절약)
# 라즈베리파이 3: 코어 4개 → 워커 2개 권장
# 공식: (코어 수 * 2) + 1 이지만, 라즈베리파이는 메모리 제한으로 축소
workers = int(os.environ.get("WORKERS", min(multiprocessing.cpu_count(), 3)))

# ── 워커 클래스 ──
# gthread: 멀티스레드로 다중 접속 처리 (메모리 효율적)
worker_class = "gthread"
threads = int(os.environ.get("THREADS", 4))

# ── 타임아웃 ──
timeout = 30          # 워커 응답 제한
graceful_timeout = 10 # 종료 시 대기
keepalive = 5         # Keep-alive 연결 유지

# ── 메모리 관리 ──
max_requests = 1000        # 워커당 최대 요청 후 재시작 (메모리 누수 방지)
max_requests_jitter = 100  # 동시 재시작 방지용 랜덤 오프셋

# ── 보안 ──
limit_request_line = 4096       # URL 최대 길이
limit_request_fields = 50       # 헤더 최대 개수
limit_request_field_size = 8190 # 헤더 최대 크기

# ── 로깅 ──
accesslog = "-"                 # stdout
errorlog = "-"                  # stdout
loglevel = os.environ.get("LOG_LEVEL", "info")

# ── Preload (메모리 절약) ──
preload_app = True

# ── 프로세스 이름 ──
proc_name = "lumion-web"
