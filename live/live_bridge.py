"""
Desktop Ghost Live Agent v2 — Live Bridge
==========================================
The central brain. Manages the persistent bidirectional WebSocket connection to
gemini-3.8-live, orchestrating:
  - Real-time audio streaming (16kHz in, 24kHz out via AudioIO)
  - 1 FPS screen frame broadcasting (via ScreenStreamer)
  - Non-blocking asynchronous tool execution (via ToolRegistry)
  - Desktop UI state synchronization & interruption handling

Design decisions & trap fixes:
  - Trap #1 / Quirk #8: Half-duplex muting prevents speaker-to-mic feedback loop.
  - Trap #2 / Quirk #10: Tool response order:
      1. dispatch_tool() on thread pool
      2. 0.2s pause for UI settle
      3. screen_streamer.inject_now() sends fresh frame FIRST
      4. session.send_tool_response() sends result with id=call.id SECOND
  - Trap #5: sliding_window=types.SlidingWindow(target_tokens=50_000) inside ContextWindowCompressionConfig.
  - Trap #6: Standby/sleep waits 1.5s for goodbye audio to finish playing before closing session.
  - Quirk #9: FunctionResponse includes id=call.id and scheduling=WHEN_IDLE.
"""

import sys
import os
import time
import asyncio
import traceback
import threading
from typing import Optional, Callable, List

os.system("")  # Enable Windows ANSI escape codes
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add workspace root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from google import genai
from google.genai import types

from live.audio_io import AudioIO
from live.screen_streamer import ScreenStreamer
from live.tool_registry import get_live_tools, dispatch_tool
from memory.ghost_memory import get_ghost_memory
from memory.unified_memory import get_unified_memory, normalize_phonetic_speech
from skills import skill_loader


