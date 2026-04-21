@echo off
setlocal

set "HOST=127.0.0.1"
set "PORT=8000"
set "ROOT=%~dp0"
set "URL=http://%HOST%:%PORT%"
set "KEY_FILE=%ROOT%start_webdemo.keys.cmd"

if not exist "%KEY_FILE%" (
  >"%KEY_FILE%" echo @echo off
  >>"%KEY_FILE%" echo rem Fill your API keys below, save this file, then run start_webdemo.cmd again.
  >>"%KEY_FILE%" echo set "ARK_API_KEY=PASTE_SEEDREAM_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "DASHSCOPE_API_KEY=PASTE_TEXT_MODEL_API_KEY_HERE"
  >>"%KEY_FILE%" echo set "XIAOMI_TTS_API_KEY=PASTE_XIAOMI_TTS_API_KEY_HERE"
)

call "%KEY_FILE%"

if /I "%ARK_API_KEY%"=="PASTE_SEEDREAM_API_KEY_HERE" (
  echo [ERROR] ARK_API_KEY not filled in yet.
  echo Please edit:
  echo   %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  pause
  exit /b 1
)

if /I "%DASHSCOPE_API_KEY%"=="PASTE_TEXT_MODEL_API_KEY_HERE" (
  echo [ERROR] DASHSCOPE_API_KEY not filled in yet.
  echo Please edit:
  echo   %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  pause
  exit /b 1
)

if /I "%XIAOMI_TTS_API_KEY%"=="PASTE_XIAOMI_TTS_API_KEY_HERE" (
  echo [ERROR] XIAOMI_TTS_API_KEY not filled in yet.
  echo Please edit:
  echo   %KEY_FILE%
  start "" notepad "%KEY_FILE%"
  pause
  exit /b 1
)

set "PYTHON_EXE="

if defined AI4STORY_PYTHON if exist "%AI4STORY_PYTHON%" set "PYTHON_EXE=%AI4STORY_PYTHON%"
if not defined PYTHON_EXE if exist "D:\Miniconda\envs\ai4story\python.exe" set "PYTHON_EXE=D:\Miniconda\envs\ai4story\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\miniconda3\envs\ai4story\python.exe" set "PYTHON_EXE=%USERPROFILE%\miniconda3\envs\ai4story\python.exe"
if not defined PYTHON_EXE if exist "%USERPROFILE%\anaconda3\envs\ai4story\python.exe" set "PYTHON_EXE=%USERPROFILE%\anaconda3\envs\ai4story\python.exe"
if not defined PYTHON_EXE if /I "%CONDA_DEFAULT_ENV%"=="ai4story" if defined CONDA_PREFIX if exist "%CONDA_PREFIX%\python.exe" set "PYTHON_EXE=%CONDA_PREFIX%\python.exe"
if not defined PYTHON_EXE for %%I in (python.exe) do set "PYTHON_EXE=%%~$PATH:I"

if not defined PYTHON_EXE (
  echo [ERROR] Python was not found.
  echo Set AI4STORY_PYTHON to your python.exe, or create the ai4story env first.
  pause
  exit /b 1
)

"%PYTHON_EXE%" -c "import fastapi,uvicorn,requests,PIL,dashscope" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Missing Python packages in:
  echo         %PYTHON_EXE%
  echo.
  echo Create or fix the environment first, for example:
  echo   conda env create -f environment.yml
  echo or install requirements.txt into the ai4story environment.
  pause
  exit /b 1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-WebRequest -UseBasicParsing '%URL%/healthz' -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
if not errorlevel 1 (
  echo AI4Story is already running. Opening %URL%
  start "" "%URL%"
  exit /b 0
)

netstat -ano | findstr /R /C:":%PORT% .*LISTENING" >nul
if not errorlevel 1 (
  echo [ERROR] Port %PORT% is already in use by another process.
  echo Change PORT at the top of this file or stop the process using that port.
  pause
  exit /b 1
)

echo Starting AI4Story on %URL%
start "AI4Story Web Demo" /D "%ROOT%" "%PYTHON_EXE%" -m uvicorn apps.api.main:app --host %HOST% --port %PORT%

powershell -NoProfile -ExecutionPolicy Bypass -Command "$url='%URL%/healthz'; $deadline=(Get-Date).AddSeconds(60); while((Get-Date) -lt $deadline){ try { $r = Invoke-WebRequest -UseBasicParsing $url -TimeoutSec 2; if ($r.StatusCode -eq 200) { exit 0 } } catch {}; Start-Sleep -Seconds 1 }; exit 1"
if errorlevel 1 (
  echo [ERROR] Server did not become ready within 60 seconds.
  echo Check the 'AI4Story Web Demo' console window for details.
  pause
  exit /b 1
)

echo AI4Story is ready. Opening %URL%
start "" "%URL%"
exit /b 0
