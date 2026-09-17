# ============================================================
#  LumiOn 웹서버 — 라즈베리파이 설치 가이드
# ============================================================

## 📁 폴더 구조

```
/home/pi/lumion/
├── app.py                 ← Flask 백엔드
├── gunicorn_config.py     ← Gunicorn 설정
├── requirements.txt       ← 의존성
├── lumion.service          ← systemd 서비스 (복사용)
├── templates/
│   └── index.html          ← 랜딩 페이지 HTML
└── static/
    └── lumion.png          ← 로고 이미지 (파비콘 겸용)
```


## 🚀 설치 방법

```bash
# 1. 프로젝트 폴더 생성
mkdir -p /home/pi/lumion/templates /home/pi/lumion/static
cd /home/pi/lumion

# 2. 파일 배치 (위 구조대로)

# 3. 가상환경 생성 & 패키지 설치
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 4. 테스트 실행
python app.py
# → http://라즈베리파이IP:5000 접속 확인

# 5. 프로덕션 실행 (Gunicorn)
gunicorn -c gunicorn_config.py app:app
```


## 🔁 자동 실행 (부팅 시)

```bash
sudo cp lumion.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable lumion
sudo systemctl start lumion

# 상태 확인
sudo systemctl status lumion

# 로그 확인
sudo journalctl -u lumion -f
```

## 🤖 Discord 봇 상시 운영

라즈베리파이에서는 메인 봇을 수동 `nohup`이 아닌 systemd로 실행하세요. 이렇게 하면 부팅 후 자동 시작되고, 네트워크 오류나 프로세스 종료 시 5초 뒤 자동 재시작됩니다.

```bash
sudo cp server/lumion-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lumion-bot.service
sudo journalctl -u lumion-bot.service -f
```

메인 봇의 Discord 상태에는 `PRESENCE_ACTIVITY_TEXT` 환경 변수(기본값: `24시간 깨어있는중`)가 표시됩니다. 상태 표시용 별도 연결은 사용하지 않아 중복 Gateway 세션과 끊김을 줄였습니다.


## ⚙️ 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `PORT` | 5000 | 서버 포트 |
| `WORKERS` | CPU 코어 수 (최대 3) | Gunicorn 워커 수 |
| `THREADS` | 4 | 워커당 스레드 수 |
| `FORCE_HTTPS` | false | HTTPS 강제 여부 |
| `STATIC_CACHE_TIMEOUT` | 86400 | 정적 파일 캐시 (초) |
| `SECRET_KEY` | 자동 생성 | Flask 시크릿 키 |


## 🛡️ 적용된 보안

- **Rate Limiting**: 분당 200회, 초당 50회 제한
- **CSP 헤더**: XSS, 인젝션 방어
- **경로 탐색 차단**: `..`, `//` 요청 거부
- **요청 크기 제한**: 1MB 초과 차단
- **보안 헤더**: X-Frame-Options, X-Content-Type-Options 등
- **systemd 샌드박싱**: 파일시스템 읽기 전용, 메모리 제한


## 🔧 라즈베리파이 최적화 포인트

- **gthread 워커**: fork 대신 스레드로 메모리 절약
- **페이지 캐싱**: 렌더링 결과 메모리 캐시 + ETag 304 응답
- **정적 파일 장기 캐시**: 24시간 브라우저 캐싱
- **워커 자동 재시작**: 1000 요청마다 재시작 (메모리 누수 방지)
- **preload_app**: 앱을 미리 로드해 워커 간 메모리 공유
- **메모리 상한**: systemd에서 256MB로 제한
