#!/usr/bin/env bash
# 律问 · 云服务器一键部署（Ubuntu 22.04/24.04，root 或 sudo 运行）
# 前提：项目已上传到 /opt/lawq（含 data/laws.db 与 data/bm25.pkl），.env 已配置 ZHIPU_API_KEY
# 用法：sudo bash /opt/lawq/deploy/deploy.sh [--domain 你的域名]
set -euo pipefail

APP_DIR="/opt/lawq"
DOMAIN=""
[ "${1:-}" = "--domain" ] && DOMAIN="${2:-}"

if [ "$(id -u)" -ne 0 ]; then echo "请用 sudo 运行"; exit 1; fi

echo "==> 1/6 系统依赖"
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip nginx >/dev/null

echo "==> 2/6 检查项目与数据"
[ -f "$APP_DIR/app/main.py" ] || { echo "缺少 $APP_DIR/app，请先把项目上传到 /opt/lawq"; exit 1; }
[ -f "$APP_DIR/data/laws.db" ] || { echo "缺少 data/laws.db：请在本机运行 scripts/build_corpus.py 后随代码一起上传"; exit 1; }
[ -f "$APP_DIR/.env" ] || { echo "警告：缺少 .env（cp .env.example .env 并填 ZHIPU_API_KEY），未配置时问答退化为纯检索模式"; }

RUN_USER="${SUDO_USER:-ubuntu}"
id "$RUN_USER" >/dev/null 2>&1 || RUN_USER=root

echo "==> 3/6 Python 环境"
cd "$APP_DIR"
[ -d .venv ] || python3 -m venv .venv
./.venv/bin/pip install -q --upgrade pip
./.venv/bin/pip install -q -r requirements.txt
chown -R "$RUN_USER":"$RUN_USER" "$APP_DIR"

echo "==> 4/6 systemd 服务"
sed -e "s|/opt/lawq|$APP_DIR|g" -e "s|User=ubuntu|User=$RUN_USER|" \
    "$APP_DIR/deploy/lawq.service" > /etc/systemd/system/lawq.service
systemctl daemon-reload
systemctl enable --now lawq
sleep 2
systemctl --no-pager --lines 3 status lawq || true

echo "==> 5/6 nginx 站点"
sed "s|/opt/lawq|$APP_DIR|g" "$APP_DIR/deploy/nginx-lawq.conf" > /etc/nginx/sites-available/lawq
[ "${DOMAIN:-}" ] && sed -i "s|server_name _;|server_name $DOMAIN;|" /etc/nginx/sites-available/lawq
ln -sf /etc/nginx/sites-available/lawq /etc/nginx/sites-enabled/lawq
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

echo "==> 6/6 防火墙"
if command -v ufw >/dev/null; then
  ufw allow 22/tcp >/dev/null 2>&1 || true
  ufw allow 80/tcp  >/dev/null 2>&1 || true
  ufw allow 8080/tcp >/dev/null 2>&1 || true
  ufw allow 443/tcp >/dev/null 2>&1 || true
fi

IP=$(curl -s --max-time 3 ifconfig.me || echo 服务器IP)
echo ""
echo "✅ 部署完成"
echo "   本机验证： curl http://127.0.0.1/api/health"
echo "   外网验证： http://${IP}:8080  （未备案期间）"
echo "   服务管理： systemctl status|restart lawq"
[ "${DOMAIN:-}" ] && echo "   域名解析生效并备案通过后：certbot --nginx -d $DOMAIN"
