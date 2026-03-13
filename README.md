# CyberBS — Real-Time BS Detector for Cybersecurity

CyberBS listens to a cybersecurity conference talk or conversations (audio file or live mic) and classifies each segment of speech in real time into one of three verdicts:

| Verdict | Meaning |
|---------|---------|
| **Legit** | Real technical content — depth, specifics, substance |
| **Neutral** | Off-topic material — intros, logistics, small talk |
| **BS** | Marketing hype, buzzwords, vague claims with no technical backing |

Results are displayed live in the terminal as the talk progresses. When finished, you get a per-chunk breakdown and an optional LLM-written summary of the overall signal-to-noise ratio.

---

## Requirements

| Dependency | Version | Notes |
|------------|---------|-------|
| Python | 3.10+ | [python.org/downloads](https://www.python.org/downloads/) |
| ffmpeg | any | Required by Whisper for audio decoding |

**Installing ffmpeg:**

```bash
# macOS
brew install ffmpeg

# Ubuntu / Debian
sudo apt install ffmpeg

# Windows — download the essentials build, extract, and add to PATH
# https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
```

---

## Installation

Run once after cloning:

```bash
# macOS / Linux
./install.sh

# Windows
install.bat
```

The installer will:
1. Verify Python 3.10+ and ffmpeg are present
2. Create a Python virtual environment (`venv/`)
3. Install all dependencies
4. Pre-download the Whisper `base` model so the first run is instant
5. Download the CyberBS classification model from Azure
6. Optionally configure your preferred LLM provider for `--summarize`

---

## Usage

```
# macOS / Linux
./run.sh [options] <audio_file>

# Windows
run.bat [options] <audio_file>
```

Omit `<audio_file>` when using `--mic` for live microphone input.

---

## Options

| Option | Default | Description |
|--------|---------|-------------|
| `--mic` | off | Analyse live microphone input instead of a file |
| `--no-play` | off | Skip audio playback — transcribe and analyse only |
| `--transcript` | off | Save a JSON transcript file when done |
| `--summarize` | off | Generate an LLM-written summary of the analysis (provider configured during install) |
| `--chunk-seconds N` | `15` | Length of each analysis chunk in seconds |
| `--whisper-model SIZE` | `base` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `--model-path PATH` | *(interactive)* | Path to a classification model directory — skips the selection prompt |

> **Whisper model tradeoff:** `base` is fast and accurate enough for most talks. Use `small` or `medium` for heavy accents or noisy recordings. `large` is slow but most accurate.

---

## Examples

```bash
# Analyse a recorded talk
./run.sh talk.mp3

# Analyse and save a JSON transcript
./run.sh --transcript conference_keynote.m4a

# Analyse and get an LLM summary (uses your configured provider)
./run.sh --summarize keynote.m4a

# Summary + save transcript
./run.sh --summarize --transcript keynote.m4a

# Live microphone input with 10-second chunks
./run.sh --mic --chunk-seconds 10

# Use a more accurate Whisper model, no playback
./run.sh --whisper-model small --no-play recording.wav

# Point directly to a model folder (skip selection prompt)
./run.sh --model-path models/cyberbs talk.mp3
```

---

## LLM Summary (`--summarize`)

When `--summarize` is passed, CyberBS sends the full transcript and per-chunk verdicts to an LLM and asks it to write a plain-English assessment of the talk's signal-to-noise ratio.

Your LLM provider and model are configured during installation and saved to `~/.cyberbs/llm_config.json`. Run the installer again to change them.

The transcript JSON is created automatically during summarization and deleted afterwards unless you also pass `--transcript`.

---

## Models

Classification models live in the `models/` folder. If multiple models are present you will be prompted to select one at startup. The `cyberbs` model is downloaded automatically by the installer.

---

## Output Files

| File | When created | Contents |
|------|-------------|----------|
| `<input_name>_transcript.json` | `--transcript` flag | Timestamped chunks with text and verdict scores |

Transcript files are saved in the directory you run the command from.

---

## Notes

- First run after install is instant — Whisper is pre-cached by the installer.
- Microphone mode requires a working audio input device.
- On macOS, microphone mode also requires **portaudio** (`brew install portaudio`).
- Use `Ctrl+C` to quit at any time.
