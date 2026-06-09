@echo off
setlocal EnableExtensions

rem AI4Story Windows launcher.
rem Keeps the console open on failures, validates local prerequisites, builds the
rem current Vue frontend, starts FastAPI, then opens the Vite dev server.

chcp 65001 >nul

rem --- When launched by double-click, the console window closes the instant the
rem     script exits (including on error), so failures are never visible. Detect
rem     that case (cmdcmdline contains this script's name) and relaunch once inside
rem     a persistent `cmd /k` window so any error stays on screen. Running from an
rem     already-open terminal does not match and runs inline as before. ---
echo %cmdcmdline% | find /i "%~nx0" >nul
if not errorlevel 1 if not defined AI4STORY_KEPT_OPEN (
  set "AI4STORY_KEPT_OPEN=1"
  start "AI4Story / MindShow launcher" cmd /k ""%~f0""
  exit /b
)

set "ROOT=%~dp0"
set "ROOT=%ROOT:~0,-1%"
rem Run from the repo root so the backend import check (`import apps.api.main`) and
rem any other cwd-relative step work no matter where the script was launched from.
cd /d "%ROOT%"
set "HOST=%HOST%"
if not defined HOST set "HOST=0.0.0.0"
set "PORT=%PORT%"
if not defined PORT set "PORT=8010"
set "FRONTEND_PORT=%FRONTEND_PORT%"
if not defined FRONTEND_PORT set "FRONTEND_PORT=5173"
set "VITE_API_PROXY_TARGET=http://127.0.0.1:%PORT%"
set "KEY_FILE=%ROOT%\start_webdemo.keys.cmd"
set "WEB_DIR=%ROOT%\apps\web"
set "LOG_DIR=%ROOT%\outputs\logs"
set "BACKEND_PID_FILE=%LOG_DIR%\backend.pid"

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
  >>"%KEY_FILE%" echo rem Local API keys. This file is gitignored.
  >>"%KEY_FILE%" echo rem Image generation: OpenAI-compatible Seedream endpoint.
  >>"%KEY_FILE%" echo set "SEEDREAM_API_KEY=PASTE_SEEDREAM_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "SEEDREAM_BASE_URL=https://api.mikaovo.ai/v1"
  >>"%KEY_FILE%" echo set "SEEDREAM_PROVIDER=openai"
  >>"%KEY_FILE%" echo set "SEEDREAM_MODEL=doubao-seedream-5-0-lite-260128"
  >>"%KEY_FILE%" echo rem Text LLM: mikaovo OpenAI-compatible endpoint.
  >>"%KEY_FILE%" echo set "LLM_API_KEY=PASTE_LLM_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "LLM_BASE_URL=https://api.mikaovo.ai/v1"
  >>"%KEY_FILE%" echo set "LLM_MODEL=grok-4.3"
  >>"%KEY_FILE%" echo rem ASR is still DashScope only. Leave placeholder if voice recognition is not needed.
  >>"%KEY_FILE%" echo set "DASHSCOPE_API_KEY=PASTE_DASHSCOPE_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "XIAOMI_TTS_API_KEY=PASTE_XIAOMI_TTS_API_KEY_HERE"
)
call "%KEY_FILE%"

if not defined SEEDREAM_API_KEY if defined ARK_API_KEY set "SEEDREAM_API_KEY=%ARK_API_KEY%"
if not defined SEEDREAM_BASE_URL set "SEEDREAM_BASE_URL=%LLM_BASE_URL%"
if not defined SEEDREAM_PROVIDER set "SEEDREAM_PROVIDER=openai"
if not defined SEEDREAM_MODEL set "SEEDREAM_MODEL=doubao-seedream-5-0-lite-260128"
if not defined LLM_BASE_URL set "LLM_BASE_URL=https://api.mikaovo.ai/v1"
if not defined LLM_MODEL set "LLM_MODEL=grok-4.3"

