@echo off

REM ── Azure model storage ───────────────────────────────────────────────────────
REM Replace the value below with your full Azure Blob container URL including
REM the embedded SAS token before distributing.
REM Use the  set "VAR=value"  form (quotes wrap the whole assignment) so that
REM the & characters in the SAS token are NOT treated as CMD command separators.
REM   e.g. set "MODEL_URL=https://mystorageaccount.blob.core.windows.net/cyberbs-models?sv=2022-11-02&ss=b&sp=rl&sig=XXXXX"
set "MODEL_URL=https://ddffrrrsseee.blob.core.windows.net/models?sp=r&st=2026-03-13T16:33:34Z&se=2026-04-01T00:48:34Z&spr=https&sv=2024-11-04&sr=c&sig=JBTS98EUpLsGkDLG0XHY7ltrfhsi28aNKj7gzT4%2BZ1c%3D"
REM ─────────────────────────────────────────────────────────────────────────────

echo === CyberBS Installer ===

REM Check Python
where python >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found.
    echo Install Python 3.10+ from https://www.python.org/downloads/
    pause
    exit /b 1
)

REM Check version
python -c "import sys; exit(0 if sys.version_info >= (3,10) else 1)" 2>nul
if errorlevel 1 (
    echo ERROR: Python 3.10 or higher is required.
    pause
    exit /b 1
)

REM Check ffmpeg -- hard requirement, Whisper cannot decode audio without it
where ffmpeg >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: ffmpeg is not installed or not in your PATH.
    echo CyberBS cannot decode audio files without ffmpeg.
    echo.
    echo  1. Download ffmpeg for Windows:
    echo     https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    echo  2. Extract and copy ffmpeg.exe to a folder, e.g. C:\ffmpeg\bin\
    echo  3. Add that folder to your system PATH:
    echo     Settings - System - Advanced system settings - Environment Variables
    echo     Edit "Path" under System variables, add C:\ffmpeg\bin
    echo  4. Re-run this installer.
    echo.
    pause
    exit /b 1
)

echo Creating virtual environment...
if not exist venv python -m venv venv

echo Installing dependencies (this may take several minutes)...
call venv\Scripts\activate.bat
pip install --upgrade pip --quiet

REM Install PyTorch with CUDA if an NVIDIA GPU is present, otherwise CPU-only
REM Check nvidia-smi in PATH and common fallback location
set NVIDIA_SMI=nvidia-smi
if not exist "%NVIDIA_SMI%.exe" (
    if exist "C:\Windows\System32\nvidia-smi.exe" set NVIDIA_SMI=C:\Windows\System32\nvidia-smi
)
%NVIDIA_SMI% >nul 2>&1
if not errorlevel 1 (
    echo NVIDIA GPU detected -- installing CUDA-enabled PyTorch...
    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128 --quiet
) else (
    echo No NVIDIA GPU detected -- installing CPU-only PyTorch...
    pip install torch torchvision --quiet
)

REM Install remaining dependencies (torch already satisfied above)
pip install -r requirements.txt --quiet

echo Downloading Whisper base model...
python -c "import whisper; whisper.load_model('base'); print('Whisper model cached.')"

REM Download CyberBS model weights from Azure
if "%MODEL_URL%"=="REPLACE_WITH_AZURE_URL" (
    echo.
    echo WARNING: Azure model URL not configured in installer.
    echo          Models must be placed in the models\ folder manually.
) else (
    echo Downloading CyberBS models from Azure...
    python app\model_downloader.py --model cyberbs --url "%MODEL_URL%" --models-dir models
)

call deactivate

REM ── LLM summary preference ───────────────────────────────────────────────────
echo.
set /p LLM_CHOICE="Configure LLM provider for --summarize? (run installer again to change) [y/N]: "
if /i not "%LLM_CHOICE%"=="y" goto :llm_done

echo.
echo Select LLM provider:
echo   1) Ollama  (local, free -- requires Ollama installed separately)
echo   2) Claude  (cloud  -- requires ANTHROPIC_API_KEY env var)
echo   3) OpenAI  (cloud  -- requires OPENAI_API_KEY env var)
echo   4) Gemini  (cloud  -- requires GOOGLE_API_KEY env var)
echo.
set /p PROVIDER_CHOICE="Choice [1-4]: "

if "%PROVIDER_CHOICE%"=="1" goto :llm_ollama
if "%PROVIDER_CHOICE%"=="2" goto :llm_claude
if "%PROVIDER_CHOICE%"=="3" goto :llm_openai
if "%PROVIDER_CHOICE%"=="4" goto :llm_gemini
echo Invalid choice. Skipping LLM configuration.
goto :llm_done

