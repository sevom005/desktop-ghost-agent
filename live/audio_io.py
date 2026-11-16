"""
Desktop Ghost Live Agent v2 — Audio I/O
========================================
Handles all real-time audio input (microphone) and output (speakers) for the
gemini-3.8-live WebSocket session.

Design decisions (all verified against SDK and hardware):
  - Trap #1 / Quirk #8: Half-duplex mode. Mic is muted while speaker plays to
    prevent laptop speaker echo from triggering Gemini's server-side VAD. The
    widget button acts as manual interrupt while Gemini is speaking.
  - Trap #4: sounddevice callbacks run on a high-priority C/PortAudio thread.
    All asyncio queue writes use loop.call_soon_threadsafe() for thread safety.
  - Note #1: When muted, we send silence chunks (b'\\x00' * 3200) rather than
    dropping packets entirely. This keeps Gemini's server-side VAD clock alive
    so there is no 1-second lag when you start talking after Gemini finishes.

Audio format contract:
  - Microphone input:  16kHz, mono, int16 PCM  (100ms chunks = 3200 bytes)
  - Speaker output:    24kHz, mono, int16 PCM  (variable chunk sizes from API)
"""

import time
import asyncio
import threading
import queue as thread_queue
from typing import Optional, Callable

import numpy as np
import sounddevice as sd

# ── Audio constants ────────────────────────────────────────────────────────────
MIC_SAMPLE_RATE   = 16_000   # Hz — required by Gemini Live API input
SPK_SAMPLE_RATE   = 24_000   # Hz — required by Gemini Live API output
CHANNELS          = 1        # Mono throughout
CHUNK_MS          = 100      # Milliseconds per mic capture chunk
MIC_BLOCK_SIZE    = int(MIC_SAMPLE_RATE * CHUNK_MS / 1000)  # 1600 samples
MIC_SILENCE_CHUNK = b"\x00" * (MIC_BLOCK_SIZE * 2)          # 3200 bytes silence (int16)


