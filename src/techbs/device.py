"""Centralized torch device + FP16 capability detection.

All three inference paths — the classifier, the file transcriber, and the mic
transcriber — share the same hardware rules from here so they can't drift apart.
"""
import torch


def classifier_device() -> torch.device:
    """Best device for the sequence-classification model: CUDA > MPS > CPU."""
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def whisper_device() -> str:
    """Device string for Whisper. faster-whisper (CTranslate2) supports only
    CUDA and CPU, so Apple Silicon runs Whisper on CPU."""
    return "cuda" if torch.cuda.is_available() else "cpu"


def use_fp16() -> bool:
    """FP16 is safe only on CUDA with compute capability >= 7.0 (Volta+).
    Older GPUs produce NaNs, so everything else stays FP32."""
    return torch.cuda.is_available() and torch.cuda.get_device_capability()[0] >= 7
