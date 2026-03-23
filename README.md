# TechBS — Real-Time BS Detection for Tech

Is that keynote actually a groundbreaking innovation, or just a 60-minute ad for a product you don't need? Is that tech influencer's "Top 10 Career Tips" list actually advice, or just trying to sell you a course?

Meet **TechBS**: your personal bullshit detector for the tech industry.

TechBS uses AI to separate real technical depth from buzzword-heavy marketing. Whether you're watching a keynote, listening to a podcast, or sitting through a tech interview, it helps you find what's real.

**Why use TechBS?**
*   **Live Analysis:** Use it in real-time to see if a speaker is delivering value or just filler.
*   **Recorded Content:** Run it against audio files to decide if they are worth your time.
*   **Career Protection:** Don't let thin content influence your career decisions. Get the facts, skip the hype.

Models are domain-specific and interchangeable. Each model is trained exclusively on content from a single technical domain, giving it a sharper eye for the difference between genuine expertise and performative jargon than a general-purpose model could.

> **Disclaimer:** TechBS is for entertainment and informational purposes only. It is an AI model, and AI gets things wrong. Don't cry if it thinks your presentation is BS — just maybe reconsider why you have twelve slides about "leveraging synergies across the threat landscape."

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
| `SOLID CONTENT` | 60–75% Legit |
| `MIXED` | Neither side above 60% |
| `MOSTLY BS` | 60–75% BS |
| `TOTAL BS` | 75%+ BS |
| `OFF-TOPIC` | 100% Neutral (no domain content detected) |

---

## Requirements

- Python 3.10 or higher — https://www.python.org/downloads/
- **ffmpeg** (audio decoding and playback)
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
  - Windows: download from https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip, extract, and add `ffmpeg.exe` to your system PATH

---

## Install

**macOS / Linux:**
```bash
curl -fsSL https://techbs.ai/install.sh | bash
```
Installs to `~/.local/share/techbs` and registers the `techbs` command in your PATH.

**Windows (PowerShell — run as Administrator):**
```powershell
irm https://techbs.ai/install.ps1 | iex
```
Installs to `%USERPROFILE%\techbs` and registers the `techbs` command.

> **Windows note:** If PowerShell blocks the script, run this once from an elevated PowerShell window, then re-run the installer:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

The installer will:
1. Verify Python 3.10+ and ffmpeg are present
2. Download the latest TechBS release from GitHub
3. Create a Python virtual environment
4. Detect your GPU and install the appropriate PyTorch build (CUDA if NVIDIA GPU found, CPU-only otherwise)
5. Install all remaining dependencies
6. Pre-cache the Whisper transcription model so the first run is instant
7. Register the `techbs` command

---

## Usage

```bash
techbs --file <audio_file> [options]
techbs --url <url> [options]
techbs --mic [options]
```

In **file mode** (`--file`), audio plays back through your system speakers in sync with the analysis so you can follow along in real time. Use `--no-play` to suppress playback and run faster than real time.

In **URL mode** (`--url`), TechBS downloads the audio from a podcast episode or any other supported site, then analyses it with real-time playback just like file mode. Add `--no-play` to skip playback and run at full speed.

In **mic mode** (`--mic`), TechBS records continuously from your default microphone and classifies each sample as it arrives. Press `Q` to stop.

---

## Options

| Flag | Description |
|------|-------------|
| `--file AUDIO_FILE` | Analyse a local audio file (mp3, wav, m4a, etc.) |
| `--url URL` | Analyse audio from a URL (podcast, etc.) |
| `--mic` | Analyse live microphone input |
| `--no-play` | Skip audio playback and run analysis only |
| `--transcript` | Save a full JSON transcript when done |
| `--chunk-seconds N` | Seconds per analysis sample (default: `15`) |
| `--whisper-model SIZE` | Transcription accuracy: `tiny`, `base`, `small`, `medium`, `large` (default: `base`) |
| `--model-list` | List available models and their install status |
| `--model-pull NAME` | Download a model by name |
| `--update-models` | Check for model updates and download any that are available |
| `--check-updates` | Show available model versions without downloading |

### Keyboard controls (during analysis)

| Key | Action |
|-----|--------|
| `S` or `Space` | Skip to the next sample (file mode only) |
| `Q` | Stop and show the final report |

---

## Examples

```bash
# Analyse a recorded talk
techbs --file talk.mp3

# Analyse without playing audio (faster than real time)
techbs --file talk.mp3 --no-play

# Analyse a podcast episode by URL
techbs --url "https://example.com/episodes/episode-42.mp3"

# Save a full JSON transcript
techbs --file conference_keynote.m4a --transcript

# Live microphone with 10-second samples
techbs --mic --chunk-seconds 10

# Use a more accurate transcription model for heavy accents or noisy audio
techbs --file recording.wav --whisper-model small --no-play
```

---

## Domain Models

Models live in the `models/` folder. Each model is custom-trained on content from a specific technical domain — giving it targeted signal on what counts as real depth versus fluff in that field.

| Model | Domain | Pull command |
|-------|--------|-------------|
| `cyberbs` | Cybersecurity | `techbs --model-pull cyberbs` |
| `netbs` | Network Engineering | `techbs --model-pull netbs` |

Models are pulled directly from HuggingFace. To see all available models and their install status:

```bash
techbs --model-list
```

Each model carries a version number and a SHA256 checksum in its `info.json` file. Downloaded weights are verified against this checksum — if the file doesn't match, it is deleted and the install fails loudly rather than silently loading a corrupted or tampered model.

---

## Model Updates

TechBS checks HuggingFace directly for model updates — no separate manifest or configuration needed.

```bash
# See what versions are available
techbs --check-updates

# Download any updates (prompts for confirmation)
techbs --update-models
```

---

## Notes

- First run after install is instant — the transcription model is pre-cached by the installer.
- TechBS runs on CPU, NVIDIA GPU (CUDA), or Apple Silicon (MPS) — the installer picks the right build automatically.
- Microphone mode requires a working audio input device.
  - Linux: `sudo apt install libportaudio2`
  - macOS: `brew install portaudio`
  - Windows ARM: `pip install sounddevice --no-binary sounddevice`
- Press `Ctrl+C` at any time to stop and show the final report.

---

## Acknowledgments

TechBS is built on the following open-source projects:

- **[Whisper](https://github.com/openai/whisper)** (OpenAI) — local speech-to-text transcription. MIT License.
- **[BERT](https://github.com/google-research/bert)** (Google Research) — base model architecture for domain classification. Apache 2.0 License. TechBS models are fine-tuned from `bert-base-uncased`.

See the [NOTICE](NOTICE) file for full attribution details.
