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
    _generate_reflection_with_fallback
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


if __name__ == "__main__":
    unittest.main(verbosity=2)
