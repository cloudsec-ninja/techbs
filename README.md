# TechBS — Real-Time BS Detection for Tech

Is that keynote actually a groundbreaking innovation, or just a 60-minute ad for a product you don't need? Is that tech influencer's "Top 10 Career Tips" list actually advice, or just trying to sell you a course?

Meet **TechBS**: your personal bullshit detector for the tech industry.

TechBS uses AI to separate real technical depth from buzzword-heavy marketing. Whether you're watching a keynote, listening to a podcast, or sitting through a tech interview, it helps you find what's real.

**Why use TechBS?**
*   **Live Analysis:** Use it in real-time to see if a speaker is delivering value or just filler.
*   **Recorded Content:** Run it against audio files to decide if they are worth your time.
*   **Career Protection:** Don't let thin content influence your career decisions. Get the facts, skip the hype.

One model covers cybersecurity, AI/ML and network engineering. It works out which of those fields a talk is about, and judges it against what real technical depth looks like in that field.

> **Disclaimer:** TechBS is for entertainment and informational purposes only. It is an AI model, and AI gets things wrong. Don't cry if it thinks your presentation is BS — just maybe reconsider why you have twelve slides about "leveraging synergies across the threat landscape."

---

## How it works

1. **Transcription** — Audio is converted to text locally with Whisper (via faster-whisper) in configurable samples (default 15 seconds). Silence and music within a sample are skipped. No external API required, everything runs on your machine.

2. **Classification** — Each transcribed sample is scored by the TechBS model, which assigns a probability across three labels and detects the field (cybersecurity, AI/ML or network engineering). The model judges each sample together with the speech just before it (the last 60 seconds by default), because the models were trained on passages about a minute long and judge short snippets poorly:

   | Label | Meaning |
   |-------|---------|
   | **LEGIT** | Real technical content — depth, specifics, actionable details |
   | **NEUTRAL** | Off-topic material — intros, logistics, audience Q&A, small talk |
   | **BS** | Marketing hype, buzzwords, vague claims, no technical substance |

3. **Live dashboard** — A full-screen terminal view updates as each sample is scored:
   - **Header** — position in the talk, the current sample's label, a rolling verdict over the last 5 samples, the running legit / neutral / BS split, and a colour timeline of the whole talk
   - **Current sample** — its full transcript with buzzwords highlighted, plus the legit / neutral / BS scores
   - **Earlier** — previous samples, newest first

4. **Final report** — When the audio ends (or you press Q), the report shows the overall verdict and what it was based on, a breakdown by time, the full timeline, the most BS and most technical moments with timestamps, and the samples where the model was unsure.

---

## Verdicts

### Per-sample
Every sample gets one of `LEGIT`, `NEUTRAL`, or `BS`, plus the probability for all three labels and a confidence level (high / medium / low).

### Overall verdict
The verdict answers two questions:
1. **How much of the talk is on-topic?** Legit and BS samples are on-topic; neutral samples (intros, logistics, small talk) are not.
2. **How good is the on-topic part?** The share of it that is legit vs. BS.

Samples count by confidence: high 1.0, medium 0.7, low 0.3. A sample the model was unsure about can't swing the result on its own.

| Verdict | When |
|---------|------|
| `HIGHLY TECHNICAL` | 75%+ of the on-topic part is legit |
| `SOLID CONTENT` | More than 60% legit |
| `MIXED` | Neither side above 60% |
| `MOSTLY BS` | More than 60% BS |
| `TOTAL BS` | 75%+ BS |
| `MOSTLY OFF-TOPIC` | Less than 40% of the talk is on-topic; the rest of the verdict says how good that part is |
| `OFF-TOPIC` | Less than 10% of the talk is on-topic |
| `NOT ENOUGH TO JUDGE` | Fewer than 4 on-topic samples |

### Rolling (live)
The header's "last 5" verdict uses the same tiers over the five most recent samples. It shows `OFF-TOPIC` when fewer than 40% of them are on-topic, and `TOO EARLY` until two on-topic samples have been heard.

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

**Windows (PowerShell):**
```powershell
irm https://techbs.ai/install.ps1 | iex
```
Installs to `%LOCALAPPDATA%\techbs` and registers the `techbs` command.

