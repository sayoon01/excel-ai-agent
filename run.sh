#!/bin/bash
# Excel AI Platform 실행 스크립트
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 가상환경 생성 (최초 1회)
if [ ! -d "venv" ]; then
    echo "가상환경 생성 중..."
    /usr/bin/python3.12 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
else
    source venv/bin/activate
fi

streamlit run app.py "$@"
