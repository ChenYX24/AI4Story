#!/usr/bin/env bash
# 在服务器（zwh-txy-sever / 115.190.116.57）上跑这个脚本一次性部署 / 升级。
# 用法：
#   首次：
#     ssh root@115.190.116.57
#     mkdir -p /root/hackthron && cd /root/hackthron
#     git clone https://github.com/ChenYX24/AI4Story.git
#     cd AI4Story
#     # 把 deploy/.env.example 复制成 .env 并把 __FILL_ME__ 换成真实 key
#     cp deploy/.env.example .env && nano .env
#     bash deploy/deploy_server.sh --first-time
#
#   常规升级（CI 也可以调）：
#     bash deploy/deploy_server.sh
#
# 行为：
#   1. git pull 最新代码
#   2. 杀掉现有 ai4story uvicorn 进程
#   3. 安装/更新 conda env + pip 依赖
#   4. 跑 seed_official 把官方 scenes 录入 OSS + DB（首次）
#   5. pnpm install + pnpm build 前端
#   6. 同步 dist → /var/www/ai4story
#   7. 写 systemd unit + nginx 配置（首次）
#   8. 重启服务

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

FIRST_TIME=0
if [[ "${1:-}" == "--first-time" ]]; then FIRST_TIME=1; fi

echo "==> Step 1: git pull"
git fetch --all --prune
git reset --hard origin/main

echo "==> Step 2: kill existing AI4Story processes"
# 不报错：可能本来就没有
pkill -f "uvicorn apps.api.main:app" || true
pkill -f "ai4story" || true
sleep 1

echo "==> Step 3: venv + pip deps"
VENV_DIR="$REPO_ROOT/.venv"
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    PYBIN="$(command -v python3.13 || command -v python3.12 || command -v python3)"
    if [[ -z "$PYBIN" ]]; then
        echo "[ERR] python3 not found. Install python3 first."
        exit 1
    fi
    "$PYBIN" -m venv "$VENV_DIR"
fi
# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"
pip install --upgrade pip wheel >/dev/null
pip install -r requirements.txt
pip install oss2  # 兜底：requirements 应该已经带了

echo "==> Step 4: load .env into shell"
set -a
# shellcheck disable=SC1091
. ./.env
set +a

if [[ "$FIRST_TIME" == "1" ]]; then
    echo "==> Step 4b: seed official scenes (first-time only)"
    python -m scripts.seed_official
fi

echo "==> Step 5: build frontend"
cd "$REPO_ROOT/apps/web"
if ! command -v pnpm >/dev/null; then
    npm install -g pnpm
fi
pnpm install --frozen-lockfile || pnpm install
# 把 .env 里的 VITE_API_BASE 透到 build 上下文
VITE_API_BASE="${VITE_API_BASE:-}" pnpm build

echo "==> Step 6: rsync dist to /var/www/ai4story"
mkdir -p /var/www/ai4story
rsync -a --delete dist/ /var/www/ai4story/

cd "$REPO_ROOT"

if [[ "$FIRST_TIME" == "1" ]]; then
    echo "==> Step 7: install systemd unit + nginx config"
    cp deploy/ai4story.service /etc/systemd/system/ai4story.service
    cp deploy/nginx.conf /etc/nginx/sites-available/ai4story
    ln -sf /etc/nginx/sites-available/ai4story /etc/nginx/sites-enabled/ai4story
    # 删默认 default 站点（如果存在），避免抢 :80
    rm -f /etc/nginx/sites-enabled/default
    systemctl daemon-reload
    systemctl enable ai4story nginx
    nginx -t
fi

echo "==> Step 8: restart services"
systemctl restart ai4story
systemctl reload nginx || systemctl restart nginx

sleep 2
systemctl is-active ai4story >/dev/null && echo "  ✓ ai4story is running" || echo "  ✗ ai4story FAILED — journalctl -u ai4story -n 80"
systemctl is-active nginx >/dev/null && echo "  ✓ nginx is running" || echo "  ✗ nginx FAILED"

echo
echo "Done."
echo "前端：  http://115.190.116.57:8818/"
echo "后端：  http://115.190.116.57:8818/api/"
echo "日志：  journalctl -u ai4story -f"
