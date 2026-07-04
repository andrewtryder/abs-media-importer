"""Tests for advanced import form helpers."""

from __future__ import annotations

from app.routes.pages import (
    _advanced_fields_from_form,
    _optional_form_bool,
    _validate_advanced_import_fields,
)


def test_optional_form_bool_tri_state():
    assert _optional_form_bool("") is None
    assert _optional_form_bool("true") is True
    assert _optional_form_bool("false") is False


def test_advanced_fields_from_form_parses_loudness():
    fields = _advanced_fields_from_form(
        loudness_normalize="true",
        loudness_target_lufs="-18",
        loudness_audio_bitrate="160k",
    )
    assert fields["loudness_normalize"] is True
    assert fields["loudness_target_lufs"] == "-18"
    assert fields["loudness_audio_bitrate"] == "160k"


def test_validate_advanced_import_fields_rejects_invalid_lufs():
    error = _validate_advanced_import_fields(
        collision_mode=None,
        filename_template=None,
        ytdlp_extra_args=None,
        ffmpeg_extra_args=None,
        cookies_file=None,
        loudness_target_lufs="5",
    )
    assert error is not None
    assert "Loudness target" in error


def test_validate_advanced_import_fields_rejects_invalid_bitrate():
    error = _validate_advanced_import_fields(
        collision_mode=None,
        filename_template=None,
        ytdlp_extra_args=None,
        ffmpeg_extra_args=None,
        cookies_file=None,
        loudness_audio_bitrate="fast",
    )
    assert error is not None
    assert "Loudness bitrate" in error
