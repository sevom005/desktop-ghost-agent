"""
Regression Test Suite for Audio I/O Queue Draining and Actuator Clipboard Injection
Verifies:
1. AudioIO drops incoming mic chunks while speaker is playing.
2. AudioIO purges lingering queue chunks on playback stop / flush.
3. Actuator execute_type automatically routes multi-line text to execute_paste.
4. Line endings are properly normalized to avoid CRLF doubling.
"""

import asyncio
import numpy as np
import pytest
from unittest.mock import patch, MagicMock

import actuator
from live.audio_io import AudioIO, MIC_SILENCE_CHUNK, MIC_BLOCK_SIZE


def test_audio_io_half_duplex_mic_drop():
    """Verifies that mic audio is dropped while speaker is playing and silence is returned."""
    async def _run():
        audio = AudioIO()
        audio._running = True
        audio._loop = asyncio.get_running_loop()
        audio._mic_queue = asyncio.Queue()

        # 1. Simulate speaker active
        audio._is_playing = True

        # 2. Incoming mic callback should drop chunks immediately
        dummy_data = np.ones((MIC_BLOCK_SIZE, 1), dtype=np.float32)
        audio._mic_callback(dummy_data, MIC_BLOCK_SIZE, None, None)

        # Queue must remain empty
        assert audio._mic_queue.empty(), "Mic queue accumulated chunks while speaker was playing!"

        # 3. get_mic_chunk() should return silence without consuming the real queue
        chunk = await audio.get_mic_chunk()
        assert chunk == MIC_SILENCE_CHUNK
        assert audio._was_playing is True

    asyncio.run(_run())


def test_audio_io_transition_drain():
    """Verifies that transitioning from playing to silent purges any straggler chunks."""
    async def _run():
        audio = AudioIO()
        audio._running = True
        audio._loop = asyncio.get_running_loop()
        audio._mic_queue = asyncio.Queue()

        # Pre-load queue with a stale chunk
        stale_chunk = b"\x01\x02" * MIC_BLOCK_SIZE
        audio._mic_queue.put_nowait(stale_chunk)
        audio._was_playing = True
        audio._is_playing = False

        # Drain mic
        audio.drain_mic()
        assert audio._mic_queue.empty()

    asyncio.run(_run())


def test_actuator_execute_type_routes_to_paste():
    """Verifies that multi-line text triggers execute_paste."""
    code = "import torch\nimport torch.nn as nn\nclass Model(nn.Module): pass"

    with patch("actuator.execute_paste") as mock_paste, patch("actuator.win32_type_unicode_char") as mock_type:
        actuator.execute_type(code, press_enter=False)
        mock_paste.assert_called_once_with(code, press_enter=False, x=None, y=None)
        mock_type.assert_not_called()


def test_actuator_execute_type_short_string_uses_keystrokes():
    """Verifies that short single-line text uses hardware keystrokes."""
    short_text = "hello"

    with patch("actuator.execute_paste") as mock_paste, patch("actuator.win32_type_unicode_char") as mock_type:
        actuator.execute_type(short_text, press_enter=False)
        mock_paste.assert_not_called()
        assert mock_type.call_count == len(short_text)


def test_actuator_execute_paste_normalizes_crlf():
    """Verifies execute_paste normalizes CRLF to LF and invokes pyperclip."""
    crlf_text = "line1\r\nline2\r\nline3"

    with patch("pyperclip.copy") as mock_copy, patch("actuator.execute_hotkey") as mock_hotkey, patch("time.sleep"):
        actuator.execute_paste(crlf_text)
        mock_copy.assert_called_once_with("line1\nline2\nline3")
        mock_hotkey.assert_called_once_with(["ctrl", "v"])
