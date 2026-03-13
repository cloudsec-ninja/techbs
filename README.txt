CyberBS — Real-Time BS Detection for Cybersecurity Talks
=========================================================

REQUIREMENTS
  - Python 3.10 or higher     https://www.python.org/downloads/
  - ffmpeg (audio decoding)
      macOS:   brew install ffmpeg
      Windows: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
               Extract and add ffmpeg.exe to your system PATH
      Linux:   sudo apt install ffmpeg

INSTALL (run once)
  macOS/Linux:  ./install.sh
  Windows:      install.bat

USAGE
  macOS/Linux:  ./run.sh [options] <audio_file>
  Windows:      run.bat  [options] <audio_file>

OPTIONS
  --mic                        Analyse live microphone input instead of a file
  --no-play                    Do not play audio (transcription + analysis only)
  --transcript                 Save a JSON transcript when done
  --summarize                  Generate an LLM summary of the analysis
  --llm-provider ollama|claude|openai
                               LLM provider for --summarize (default: ollama)
  --llm-model MODEL            Override the default model for the provider
  --chunk-seconds N            Seconds per analysis chunk (default: 15)
  --whisper-model SIZE         Whisper model: tiny, base, small, medium, large
                               (default: base — larger = slower but more accurate)

EXAMPLES
  ./run.sh talk.mp3
  ./run.sh --transcript conference_keynote.m4a
  ./run.sh --summarize keynote.m4a
  ./run.sh --summarize --llm-provider claude keynote.m4a
  ./run.sh --summarize --transcript keynote.m4a
  ./run.sh --mic --chunk-seconds 10
  ./run.sh --whisper-model small --no-play recording.wav

LLM SUMMARY (--summarize)
  Ollama (local, default): install Ollama from https://ollama.com, pull a model
    with "ollama pull llama3.2", then use --summarize. You will be prompted to
    select a model if multiple are installed.
  Claude: set the ANTHROPIC_API_KEY environment variable, then use
    --summarize --llm-provider claude
  OpenAI: set the OPENAI_API_KEY environment variable, then use
    --summarize --llm-provider openai
  The transcript JSON is created automatically and deleted after the summary
  unless you also pass --transcript.

MODELS
  Domain models are in the models/ folder.
  You will be prompted to select one if multiple are available.

NOTES
  - First run after install will be instant (Whisper is pre-cached by installer).
  - Microphone mode requires a working audio input device.
  - Transcripts are saved as JSON in the folder you run the command from.
