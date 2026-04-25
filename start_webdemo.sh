#!/usr/bin/env bash
# AI4Story 开发启动脚本 (macOS / Linux)
# 同时启动：前端 Vite dev server + 后端 uvicorn (--reload)
set -euo pipefail

HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
KEY_FILE="${ROOT}/start_webdemo.keys.sh"
LOG_DIR="${ROOT}/outputs/logs"
mkdir -p "${LOG_DIR}"

# ---- 加载 API Keys ----
if [[ ! -f "$KEY_FILE" ]]; then
  cat >"$KEY_FILE" <<'EOF'
#!/usr/bin/env bash
export ARK_API_KEY="PASTE_SEEDREAM_API_KEY_HERE"
# 主语言模型（默认 mikaovo.ai 的 gpt-5-4），把 mikaovo 平台的 API key 粘进来。
export LLM_API_KEY="PASTE_LLM_API_KEY_HERE"
# 可选覆盖：默认 https://api.mikaovo.ai/v1 / gpt-5-4，没事别动。
# export LLM_BASE_URL="https://api.mikaovo.ai/v1"
# export LLM_MODEL="gpt-5-4"
# ASR（语音识别）仍走 DashScope；不用语音可留空。
export DASHSCOPE_API_KEY="PASTE_DASHSCOPE_API_KEY_HERE"
export XIAOMI_TTS_API_KEY="PASTE_XIAOMI_TTS_API_KEY_HERE"
EOF
fi
# shellcheck source=/dev/null
source "$KEY_FILE"

if [[ "${ARK_API_KEY}" == "PASTE_SEEDREAM_API_KEY_HERE" ]]; then
  echo "[ERROR] ARK_API_KEY not filled in yet. Edit: $KEY_FILE"; exit 1
fi
if [[ "${LLM_API_KEY:-}" == "PASTE_LLM_API_KEY_HERE" || -z "${LLM_API_KEY:-}" ]]; then
  echo "[ERROR] LLM_API_KEY not filled in yet. Edit: $KEY_FILE"; exit 1
fi
if [[ "${DASHSCOPE_API_KEY:-}" == "PASTE_DASHSCOPE_API_KEY_HERE" ]]; then
  echo "[WARN] DASHSCOPE_API_KEY not filled in. ASR / 语音识别 will be unavailable."
fi

# ---- 找 Python ----
PYTHON_EXE=""
if [[ -n "${AI4STORY_PYTHON:-}" && -x "${AI4STORY_PYTHON}" ]]; then
  PYTHON_EXE="${AI4STORY_PYTHON}"
fi
for p in \
  "${HOME}/miniconda3/envs/ai4story/bin/python" \
  "${HOME}/miniforge3/envs/ai4story/bin/python" \
  "${HOME}/anaconda3/envs/ai4story/bin/python"; do
  if [[ -z "${PYTHON_EXE}" && -x "$p" ]]; then PYTHON_EXE="$p"; fi
done
if [[ -z "${PYTHON_EXE}" && "${CONDA_DEFAULT_ENV:-}" == "ai4story" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
  PYTHON_EXE="${CONDA_PREFIX}/bin/python"
fi
if [[ -z "${PYTHON_EXE}" ]]; then
  PYTHON_EXE="$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)"
fi
if [[ -z "${PYTHON_EXE}" ]]; then
  echo "[ERROR] Python not found."; exit 1
fi

if ! "${PYTHON_EXE}" -c "import fastapi,uvicorn" >/dev/null 2>&1; then
  echo "[ERROR] Missing Python packages (fastapi/uvicorn) in: ${PYTHON_EXE}"; exit 1
fi

# ---- 检查端口 ----
if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[ERROR] Port ${PORT} is already in use. PORT=8001 ./start_webdemo.sh"; exit 1
fi

# ---- 前端依赖 ----
WEB_DIR="${ROOT}/apps/web"
if [[ -f "${WEB_DIR}/package.json" && ! -d "${WEB_DIR}/node_modules" ]]; then
  echo "[BUILD] Installing frontend dependencies..."
  if command -v pnpm >/dev/null 2>&1; then
    (cd "${WEB_DIR}" && pnpm install --silent)
  elif command -v npm >/dev/null 2>&1; then
    (cd "${WEB_DIR}" && npm install --silent)
  else
    echo "[ERROR] Neither pnpm nor npm found."; exit 1
  fi
fi

# ---- 启动后端 ----
echo "[START] Backend: uvicorn on http://${HOST}:${PORT}"
cd "${ROOT}"
export ARK_API_KEY DASHSCOPE_API_KEY XIAOMI_TTS_API_KEY LLM_API_KEY LLM_BASE_URL LLM_MODEL
"${PYTHON_EXE}" -m uvicorn apps.api.main:create_app \
  --host "${HOST}" --port "${PORT}" --factory --reload \
  >>"${LOG_DIR}/backend.out.log" 2>>"${LOG_DIR}/backend.err.log" &
BACKEND_PID=$!

# ---- 启动前端 ----
echo "[START] Frontend: Vite dev server"
if command -v pnpm >/dev/null 2>&1; then
  (cd "${WEB_DIR}" && pnpm dev) &
else
  (cd "${WEB_DIR}" && npm run dev) &
fi
FRONTEND_PID=$!

# ---- Ctrl+C 同时停两个 ----
trap "kill ${BACKEND_PID} ${FRONTEND_PID} 2>/dev/null; exit" INT TERM

# ---- 等后端就绪 ----
URL="http://127.0.0.1:${PORT}"
deadline=$((SECONDS + 30))
while (( SECONDS < deadline )); do
  if curl -sf --max-time 2 "${URL}/healthz" >/dev/null 2>&1; then
    echo "[READY] Backend ready. Frontend at http://localhost:5173"
    if command -v open >/dev/null 2>&1; then open "http://localhost:5173"
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "http://localhost:5173"
    fi
    break
  fi
  sleep 1
done

wait
