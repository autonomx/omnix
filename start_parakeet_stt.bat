@echo off
setlocal

set "RPG_STT_PYTHON=C:\Users\unx47\miniconda3\envs\rpg-stt\python.exe"
set "STT_SERVER=%~dp0src\parakeet_stt_server.py"

if not exist "%RPG_STT_PYTHON%" (
    echo ERROR: rpg-stt python not found:
    echo   %RPG_STT_PYTHON%
    pause
    exit /b 1
)

if not exist "%STT_SERVER%" (
    echo ERROR: Omnix STT compatibility entrypoint not found:
    echo   %STT_SERVER%
    pause
    exit /b 1
)

echo Starting Nemotron Streaming ASR + Parakeet Realtime EOU...
echo Authoritative transcript: nvidia/nemotron-speech-streaming-en-0.6b
echo Turn endpoint: nvidia/parakeet_realtime_eou_120m-v1
echo Python: %RPG_STT_PYTHON%
echo Server: %STT_SERVER%
echo WebSocket: ws://127.0.0.1:5201/ws/transcribe
echo Chunk target: 160 ms
echo.

"%RPG_STT_PYTHON%" -c "import fastapi, uvicorn, websockets, nemo.collections.asr; import nemo; from packaging.version import Version; print('[STT] NeMo:', nemo.__version__); assert Version(nemo.__version__) >= Version('2.5.3'), 'NeMo 2.5.3+ required for Parakeet Realtime EOU'; print('[STT] dependencies OK')"
if errorlevel 1 (
    echo.
    echo ERROR: The rpg-stt environment is missing a required dependency or has an old NeMo version.
    echo Update the STT environment with:
    echo   "%RPG_STT_PYTHON%" -m pip install --upgrade "nemo_toolkit[asr]>=2.5.3" "uvicorn[standard]" python-multipart
    pause
    exit /b 1
)

set "OMNIX_STT_PORT=5201"
if not defined OMNIX_STT_STREAM_CHUNK_MS set "OMNIX_STT_STREAM_CHUNK_MS=160"
if not defined OMNIX_NEMOTRON_RIGHT_CONTEXT set "OMNIX_NEMOTRON_RIGHT_CONTEXT=1"
if not defined OMNIX_EOU_RIGHT_CONTEXT set "OMNIX_EOU_RIGHT_CONTEXT=1"
if not defined OMNIX_STT_DEVICE set "OMNIX_STT_DEVICE=auto"
"%RPG_STT_PYTHON%" "%STT_SERVER%"

endlocal