:llm_ollama
set LLM_PROVIDER=ollama
echo.
REM Write a Python selector that: prints display to stderr, prints chosen model name to stdout
REM This lets us capture only the model name while the user sees the list and prompt normally.
set OLPY=%TEMP%\cyberbs_ol.py
set OLOUT=%TEMP%\cyberbs_ol_out.txt
echo import urllib.request,json,sys > "%OLPY%"
echo try: >> "%OLPY%"
echo     r=urllib.request.urlopen('http://localhost:11434/api/tags',timeout=2).read() >> "%OLPY%"
echo     ms=json.loads(r).get('models',[]) >> "%OLPY%"
echo     if ms: >> "%OLPY%"
echo         sys.stderr.write('Available Ollama models:\n') >> "%OLPY%"
echo         for i,m in enumerate(ms,1): >> "%OLPY%"
echo             sys.stderr.write('  '+str(i)+') '+m['name']+'\n') >> "%OLPY%"
echo         sys.stderr.write('\nModel [number or name]: ') >> "%OLPY%"
echo         sys.stderr.flush() >> "%OLPY%"
echo         c=sys.stdin.readline().strip() >> "%OLPY%"
echo         try: >> "%OLPY%"
echo             n=int(c)-1 >> "%OLPY%"
echo             name=ms[n]['name'] if n^>=0 and n^<len(ms) else c >> "%OLPY%"
echo         except: >> "%OLPY%"
echo             name=c >> "%OLPY%"
echo         print(name) >> "%OLPY%"
echo     else: >> "%OLPY%"
echo         sys.stderr.write('No models found. Pull one: ollama pull llama3.2\n') >> "%OLPY%"
echo         sys.stderr.write('Model name: ') >> "%OLPY%"
echo         sys.stderr.flush() >> "%OLPY%"
echo         print(sys.stdin.readline().strip()) >> "%OLPY%"
echo except: >> "%OLPY%"
echo     sys.stderr.write('Ollama not running.\nExamples: llama3.2  mistral  qwen3:mcp\n') >> "%OLPY%"
echo     sys.stderr.write('Model name: ') >> "%OLPY%"
echo     sys.stderr.flush() >> "%OLPY%"
echo     print(sys.stdin.readline().strip()) >> "%OLPY%"
python "%OLPY%" > "%OLOUT%"
set /p LLM_MODEL=< "%OLOUT%"
del "%OLPY%" "%OLOUT%" 2>nul
goto :llm_save

:llm_claude
set LLM_PROVIDER=claude
set LLM_MODEL=claude-sonnet-4-6
set /p LLM_MODEL="Claude model [claude-sonnet-4-6]: "
if "%LLM_MODEL%"=="" set LLM_MODEL=claude-sonnet-4-6
goto :llm_save

:llm_openai
set LLM_PROVIDER=openai
set LLM_MODEL=gpt-4o
set /p LLM_MODEL="OpenAI model [gpt-4o]: "
if "%LLM_MODEL%"=="" set LLM_MODEL=gpt-4o
goto :llm_save

:llm_gemini
set LLM_PROVIDER=gemini
set LLM_MODEL=gemini-2.0-flash
set /p LLM_MODEL="Gemini model [gemini-2.0-flash]: "
if "%LLM_MODEL%"=="" set LLM_MODEL=gemini-2.0-flash
goto :llm_save

:llm_save
if not exist "%USERPROFILE%\.cyberbs" mkdir "%USERPROFILE%\.cyberbs"
python -c "import json; json.dump({'provider':'%LLM_PROVIDER%','model':'%LLM_MODEL%'},open(r'%USERPROFILE%\.cyberbs\llm_config.json','w'),indent=2)"
echo Saved: %LLM_PROVIDER% / %LLM_MODEL%

REM Install the provider's Python package into the venv
if "%LLM_PROVIDER%"=="claude" (
    echo Installing anthropic package...
    call venv\Scripts\activate.bat
    pip install anthropic --quiet
    call deactivate
)
if "%LLM_PROVIDER%"=="openai" (
    echo Installing openai package...
    call venv\Scripts\activate.bat
    pip install openai --quiet
    call deactivate
)
if "%LLM_PROVIDER%"=="gemini" (
    echo Installing google-genai package...
    call venv\Scripts\activate.bat
    pip install google-genai --quiet
    call deactivate
)

if "%LLM_PROVIDER%"=="ollama" echo Make sure Ollama is installed (https://ollama.com) and the model is pulled.
if "%LLM_PROVIDER%"=="claude" echo Set ANTHROPIC_API_KEY in your environment before using --summarize.
if "%LLM_PROVIDER%"=="openai" echo Set OPENAI_API_KEY in your environment before using --summarize.
if "%LLM_PROVIDER%"=="gemini" echo Set GOOGLE_API_KEY in your environment before using --summarize.

:llm_done

echo.
echo Installation complete. Run the app with: run.bat
pause
