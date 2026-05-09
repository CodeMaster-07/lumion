#!/bin/bash
# ============================================================
# LumiOn 설치 & 실행 스크립트
# 사용법: chmod +x setup.sh && ./setup.sh
# ============================================================

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  🟣 LumiOn 웹서버 설치 시작"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# 가상환경 생성
echo "[1/3] 가상환경 생성 중..."
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
echo "[2/3] 패키지 설치 중..."
pip install -r requirements.txt --quiet

# lumion.png 확인
if [ ! -f "static/lumion.png" ]; then
    echo ""
    echo "⚠️  static/lumion.png 파일이 없습니다!"
    echo "    로고 이미지를 static/lumion.png 경로에 넣어주세요."
    echo ""
fi

# 실행
echo "[3/3] 서버 시작!"
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  ✅ http://0.0.0.0:5000 에서 접속 가능"
echo "  ✅ 같은 네트워크: http://$(hostname -I | awk '{print $1}'):5000"
echo "  ✅ 종료: Ctrl+C"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""

gunicorn -c gunicorn_config.py app:app