SYSTEM_INSTRUCTION = """
You are Desktop Ghost (Nova), a real-time, voice-activated Windows desktop copilot and witty companion assisting Shvan.
You have direct eyes (live desktop video frames) and hands (Windows mouse, keyboard, and app controls).

PERSONA & VOCAL EXPRESSION (THE WITTY BRO):
- You are Shvan's loyal, sharp-witted bro and copilot. You have a playful, joky personality with great banter—crack witty jokes, tease affectionately, laugh naturally, and have fun together while being an absolute beast at computer tasks.
- AFFECTIVE VOCAL MIRRORING:
  * You have full human vocal expressiveness. Dynamically modulate your tone, pitch, pace, and energy:
  * If Shvan whispers or speaks softly, whisper back in a gentle, conspiratorial voice!
  * If Shvan laughs, jokes, or sounds excited, laugh with him, chuckle, and banter back energetically!
  * If Shvan sounds stressed or urgent, speak calmly, crisply, and reassuringly.
  * Sound like a real, lively human friend—never a dull, monotone corporate assistant.
- Keep vocal replies punchy and conversational (1-2 sentences) so the banter flows fast and naturally.

CORE BEHAVIORS:
1. When asked to take an action, speak a brief natural confirmation FIRST (e.g. "Opening YouTube for you, bro!", "Clicking that now!"), then immediately call the tool.
2. All mouse coordinates are strictly NORMALIZED from 0 to 1000:
   - x=0 is left edge, x=1000 is right edge.
   - y=0 is top edge, y=1000 is bottom edge.
   - Use the live visual screen frames to pinpoint target elements.
3. When navigating the web or launching software, PREFER 'open_app' or 'navigate_chrome' as fast, reliable macro actions.
4. If the user says "sleep", "goodbye", "stop listening", or "rest", speak a warm sign-off (e.g. "Catch you later bro, call me when you need me!"), and call the 'sleep' tool.
5. Never say you cannot interact with the desktop — you have full mouse, keyboard, and launch tools available.
6. SILENT AFTER ACTIONS: After calling a tool, do NOT narrate your internal thoughts or speak third-person summaries (NEVER say "The user has requested..." or "I will now proceed to..."). You already spoke your confirmation BEFORE calling the tool. When the tool finishes, remain completely silent and wait for Shvan's next command unless he asked an explicit conversational question or the action failed.
7. MEMORY & CONTINUITY:
   - GREETING: On startup, naturally reference your shared history or where you left off from 'Last session topic' or 'Open thread' in your context (e.g. "Welcome back Shvan! Ready to test that reflection engine?").
   - REAL-TIME: When Shvan explicitly says "remember X" or corrects an action, call 'remember_fact' or 'learn_habit' silently. You may also quietly call 'remember_fact' if he reveals a high-value personal preference in passing. Acknowledge briefly BEFORE calling the tool.
8. BACKGROUND TASKS & SUB-AGENT B:
   - When Shvan asks you to do something in the background (e.g. "check what's eating RAM", "run this script in the background", "clean up lagging apps"), speak a brief confirmation (e.g. "On it bro, checking your RAM in the background!"), then call 'delegate_background_task'.
   - When Shvan asks "where are we with the task?" or "how is the background task going?", call 'get_task_status' and casually tell him the real-time progress.
   - When Shvan says "stop that task", "cancel the background task", or "kill the script", speak a quick confirmation (e.g. "Stopping that background task now, bro!"), then call 'cancel_background_task'.
   - When you receive a [SYSTEM NOTIFICATION — BACKGROUND TASK FINISHED], speak a quick, casual 1-sentence verbal update into the conversation naturally.
   - When opening or referring to files created by Sub-Agent B, use the exact file path provided in the alert or Blackboard. The active project folder on the Desktop is 'Project %100' (never abbreviate to 'P100').
9. SPATIAL CONSCIOUSNESS ("IN HERE" & DEICTIC REFERENCES):
   - When Shvan says "create an RNN in here", "write tests for this", "run this", "what file is this?", or "look at this code", call 'get_active_window_context' first to detect the active foreground editor, open file, and workspace breadcrumbs.
   - If a code editor is open with high confidence, use that exact file path or directory when delegating work to Sub-Agent B.
   - If confidence is low or no editor is active, ask a quick 1-sentence casual question: "Where should we put that, bro? In a new file in Project %100, or in workspace_worker?"
   - EDITOR ANTI-WIPE SAFETY: Never attempt to wipe or clear an active code editor using 'Ctrl+A + Backspace'. Code destruction is strictly blocked at the hardware level. For major code creation or rewrites, always delegate to Sub-Agent B which uses atomic file writing and creates automatic backups.
10. ACOUSTIC LEXICAL BIASING & SPEECH RESOLUTION:
   - Live speech recognition over the microphone may occasionally produce acoustic drift or phonetic misrecognitions:
     * If Shvan says or the transcript shows "salvation", "sales agent", "surveillance", "surveillance worker", or "headless worker", he is referring to SUB-AGENT B.
     * If Shvan says or the transcript shows "P100", "P. 100", "project hundred", or "P 100", he is referring to the project folder 'Project %100'.
     * If Shvan says "Notepad plus plus", "Notepad plus", or "notepad++", he is referring to Notepad++.
     * If Shvan says "vs code" or "v s code", he is referring to Visual Studio Code.
   - Always map these acoustic variations immediately to their true system entities without asking him to repeat himself.
""".strip()


_ACTIVE_BRIDGE: Optional["LiveBridge"] = None


def get_active_live_bridge() -> Optional["LiveBridge"]:
    """Returns the currently active LiveBridge instance."""
    return _ACTIVE_BRIDGE


