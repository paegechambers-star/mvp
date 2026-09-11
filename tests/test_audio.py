"""Tests for frapp.audio (MP3 transcription tool). No network/model download:
faster-whisper is mocked out so this runs without the optional `audio` extra."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from frapp import audio


class _FakeSegment:
    def __init__(self, start: float, end: float, text: str) -> None:
        self.start, self.end, self.text = start, end, text


class _FakeInfo:
    language = "de"
    language_probability = 0.987
    duration = 2.0


def test_get_metadata_missing_file_returns_empty() -> None:
    assert audio.get_metadata("/nonexistent/does-not-exist.mp3") == {}


def test_transcribe_mp3_raises_for_missing_file() -> None:
    try:
        audio.transcribe_mp3("/nonexistent/does-not-exist.mp3")
        assert False, "expected AudioToolError"
    except audio.AudioToolError as exc:
        assert "nicht gefunden" in str(exc)


def test_transcribe_mp3_wires_segments_and_text(tmp_path) -> None:
    fake_model = MagicMock()
    fake_model.transcribe.return_value = (
        [_FakeSegment(0.0, 1.0, " Hallo Welt"), _FakeSegment(1.0, 2.0, " Test.")],
        _FakeInfo(),
    )
    dummy = tmp_path / "dummy.mp3"
    dummy.write_bytes(b"\x00")

    with patch.object(audio, "_require_faster_whisper", return_value=MagicMock(return_value=fake_model)):
        result = audio.transcribe_mp3(dummy, model_size="base")

    assert result.text == "Hallo Welt Test."
    assert len(result.segments) == 2
    assert result.segments[0] == audio.Segment(start=0.0, end=1.0, text="Hallo Welt")
    assert result.language == "de"
    assert result.language_probability == 0.987
    assert result.duration == 2.0


def test_cli_listen_missing_file_exits_nonzero() -> None:
    import subprocess
    import sys

    p = subprocess.run(
        [sys.executable, "-m", "frapp.cli", "listen", "/nonexistent/does-not-exist.mp3"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert p.returncode != 0
    assert "nicht gefunden" in p.stdout + p.stderr