if not defined SEEDREAM_API_KEY (
  echo [ERROR] SEEDREAM_API_KEY is not filled in: %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  goto fail
)
if /I "%SEEDREAM_API_KEY%"=="PASTE_SEEDREAM_API_KEY_HERE" (
  echo [ERROR] SEEDREAM_API_KEY is not filled in: %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  goto fail
)
if /I "%LLM_API_KEY%"=="PASTE_LLM_API_KEY_HERE" (
  echo [ERROR] LLM_API_KEY is not filled in: %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  goto fail
)
if /I "%DASHSCOPE_API_KEY%"=="PASTE_DASHSCOPE_API_KEY_HERE" (
  echo [WARN] DASHSCOPE_API_KEY is not filled in. ASR will be unavailable.
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
rem Auto-pick the first free port at/above the default, so running this alongside
rem another Vite project (which also defaults to 5173) does not collide. Set PORT /
rem FRONTEND_PORT explicitly to pin a specific port; the scan starts from that value.
echo [CHECK] Checking ports...
call :find_free_port PORT %PORT% 20 "API"
if errorlevel 1 goto fail
call :find_free_port FRONTEND_PORT %FRONTEND_PORT% 30 "Frontend"
if errorlevel 1 goto fail
set "VITE_API_PROXY_TARGET=http://127.0.0.1:%PORT%"
echo [OK] API port: %PORT%   Frontend port: %FRONTEND_PORT%

rem ----------------------------------------------------------------------
rem Start services
rem ----------------------------------------------------------------------
echo [START] Backend in background. Logs: %LOG_DIR%\backend.out.log / backend.err.log
set "BACKEND_PID="
del "%BACKEND_PID_FILE%" >nul 2>&1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$p = Start-Process -FilePath '%PYTHON_EXE%' -ArgumentList @('-m','uvicorn','apps.api.main:create_app','--host','%HOST%','--port','%PORT%','--factory','--reload') -WorkingDirectory '%ROOT%' -RedirectStandardOutput '%LOG_DIR%\backend.out.log' -RedirectStandardError '%LOG_DIR%\backend.err.log' -WindowStyle Hidden -PassThru; Set-Content -Path '%BACKEND_PID_FILE%' -Value $p.Id -Encoding ASCII"
if exist "%BACKEND_PID_FILE%" set /p BACKEND_PID=<"%BACKEND_PID_FILE%"
if not defined BACKEND_PID (
  echo [ERROR] Backend process did not start.
  goto fail
)

echo [CHECK] Waiting for API readiness...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='http://127.0.0.1:%PORT%/healthz'; $deadline=(Get-Date).AddSeconds(60); while((Get-Date) -lt $deadline){ try { $r = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2; if ($r.StatusCode -eq 200) { Write-Host '[OK] API ready:' $url; exit 0 } } catch {}; Start-Sleep -Seconds 1 }; Write-Host '[ERROR] API did not become ready in 60 seconds:' $url; exit 1"
if errorlevel 1 (
  echo [ERROR] API readiness check failed. See logs under: %LOG_DIR%
  taskkill /PID %BACKEND_PID% /T /F >nul 2>&1
  goto fail
)

echo [READY] Opening latest Vue app: http://localhost:%FRONTEND_PORT%
start "" "http://localhost:%FRONTEND_PORT%"
echo.
echo Frontend is running in this terminal. Press Ctrl+C to stop it.
echo Backend PID: %BACKEND_PID%
echo.
pushd "%WEB_DIR%"
call pnpm dev --host 127.0.0.1 --port %FRONTEND_PORT%
set "FRONTEND_EXIT=%ERRORLEVEL%"
popd
echo [STOP] Stopping backend PID %BACKEND_PID%...
taskkill /PID %BACKEND_PID% /T /F >nul 2>&1
exit /b %FRONTEND_EXIT%

rem ----------------------------------------------------------------------
rem find_free_port  %1=var to set  %2=start port  %3=how many to scan  %4=label
rem Scans [start, start+span] and sets %1 to the first port not in LISTENING state.
rem ----------------------------------------------------------------------
:find_free_port
setlocal EnableDelayedExpansion
set /a _start=%~2
set /a _end=%~2 + %~3
set "_chosen="
for /L %%P in (!_start!,1,!_end!) do (
  if not defined _chosen (
    netstat -ano | findstr /R /C:":%%P .*LISTENING" >nul
    if errorlevel 1 set "_chosen=%%P"
  )
)
if not defined _chosen (
  echo [ERROR] No free %~4 port in range %~2-!_end!. Close some processes and retry.
  endlocal & exit /b 1
)
if not "!_chosen!"=="%~2" echo [WARN] %~4 port %~2 is busy, using !_chosen! instead.
endlocal & set "%~1=%_chosen%" & exit /b 0

:fail
echo.
echo Launch failed. Fix the error above and rerun start_webdemo.cmd.
pause
exit /b 1
