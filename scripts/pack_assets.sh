#!/usr/bin/env bash
# pack_assets.sh — 维护者用。
# 把 scenes/ 下所有预置图片资源打包为 tar.gz，便于传给其他开发机/协作者，
# 或作为 GitHub Release 附件分发。
#
# 用法:
#   bash scripts/pack_assets.sh                       # 默认输出到 outputs/releases/
#   bash scripts/pack_assets.sh path/to/output.tgz    # 自定义输出文件
#
# 注意：outputs/ 在 .gitignore，打包文件不会进 git。

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

STAMP="$(date +%Y-%m-%d)"
OUT="${1:-outputs/releases/scenes-assets-$STAMP.tar.gz}"

if [[ ! -d "scenes" ]]; then
  echo "[ERROR] scenes/ 目录不存在于 $ROOT"
  exit 1
fi

if ! find scenes -name "*.png" -o -name "*.svg" | grep -q .; then
  echo "[WARN] scenes/ 下没有图片文件，打出来是空包。"
fi

mkdir -p "$(dirname "$OUT")"

echo "[info] 打包 scenes/ 到 $OUT"
tar -czf "$OUT" \
  --exclude="scenes/*/_object_grids" \
  --exclude="scenes/*/_refs" \
  --exclude="scenes/global/_object_grids" \
  --exclude="scenes/global/_character_grids" \
  --exclude="scenes/*/placements.json" \
  scenes/

SIZE="$(du -h "$OUT" | cut -f1)"
COUNT="$(tar -tzf "$OUT" | wc -l | tr -d ' ')"

echo ""
echo "[done] $OUT"
echo "       大小: $SIZE"
echo "       条目: $COUNT"
echo ""
echo "把它发给协作者，或作为 GitHub Release 附件上传："
echo "  gh release create assets-$STAMP \"$OUT\" --title \"Assets $STAMP\" --notes \"场景图片资产\""
echo "协作者侧用 scripts/fetch_assets.sh 恢复。"
