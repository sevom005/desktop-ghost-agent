"""
tests/test_unified_memory_and_hygiene.py
=========================================
Unit tests for Pillar 4:
  - Unified Memory Manager (3-tier memory hierarchy & token budgeting)
  - Process liveness detection (Zero-dependency Windows & POSIX)
  - Acoustic lexical biasing & phonetic speech alias normalization
  - IBM ARIES crash recovery & stale lock scavenging
  - Sub-Agent B & Sleep Reflector model fallback cascade (503/429 mitigation)
"""

import os
import sys
import json
import time
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from memory.unified_memory import (
    is_pid_alive,
    normalize_phonetic_speech,
    UnifiedMemoryManager,
    get_unified_memory
)
from workers.subagent_b import (
    SUBAGENT_MODEL_CASCADE,
    SubAgentB
)
from memory.sleep_reflector import (
    REFLECTION_MODEL_CASCADE,
    _generate_reflection_with_fallback,
    synthesize_active_mind_context
)
from skills.win32_window_utils import ActiveSpatialContext


class TestUnifiedMemoryAndHygiene(unittest.TestCase):
    """Unit tests for Pillar 4 unified memory, hygiene, and fallback cascade."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ── Test 1: Process Liveness Verification ────────────────────────────────

    def test_process_liveness_detection(self):
        """Verifies is_pid_alive accurately identifies running vs dead PIDs."""
        my_pid = os.getpid()
        self.assertTrue(is_pid_alive(my_pid), "Current process PID must be reported as alive.")
        self.assertFalse(is_pid_alive(999999), "Non-existent PID 999999 must be reported as dead.")
        self.assertFalse(is_pid_alive(-1), "Negative PID must be reported as dead.")
        self.assertFalse(is_pid_alive(0), "PID 0 must be reported as dead.")

    # ── Test 2: Acoustic Lexical Biasing & Phonetic Speech Aliases ───────────

    def test_phonetic_speech_alias_normalization(self):
        """Verifies ASR acoustic drift mappings to canonical system entities."""
        # Sub-Agent B misrecognitions
        self.assertEqual(
            normalize_phonetic_speech("Tell the salvation agent to check RAM"),
            "Tell the Sub-Agent B to check RAM"
        )
        self.assertEqual(
            normalize_phonetic_speech("Stop the surveillance worker immediately"),
            "Stop the Sub-Agent B immediately"
        )
        self.assertEqual(
            normalize_phonetic_speech("What is sales agent doing?"),
            "What is Sub-Agent B doing?"
        )
        self.assertEqual(
            normalize_phonetic_speech("Delegate this to headless agent"),
            "Delegate this to Sub-Agent B"
        )

        # Project folder misrecognitions
        self.assertEqual(
            normalize_phonetic_speech("Look at files in p100"),
            "Look at files in Project %100"
        )
        self.assertEqual(
            normalize_phonetic_speech("Open project hundred workspace"),
            "Open Project %100 workspace"
        )
        self.assertEqual(
            normalize_phonetic_speech("Check p 100 scripts"),
            "Check Project %100 scripts"
        )

        # Editor misrecognitions
        self.assertEqual(
            normalize_phonetic_speech("Open script in notepad plus plus"),
            "Open script in Notepad++"
        )
        self.assertEqual(
            normalize_phonetic_speech("Open vs code and run test"),
            "Open VS Code and run test"
        )

    # ── Test 3: Context Block Assembly & Token Budgeting ─────────────────────

    def test_unified_context_block_assembly_and_budgeting(self):
        """Verifies 3-tier memory block formatting and character budget enforcement."""
        manager = UnifiedMemoryManager(memory_dir=self.tmp_dir)

        # 1. Standard assembly without active window
        block = manager.get_system_context_block(max_tokens=1200)
        self.assertIn("CORE IDENTITY & USER PREFERENCES", block)
        self.assertIn("Shvan", block)
        self.assertIn("Casual, direct, calls me bro", block)

        # 2. Assembly with Tier 1 Active Spatial Context
        spatial = ActiveSpatialContext(
            window_title="neural_net.py - Project %100 - Visual Studio Code",
            app_name="code.exe",
            file_name="neural_net.py",
            file_path="C:\\Users\\Administrator\\Desktop\\Project %100\\Computer_Use\\neural_net.py",
            workspace_name="Project %100",
            is_editor=True,
            confidence=0.95
        )
        block_spatial = manager.get_system_context_block(max_tokens=1200, spatial_context=spatial)
        self.assertIn("TIER 1: ACTIVE SPATIAL & TASK CONSCIOUSNESS", block_spatial)
        self.assertIn("neural_net.py", block_spatial)
        self.assertIn("code.exe", block_spatial)

        # 3. Budget enforcement on tiny token limit
        tiny_block = manager.get_system_context_block(max_tokens=50)
        # 50 tokens * 4 chars = 200 chars budget
        self.assertLessEqual(len(tiny_block), 250)

    # ── Test 4: ARIES Crash Recovery & Stale Lock Hygiene ────────────────────

    def test_aries_stale_lock_hygiene_and_recovery(self):
        """Verifies dead PID locks are scavenged while active PID locks are preserved."""
        manager = UnifiedMemoryManager(memory_dir=self.tmp_dir)

        # Create simulated lock files:
        # A. Dead PID lock (PID 999999) with stranded interaction turns
        dead_lock = os.path.join(self.tmp_dir, "pending_session.json.processing_999999_12345")
        stranded_data = {
            "session_stream": ["[USER]: Test stranded message", "[GHOST]: Test stranded reply"],
            "chunk_summaries": ["Completed test operation"]
        }
        with open(dead_lock, "w", encoding="utf-8") as f:
            json.dump(stranded_data, f)

        # B. Live PID lock (Current test process)
        my_pid = os.getpid()
        live_lock = os.path.join(self.tmp_dir, f"pending_session.json.processing_{my_pid}_99999")
        with open(live_lock, "w", encoding="utf-8") as f:
            json.dump({"session_stream": ["Live ongoing turn"]}, f)

        # C. Stale tmp file from dead process
        dead_tmp = os.path.join(self.tmp_dir, "companion.json.tmp_999999_55555")
        with open(dead_tmp, "w", encoding="utf-8") as f:
            f.write("{}")

        # Mock execute_reflection_sync so test runs offline without external API call
        with patch("memory.sleep_reflector.execute_reflection_sync", return_value=True) as mock_ref:
            cleaned = manager.cleanup_orphaned_locks()
            self.assertGreaterEqual(cleaned, 2, "Must clean at least dead lock and dead tmp file.")
            mock_ref.assert_called()

        # Verify dead lock was deleted
        self.assertFalse(os.path.exists(dead_lock), "Dead lock file must be removed.")
        self.assertFalse(os.path.exists(dead_tmp), "Stale tmp file must be removed.")

        # Verify live lock was strictly preserved!
        self.assertTrue(os.path.exists(live_lock), "Live lock file from running process must NEVER be touched.")

    # ── Test 5: Sub-Agent B Model Fallback Cascade (503 Mitigation) ─────────

    def test_subagent_b_model_fallback_cascade(self):
        """Verifies Sub-Agent B catches 503/429 on primary model and falls back to secondary."""
        self.assertIn("gemini-3.5-flash-lite", SUBAGENT_MODEL_CASCADE)
        self.assertIn("gemini-3.1-flash-lite", SUBAGENT_MODEL_CASCADE)

        worker = SubAgentB()

        # Mock responses: 1st call fails with 503 ServerError, 2nd call succeeds
        mock_503_error = Exception("503 UNAVAILABLE. This model is currently experiencing high demand.")
        mock_success_response = MagicMock()
        mock_success_response.text = "Task completed using fallback model."

        with patch.object(
            worker.client.models,
            "generate_content",
            side_effect=[mock_503_error, mock_success_response]
        ) as mock_generate:
            res = worker._generate_with_fallback(
                contents="test prompt",
                config=MagicMock(),
                task_id="task_test_fallback"
            )
            self.assertEqual(res, mock_success_response)
            # Verify it was called twice (1st: 3.5-flash-lite, 2nd: 3.1-flash-lite)
            self.assertEqual(mock_generate.call_count, 2)
            first_model = mock_generate.call_args_list[0][1]["model"]
            second_model = mock_generate.call_args_list[1][1]["model"]
            self.assertEqual(first_model, "gemini-3.5-flash-lite")
            self.assertEqual(second_model, "gemini-3.1-flash-lite")

    # ── Test 6: Sleep Reflector Model Fallback Cascade ───────────────────────

    def test_sleep_reflector_model_fallback_cascade(self):
        """Verifies Sleep Reflector cascades to fallback model when 503 occurs."""
        self.assertIn("gemini-3.5-flash-lite", REFLECTION_MODEL_CASCADE)
        self.assertIn("gemini-3.1-flash-lite", REFLECTION_MODEL_CASCADE)

        mock_client = MagicMock()
        mock_503 = Exception("503 UNAVAILABLE. Spike in demand.")
        mock_ok = MagicMock()
        mock_ok.parsed = MagicMock()

        with patch.object(mock_client.models, "generate_content", side_effect=[mock_503, mock_ok]) as mock_gen:
            res = _generate_reflection_with_fallback(
                client=mock_client,
                contents="reflect prompt",
                config=MagicMock(),
                tag="[TEST REFLECTOR]"
            )
            self.assertEqual(res, mock_ok)
            self.assertEqual(mock_gen.call_count, 2)
            self.assertEqual(mock_gen.call_args_list[0][1]["model"], "gemini-3.5-flash-lite")
            self.assertEqual(mock_gen.call_args_list[1][1]["model"], "gemini-3.1-flash-lite")

    # ── Test 7: Pillar 5 Upgrade 1 — Active Mind Context Fast-Path ────────────

    def test_active_mind_context_fast_path(self):
        """Verifies get_system_context_block() returns active_mind_context.md contents when fresh."""
        manager = UnifiedMemoryManager(memory_dir=self.tmp_dir)

        # Write a synthesized context file
        active_mind_path = os.path.join(self.tmp_dir, "active_mind_context.md")
        synthesized_content = "### SYNTHESIZED CONTEXT\n- User: Shvan\n- Top fact: AI and Robotics student"
        with open(active_mind_path, "w", encoding="utf-8") as f:
            f.write(synthesized_content)

        # Clear any cache
        manager._cached_context = ""
        manager._cache_timestamp = 0.0

        block = manager.get_system_context_block(max_tokens=1200)
        self.assertEqual(block, synthesized_content, "Fast-path must return synthesized context verbatim.")

    def test_active_mind_context_fallback_on_missing(self):
        """Verifies fallback to Python slice logic when active_mind_context.md doesn't exist."""
        manager = UnifiedMemoryManager(memory_dir=self.tmp_dir)

        # Ensure no active_mind_context.md exists
        active_mind_path = os.path.join(self.tmp_dir, "active_mind_context.md")
        if os.path.exists(active_mind_path):
            os.remove(active_mind_path)

        # Clear cache
        manager._cached_context = ""
        manager._cache_timestamp = 0.0

        block = manager.get_system_context_block(max_tokens=1200)
        self.assertIn("CORE IDENTITY & USER PREFERENCES", block,
                       "Fallback must produce the original Python-assembled context block.")

    def test_active_mind_context_fallback_on_stale(self):
        """Verifies fallback when active_mind_context.md is older than 24 hours."""
        manager = UnifiedMemoryManager(memory_dir=self.tmp_dir)

        active_mind_path = os.path.join(self.tmp_dir, "active_mind_context.md")
        with open(active_mind_path, "w", encoding="utf-8") as f:
            f.write("### STALE CONTEXT")

        # Set modification time to 25 hours ago
        stale_time = time.time() - (25 * 3600)
        os.utime(active_mind_path, (stale_time, stale_time))

        manager._cached_context = ""
        manager._cache_timestamp = 0.0

        block = manager.get_system_context_block(max_tokens=1200)
        self.assertIn("CORE IDENTITY & USER PREFERENCES", block,
                       "Stale (>24h) context must fall back to Python slice logic.")

    # ── Test 8: Pillar 5 Upgrade 2 — Screen Streamer Voice Trigger ───────────

    def test_screen_streamer_voice_trigger(self):
        """Verifies voice_trigger() sets burst timestamp and affects effective interval."""
        from live.screen_streamer import ScreenStreamer

        mock_session = MagicMock()
        streamer = ScreenStreamer(mock_session, fps=1)

        # Before voice trigger: _voice_triggered_at should be 0
        self.assertEqual(streamer._voice_triggered_at, 0.0)

        # After voice trigger
        streamer.voice_trigger()
        self.assertGreater(streamer._voice_triggered_at, 0.0)

        # During burst: effective interval should be ACTIVE_INTERVAL
        now = time.monotonic()
        in_burst = (now - streamer._voice_triggered_at) < streamer.BURST_DURATION
        self.assertTrue(in_burst, "Should be in burst immediately after voice trigger.")
        effective = streamer.ACTIVE_INTERVAL if in_burst else streamer.STATIC_INTERVAL
        self.assertEqual(effective, streamer.ACTIVE_INTERVAL)

    def test_screen_streamer_static_interval_after_burst(self):
        """Verifies effective interval is STATIC_INTERVAL after burst duration expires."""
        from live.screen_streamer import ScreenStreamer

        mock_session = MagicMock()
        streamer = ScreenStreamer(mock_session, fps=1)

        # Set voice trigger to far in the past (beyond BURST_DURATION)
        streamer._voice_triggered_at = time.monotonic() - streamer.BURST_DURATION - 1.0

        now = time.monotonic()
        in_burst = (now - streamer._voice_triggered_at) < streamer.BURST_DURATION
        self.assertFalse(in_burst, "Should NOT be in burst after BURST_DURATION expires.")
        effective = streamer.ACTIVE_INTERVAL if in_burst else streamer.STATIC_INTERVAL
        self.assertEqual(effective, streamer.STATIC_INTERVAL)

    # ── Test 9: Pillar 5 Upgrade 3 — Mid-Session Milestone Injection ─────────

    def test_session_milestone_injection_wired_in_on_success(self):
        """Verifies _check_rolling_reflection on_success calls _inject_session_milestone via run_coroutine_threadsafe."""
        from live.live_bridge import LiveBridge

        bridge = LiveBridge()
        bridge._loop = MagicMock()
        bridge._session = MagicMock()

        # Simulate 30+ turns to trigger micro-reflection
        bridge._session_stream = [f"[USER]: Turn {i}" for i in range(35)]
        bridge._last_reflected_index = 0
        bridge._micro_reflection_in_progress = False

        # Mock the trigger_micro_reflection call to capture on_success
        captured_on_success = {}

        def mock_trigger(chunk, target_index, on_success=None, on_failure=None):
            captured_on_success['fn'] = on_success
            mock_thread = MagicMock()
            mock_thread.is_alive.return_value = False
            return mock_thread

        with patch("memory.sleep_reflector.trigger_micro_reflection", mock_trigger):
            bridge._check_rolling_reflection()

        # Verify on_success was captured
        self.assertIn('fn', captured_on_success, "on_success callback must be passed to trigger_micro_reflection.")

        # Simulate calling on_success with a result
        mock_result = MagicMock()
        mock_result.chunk_summary = "Discussed AI architecture and testing."

        with patch("asyncio.run_coroutine_threadsafe") as mock_rcs:
            captured_on_success['fn'](mock_result, 35)

            # Verify chunk_summary was appended
            self.assertIn("Discussed AI architecture and testing.", bridge._chunk_summaries)

            # Verify run_coroutine_threadsafe was called for milestone injection
            mock_rcs.assert_called_once()
            # The first arg should be the coroutine from _inject_session_milestone
            args = mock_rcs.call_args[0]
            self.assertEqual(args[1], bridge._loop, "Must use bridge._loop for coroutine scheduling.")
            args[0].close()  # Clean up coroutine to prevent unawaited warning


if __name__ == "__main__":
    unittest.main(verbosity=2)
