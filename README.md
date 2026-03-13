# TechBS — Real-Time BS Detection for Tech

Detect technical depth vs. marketing fluff in real time. Works with conference talks, podcasts, phone screens, interviews, and any recorded or live audio.

---

## Requirements

- Python 3.10 or higher — https://www.python.org/downloads/
- **ffmpeg** (audio decoding)
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
  - Windows: download from https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip, extract, and add `ffmpeg.exe` to your system PATH

---

## Install

Run once after extracting the package:

```bash
# macOS / Linux
./install.sh

# Windows
install.bat
```

The installer sets up a virtual environment, downloads dependencies, caches the Whisper model, and optionally configures an LLM provider for `--summarize`.

---

## Usage

```bash
# macOS / Linux
./run.sh [options] <audio_file>
./run.sh --mic

# Windows
run.bat [options] <audio_file>
run.bat --mic
```

---

## Options

| Flag | Description |
|------|-------------|
| `--mic` | Analyse live microphone input instead of a file |
| `--no-play` | Skip audio playback (transcription + analysis only) |
| `--transcript` | Save a full JSON transcript when done |
| `--summarize` | Generate an LLM summary of the analysis |
| `--chunk-seconds N` | Seconds per analysis chunk (default: `15`) |
| `--whisper-model SIZE` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` (default: `base`) |

---

## Examples

```bash
./run.sh talk.mp3
./run.sh --transcript conference_keynote.m4a
./run.sh --summarize keynote.m4a
./run.sh --transcript --summarize keynote.m4a
./run.sh --mic
./run.sh --mic --chunk-seconds 10
./run.sh --whisper-model small --no-play recording.wav
```

---

## LLM Summary (`--summarize`)

The LLM provider is configured once during `install.sh` / `install.bat`. Supported providers:

| Provider | Requirement |
|----------|-------------|
| **Ollama** (local, default) | Install from https://ollama.com and pull a model: `ollama pull llama3.2` |
| **Claude** | Set `ANTHROPIC_API_KEY` environment variable |
| **OpenAI** | Set `OPENAI_API_KEY` environment variable |
| **Gemini** | Set `GOOGLE_API_KEY` environment variable |

The transcript JSON is generated automatically for the LLM and deleted after the summary unless you also pass `--transcript`.

To change your LLM preference, re-run the installer.

---

## Domain Models

Models live in the `models/` folder. If multiple models are present you will be prompted to select one at startup. Each model is trained for a specific tech domain (cybersecurity, networking, AI, etc.).

---

## Notes

- First run after install is instant — Whisper is pre-cached by the installer.
- Microphone mode requires a working audio input device.
  - Linux: `sudo apt install libportaudio2`
  - macOS: `brew install portaudio`
- Transcripts are saved as JSON in the folder you run the command from.
- Larger Whisper models are slower but more accurate. `base` is the recommended default.