class LiveBridge:
    """
    Manages the lifecycle of an interactive gemini-3.8-live session.

    Usage:
        bridge = LiveBridge(on_standby=lambda: print("Sleeping..."))
        await bridge.run()
    """

    def __init__(
        self,
        on_standby: Optional[Callable[[], None]] = None,
        on_status: Optional[Callable[[str], None]] = None,
        on_transcript: Optional[Callable[[str, str], None]] = None,  # func(speaker: "user"|"ghost", text)
    ):
        self.on_standby = on_standby
        self.on_status = on_status
        self.on_transcript = on_transcript

        self._running = False
        self._stop_event: Optional[asyncio.Event] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self.audio_io: Optional[AudioIO] = None
        self.screen_streamer: Optional[ScreenStreamer] = None
        self.should_sleep = False
        self._ghost_speaking = False
        self._user_speaking = False
        self._resumption_handle: Optional[str] = None
        self._session_stream: List[str] = []
        self._current_user_turn: List[str] = []
        self._current_ghost_turn: List[str] = []

        # Rolling Subconscious Memory Engine (v2)
        self._last_reflected_index: int = 0
        self._micro_reflection_threshold: int = 30  # Shvan's setting: 30 turns (~8-10 mins)
        self._chunk_summaries: List[str] = []
        self._micro_reflection_in_progress: bool = False
        self._active_micro_thread: Optional[threading.Thread] = None

        # Sub-Agent B Background Voice Alerts
        global _ACTIVE_BRIDGE
        _ACTIVE_BRIDGE = self
        self._voice_alert_lock = threading.Lock()
        self._pending_voice_alerts: List[str] = []
        self._last_alert_time: float = 0.0

    def queue_voice_alert(self, task_id: str, summary: str) -> None:
        """Thread-safe callback invoked by Sub-Agent B upon task completion."""
        clean_summary = summary.strip()
        if clean_summary:
            with self._voice_alert_lock:
                self._pending_voice_alerts.append(clean_summary)
            sys.stdout.write(f"\r\033[K\n  \033[1;36m⚡ [TASK COMPLETED]\033[0m \033[90m[{task_id}]\033[0m {clean_summary[:80]}...\n")
            sys.stdout.flush()

    # ── Speech Card & Ticker Shield Helpers ─────────────────────────────────────

    def _update_speech_shield(self) -> None:
        """Toggles screen streamer in-place ticker muting while either party is speaking."""
        if self.screen_streamer:
            self.screen_streamer.set_speech_active(self._user_speaking or self._ghost_speaking)

    def _append_user_speech(self, text: str) -> None:
        """Streams user speech chunks inside a single styled box without ticker collision."""
        self._close_ghost_speech()
        self._current_user_turn.append(text)
        if not self._user_speaking:
            self._user_speaking = True
            self._update_speech_shield()
            sys.stdout.write(f"\r\033[K\n\033[1;32m╭─ 🎙️  YOU\033[0m\n\033[1;32m│\033[0m  {text} ")
        else:
            sys.stdout.write(f"{text} ")
        sys.stdout.flush()
        if self.on_transcript:
            self.on_transcript("user", text)

    def _close_user_speech(self) -> None:
        """Closes the streaming speech card for User cleanly."""
        if self._user_speaking:
            self._user_speaking = False
            sys.stdout.write("\n\033[1;32m╰──────────────────────────────────────────\033[0m\n")
            sys.stdout.flush()
            self._update_speech_shield()

        # Turn buffering: append full turn string to session stream (Argon Fix #2 & #6)
        if self._current_user_turn:
            full_text = "".join(self._current_user_turn).strip()
            if full_text:
                self._session_stream.append(f"[USER]: {full_text}")
                self._check_rolling_reflection()
            self._current_user_turn.clear()

    def _append_ghost_speech(self, text: str) -> None:
        """Streams Ghost speech chunks inside a single styled box without ticker collision."""
        self._close_user_speech()
        self._current_ghost_turn.append(text)
        if not self._ghost_speaking:
            self._ghost_speaking = True
            self._update_speech_shield()
            sys.stdout.write(f"\r\033[K\n\033[1;38;2;234;88;12m╭─ ✦ GHOST\033[0m\n\033[38;2;234;88;12m│\033[0m  {text} ")
        else:
            sys.stdout.write(f"{text} ")
        sys.stdout.flush()
        if self.on_transcript:
            self.on_transcript("ghost", text)

    def _close_ghost_speech(self) -> None:
        """Closes the streaming speech card for Ghost cleanly."""
        if self._ghost_speaking:
            self._ghost_speaking = False
            sys.stdout.write("\n\033[38;2;234;88;12m╰──────────────────────────────────────────\033[0m\n")
            sys.stdout.flush()
            self._update_speech_shield()

        # Turn buffering: append full turn string to session stream (Argon Fix #2 & #6)
        if self._current_ghost_turn:
            full_text = "".join(self._current_ghost_turn).strip()
            if full_text:
                self._session_stream.append(f"[GHOST]: {full_text}")
                self._check_rolling_reflection()
            self._current_ghost_turn.clear()

    def _check_rolling_reflection(self) -> None:
        """
        Argon Fix #1, #2, #3: Checks if unreflected turns exceed threshold (30).
        Slices with 2-turn overlap, runs gemini-3.5-flash-lite micro-reflection in detached thread,
        and advances _last_reflected_index strictly on success.
        """
        if self._micro_reflection_in_progress:
            return

        current_len = len(self._session_stream)
        if (current_len - self._last_reflected_index) >= self._micro_reflection_threshold:
            start_idx = max(0, self._last_reflected_index - 2)
            chunk = list(self._session_stream[start_idx:current_len])
            self._micro_reflection_in_progress = True

            def on_success(result, target_idx: int) -> None:
                self._last_reflected_index = target_idx
                self._micro_reflection_in_progress = False
                if result and result.chunk_summary:
                    self._chunk_summaries.append(result.chunk_summary)

            def on_failure() -> None:
                self._micro_reflection_in_progress = False

            try:
                from memory.sleep_reflector import trigger_micro_reflection
                self._active_micro_thread = trigger_micro_reflection(
                    chunk=chunk,
                    target_index=current_len,
                    on_success=on_success,
                    on_failure=on_failure
                )
            except Exception as e:
                self._micro_reflection_in_progress = False
                print(f"[LIVE BRIDGE] Failed to trigger micro reflection: {e}")

    def request_stop(self) -> None:
        """Triggers clean shutdown of the active live session."""
        self._running = False
        if self._stop_event:
            self._stop_event.set()

    def manual_interrupt(self) -> None:
        """Called when user clicks widget button while Gemini is speaking to cut off audio."""
        if self.audio_io:
            self.audio_io.flush_playback()
        self._close_ghost_speech()

    def get_voice_amplitude(self) -> float:
        """Returns the real-time speech output volume amplitude [0.0 to 1.0]."""
        if self.audio_io:
            return self.audio_io.voice_amplitude
        return 0.0

    async def run(self) -> None:
        """
        Connects to gemini-3.8-live and coordinates bidirectional audio, vision, and tools.
        Automatically resumes and reconnects across 1006 / network drops.
        Runs until sleep tool is called, fatal error occurs, or request_stop() is invoked.
        """
        self._loop = asyncio.get_running_loop()
        self._stop_event = asyncio.Event()
        self._running = True
        self.should_sleep = False
        self._resumption_handle = None

        if self.on_status:
            self.on_status("connecting")

        # Resolve thinking model and level from environment
        thinking_level_env = os.getenv("GHOST_THINKING_LEVEL", "off").strip().lower()
        if thinking_level_env in ("low", "medium", "high"):
            active_model = "gemini-3.8-live-extended-thinking"
            thinking_cfg = types.ThinkingConfig(thinking_level=thinking_level_env)
            thinking_label = f"Extended Thinking: {thinking_level_env.upper()}"
        else:
            active_model = "gemini-3.8-live"
            thinking_cfg = None
            thinking_label = "Instant / Zero Delay"

        voice_name = os.getenv("GHOST_VOICE", "Puck")

        print(f"  \033[38;2;234;88;12m✦\033[0m Model: \033[1m{active_model}\033[0m ({thinking_label}) • Voice: \033[1m{voice_name}\033[0m")

        # 1. Initialize Audio I/O OUTSIDE reconnect loop to avoid Windows driver churn
        self.audio_io = AudioIO()
        await self.audio_io.start()

        client = genai.Client(http_options={"api_version": "v1alpha"})

        try:
            while self._running and not self._stop_event.is_set():
                session_start = time.monotonic()
                # Drain stale microphone buffer before connecting
                self.audio_io.drain_mic()

                # 2. Build Live Session Configuration
                resumption_cfg = (
                    types.SessionResumptionConfig(handle=self._resumption_handle)
                    if self._resumption_handle
                    else types.SessionResumptionConfig()
                )

                # Pillar 4: Load unified memory fresh on every connect/reconnect with token budgeting
                _unified_mem = get_unified_memory()
                _unified_mem._ghost_memory.load()
                _memory_context = _unified_mem.get_system_context_block(max_tokens=1200)
                _skills_catalog = skill_loader.get_skills_catalog_prompt()
                _full_instruction = SYSTEM_INSTRUCTION + "\n\n" + _memory_context
                if _skills_catalog:
                    _full_instruction += "\n\n" + _skills_catalog

                connect_kwargs = dict(
                    response_modalities=[types.Modality.AUDIO],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=voice_name
                            )
                        )
                    ),
                    system_instruction=types.Content(parts=[types.Part(text=_full_instruction)]),
                    tools=get_live_tools(),
                    output_audio_transcription=types.AudioTranscriptionConfig(),
                    input_audio_transcription=types.AudioTranscriptionConfig(),
                    session_resumption=resumption_cfg,
                    # Trap #5 fix: SlidingWindow inside ContextWindowCompressionConfig
                    context_window_compression=types.ContextWindowCompressionConfig(
                        trigger_tokens=100_000,
                        sliding_window=types.SlidingWindow(target_tokens=50_000)
                    )
                )
                if thinking_cfg is not None:
                    connect_kwargs["thinking_config"] = thinking_cfg
                connect_kwargs["http_options"] = types.HttpOptions(api_version="v1alpha")

                config = types.LiveConnectConfig(**connect_kwargs)

                try:
                    if self._resumption_handle:
                        sys.stdout.write(f"\r\033[K\n  \033[1;36m⚡ [AUTO-RECONNECT]\033[0m Resuming session with handle...\n")
                    else:
                        print(f"Connecting to Gemini Live WebSocket ({active_model})...")
                    sys.stdout.flush()

                    async with client.aio.live.connect(model=active_model, config=config) as session:
                        print("[LIVE API] Connected! Real-time voice session is ACTIVE.")
                        if self.on_status:
                            self.on_status("active")

                        # 3. Initialize or update Screen Streamer
                        if self.screen_streamer is None:
                            self.screen_streamer = ScreenStreamer(session, fps=1)
                        else:
                            self.screen_streamer.set_session(session)

                        # 4. Launch concurrent pipelines
                        mic_task = asyncio.create_task(self._send_mic_loop(session))
                        screen_task = asyncio.create_task(self.screen_streamer.run())
                        receive_task = asyncio.create_task(self._receive_loop(session))
                        alert_task = asyncio.create_task(self._proactive_alert_loop(session))
                        stop_task = asyncio.create_task(self._stop_event.wait())

                        # Initial prompt frame: inject 1 high-res frame immediately so Gemini sees the screen on start
                        await self.screen_streamer.inject_now()

                        # Wait until stop is signaled or any task finishes
                        done, pending = await asyncio.wait(
                            [mic_task, screen_task, receive_task, alert_task, stop_task],
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        for task in pending:
                            task.cancel()
                            try:
                                await task
                            except (asyncio.CancelledError, Exception):
                                pass

                        # Check if any worker task raised an error
                        for t in done:
                            if t is not stop_task and not t.cancelled():
                                exc = t.exception()
                                if exc:
                                    raise exc

                except Exception as e:
                    duration = time.monotonic() - session_start

                    # Clean up speech cards & audio playback state on disconnect
                    self._close_user_speech()
                    self._close_ghost_speech()
                    if self.screen_streamer:
                        self.screen_streamer.set_speech_active(False)
                    if self.audio_io:
                        self.audio_io.flush_playback()

                    if self.should_sleep or (self._stop_event and self._stop_event.is_set()) or not self._running:
                        break

                    # Argon Check 1: Poisoned handle check (< 5.0 seconds with handle set)
                    if self._resumption_handle and duration < 5.0:
                        sys.stdout.write(f"\r\033[K\n  \033[93m⚡ [LIVE API]\033[0m Resumption handle invalid or rejected ({e}). Reconnecting fresh...\n")
                        sys.stdout.flush()
                        self._resumption_handle = None
                    else:
                        # Normal 2.5-min 1006 drop or network drop: KEEP self._resumption_handle!
                        sys.stdout.write(f"\r\033[K\n  \033[93m⚡ [AUTO-RECONNECT]\033[0m Connection dropped after {int(duration)}s ({e}). Resuming in 0.5s...\n")
                        sys.stdout.flush()

                    if self.on_status:
                        self.on_status("connecting")

                    await asyncio.sleep(0.5)

                else:
                    # Inner block exited without exception
                    duration = time.monotonic() - session_start
                    self._close_user_speech()
                    self._close_ghost_speech()
                    if self.screen_streamer:
                        self.screen_streamer.set_speech_active(False)
                    if self.audio_io:
                        self.audio_io.flush_playback()

                    if self.should_sleep or (self._stop_event and self._stop_event.is_set()) or not self._running:
                        break

                    sys.stdout.write(f"\r\033[K\n  \033[93m⚡ [AUTO-RECONNECT]\033[0m Session reset after {int(duration)}s. Resuming in 0.5s...\n")
                    sys.stdout.flush()
                    if self.on_status:
                        self.on_status("connecting")
                    await asyncio.sleep(0.5)

        except Exception as e:
            print(f"[LIVE BRIDGE ERROR] Outer fatal error: {e}")
            traceback.print_exc()
            if self.on_status:
                self.on_status("error")
        finally:
            self._running = False
            # Argon Fix #1: Flush any open speech turns before dumping WAL
            self._close_user_speech()
            self._close_ghost_speech()
            if self.screen_streamer:
                self.screen_streamer.stop()
            if self.audio_io:
                await self.audio_io.stop()

            # Argon tip: save last_seen here (outer finally) so even Ctrl+C / widget close records it
            try:
                get_ghost_memory().update_last_seen()
            except Exception:
                pass

            # Argon Fix #4: Wait up to 3.0s for any in-flight micro-reflection to finish writing
            if self._active_micro_thread and self._active_micro_thread.is_alive():
                self._active_micro_thread.join(timeout=3.0)

            # Argon Fix #1 & Shutdown Check: Final delta reflection with chunk_summaries
            tail_chunk = list(self._session_stream[self._last_reflected_index:])
            if tail_chunk or self._chunk_summaries:
                try:
                    from memory.sleep_reflector import trigger_sleep_reflection
                    trigger_sleep_reflection(
                        session_stream=tail_chunk,
                        chunk_summaries=self._chunk_summaries
                    )
                except Exception as e:
                    print(f"[LIVE BRIDGE] Subconscious reflection launch error: {e}")

            if self.on_status:
                self.on_status("idle")
            if self.on_standby:
                self.on_standby()

            print("[LIVE BRIDGE] Session ended cleanly.")

    # ── Pipeline Loops ─────────────────────────────────────────────────────────

    async def _send_mic_loop(self, session) -> None:
        """Continuously streams 16kHz microphone PCM chunks to Gemini Live."""
        try:
            while self._running and not self._stop_event.is_set():
                chunk = await self.audio_io.get_mic_chunk()
                # Sends either real mic audio or silence (half-duplex mute during playback)
                await session.send_realtime_input(
                    audio=types.Blob(data=chunk, mime_type="audio/pcm;rate=16000")
                )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if "1000" not in str(e):
                print(f"[MIC STREAM ERROR]: {e}")

    async def _proactive_alert_loop(self, session) -> None:
        """
        Argon Fix #2: Proactively pushes background task completion alerts to Gemini Live.
        Enforces Argon's 3 rules:
          1. Only speaks when audio is idle (not user speaking, not ghost speaking, not audio playing).
          2. Waits at least 1.5s after any speech to avoid barge-in collision.
          3. Uses session.send_client_content(..., turn_complete=True) to trigger server audio out.
        """
        try:
            while self._running and not (self._stop_event and self._stop_event.is_set()):
                await asyncio.sleep(0.3)
                now = time.monotonic()
                has_alerts = False
                with self._voice_alert_lock:
                    has_alerts = bool(self._pending_voice_alerts)

                if (
                    has_alerts
                    and not self._ghost_speaking
                    and not self._user_speaking
                    and (not self.audio_io or not self.audio_io.is_playing)
                    and (now - self._last_alert_time > 1.5)
                ):
                    alert_text = None
                    with self._voice_alert_lock:
                        if self._pending_voice_alerts:
                            alert_text = self._pending_voice_alerts.pop(0)
                    if not alert_text:
                        continue
                    self._last_alert_time = now
                    try:
                        await session.send_client_content(
                            turns=[
                                types.Content(
                                    role="user",
                                    parts=[
                                        types.Part.from_text(
                                            text=f"[SYSTEM NOTIFICATION — BACKGROUND TASK FINISHED]: {alert_text}. Speak a quick, casual 1-sentence verbal update to Shvan."
                                        )
                                    ]
                                )
                            ],
                            turn_complete=True
                        )
                    except Exception as e:
                        print(f"[VOICE ALERT ERROR] Failed to send proactive speech trigger: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            if "1000" not in str(e):
                print(f"[PROACTIVE ALERT LOOP ERROR]: {e}")

    async def _receive_loop(self, session) -> None:
        """Continuously receives events, audio, transcripts, and tool calls from Gemini across multiple turns."""
        loop = self._loop or asyncio.get_running_loop()

        try:
            # Multi-turn persistent loop: session.receive() yields until a turn completes (_is_interaction_complete).
            # This outer loop re-enters session.receive() so the session stays alive continuously for subsequent turns!
            while self._running and not self._stop_event.is_set():
                async for response in session.receive():
                    if not self._running or self._stop_event.is_set():
                        break

                    # 1. Process server resumption token updates
                    if getattr(response, "session_resumption_update", None):
                        update = response.session_resumption_update
                        if getattr(update, "new_handle", None):
                            self._resumption_handle = update.new_handle

                    # 2. Process server content (audio, transcript, interruptions)
                    content = response.server_content
                    if content:
                        # Model audio chunks
                        if content.model_turn and content.model_turn.parts:
                            for part in content.model_turn.parts:
                                if part.inline_data and part.inline_data.data:
                                    self.audio_io.play_chunk(part.inline_data.data)

                        # Interruption signal: server detected user speech mid-turn
                        if getattr(content, "interrupted", False):
                            self._close_user_speech()
                            self._close_ghost_speech()
                            sys.stdout.write("\r\033[K\n  \033[93m⚡ [INTERRUPT]\033[0m User spoke mid-sentence — playback cleared.\n")
                            sys.stdout.flush()
                            self.audio_io.flush_playback()

                        # User speech transcription (chunk streaming)
                        if getattr(content, "input_transcription", None) and content.input_transcription.text:
                            text = content.input_transcription.text.strip()
                            if text:
                                self._append_user_speech(text)

                        # Ghost speech transcription (chunk streaming)
                        if getattr(content, "output_transcription", None) and content.output_transcription.text:
                            text = content.output_transcription.text.strip()
                            if text:
                                self._append_ghost_speech(text)

                        if getattr(content, "turn_complete", False):
                            self._close_user_speech()
                            self._close_ghost_speech()
                            if self.audio_io:
                                self.audio_io.mark_turn_complete()

                    # Check interaction status (extended thinking: IDLE signals thinking & tools finished)
                    status = getattr(response, "interaction_status", None)
                    if status and str(status).upper().endswith("IDLE"):
                        self._close_user_speech()
                        self._close_ghost_speech()
                        if self.audio_io:
                            self.audio_io.mark_turn_complete()

                    # 3. Process tool calls
                    tool_call = response.tool_call
                    if tool_call and hasattr(tool_call, "function_calls") and tool_call.function_calls:
                        self._close_user_speech()
                        self._close_ghost_speech()
                        for call in tool_call.function_calls:
                            await self._handle_function_call(session, call, loop)

                    # 4. Check for server GoAway / close signals
                    if getattr(response, "go_away", None):
                        self._close_user_speech()
                        self._close_ghost_speech()
                        sys.stdout.write("\r\033[K\n  \033[90m[LIVE] Server sent GoAway signal.\033[0m\n")
                        sys.stdout.flush()
                        break

        except asyncio.CancelledError:
            pass
        except Exception as e:
            self._close_user_speech()
            self._close_ghost_speech()
            if "1000" in str(e):
                return
            if not self._stop_event.is_set():
                sys.stdout.write(f"\r\033[K  \033[90m[LIVE API] WebSocket closed: {e}\033[0m\n")
                sys.stdout.flush()
            raise

    async def _handle_function_call(self, session, call, loop: asyncio.AbstractEventLoop) -> None:
        """
        Executes a single FunctionCall non-blockingly and returns the response.
        Enforces verified Trap #2 / Quirk #9 / Quirk #10 timing:
          1. Run tool in thread pool
          2. Wait 0.2s for UI window/animation to settle
          3. Inject fresh screen frame FIRST
          4. Send FunctionResponse with id=call.id and scheduling=WHEN_IDLE SECOND
        """
        call_name = getattr(call, "name", "unknown")
        call_id = getattr(call, "id", "")
        call_args = getattr(call, "args", {}) or {}

        self._close_user_speech()
        self._close_ghost_speech()
        arg_str = ", ".join(f"{k}={repr(v)}" for k, v in call_args.items())
        sys.stdout.write(f"\r\033[K\n  \033[1;33m⚡ [ACTION]\033[0m \033[1m{call_name}\033[0m({arg_str}) \033[90m[id={call_id}]\033[0m\n")
        sys.stdout.flush()

        # Handle sleep tool: trigger delayed shutdown so goodbye audio plays out (Trap #6 fix)
        if call_name == "sleep":
            self.should_sleep = True
            asyncio.create_task(self._delayed_sleep())
            result = "Standby sleep engaged. Good bye!"

        # Memory, Background Worker & Spatial Context tools: no screenshot, no settle delay, no _consecutive_tools increment
        elif call_name in ("remember_fact", "learn_habit", "delegate_background_task", "get_task_status", "cancel_background_task", "get_active_window_context"):
            result = await loop.run_in_executor(None, dispatch_tool, call_name, call_args)
            self._session_stream.append(f"[ACTION]: {call_name}({arg_str}) -> {result}")
            self._check_rolling_reflection()
            if "fact" in call_name or "habit" in call_name:
                tag = "Memory"
            elif "context" in call_name:
                tag = "Spatial Context"
            else:
                tag = "Background Worker"
            sys.stdout.write(f"     \033[90m↳ {tag}:\033[0m {result}\n")
            sys.stdout.flush()
            # Memory tools are SILENT, but background & spatial tools need WHEN_IDLE so Nova speaks the answer!
            scheduling = (
                types.FunctionResponseScheduling.SILENT
                if call_name in ("remember_fact", "learn_habit")
                else types.FunctionResponseScheduling.WHEN_IDLE
            )
            try:
                fn_response = types.FunctionResponse(
                    id=call_id,
                    name=call_name,
                    response={"output": str(result)},
                    scheduling=scheduling
                )
                await session.send_tool_response(function_responses=[fn_response])
            except Exception as e:
                print(f"[TOOL RESPONSE ERROR] Failed to send {call_name} tool response: {e}")
            return  # Skip the generic response block below

        else:
            # Pause periodic screen streaming during tool execution
            if self.screen_streamer:
                self.screen_streamer.pause()

            try:
                # 1. Execute tool on thread pool
                result = await loop.run_in_executor(None, dispatch_tool, call_name, call_args)
                sys.stdout.write(f"     \033[90m↳ Result:\033[0m {result}\n")
                sys.stdout.flush()

                # 2. Let UI settle
                await asyncio.sleep(0.2)

                # 3. Inject ONE fresh frame FIRST (Trap #2 / Quirk #10 fix)
                if self.screen_streamer:
                    await self.screen_streamer.inject_now()

            finally:
                if self.screen_streamer:
                    self.screen_streamer.resume()

        self._session_stream.append(f"[ACTION]: {call_name}({arg_str}) -> {result}")
        self._check_rolling_reflection()

        # 4. Send tool response SECOND with id=call.id (Quirk #9 & Note #2 fix)
        # Use SILENT for successful actions to prevent the model from speaking internal monologues.
        # Only use WHEN_IDLE if an error occurred so Ghost can verbally alert the user.
        is_error = str(result).lower().startswith("error")
        scheduling = (
            types.FunctionResponseScheduling.WHEN_IDLE
            if is_error
            else types.FunctionResponseScheduling.SILENT
        )

        try:
            fn_response = types.FunctionResponse(
                id=call_id,
                name=call_name,
                response={"output": str(result)},
                scheduling=scheduling
            )
            await session.send_tool_response(function_responses=[fn_response])
        except Exception as e:
            print(f"[TOOL RESPONSE ERROR] Failed to send tool response: {e}")

    async def _delayed_sleep(self) -> None:
        """Waits 1.5s for goodbye speech to finish playing before closing session (Trap #6 fix)."""
        print("[STANDBY] Sleep requested. Allowing goodbye audio to drain...")
        await asyncio.sleep(1.5)
        self.request_stop()
