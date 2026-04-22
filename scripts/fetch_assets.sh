#!/usr/bin/env bash
# fetch_assets.sh — 协作者用。
# 把 scenes/ 下的预置图片资源恢复到本地工作树（因为图片不进 git）。
#
# 支持四种来源，按优先级：
#   1) --from <tarball.tar.gz>      本地 tar.gz 解压
#   2) --from-url <https://...>     HTTP(S) 下载后解压
#   3) --from-dir <path>            rsync 自另一台机器 (有完整 scenes/)
#   4) env MINDSHOW_ASSETS_URL      同 --from-url
#
# 示例
#   # 收到维护者发来的 tar
#   bash scripts/fetch_assets.sh --from ~/Downloads/scenes-assets-2026-04-22.tar.gz
#
#   # 从 GitHub Release 下载
#   bash scripts/fetch_assets.sh --from-url https://github.com/ChenYX24/AI4Story/releases/download/assets-2026-04-22/scenes-assets-2026-04-22.tar.gz
#
#   # 本机另一个工作目录有完整图
#   bash scripts/fetch_assets.sh --from-dir /Users/xxx/projects/AI4Story_v2_backup
#
# 完成后 scenes/ 下会有 45+ PNG / 31+ SVG，前后端直接可用。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

MODE=""
ARG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)      MODE="file";  ARG="$2"; shift 2 ;;
    --from-url)  MODE="url";   ARG="$2"; shift 2 ;;
    --from-dir)  MODE="dir";   ARG="$2"; shift 2 ;;
    -h|--help)
      sed -n '1,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      echo "[ERROR] 未知参数: $1"
      exit 1
      ;;
  esac
done

# 兜底：env
if [[ -z "$MODE" && -n "${MINDSHOW_ASSETS_URL:-}" ]]; then
  MODE="url"
  ARG="$MINDSHOW_ASSETS_URL"
fi

if [[ -z "$MODE" ]]; then
  cat <<'EOF'
[ERROR] 没有指定资产来源。

三种方式任选一：
  bash scripts/fetch_assets.sh --from <tarball.tar.gz>
  bash scripts/fetch_assets.sh --from-url <http(s)://.../assets.tar.gz>
  bash scripts/fetch_assets.sh --from-dir <path/with/scenes>

或：  export MINDSHOW_ASSETS_URL=... && bash scripts/fetch_assets.sh
EOF
  exit 1
fi

case "$MODE" in
  file)
    if [[ ! -f "$ARG" ]]; then
      echo "[ERROR] 文件不存在: $ARG"
      exit 1
    fi
    echo "[info] 解压 $ARG 到项目根目录..."
    tar -xzf "$ARG" -C "$ROOT"
    ;;
  url)
    TMP="$(mktemp -t mindshow-assets.XXXXXX.tar.gz)"
    trap "rm -f '$TMP'" EXIT
    echo "[info] 下载 $ARG..."
    if command -v curl >/dev/null 2>&1; then
      curl -L --fail --progress-bar "$ARG" -o "$TMP"
    elif command -v wget >/dev/null 2>&1; then
      wget -O "$TMP" "$ARG"
    else
      echo "[ERROR] 需要 curl 或 wget"; exit 1
    fi
    echo "[info] 解压..."
    tar -xzf "$TMP" -C "$ROOT"
    ;;
  dir)
    if [[ ! -d "$ARG/scenes" ]]; then
      echo "[ERROR] $ARG/scenes 不存在"
      exit 1
    fi
    echo "[info] rsync $ARG/scenes/ 到 ./scenes/..."
    if command -v rsync >/dev/null 2>&1; then
      rsync -av --exclude '_object_grids' --exclude '_refs' --exclude '_character_grids' --exclude 'placements.json' \
        "$ARG/scenes/" "$ROOT/scenes/"
    else
      cp -R "$ARG/scenes/." "$ROOT/scenes/"
    fi
    ;;
esac

PNG=$(find scenes -name '*.png' 2>/dev/null | wc -l | tr -d ' ')
SVG=$(find scenes -name '*.svg' 2>/dev/null | wc -l | tr -d ' ')

echo ""
echo "[done] 资产恢复完成"
echo "       scenes/ PNG: $PNG"
echo "       scenes/ SVG: $SVG"
echo ""
echo "现在可以直接 bash start_webdemo.sh 启动。"
