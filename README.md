# TechBS — Real-Time BS Detection for Tech

TechBS listens to live or recorded tech talks, conference presentations, podcasts, or interviews and classifies every segment of speech in real time using a custom-trained domain specific model. It tells you whether the speaker is delivering real technical depth or dressing up thin content in buzzwords.

Models are domain-specific and interchangeable. Each model is trained exclusively on content from a single technical domain, giving it a much sharper eye for the difference between genuine expertise and performative jargon than a general-purpose model could. For example the `cyberbs` model is tuned for cybersecurity. Additional domain models will be released in time.

> **Disclaimer:** TechBS is for entertainment and informational purposes only. It is an AI model, and AI gets things wrong. Don't cry if it thinks your presentation is BS, just maybe reconsider why you have twelve slides about "leveraging synergies across the threat landscape."

---

## How it works

1. **Transcription** — Audio is converted to text locally in configurable samples (default 15 seconds). No external API required, everything runs on your machine.

2. **Classification** — Each transcribed sample is scored by a custom-trained domain model that assigns a probability across three labels:

   | Label | Meaning |
   |-------|---------|
   | **LEGIT** | Real technical content — depth, specifics, actionable details |
   | **NEUTRAL** | Off-topic material — intros, logistics, audience Q&A, small talk |
   | **BS** | Marketing hype, buzzwords, vague claims, no technical substance |

3. **Live UI** — Results appear in a Rich terminal dashboard updated in real time with three panels:
   - **TechBS Meter** — current sample verdict with per-label confidence percentages, rolling verdict over the last 5 samples, and running totals
   - **Live Transcript** — the last few transcribed samples with their labels and timestamps
   - **Sample History** — a scrolling table of every sample analyzed so far with full score breakdown

4. **Final Report** — When the audio ends (or you press Q), a summary shows the overall verdict, percentage breakdown across all samples, and average confidence scores.

---

## Verdicts

### Per-sample
Every sample gets one of `LEGIT`, `NEUTRAL`, or `BS`, plus the raw probability for all three labels.

### Rolling (live)
The meter shows a live verdict over the last 5 samples as the talk progresses:

| Verdict | When |
|---------|------|
| `LEGIT CONTENT` | 60%+ of recent samples are Legit |
| `MIXED — SOME GOOD STUFF` | No clear majority |
| `SMELLS LIKE BS` | 40–60% of recent samples are BS |
| `TOTAL BS` | 60%+ of recent samples are BS |
| `OFF-TOPIC/SMALL TALK` | 60%+ of recent samples are Neutral |

### Overall (final report)
Neutral samples are excluded when calculating the final quality score so intros and housekeeping don't skew the result:

| Verdict | Threshold |
|---------|-----------|
| `HIGHLY TECHNICAL` | 75%+ of content samples are Legit |
| `SOLID CONTENT` | 50–75% Legit |
| `MIXED` | No clear majority |
| `MOSTLY BS` | 50–75% BS |
| `TOTAL BS` | 75%+ BS |
| `OFF-TOPIC` | 70%+ Neutral overall |

---

## Requirements

- Python 3.10 or higher — https://www.python.org/downloads/
- **ffmpeg** (audio decoding and playback)
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

The installer will:
1. Verify Python 3.10+ and ffmpeg are present
2. Create a Python virtual environment (`venv/`)
3. Detect your GPU and install the appropriate PyTorch build (CUDA if an NVIDIA GPU is found, CPU-only otherwise)
4. Install all remaining dependencies
5. Pre-cache the transcription model so the first run is instant
6. Download the TechBS domain classification model
7. Prompt you to configure an LLM provider for the optional `--summarize` feature

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

In **file mode**, audio plays back through your system speakers in sync with the analysis so you can follow along in real time. Use `--no-play` to suppress playback and run faster than real time.

In **mic mode**, TechBS records continuously from your default microphone and classifies each sample as it arrives. Press `Q` to stop.

---

## Options

| Flag | Description |
|------|-------------|
| `--mic` | Analyse live microphone input instead of a file |
| `--no-play` | Skip audio playback (analysis only, runs faster than real time) |
| `--transcript` | Save a full JSON transcript when done |
| `--summarize` | Generate an LLM summary of the analysis (provider configured at install) |
| `--chunk-seconds N` | Seconds per analysis sample (default: `15`) |
| `--whisper-model SIZE` | Transcription accuracy: `tiny`, `base`, `small`, `medium`, `large` (default: `base`) |

### Keyboard controls (during analysis)

| Key | Action |
|-----|--------|
| `S` or `Space` | Skip to the next sample (file mode only) |
| `Q` | Stop and show the final report |

---

## Examples

```bash
# Analyse a recorded talk
./run.sh talk.mp3

# Analyse without playing audio (faster than real time)
./run.sh --no-play talk.mp3

# Save a full JSON transcript
./run.sh --transcript conference_keynote.m4a

# Analyse and get an LLM summary at the end
./run.sh --summarize keynote.m4a

# Save transcript and get LLM summary
./run.sh --transcript --summarize keynote.m4a

# Live microphone with 10-second samples
./run.sh --mic --chunk-seconds 10

# Use a more accurate transcription model for heavy accents or noisy audio
./run.sh --whisper-model small --no-play recording.wav
```

---

## Domain Models

Models live in the `models/` folder. Each model is custom-trained on content from a specific technical domain — giving it targeted signal on what counts as real depth versus fluff in that field. A cybersecurity model knows the difference between an actual CVE breakdown and a vendor-speak slide. A networking model knows when someone actually understands BGP versus when they're just saying "software-defined."

If multiple models are present, TechBS prompts you to select one at startup. The `cyberbs` model is downloaded automatically by the installer. To add a model, place its folder inside `models/`.

---

## LLM Summary (`--summarize`)

After analysis completes, TechBS sends the full transcript — including per-sample text, timestamps, and label scores — to an LLM and asks for a detailed, evidence-based evaluation of the talk.

The summary covers:
- An opening verdict on whether the automated scores are accurate
- 3–5 sections analysing specific patterns in the data, with sample citations and transcript quotes
- A closing sentence on the talk's practical value to a working practitioner

The LLM provider is configured once during installation. Supported providers:

| Provider | Requirement |
|----------|-------------|
| **Ollama** (local, default) | Install from https://ollama.com and pull a model: `ollama pull llama3.2` |
| **Claude** | Set `ANTHROPIC_API_KEY` environment variable |
| **OpenAI** | Set `OPENAI_API_KEY` environment variable |
| **Gemini** | Set `GOOGLE_API_KEY` environment variable |

The transcript JSON is generated automatically for the LLM and deleted after the summary unless you also pass `--transcript`. To change your LLM preference, re-run the installer.

---

## Transcript JSON (`--transcript`)

Saved as `<filename>_<timestamp>_techbs.json` in the folder you run the command from. Contains:

- Overall verdict and analysis timestamp
- Summary stats: sample count, duration, per-label counts and percentages, average confidence scores
- Full per-sample data: start/end time, label, all three confidence scores, and the raw transcript text

---

## Notes

- First run after install is instant — the transcription model is pre-cached by the installer.
- TechBS runs on CPU, NVIDIA GPU (CUDA), or Apple Silicon (MPS) — the installer picks the right build automatically.
- Microphone mode requires a working audio input device.
  - Linux: `sudo apt install libportaudio2`
  - macOS: `brew install portaudio`
- Press `Ctrl+C` at any time to stop and show the final report.
