"""
Desktop Ghost Live Agent v2 — Screen Streamer
==============================================
Broadcasts periodic JPEG frames of your desktop into the gemini-3.8-live
WebSocket session so the model always knows what is on screen.

Design decisions:
  - Streams at 1 FPS by default — enough for scene understanding without
    flooding the 65K TPM token budget with redundant frames.
  - Pauses during tool execution to avoid visual noise mid-action.
  - Trap #2 / Quirk #10 fix: inject_now() sends ONE immediate fresh high-res
    frame outside the normal cadence. Called by live_bridge BEFORE sending
    send_tool_response(), so the model sees the result of its action before
    it decides the next step.
  - Uses actuator.capture_desktop_screenshot() — thread-safe MSS grab with
    DPI awareness and Win32 desktop attachment already handled.
"""

import os
import sys
import time
import asyncio
from typing import Optional, TYPE_CHECKING

os.system("")  # Enable Windows ANSI escape codes
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

if TYPE_CHECKING:
    from google.genai.live import AsyncSession  # type hints only

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import actuator
from google.genai import types


class ScreenStreamer:
    """
    Sends periodic desktop JPEG frames into an active gemini-3.8-live session.

    Usage (inside live_bridge):
        streamer = ScreenStreamer(session, fps=1)
        task = asyncio.create_task(streamer.run())

        # During tool execution:
        streamer.pause()
        result = dispatch_tool(...)
        await asyncio.sleep(0.2)           # let UI settle
        await streamer.inject_now()        # fresh frame before tool response
        await session.send_tool_response(...)
        streamer.resume()

        # On shutdown:
        streamer.stop()
        await task
    """

    # JPEG quality: ambient stream uses 65, precision on-demand uses 88 (native crispness)
    STREAM_QUALITY    = 65
    PRECISION_QUALITY = 88
    HEARTBEAT_SEC     = 6.0   # Send refresh frame every 6s even when static

    # Pillar 5 Upgrade 2: Motion-adaptive streaming intervals
    STATIC_INTERVAL   = 5.0   # 0.2 FPS when nothing is moving on screen
    ACTIVE_INTERVAL   = 1.0   # 1.0 FPS during voice-triggered burst
    BURST_DURATION    = 10.0  # Seconds to stay at 1 FPS after voice trigger

    def __init__(self, session, fps: int = 1):
        """
        :param session: Active gemini-3.8-live AsyncSession from live_bridge.
        :param fps: Frames per second to stream. 1 is recommended.
        """
        self._session        = session
        self._interval       = 1.0 / max(1, min(fps, 5))   # Clamp 1–5 FPS
        self._running        = False
        self._paused         = False
        self._speech_active  = False
        self._last_send_time = 0.0
        self._last_thumb: Optional[bytes] = None
        self._frames_sent    = 0
        self._frames_skipped = 0
        # Pillar 5 Upgrade 2: Voice-triggered burst mode
        self._voice_triggered_at: float = 0.0

    # ── Control API ────────────────────────────────────────────────────────────

    def set_speech_active(self, active: bool) -> None:
        """Mutes in-place console ticker during speech to prevent text collision."""
        self._speech_active = active

    def set_session(self, session) -> None:
        """Updates the active Gemini Live session reference on auto-reconnect."""
        self._session = session

    def voice_trigger(self) -> None:
        """
        Pillar 5 Upgrade 2: Call when user starts speaking.
        Boosts screen capture to 1 FPS (ACTIVE_INTERVAL) for BURST_DURATION seconds,
        then automatically drops back to 0.2 FPS (STATIC_INTERVAL) when static.
        """
        self._voice_triggered_at = time.monotonic()

    def pause(self) -> None:
        """
        Pauses periodic frame sending. Called at the start of tool execution
        to avoid flooding the session with mid-action frames.
        """
        self._paused = True

    def resume(self) -> None:
        """
        Resumes periodic frame sending after tool execution completes.
        Resets the last-send timestamp so the next frame goes immediately.
        """
        self._paused = False
        self._last_send_time = 0.0  # Send fresh frame on next loop iteration

    def stop(self) -> None:
        """Signals the run() loop to exit cleanly."""
        self._running = False

    @property
    def frames_sent(self) -> int:
        return self._frames_sent

    # ── Main streaming loop ────────────────────────────────────────────────────

    async def run(self) -> None:
        """
        Background task: captures and sends desktop frames at adaptive FPS.
        Pillar 5 Upgrade 2: Uses STATIC_INTERVAL (0.2 FPS) when idle,
        ACTIVE_INTERVAL (1 FPS) during voice-triggered burst.
        Run as: asyncio.create_task(streamer.run())
        """
        self._running = True
        print(f"[SCREEN] Streamer started (adaptive: {1/self.ACTIVE_INTERVAL:.1f} FPS active, "
              f"{1/self.STATIC_INTERVAL:.1f} FPS static, quality={self.STREAM_QUALITY})")

        while self._running:
            now = time.monotonic()
            # Pillar 5: Dynamic interval based on voice activity
            in_burst = (now - self._voice_triggered_at) < self.BURST_DURATION
            effective_interval = self.ACTIVE_INTERVAL if in_burst else self.STATIC_INTERVAL
            elapsed = now - self._last_send_time

            if not self._paused and elapsed >= effective_interval:
                await self._capture_and_send(quality=self.STREAM_QUALITY)
                self._last_send_time = time.monotonic()
            else:
                self._frames_skipped += 1

            # Sleep a short slice so we yield control — avoids spinning CPU
            await asyncio.sleep(0.05)

        print(f"[SCREEN] Streamer stopped. "
              f"Sent={self._frames_sent}, Skipped={self._frames_skipped}")

    async def inject_now(self, quality: Optional[int] = None) -> None:
        """
        Captures and sends ONE immediate frame at highest quality (q=88).
        Called by live_bridge BEFORE send_tool_response() so the model sees
        the updated screen state when evaluating the tool result. (Trap #2 fix)

        :param quality: JPEG quality override. Defaults to PRECISION_QUALITY (88).
        """
        q = quality if quality is not None else self.PRECISION_QUALITY
        await self._capture_and_send(quality=q, label="[PRECISION]", force=True)

    # ── Internal ───────────────────────────────────────────────────────────────

    async def _capture_and_send(self, quality: int, label: str = "", force: bool = False) -> None:
        """
        Adaptive Screen Capture:
        - Uses perceptual thumbnail diffing: drops unchanged static frames to save tokens & WiFi.
        - Sends full frame if changed, or if heartbeat (6s) elapsed, or if forced.
        """
        loop = asyncio.get_running_loop()

        try:
            now = time.monotonic()
            is_heartbeat = (now - self._last_send_time >= self.HEARTBEAT_SEC)
            should_force_encode = force or is_heartbeat or (self._last_thumb is None)

            # Capture in executor — MSS is synchronous and takes ~20ms
            jpeg_bytes, new_thumb, is_changed = await loop.run_in_executor(
                None,
                actuator.capture_desktop_screenshot_adaptive,
                quality,
                self._last_thumb,
                should_force_encode
            )
            self._last_thumb = new_thumb

            # If unchanged and not forced/heartbeat, skip sending over WebSocket
            if not is_changed and not should_force_encode:
                self._frames_skipped += 1
                return

            if not jpeg_bytes:
                self._frames_skipped += 1
                return

            # Send to Live session as a video frame
            await self._session.send_realtime_input(
                video=types.Blob(data=jpeg_bytes, mime_type="image/jpeg")
            )

            self._frames_sent += 1
            self._last_send_time = time.monotonic()
            if label:
                # Precision snapshot: clear any in-place ticker residue and print on new line
                sys.stdout.write(f"\r\033[K\n  \033[1;36m[VISION]\033[0m 📸 High-res frame #{self._frames_sent} sent ({len(jpeg_bytes)//1024} KB, q={quality})\n")
                sys.stdout.flush()
            elif not self._speech_active:
                # Dynamic in-place ticker (overwrites current line, never scrolls terminal!)
                # Muted during active speech to eliminate card collisions.
                sys.stdout.write(f"\r  \033[90m[VISION] 👁️  Streaming Desktop • Frame #{self._frames_sent} ({len(jpeg_bytes)//1024} KB)\033[0m   ")
                sys.stdout.flush()

        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Non-fatal: log and continue streaming
            print(f"[SCREEN] Warning: frame send failed — {e}")