> **Windows note:** If PowerShell blocks the script, run this once from an elevated PowerShell window, then re-run the installer:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```

The installer will:
1. Verify Python 3.10+ and ffmpeg are present
2. Download the latest TechBS release from GitHub
3. Create a Python virtual environment
4. Detect your GPU and install the appropriate PyTorch build (CUDA if NVIDIA GPU found, CPU-only otherwise)
5. Install TechBS and its dependencies into the virtual environment
6. Download the TechBS model (about 420 MB)
7. Register the `techbs` command

Re-running the installer updates TechBS in place. Downloaded models are kept.

## Uninstall

**macOS / Linux:**
```bash
curl -fsSL https://techbs.ai/install.sh | bash -s -- --uninstall
```

**Windows (PowerShell):**
```powershell
$env:TECHBS_UNINSTALL=1; irm https://techbs.ai/install.ps1 | iex
```

Removes the install directory (including downloaded models) and the `techbs` command. On Linux/macOS you may also remove the PATH line added to your shell rc file.

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

### Choosing a transcription model

The first time you analyse something, TechBS asks which Whisper model to use and remembers your choice. Bigger models transcribe technical terms more accurately (for example "MITRE ATT&CK" rather than "Miter Attack"), which gives the classifier better input. They are larger downloads and slower on CPU.

| Model | Download | Good for |
|-------|----------|----------|
| `tiny` | 75 MB | Very slow machines; expect errors |
| `base` | 145 MB | CPU; the previous default |
| `small` | 485 MB | Best balance on CPU |
| `medium` | 1.5 GB | GPU recommended |
| `large-v3-turbo` | 1.6 GB | Best balance on an NVIDIA GPU |
| `distil-large-v3` | 1.5 GB | NVIDIA GPU, English only |
| `large-v3` | 3.1 GB | Highest accuracy; GPU strongly recommended |

The model downloads once on first use. Change it any time with `techbs --select-whisper`, or try one for a single run with `--whisper-model NAME`.

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
| `--context-seconds N` | Seconds of speech each sample is judged with, counting back from the sample (default: `60`). Set it equal to `--chunk-seconds` to judge each sample on its own |
| `--whisper-model NAME` | Use this Whisper model for one run, e.g. `small` or `large-v3-turbo` (default: the model you chose) |
| `--select-whisper` | Choose the Whisper model again and save it |
| `--model-list` | List available models and their install status |
| `--model NAME` | Use a specific model (default: `techbs`) |
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

## The TechBS model

One model, `techbs`, covers three fields:

| Field | Examples of what it recognises |
|-------|--------------------------------|
| Cybersecurity | Exploit walkthroughs and malware analysis vs. vendor pitches and CISO platitudes |
| AI / ML | How models are trained and evaluated vs. "AI will change everything" hype |
| Network Engineering | QoS, routing and protocol detail vs. data-centre transformation marketing |

The report shows the detected field ("Field: Network Engineering (84%)"). Speech outside these fields counts as off-topic. The model was retrained in 2026 on a reviewed dataset; each passage was checked against a written labelling guide.

The installer downloads it. If it's missing (for example, the download failed), TechBS offers to download it on first run, or you can fetch it yourself:

```bash
techbs --model-pull techbs
techbs --model-list            # see installed and available models
```

Older single-field models (`cyberbs`, `netbs`, `aibs`) still work with `--model NAME`, but `techbs` replaces them and is used by default.

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

- The classifier runs on CPU, NVIDIA GPU (CUDA), or Apple Silicon (MPS). Whisper runs on CUDA or CPU (on Apple Silicon it uses the CPU). The installer picks the right PyTorch build automatically.
- If the GPU libraries fail to load, Whisper falls back to CPU with a warning rather than stopping.
- Microphone mode requires a working audio input device.
  - Linux: `sudo apt install libportaudio2`
  - macOS: `brew install portaudio`
  - Windows ARM: `pip install sounddevice --no-binary sounddevice`
- Press `Ctrl+C` at any time to stop and show the final report.

---

## Acknowledgments

TechBS is built on the following open-source projects:

- **[Whisper](https://github.com/openai/whisper)** (OpenAI) — speech-to-text models. MIT License.
- **[faster-whisper](https://github.com/SYSTRAN/faster-whisper)** (SYSTRAN) — fast local Whisper inference on CTranslate2. MIT License.
- **[BERT](https://github.com/google-research/bert)** (Google Research) — base model architecture for domain classification. Apache 2.0 License. TechBS models are fine-tuned from `bert-base-uncased`.

See the [NOTICE](NOTICE) file for full attribution details.
