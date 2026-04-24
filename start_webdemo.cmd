@echo off
setlocal EnableExtensions

rem AI4Story Windows launcher.
rem Keeps the console open on failures, validates local prerequisites, builds the
rem current Vue frontend, starts FastAPI, then opens the Vite dev server.

chcp 65001 >nul

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
set "HOST=%HOST%"
if not defined HOST set "HOST=0.0.0.0"
set "PORT=%PORT%"
if not defined PORT set "PORT=8000"
set "FRONTEND_PORT=%FRONTEND_PORT%"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
set "KEY_FILE=%ROOT%\start_webdemo.keys.cmd"
set "WEB_DIR=%ROOT%\apps\web"
set "LOG_DIR=%ROOT%\outputs\logs"

if not exist "%LOG_DIR%" mkdir "%LOG_DIR%" >nul 2>&1

echo.
echo ============================================================
echo  AI4Story / MindShow launcher
echo ============================================================
echo  Root: %ROOT%
echo  API:  http://127.0.0.1:%PORT%
echo  Web:  http://localhost:%FRONTEND_PORT%
echo.

if not exist "%ROOT%\apps\api\main.py" (
  echo [ERROR] This script must be run from the AI4Story repository root.
  goto fail
)

rem ----------------------------------------------------------------------
rem API keys
rem ----------------------------------------------------------------------
if not exist "%KEY_FILE%" (
  >"%KEY_FILE%" echo @echo off
  >>"%KEY_FILE%" echo rem Fill your API keys below, save this file, then run start_webdemo.cmd again.
  >>"%KEY_FILE%" echo set "ARK_API_KEY=PASTE_SEEDREAM_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "DASHSCOPE_API_KEY=PASTE_TEXT_MODEL_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "XIAOMI_TTS_API_KEY=PASTE_XIAOMI_TTS_API_KEY_HERE"
)
call "%KEY_FILE%"

if /I "%ARK_API_KEY%"=="PASTE_SEEDREAM_API_KEY_HERE" (
  echo [ERROR] ARK_API_KEY is not filled in: %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  goto fail
)
if /I "%DASHSCOPE_API_KEY%"=="PASTE_TEXT_MODEL_API_KEY_HERE" (
  echo [ERROR] DASHSCOPE_API_KEY is not filled in: %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  goto fail
)
if /I "%XIAOMI_TTS_API_KEY%"=="PASTE_XIAOMI_TTS_API_KEY_HERE" (
  echo [WARN] XIAOMI_TTS_API_KEY is not filled in. TTS endpoints may fail.
)

rem ----------------------------------------------------------------------
rem Python environment
rem ----------------------------------------------------------------------
echo [CHECK] Locating Python...
set "PYTHON_EXE="
if defined AI4STORY_PYTHON if exist "%AI4STORY_PYTHON%" set "PYTHON_EXE=%AI4STORY_PYTHON%"
if not defined PYTHON_EXE if exist "D:\Miniconda\envs\ai4story\python.exe" set "PYTHON_EXE=D:\Miniconda\envs\ai4story\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\ai4story\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\ai4story\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniforge3\envs\ai4story\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniforge3\envs\ai4story\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\ai4story\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\ai4story\python.exe"
if not defined PYTHON_EXE if /I "%CONDA_DEFAULT_ENV%"=="ai4story" if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
if not defined PYTHON_EXE for %%I in (python.exe) do set "PYTHON_EXE=%%~$PATH:I"

if not defined PYTHON_EXE (
  echo [ERROR] Python not found. Set AI4STORY_PYTHON or activate the ai4story conda env.
  goto fail
)

echo [OK] Python: %PYTHON_EXE%
"%PYTHON_EXE%" --version
if errorlevel 1 goto fail

echo [CHECK] Installing/verifying Python packages from requirements.txt...
"%PYTHON_EXE%" -m pip install -r "%ROOT%\requirements.txt"
if errorlevel 1 (
  echo [ERROR] Python dependency installation failed.
  goto fail
)

