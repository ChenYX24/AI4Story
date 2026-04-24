@echo off
setlocal

rem ======================================================================
rem  AI4Story 开发启动脚本 (Windows)
rem  同时启动：前端 Vite dev server + 后端 uvicorn (--reload)
rem ======================================================================

set "HOST=0.0.0.0"
set "PORT=8000"
set "ROOT=%~dp0"
set "KEY_FILE=%ROOT%start_webdemo.keys.cmd"

rem ---- 加载 API Keys ----
if not exist "%KEY_FILE%" (
  >"%KEY_FILE%" echo @echo off
  >>"%KEY_FILE%" echo rem Fill your API keys below, save this file, then run start_webdemo.cmd again.
  >>"%KEY_FILE%" echo set "ARK_API_KEY=PASTE_SEEDREAM_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "DASHSCOPE_API_KEY=PASTE_TEXT_MODEL_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "XIAOMI_TTS_API_KEY=PASTE_XIAOMI_TTS_API_KEY_HERE"
)
call "%KEY_FILE%"

if /I "%ARK_API_KEY%"=="PASTE_SEEDREAM_API_KEY_HERE" (
  echo [ERROR] ARK_API_KEY not filled in yet. Edit: %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  pause & exit /b 1
)
if /I "%DASHSCOPE_API_KEY%"=="PASTE_TEXT_MODEL_API_KEY_HERE" (
  echo [ERROR] DASHSCOPE_API_KEY not filled in yet. Edit: %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  pause & exit /b 1
)

rem ---- 找 Python ----
set "PYTHON_EXE="
if defined AI4STORY_PYTHON if exist "%AI4STORY_PYTHON%" set "PYTHON_EXE=%AI4STORY_PYTHON%"
if not defined PYTHON_EXE if exist "D:\Miniconda\envs\ai4story\python.exe" set "PYTHON_EXE=D:\Miniconda\envs\ai4story\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\ai4story\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\ai4story\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\ai4story\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\ai4story\python.exe"
if not defined PYTHON_EXE if /I "%CONDA_DEFAULT_ENV%"=="ai4story" if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
if not defined PYTHON_EXE for %%I in (python.exe) do set "PYTHON_EXE=%%~$PATH:I"

if not defined PYTHON_EXE (
  echo [ERROR] Python not found. Set AI4STORY_PYTHON or activate ai4story env.
  pause & exit /b 1
)

"%PYTHON_EXE%" -c "import fastapi,uvicorn" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Missing Python packages (fastapi/uvicorn) in: %PYTHON_EXE%
  pause & exit /b 1
)

rem ---- 检查端口 ----
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo [ERROR] Port %PORT% is already in use.
  pause & exit /b 1
)

rem ---- 前端依赖检查 ----
set "WEB_DIR=%ROOT%apps\web"
if not exist "%WEB_DIR%\node_modules" (
  echo [BUILD] Installing frontend dependencies...
  pushd "%WEB_DIR%"
  where pnpm >nul 2>&1
  if errorlevel 1 (
    call npm install
  ) else (
    call pnpm install
  )
  popd
)

rem ---- 启动后端 (uvicorn --factory --reload) ----
echo [START] Backend: uvicorn on http://%HOST%:%PORT%
start "AI4Story Backend" /D "%ROOT%" "%PYTHON_EXE%" -m uvicorn apps.api.main:create_app --host %HOST% --port %PORT% --factory --reload

rem ---- 启动前端 (Vite dev server) ----
echo [START] Frontend: Vite dev server
start "AI4Story Frontend" /D "%WEB_DIR%" cmd /c "npm run dev"

rem ---- 等后端就绪后打开浏览器 ----
set "URL=http://127.0.0.1:%PORT%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='%URL%/healthz'; $deadline=(Get-Date).AddSeconds(30); while((Get-Date) -lt $deadline){ try { $r = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 (
  echo [WARN] Backend not ready in 30s, check the console window.
) else (
  echo [READY] Opening http://localhost:5173 (Vite dev)
  start "" "http://localhost:5173"
)

exit /b 0
