"""MP3/Audio transcription so Claude can read what's in an audio file.

Runs fully local (faster-whisper on CPU) — no audio leaves the machine,
in line with DSGVO.md's data-minimisation requirement. No API key needed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Segment:
    start: float
    end: float
    text: str


@dataclass
class TranscriptResult:
    text: str
    segments: list[Segment] = field(default_factory=list)
    language: str | None = None
    language_probability: float | None = None
    duration: float | None = None


class AudioToolError(RuntimeError):
    """Raised for missing dependencies or unreadable audio files."""


def _require_faster_whisper():
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise AudioToolError(
            "faster-whisper ist nicht installiert. "
            "Installieren mit: pip install -e '.[audio]'"
        ) from exc
    return WhisperModel


def get_metadata(path: Path) -> dict:
    """Best-effort tag/duration/bitrate lookup via mutagen. Returns {} if unreadable."""
    try:
        from mutagen import File as MutagenFile
    except ImportError:
        return {}

    try:
        audio = MutagenFile(path)
    except Exception:  # noqa: BLE001 - mutagen raises many undocumented format-specific errors
        return {}
    if audio is None:
        return {}

    info = getattr(audio, "info", None)
    meta = {
        "duration_seconds": round(info.length, 2) if info and hasattr(info, "length") else None,
        "bitrate": getattr(info, "bitrate", None) if info else None,
    }
    tags = getattr(audio, "tags", None)
    if tags:
        for key in ("title", "artist", "album", "TIT2", "TPE1", "TALB"):
            if key in tags:
                value = tags[key]
                meta[key.lower()] = str(value[0]) if isinstance(value, list) else str(value)
    return {k: v for k, v in meta.items() if v is not None}


def transcribe_mp3(
    path: Path,
    model_size: str = "base",
    language: str | None = None,
    device: str = "cpu",
    compute_type: str = "int8",
) -> TranscriptResult:
    """Transcribe an mp3/audio file to text using a local faster-whisper model.

    model_size: tiny|base|small|medium|large-v3 (bigger = more accurate, slower).
    language: force a language code (e.g. "de"); None = auto-detect.
    First call for a given model_size downloads the model from Hugging Face
    into ~/.cache/huggingface — needs network once, then works offline.
    """
    path = Path(path)
    if not path.exists():
        raise AudioToolError(f"Datei nicht gefunden: {path}")

    WhisperModel = _require_faster_whisper()
    model = WhisperModel(model_size, device=device, compute_type=compute_type)

    segments_iter, info = model.transcribe(str(path), language=language)
    segments = [
        Segment(start=round(s.start, 2), end=round(s.end, 2), text=s.text.strip())
        for s in segments_iter
    ]
    full_text = " ".join(s.text for s in segments).strip()

    return TranscriptResult(
        text=full_text,
        segments=segments,
        language=info.language,
        language_probability=round(info.language_probability, 3),
        duration=round(info.duration, 2),
    )
