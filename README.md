# TechBS — Real-Time BS Detection for Tech

Is that keynote actually a groundbreaking innovation, or just a 60-minute ad for a product you don’t need? Is that tech influencer’s "Top 10 Career Tips" list actually advice, or just trying to sell you a course?

Meet **TechBS**: your personal bullshit detector for the tech industry.

TechBS uses AI to separate real technical depth from buzzword-heavy marketing. Whether you're watching a keynote, listening to a podcast, or sitting through a tech interview, we help you cut through the noise.

**Why use TechBS?**
*   **Live Analysis:** Use it in real-time to see if a speaker is delivering value or just filler.
*   **Recorded Content:** Run it against videos or audio files to decide if they are worth your time before you hit play.
*   **Career Protection:** Don't let thin content influence your career decisions. Get the facts, skip the hype.

**Stop listening to the noise and start learning what actually matters.**

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
- **yt-dlp** (required for `--url` mode — installed automatically by the installer)
  - Or install manually: `pip install yt-dlp`

---

## Install

Run once after extracting the package:

```bash
# macOS / Linux
./install.sh

# Windows (PowerShell)
.\install.ps1
```

> **Windows note:** If PowerShell blocks the script due to execution policy, run this once from an elevated PowerShell window, then re-run the installer:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

The installer will:
1. Verify Python 3.10+ and ffmpeg are present
2. Create a Python virtual environment (`venv/`)
3. Detect your GPU and install the appropriate PyTorch build (CUDA if an NVIDIA GPU is found, CPU-only otherwise)
4. Install all remaining dependencies
5. Pre-cache the transcription model so the first run is instant
6. Download all TechBS domain classification models found in `models/` and verify their integrity (SHA256)
7. Verify model integrity (SHA256 checksums)

---

## Usage

```bash
# macOS / Linux
./techbs.sh --file <audio_file> [options]
./techbs.sh --url <url> [options]
./techbs.sh --mic [options]

# Windows (PowerShell)
.\techbs.ps1 --file <audio_file> [options]
.\techbs.ps1 --url <url> [options]
.\techbs.ps1 --mic [options]
```

In **file mode** (`--file`), audio plays back through your system speakers in sync with the analysis so you can follow along in real time. Use `--no-play` to suppress playback and run faster than real time.

In **URL mode** (`--url`), TechBS downloads the audio from a YouTube video, podcast episode, or any other supported site using `yt-dlp`, then analyses it with real-time playback just like file mode. Add `--no-play` to skip playback and run at full speed. This works with YouTube, SoundCloud, and [many other sites supported by yt-dlp](https://github.com/yt-dlp/yt-dlp/blob/master/supportedsites.md). Note: services that require authentication or use DRM (e.g. Spotify, Apple Podcasts) are not supported.

In **mic mode** (`--mic`), TechBS records continuously from your default microphone and classifies each sample as it arrives. Press `Q` to stop.

---

## Options

| Flag | Description |
|------|-------------|
| `--file AUDIO_FILE` | Analyse a local audio file (mp3, wav, m4a, etc.) |
| `--url URL` | Analyse audio from a URL (YouTube, podcast, etc.) |
| `--mic` | Analyse live microphone input |
| `--no-play` | Skip audio playback and run analysis only. This is the key to screening recorded content quickly — the model processes the audio without playing it back, so you can vet a recording before deciding whether it's worth the listen |
| `--transcript` | Save a full JSON transcript when done |
| `--chunk-seconds N` | Seconds per analysis sample (default: `15`) |
| `--whisper-model SIZE` | Transcription accuracy: `tiny`, `base`, `small`, `medium`, `large` (default: `base`) |
| `--update-models` | Check for model updates and download any that are available |
| `--check-updates` | Show available model versions without downloading |
| `--manifest-url URL` | Override the update manifest URL (for `--update-models` / `--check-updates`) |

### Keyboard controls (during analysis)

| Key | Action |
|-----|--------|
| `S` or `Space` | Skip to the next sample (file mode only) |
| `Q` | Stop and show the final report |

---

## Examples

```bash
# Analyse a recorded talk
./techbs.sh --file talk.mp3

# Analyse without playing audio (faster than real time)
./techbs.sh --file talk.mp3 --no-play

# Analyse a YouTube video
./techbs.sh --url "https://youtube.com/watch?v=dQw4w9WgXcQ"

# Analyse a podcast episode by URL
./techbs.sh --url "https://example.com/episodes/episode-42.mp3"

# Save a full JSON transcript
./techbs.sh --file conference_keynote.m4a --transcript

# Check for model updates
./techbs.sh --check-updates

# Download available model updates
./techbs.sh --update-models

# Live microphone with 10-second samples
./techbs.sh --mic --chunk-seconds 10

# Use a more accurate transcription model for heavy accents or noisy audio
./techbs.sh --file recording.wav --whisper-model small --no-play
```

---

## Domain Models

Models live in the `models/` folder. Each model is custom-trained on content from a specific technical domain — giving it targeted signal on what counts as real depth versus fluff in that field. A cybersecurity model knows the difference between an actual CVE breakdown and a vendor-speak slide. A networking model knows when someone actually understands BGP versus when they're just saying "software-defined."

If multiple models are present, TechBS prompts you to select one at startup. The installer automatically downloads any model whose directory exists in `models/` and whose weights are available on the distribution storage. To add a new model, place its directory inside `models/` and re-run the installer.

Each model carries a version number and a SHA256 checksum in its `info.json` file. Downloaded weights are verified against this checksum — if the file doesn't match, it is deleted and the install fails loudly rather than silently loading a corrupted or tampered model.

---

## Model Updates

TechBS can check for and apply model updates without reinstalling.

```bash
# See what versions are available
./techbs.sh --check-updates

# Download any updates (prompts for confirmation)
./techbs.sh --update-models
```

Updates are fetched from a remote manifest JSON that lists the latest version, SHA256, and download URL for each model. Downloaded weights are verified against the manifest SHA256 before the old file is replaced. If verification fails, the download is discarded and your existing model is left untouched.

The manifest URL is configured by the distribution. You can override it with `--manifest-url` or by setting the `TECHBS_MANIFEST_URL` environment variable — useful if you are hosting your own model registry.

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
  - Windows ARM: `pip install sounddevice --no-binary sounddevice`
  - Windows x64: PortAudio DLL should be included with sounddevice; if issues occur, try the ARM command above
- Press `Ctrl+C` at any time to stop and show the final report.

---

## Acknowledgments

TechBS is built on the following open-source projects:

- **[Whisper](https://github.com/openai/whisper)** (OpenAI) — local speech-to-text transcription. MIT License.
- **[BERT](https://github.com/google-research/bert)** (Google Research) — base model architecture for domain classification. Apache 2.0 License. TechBS models are fine-tuned from `bert-base-uncased`.

See the [NOTICE](NOTICE) file for full attribution details.
