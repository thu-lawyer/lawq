#!/usr/bin/env bash
# 律问 · 一键本地启动：建环境 → 建法条库(首次) → 起服务 → 开浏览器
set -e
cd "$(dirname "$0")"
PORT="${LAWQ_PORT:-8790}"

[ -d .venv ] || python3 -m venv .venv
source .venv/bin/activate
pip install -q -r requirements.txt

[ -f data/laws.db ] || python scripts/build_corpus.py
[ -f .env ] || { cp .env.example .env; echo "已生成 .env，可填入 ZHIPU_API_KEY 开启智能问答（不填也能用）"; }

echo ""
echo "  律问 · 法律检索问答  →  http://127.0.0.1:${PORT}"
echo ""
( sleep 2; open "http://127.0.0.1:${PORT}" ) 2>/dev/null &
exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT}"