class AudioIO:
    """
    Manages microphone capture and speaker playback for the Live session.

    Usage:
        audio = AudioIO(on_interrupt_requested=widget.flash_button)
        await audio.start()
        ...
        chunk = await audio.get_mic_chunk()     # yields 3200-byte PCM chunks
        audio.play_chunk(pcm_bytes)             # plays incoming audio from Gemini
        audio.flush_playback()                  # instantly cuts Gemini off (widget button)
        await audio.stop()
    """

    def __init__(self, on_flushed: Optional[Callable] = None):
        """
        :param on_flushed: Optional notification callback invoked after speaker playback
               buffer has been flushed.
        """
        self._on_flushed = on_flushed

        # asyncio event loop — set when start() is called
        self._loop: Optional[asyncio.AbstractEventLoop] = None

        # Mic → WebSocket pipeline (asyncio-safe queue)
        self._mic_queue: Optional[asyncio.Queue] = None

        # Speaker playback (thread queue for the output stream callback)
        self._spk_queue: thread_queue.Queue = thread_queue.Queue()

        # Half-duplex state: True while speaker buffer has audio playing
        self._is_playing: bool = False
        self._was_playing: bool = False

        # Pre-roll jitter buffer & debounce hysteresis (absorbs WiFi packet lag & stops voice stutter)
        self._is_pre_rolling: bool = True
        self._pre_roll_start: float = 0.0
        self._pre_roll_timeout: float = 0.100  # 100ms max wait for pre-roll cushion
        self._pre_roll_min_bytes: int = 4800   # 100ms of 24kHz int16 mono (24000 * 2 * 0.10 = 4800 bytes)
        self._turn_complete: bool = False
        self._underrun_start: float = 0.0

        # Leftover buffer for speaker output stream (partial chunk handling)
        self._spk_buffer: bytes = b""
        self._voice_amplitude: float = 0.0

        # sounddevice stream handles
        self._mic_stream: Optional[sd.InputStream]  = None
        self._spk_stream: Optional[sd.OutputStream] = None

        # Graceful shutdown flag
        self._running: bool = False

    # ── Public API ─────────────────────────────────────────────────────────────

    async def start(self) -> None:
        """Opens mic and speaker streams. Must be called from the asyncio event loop."""
        self._loop     = asyncio.get_running_loop()
        self._mic_queue = asyncio.Queue()
        self._running  = True
        self._spk_buffer = b""

        # Open speaker output FIRST so it is ready before mic starts pushing data
        self._spk_stream = sd.OutputStream(
            samplerate=SPK_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=0,       # Variable block size — smoothest for streaming
            callback=self._spk_callback,
        )
        self._spk_stream.start()

        # Open microphone input
        self._mic_stream = sd.InputStream(
            samplerate=MIC_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=MIC_BLOCK_SIZE,
            callback=self._mic_callback,
        )
        self._mic_stream.start()

        print("[AUDIO] Mic and speaker streams open.")
        print(f"  Mic:     {sd.query_devices(kind='input')['name']} @ {MIC_SAMPLE_RATE}Hz")
        print(f"  Speaker: {sd.query_devices(kind='output')['name']} @ {SPK_SAMPLE_RATE}Hz")

    async def stop(self) -> None:
        """Closes all audio streams cleanly."""
        self._running = False

        if self._mic_stream:
            self._mic_stream.stop()
            self._mic_stream.close()
            self._mic_stream = None

        if self._spk_stream:
            self._spk_stream.stop()
            self._spk_stream.close()
            self._spk_stream = None

        # Drain queues
        if self._mic_queue:
            while not self._mic_queue.empty():
                try:
                    self._mic_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
        while not self._spk_queue.empty():
            try:
                self._spk_queue.get_nowait()
            except thread_queue.Empty:
                break

        self._is_playing = False
        print("[AUDIO] Streams closed.")

    def drain_mic(self) -> None:
        """Drains any buffered microphone audio chunks so stale speech isn't sent on reconnect or unmute."""
        if self._mic_queue:
            cleared = 0
            while not self._mic_queue.empty():
                try:
                    self._mic_queue.get_nowait()
                    cleared += 1
                except (asyncio.QueueEmpty, Exception):
                    break
            if cleared > 0:
                print(f"[AUDIO] Purged {cleared} stale microphone chunks.")

    async def get_mic_chunk(self) -> bytes:
        """
        Awaitable. Returns the next 3200-byte PCM chunk from the microphone.
        While the speaker is playing (half-duplex mute), returns silence chunks
        instead of real mic audio — keeps Gemini's VAD clock alive (Note #1).

        When playback finishes or is interrupted, any buffered chunks are purged
        so only fresh real-time audio recorded after the speaker went silent is sent.
        """
        if self._is_playing:
            self._was_playing = True
            # Muted: return silence without consuming the real audio queue.
            # Sleep one chunk-duration so the caller doesn't spin at CPU max.
            await asyncio.sleep(CHUNK_MS / 1000)
            return MIC_SILENCE_CHUNK

        # Transition barrier: if speaker just finished, purge any speaker bleed/straggler chunks
        if self._was_playing:
            self._was_playing = False
            self.drain_mic()

        chunk = await self._mic_queue.get()
        return chunk

    def play_chunk(self, pcm_bytes: bytes) -> None:
        """
        Enqueues a PCM audio chunk for playback through the speaker.
        Called by live_bridge._receive_loop() for each audio delta from Gemini.
        Sets is_playing=True as soon as audio arrives.
        """
        self._is_playing = True
        self._underrun_start = 0.0
        self._turn_complete = False
        if self._is_pre_rolling and self._pre_roll_start == 0.0:
            self._pre_roll_start = time.monotonic()
        self._spk_queue.put_nowait(pcm_bytes)

    def mark_turn_complete(self) -> None:
        """
        Signals that Gemini finished generating the current turn's audio.
        Instantly opens the pre-roll gate so any remaining/short buffered audio plays out immediately.
        """
        self._turn_complete = True
        self._is_pre_rolling = False
        self._pre_roll_start = 0.0

    def flush_playback(self) -> None:
        """
        Instantly clears the speaker buffer — used for two cases:
          1. Gemini's server sends content.interrupted=True (server detected your voice)
          2. You manually click the widget button while Gemini is speaking

        After flushing, is_playing is reset to False and the mic is live again.
        """
        # Drain the speaker queue
        cleared = 0
        while not self._spk_queue.empty():
            try:
                self._spk_queue.get_nowait()
                cleared += 1
            except thread_queue.Empty:
                break

        self._spk_buffer  = b""
        self._voice_amplitude = 0.0
        self._is_playing  = False
        self._was_playing = False
        self._is_pre_rolling = True
        self._pre_roll_start = 0.0
        self._turn_complete = False
        self._underrun_start = 0.0
        self.drain_mic()

        if cleared > 0:
            print(f"[AUDIO] Flushed {cleared} pending speaker chunks (interrupted).")

        if self._on_flushed:
            try:
                self._on_flushed()
            except Exception:
                pass

    @property
    def is_playing(self) -> bool:
        """True while Gemini's voice is actively playing through speakers."""
        return self._is_playing

    @property
    def voice_amplitude(self) -> float:
        """Current speaker audio volume amplitude [0.0 to 1.0]."""
        return self._voice_amplitude

    # ── sounddevice callbacks (run on C/PortAudio high-priority thread) ────────

    def _mic_callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        """
        Called by sounddevice every 100ms with fresh microphone audio.
        Runs on a C/PortAudio thread — MUST use loop.call_soon_threadsafe()
        to safely bridge data into the asyncio event loop. (Trap #4 fix)
        """
        if not self._running or not self._loop or not self._mic_queue:
            return
        # Coarse drop while speaker is playing to eliminate queue bloat and feedback
        if self._is_playing:
            return
        # Convert float32 [-1.0, 1.0] → int16 PCM bytes
        pcm_int16 = (indata[:, 0] * 32767).astype(np.int16).tobytes()
        # Thread-safe enqueue into the asyncio queue
        self._loop.call_soon_threadsafe(self._mic_queue.put_nowait, pcm_int16)

    def _spk_callback(self, outdata: np.ndarray, frames: int, time_info, status) -> None:
        """
        Called by sounddevice when the speaker needs the next audio block.
        Runs on a C/PortAudio thread. Reads from thread_queue.Queue (thread-safe).
        Features:
        - 150ms Pre-Roll Jitter Buffer: smooths WiFi packet delivery variance
        - 150ms Debounce Hysteresis: eliminates 'uuu... u-u-u' audio stutter and mic flapping
        - Clean silence padding on underrun (zero pop/click artifacts)
        """
        needed_bytes = frames * 2  # int16 = 2 bytes/sample

        # Drain incoming queue chunks into local buffer
        while len(self._spk_buffer) < needed_bytes * 4:
            try:
                chunk = self._spk_queue.get_nowait()
                self._spk_buffer += chunk
            except thread_queue.Empty:
                break

        # 1. Check Pre-Roll Jitter Buffer
        if self._is_pre_rolling:
            now = time.monotonic()
            time_waited = (now - self._pre_roll_start) if self._pre_roll_start > 0 else 0.0

            should_release = (
                len(self._spk_buffer) >= self._pre_roll_min_bytes
                or self._turn_complete
                or (time_waited >= self._pre_roll_timeout and len(self._spk_buffer) > 0)
                or (self._spk_queue.empty() and time_waited >= 0.050 and len(self._spk_buffer) > 0)
            )

            if should_release:
                self._is_pre_rolling = False
                self._pre_roll_start = 0.0
            elif len(self._spk_buffer) > 0 or not self._spk_queue.empty():
                # Still filling jitter cushion within timeout window — output silence
                outdata[:] = np.zeros((frames, 1), dtype=np.int16)
                return
            else:
                # No audio in queue or buffer
                outdata[:] = np.zeros((frames, 1), dtype=np.int16)
                return

        # 2. Process Playback
        if len(self._spk_buffer) >= needed_bytes:
            self._underrun_start = 0.0
            self._is_playing = True
            block = self._spk_buffer[:needed_bytes]
            self._spk_buffer = self._spk_buffer[needed_bytes:]
            outdata[:] = np.frombuffer(block, dtype=np.int16).reshape(-1, 1)
            # Live voice amplitude extraction for UI wave animation
            try:
                samples = outdata[:, 0].astype(np.float32)
                self._voice_amplitude = min(1.0, float(np.sqrt(np.mean(samples ** 2))) / 8000.0)
            except Exception:
                self._voice_amplitude = 0.0
        else:
            self._voice_amplitude = 0.0
            # Buffer underrun — fill with silence (no click/pop artifacts)
            if self._spk_buffer:
                partial = np.frombuffer(self._spk_buffer, dtype=np.int16)
                self._spk_buffer = b""
                silence = np.zeros(frames - len(partial), dtype=np.int16)
                outdata[:] = np.concatenate([partial, silence]).reshape(-1, 1)
            else:
                outdata[:] = np.zeros((frames, 1), dtype=np.int16)

            # 3. Debounce Hysteresis: Hold is_playing=True for 150ms across brief packet delays
            now = time.monotonic()
            if self._underrun_start == 0.0:
                self._underrun_start = now
            elif (now - self._underrun_start) >= 0.150:
                # Only declare speech finished when silence persists > 150ms
                self._is_playing = False
                self._is_pre_rolling = True
                self._pre_roll_start = 0.0
                self._turn_complete = False
                self._underrun_start = 0.0
