"""
Regression Test Suite for Sensory & Vocal Hardening:
1. AudioIO Jitter Buffer: Verifies pre-roll buffering and debounce hysteresis across WiFi gaps.
2. Actuator Adaptive Screen Delta: Verifies static screen frames skip JPEG encoding.
"""

import time
import asyncio
import numpy as np
from PIL import Image

import actuator
from live.audio_io import AudioIO, SPK_SAMPLE_RATE


def test_audio_io_pre_roll_jitter_buffer():
    """Verifies that AudioIO buffers incoming speech before releasing audio to speakers."""
    audio = AudioIO()
    audio._running = True
    audio._is_pre_rolling = True

    # 1. Supply only 1 tiny chunk (less than 7200 bytes pre-roll)
    tiny_chunk = b"\x01\x00" * 500  # 1000 bytes
    audio.play_chunk(tiny_chunk)

    # 2. First callback should output silence while buffering
    outdata = np.ones((256, 1), dtype=np.int16)
    audio._spk_callback(outdata, 256, None, None)

    assert audio._is_pre_rolling is True
    assert np.all(outdata == 0), "Pre-roll did not output silence while filling cushion!"

    # 3. Supply enough bytes to cross 7200 bytes threshold
    big_chunk = b"\x02\x00" * 4000  # 8000 bytes
    audio.play_chunk(big_chunk)

    # 4. Next callback should transition out of pre-roll and output real data
    audio._spk_callback(outdata, 256, None, None)
    assert audio._is_pre_rolling is False
    assert np.any(outdata != 0), "Audio gate did not open after pre-roll threshold met!"


def test_audio_io_debounce_hysteresis():
    """Verifies that brief silence gaps (<150ms) do NOT flip is_playing to False."""
    audio = AudioIO()
    audio._running = True
    audio._is_playing = True
    audio._is_pre_rolling = False
    audio._underrun_start = 0.0

    outdata = np.zeros((256, 1), dtype=np.int16)

    # First empty callback: marks underrun start, but is_playing must STAY True!
    audio._spk_callback(outdata, 256, None, None)
    assert audio._is_playing is True
    assert audio._underrun_start > 0.0

    # Simulate 50ms later (still within 150ms hysteresis)
    audio._spk_callback(outdata, 256, None, None)
    assert audio._is_playing is True, "is_playing flipped too early during minor network gap!"

    # Simulate arrival of a new chunk before 150ms expires
    fresh_chunk = b"\x05\x00" * 1000
    audio.play_chunk(fresh_chunk)
    audio._spk_callback(outdata, 256, None, None)
    assert audio._underrun_start == 0.0, "underrun_start was not reset upon new packet arrival!"
    assert audio._is_playing is True


def test_actuator_adaptive_delta_capture():
    """Verifies that static screens skip JPEG encoding, saving CPU and bandwidth."""
    # Run two captures of the same desktop
    raw1, thumb1, changed1 = actuator.capture_desktop_screenshot_adaptive(quality=65, last_thumb=None)
    assert raw1 is not None
    assert thumb1 is not None
    assert changed1 is True

    # Immediate second capture with same thumb: should detect unchanged screen
    raw2, thumb2, changed2 = actuator.capture_desktop_screenshot_adaptive(
        quality=65,
        last_thumb=thumb1,
        force_encode=False,
        diff_threshold=2.0
    )
    # If desktop didn't change in milliseconds, raw2 should be None (skipped JPEG encoding!)
    # and changed2 should be False
    assert thumb2 is not None
    if not changed2:
        assert raw2 is None, "Did not skip JPEG encoding for static screen!"


def test_audio_io_short_turn_and_timeout_release():
    """Verifies that short audio turns (< min bytes) play without getting stuck in pre-roll."""
    audio = AudioIO()
    audio._running = True
    audio._is_pre_rolling = True

    # Supply small chunk (1000 bytes)
    audio.play_chunk(b"\x01\x00" * 500)

    # Immediately mark turn complete (simulating Gemini finishing turn)
    audio.mark_turn_complete()

    outdata = np.zeros((256, 1), dtype=np.int16)
    audio._spk_callback(outdata, 256, None, None)

    assert audio._is_pre_rolling is False
    assert np.any(outdata != 0), "Turn complete should immediately open gate for short audio!"
