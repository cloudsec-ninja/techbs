"""faster-whisper loading and transcription, shared by file and mic modes."""
import subprocess
import sys
from pathlib import Path

import numpy as np

from .device import use_fp16, whisper_device

SAMPLE_RATE = 16_000

# Files faster-whisper needs from a model repo (mirrors faster_whisper.utils.download_model)
_MODEL_FILES = [
    "config.json",
    "preprocessor_config.json",
    "model.bin",
    "tokenizer.json",
    "vocabulary.*",
]


def _ensure_downloaded(name: str) -> str:
    """Return a local path for *name*, downloading it (with progress) on first use.

    faster-whisper's own downloader hides progress, which makes a multi-GB
    first download look like a hang.
    """
    if Path(name).is_dir():
        return name

    from faster_whisper.utils import _MODELS, download_model

    try:
        return download_model(name, local_files_only=True)
    except Exception:
        pass  # not cached yet

    import huggingface_hub

    repo_id = name if "/" in name else _MODELS.get(name)
    if repo_id is None:
        raise ValueError(f"Unknown Whisper model '{name}'")
    print(f"Downloading Whisper model '{name}' (first use only)...", flush=True)
    return huggingface_hub.snapshot_download(repo_id, allow_patterns=_MODEL_FILES)


def _compute_type(device: str) -> str:
    if device == "cuda":
        return "float16" if use_fp16() else "float32"
    return "int8"  # fast and accurate enough on CPU


def load_whisper(name: str):
    """Load a faster-whisper model on the best available device.

    If CUDA is available but the GPU libraries fail to load (e.g. missing
    cuDNN), fall back to CPU with a warning instead of crashing mid-analysis.
    """
    from faster_whisper import WhisperModel

    path = _ensure_downloaded(name)
    device = whisper_device()

    if device == "cuda":
        try:
            model = WhisperModel(path, device="cuda", compute_type=_compute_type("cuda"))
            # Warm up: CUDA/cuDNN libraries load lazily on the first inference
            transcribe_array(model, np.zeros(SAMPLE_RATE, dtype=np.float32), vad=False)
            model.techbs_device = "cuda"
            return model
        except Exception as exc:  # noqa: BLE001 - any GPU failure should fall back
            print(f"WARNING: Whisper could not use the GPU ({exc}). Falling back to CPU.",
                  file=sys.stderr)

    model = WhisperModel(path, device="cpu", compute_type=_compute_type("cpu"))
    model.techbs_device = "cpu"
    return model


def transcribe_array(model, audio: np.ndarray, vad: bool = True) -> str:
    """Transcribe a 16 kHz mono float32 array and return the joined text.

    vad=True skips non-speech audio, which stops Whisper from inventing text
    ("Thank you.") during silence or music.
    """
    segments, _info = model.transcribe(
        audio,
        beam_size=5,
        vad_filter=vad,
        condition_on_previous_text=False,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


def load_audio(path: str) -> np.ndarray:
    """Decode any audio/video file to 16 kHz mono float32 using the ffmpeg CLI.

    ffmpeg is already required for playback and --url, and the CLI is more
    stable across versions than faster-whisper's PyAV-based decode_audio
    (which breaks on PyAV 19).
    """
    cmd = [
        "ffmpeg", "-nostdin", "-threads", "0", "-i", path,
        "-f", "s16le", "-ac", "1", "-acodec", "pcm_s16le", "-ar", str(SAMPLE_RATE), "-",
    ]
    try:
        out = subprocess.run(cmd, capture_output=True, check=True).stdout
    except FileNotFoundError:
        raise RuntimeError(
            "ffmpeg not found. TechBS requires ffmpeg to decode audio files.\n"
            "  Windows: download from https://www.gyan.dev/ffmpeg/builds/ and add to PATH\n"
            "  macOS:   brew install ffmpeg\n"
            "  Linux:   sudo apt install ffmpeg"
        ) from None
    except subprocess.CalledProcessError as exc:
        detail = exc.stderr.decode(errors="replace").strip().splitlines()[-1:] or ["unknown error"]
        raise RuntimeError(f"Could not decode audio file '{path}': {detail[0]}") from None
    return np.frombuffer(out, np.int16).astype(np.float32) / 32768.0