echo [CHECK] Importing backend modules...
"%PYTHON_EXE%" -c "import fastapi, uvicorn, dashscope, requests, PIL; import apps.api.main; print('backend imports ok')"
if errorlevel 1 (
  echo [ERROR] Backend import check failed.
  goto fail
)

rem ----------------------------------------------------------------------
rem Node / frontend dependencies
rem ----------------------------------------------------------------------
echo [CHECK] Locating Node.js and npm...
where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js not found. Install Node.js, then rerun this script.
  goto fail
)
where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] npm not found. Reinstall Node.js with npm enabled.
  goto fail
)
node --version
call npm --version

echo [CHECK] Locating pnpm...
where pnpm >nul 2>&1
if errorlevel 1 (
  where corepack >nul 2>&1
  if not errorlevel 1 (
    echo [SETUP] Enabling pnpm via corepack...
    call corepack enable
    if errorlevel 1 goto fail
    call corepack prepare pnpm@latest --activate
    if errorlevel 1 goto fail
  )
)
where pnpm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] pnpm not found. Install it with: npm install -g pnpm
  goto fail
)
call pnpm --version

echo [CHECK] Installing/verifying frontend packages...
pushd "%WEB_DIR%"
call pnpm install --frozen-lockfile
if errorlevel 1 (
  popd
  echo [ERROR] Frontend dependency installation failed.
  goto fail
)

echo [BUILD] Building current Vue frontend so FastAPI never falls back to legacy...
call pnpm build
if errorlevel 1 (
  popd
  echo [ERROR] Frontend build failed.
  goto fail
)
popd

if not exist "%WEB_DIR%\dist\index.html" (
  echo [ERROR] Vue dist was not created: %WEB_DIR%\dist\index.html
  goto fail
)

rem ----------------------------------------------------------------------
rem Ports
rem ----------------------------------------------------------------------
echo [CHECK] Checking ports...
netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo [ERROR] API port %PORT% is already in use. Close that process or run: set PORT=8001
  goto fail
)
netstat -ano | findstr /R /C:":%FRONTEND_PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo [ERROR] Frontend port %FRONTEND_PORT% is already in use. Close that process or run: set FRONTEND_PORT=5174
  goto fail
)

rem ----------------------------------------------------------------------
rem Start services
rem ----------------------------------------------------------------------
echo [START] Backend window will stay open on errors.
start "AI4Story Backend" /D "%ROOT%" cmd /k ""%PYTHON_EXE%" -m uvicorn apps.api.main:create_app --host %HOST% --port %PORT% --factory --reload"

echo [START] Frontend window will stay open on errors.
start "AI4Story Frontend" /D "%WEB_DIR%" cmd /k "pnpm dev --host 127.0.0.1 --port %FRONTEND_PORT%"

echo [CHECK] Waiting for API readiness...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='http://127.0.0.1:%PORT%/healthz'; $deadline=(Get-Date).AddSeconds(60); while((Get-Date) -lt $deadline){ try { $r = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2; if ($r.StatusCode -eq 200) { Write-Host '[OK] API ready:' $url; exit 0 } } catch {}; Start-Sleep -Seconds 1 }; Write-Host '[ERROR] API did not become ready in 60 seconds:' $url; exit 1"
if errorlevel 1 (
  echo [ERROR] API readiness check failed. See the "AI4Story Backend" window.
  goto fail
)

echo [READY] Opening latest Vue app: http://localhost:%FRONTEND_PORT%
start "" "http://localhost:%FRONTEND_PORT%"
echo.
echo Services are running in separate windows. Close those windows to stop them.
echo This launcher window can now be closed.
pause
exit /b 0

:fail
echo.
echo Launch failed. Fix the error above and rerun start_webdemo.cmd.
pause
exit /b 1
