CyberBS — Real-Time BS Detection for Cybersecurity Talks
=========================================================

REQUIREMENTS
  - Python 3.10 or higher     https://www.python.org/downloads/
  - ffmpeg (audio decoding)
      macOS:   brew install ffmpeg
      Windows: https://ffmpeg.org/download.html  (add to PATH)
      Linux:   sudo apt install ffmpeg

INSTALL (run once)
  macOS/Linux:  ./install.sh
  Windows:      install.bat

USAGE
  macOS/Linux:  ./run.sh [options] <audio_file>
  Windows:      run.bat  [options] <audio_file>

OPTIONS
  --mic                 Analyse live microphone input instead of a file
  --no-play             Do not play audio (transcription + analysis only)
  --transcript          Save a JSON transcript when done
  --chunk-seconds N     Seconds per analysis chunk (default: 15)
  --whisper-model SIZE  Whisper model to use: tiny, base, small, medium, large
                        (default: base — larger = slower but more accurate)

EXAMPLES
  ./run.sh talk.mp3
  ./run.sh --transcript conference_keynote.m4a
  ./run.sh --mic --chunk-seconds 10
  ./run.sh --whisper-model small --no-play recording.wav

MODELS
  Domain models are in the models/ folder.
  You will be prompted to select one if multiple are available.

NOTES
  - First run after install will be instant (Whisper is pre-cached by installer).
  - Microphone mode requires a working audio input device.
  - Transcripts are saved as JSON in the same folder you run the command from.
