# ============================================================
# LumiOn Web Server — Raspberry Pi 최적화 Flask 백엔드
# ============================================================
# 설치: pip install flask flask-limiter flask-talisman gunicorn
# 실행: gunicorn -c gunicorn_config.py app:app
# ============================================================

import os
import logging
from logging.handlers import RotatingFileHandler
from functools import wraps
from hashlib import md5

from flask import (
    Flask, render_template, send_from_directory,
    request, abort, make_response, g
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman

# ──────────────────────────────────────────────
# 앱 초기화
# ──────────────────────────────────────────────
app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)

# 시크릿 키 (세션/CSRF 용)
app.config["SECRET_KEY"] = os.environ.get(
    "SECRET_KEY",
    os.urandom(32).hex()
)

# ──────────────────────────────────────────────
# 로깅 설정
# ──────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler("lumion.log", maxBytes=5_000_000, backupCount=2)
        if not os.environ.get("NO_FILE_LOG")
        else logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Rate Limiting (DDoS / 과부하 방지)
# ──────────────────────────────────────────────
limiter = Limiter(
    key_func=get_remote_address,
    app=app,
    default_limits=["200 per minute", "50 per second"],
    storage_uri="memory://",          # 라즈베리파이: 메모리 기반 (Redis 불필요)
    strategy="fixed-window"
)

# ──────────────────────────────────────────────
# 보안 헤더 (CSP, HSTS, XSS 방어 등)
# ──────────────────────────────────────────────
csp = {
    "default-src": "'self'",
    "script-src": "'self' 'unsafe-inline'",
    "style-src": "'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src": "'self' https://fonts.gstatic.com",
    "img-src": "'self' data:",
    "connect-src": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'self'",
    "form-action": "'self'"
}

# HTTPS 강제 여부 (로컬 개발 시 False)
FORCE_HTTPS = os.environ.get("FORCE_HTTPS", "false").lower() == "true"

Talisman(
    app,
    force_https=FORCE_HTTPS,
    content_security_policy=csp,
    strict_transport_security=FORCE_HTTPS,
    session_cookie_secure=FORCE_HTTPS,
    session_cookie_http_only=True,
    frame_options="DENY",
    x_content_type_options=True,
    x_xss_protection=True,
    referrer_policy="strict-origin-when-cross-origin"
)

# ──────────────────────────────────────────────
# 정적 파일 캐싱 (라즈베리파이 부하 절감)
# ──────────────────────────────────────────────
STATIC_CACHE_TIMEOUT = int(os.environ.get("STATIC_CACHE_TIMEOUT", 86400))  # 24시간

# 템플릿 캐싱 (렌더링 결과 메모리 캐시)
_page_cache = {}
_page_cache_etag = {}


def cached_page(timeout_seconds=300):
    """간단한 페이지 캐시 데코레이터 (라즈베리파이 CPU 절약)"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            cache_key = request.path

            # ETag 기반 304 응답
            if cache_key in _page_cache_etag:
                client_etag = request.headers.get("If-None-Match")
                if client_etag == _page_cache_etag[cache_key]:
                    return make_response("", 304)

            # 캐시 히트
            if cache_key in _page_cache:
                resp = make_response(_page_cache[cache_key])
                resp.headers["ETag"] = _page_cache_etag[cache_key]
                resp.headers["Cache-Control"] = f"public, max-age={timeout_seconds}"
                return resp

            # 캐시 미스 → 렌더링
            result = f(*args, **kwargs)
            etag = md5(result.encode()).hexdigest()

            _page_cache[cache_key] = result
            _page_cache_etag[cache_key] = etag

            resp = make_response(result)
            resp.headers["ETag"] = etag
            resp.headers["Cache-Control"] = f"public, max-age={timeout_seconds}"
            return resp

        return wrapper
    return decorator


# ──────────────────────────────────────────────
# 요청 전/후 처리
# ──────────────────────────────────────────────
@app.before_request
def before_request():
    """악의적 요청 차단"""
    # 경로 탐색 공격 차단
    if ".." in request.path or "//" in request.path:
        abort(400)

    # 비정상적으로 큰 요청 차단 (1MB)
    if request.content_length and request.content_length > 1_048_576:
        abort(413)


@app.after_request
def after_request(response):
    """공통 보안/성능 헤더"""
    # Gzip 압축 힌트 (gunicorn/nginx에서 처리)
    response.headers["Vary"] = "Accept-Encoding"

    # 정적 파일 장기 캐싱
    if request.path.startswith("/static/"):
        response.headers["Cache-Control"] = f"public, max-age={STATIC_CACHE_TIMEOUT}, immutable"

    return response


# ──────────────────────────────────────────────
# 라우트
# ──────────────────────────────────────────────
@app.route("/")
@limiter.limit("30 per minute")
@cached_page(timeout_seconds=600)  # 10분 캐시
def index():
    """메인 랜딩 페이지"""
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    """파비콘"""
    return send_from_directory(
        app.static_folder, "lumion.png",
        mimetype="image/png",
        max_age=STATIC_CACHE_TIMEOUT
    )


@app.route("/robots.txt")
def robots():
    """검색 엔진 크롤러 제어"""
    return make_response(
        "User-agent: *\nAllow: /\nSitemap: \n",
        200,
        {"Content-Type": "text/plain"}
    )


# ──────────────────────────────────────────────
# 에러 핸들러
# ──────────────────────────────────────────────
@app.errorhandler(404)
def not_found(e):
    return make_response(
        "<h1 style='text-align:center;margin-top:20vh;font-family:sans-serif;color:#8b6cff'>"
        "404 — 페이지를 찾을 수 없습니다</h1>",
        404
    )


@app.errorhandler(429)
def rate_limited(e):
    return make_response(
        "<h1 style='text-align:center;margin-top:20vh;font-family:sans-serif;color:#ff5e8a'>"
        "429 — 요청이 너무 많습니다. 잠시 후 다시 시도해주세요.</h1>",
        429
    )


@app.errorhandler(500)
def server_error(e):
    logger.error(f"Internal error: {e}")
    return make_response(
        "<h1 style='text-align:center;margin-top:20vh;font-family:sans-serif;color:#ff5e8a'>"
        "500 — 서버 오류가 발생했습니다</h1>",
        500
    )


# ──────────────────────────────────────────────
# 직접 실행 (개발용)
# ──────────────────────────────────────────────
if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    )
