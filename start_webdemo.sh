#!/usr/bin/env bash
# macOS / Linux 启动脚本
set -euo pipefail

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
ROOT="$(cd "$(dirname "$0")" && pwd)"
URL="http://${HOST}:${PORT}"
KEY_FILE="${ROOT}/start_webdemo.keys.sh"
LOG_DIR="${ROOT}/outputs/logs"
mkdir -p "${LOG_DIR}"

if [[ ! -f "$KEY_FILE" ]]; then
  cat >"$KEY_FILE" <<'EOF'
#!/usr/bin/env bash
# Fill your API keys below, save this file, then run ./start_webdemo.sh again.
export ARK_API_KEY="PASTE_SEEDREAM_API_KEY_HERE"
export DASHSCOPE_API_KEY="PASTE_TEXT_MODEL_API_KEY_HERE"
export XIAOMI_TTS_API_KEY="PASTE_XIAOMI_TTS_API_KEY_HERE"
EOF
fi

# shellcheck source=/dev/null
source "$KEY_FILE"

if [[ "${ARK_API_KEY}" == "PASTE_SEEDREAM_API_KEY_HERE" ]]; then
  echo "[ERROR] ARK_API_KEY not filled in yet. Please edit: $KEY_FILE"
  exit 1
fi
if [[ "${DASHSCOPE_API_KEY}" == "PASTE_TEXT_MODEL_API_KEY_HERE" ]]; then
  echo "[ERROR] DASHSCOPE_API_KEY not filled in yet. Please edit: $KEY_FILE"
  exit 1
fi
if [[ "${XIAOMI_TTS_API_KEY}" == "PASTE_XIAOMI_TTS_API_KEY_HERE" ]]; then
  echo "[ERROR] XIAOMI_TTS_API_KEY not filled in yet. Please edit: $KEY_FILE"
  exit 1
fi

PYTHON_EXE=""
if [[ -n "${AI4STORY_PYTHON:-}" && -x "${AI4STORY_PYTHON}" ]]; then
  PYTHON_EXE="${AI4STORY_PYTHON}"
fi
if [[ -z "${PYTHON_EXE}" && -x "${HOME}/miniconda3/envs/ai4story/bin/python" ]]; then
  PYTHON_EXE="${HOME}/miniconda3/envs/ai4story/bin/python"
fi
if [[ -z "${PYTHON_EXE}" && -x "${HOME}/miniforge3/envs/ai4story/bin/python" ]]; then
  PYTHON_EXE="${HOME}/miniforge3/envs/ai4story/bin/python"
fi
if [[ -z "${PYTHON_EXE}" && -x "${HOME}/anaconda3/envs/ai4story/bin/python" ]]; then
  PYTHON_EXE="${HOME}/anaconda3/envs/ai4story/bin/python"
fi
if [[ -z "${PYTHON_EXE}" && "${CONDA_DEFAULT_ENV:-}" == "ai4story" && -n "${CONDA_PREFIX:-}" && -x "${CONDA_PREFIX}/bin/python" ]]; then
  PYTHON_EXE="${CONDA_PREFIX}/bin/python"
fi
if [[ -z "${PYTHON_EXE}" ]]; then
  if command -v python3 >/dev/null 2>&1; then
    PYTHON_EXE="$(command -v python3)"
  elif command -v python >/dev/null 2>&1; then
    PYTHON_EXE="$(command -v python)"
  fi
fi
if [[ -z "${PYTHON_EXE}" ]]; then
  echo "[ERROR] Python was not found."
  exit 1
fi

if ! "${PYTHON_EXE}" -c "import fastapi,uvicorn,requests,PIL,dashscope" >/dev/null 2>&1; then
  echo "[ERROR] Missing Python packages in: ${PYTHON_EXE}"
  echo "Create or fix the environment first: conda env create -f environment.yml"
  exit 1
fi

if curl -sf --max-time 2 "${URL}/healthz" >/dev/null 2>&1; then
  echo "AI4Story is already running. Opening ${URL}"
  if command -v open >/dev/null 2>&1; then
    open "${URL}"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "${URL}"
  fi
  exit 0
fi

if lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "[ERROR] Port ${PORT} is already in use."
  echo "Example: PORT=8001 ./start_webdemo.sh"
  exit 1
fi

echo "Starting AI4Story on ${URL}"
cd "${ROOT}"
export ARK_API_KEY DASHSCOPE_API_KEY XIAOMI_TTS_API_KEY
nohup "${PYTHON_EXE}" -m uvicorn apps.api.main:app --host "${HOST}" --port "${PORT}" \
  >>"${LOG_DIR}/backend.out.log" 2>>"${LOG_DIR}/backend.err.log" &

deadline=$((SECONDS + 60))
while (( SECONDS < deadline )); do
  if curl -sf --max-time 2 "${URL}/healthz" >/dev/null 2>&1; then
    echo "AI4Story is ready. Opening ${URL}"
    if command -v open >/dev/null 2>&1; then
      open "${URL}"
    elif command -v xdg-open >/dev/null 2>&1; then
      xdg-open "${URL}"
    fi
    exit 0
  fi
  sleep 1
done

echo "[ERROR] Server did not become ready within 60 seconds."
echo "Check ${LOG_DIR}/backend.err.log for details."
exit 1
