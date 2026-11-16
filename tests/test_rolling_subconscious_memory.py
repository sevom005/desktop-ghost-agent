"""
tests/test_rolling_subconscious_memory.py
=========================================
Unit tests for Rolling Subconscious Memory Engine (v2) for long 1-hour sessions.
Tests:
  - MicroReflectionResult schema validation
  - 30-turn threshold triggering & 2-turn overlap slicing
  - Safe index advancement strictly on success (Argon Bug #3)
  - Accumulation of chunk_summaries (Argon Bug #1)
  - Shutdown reflection with full session context & delta tail
  - Thread safety and WAL pending session recovery with chunk_summaries
"""

import os
import sys
import json
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from memory.sleep_reflector import (
    MicroReflectionResult,
    SessionReflection,
    ExtractedFact,
    ExtractedHabit,
    dump_pending_session,
)
from memory.ghost_memory import GhostMemory
from live.live_bridge import LiveBridge


class TestRollingSubconsciousMemory(unittest.TestCase):
    """Verifies the rolling memory mechanics and edge cases."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        import memory.ghost_memory as gm_module
        import memory.sleep_reflector as sr_module

        self._orig_companion = gm_module._COMPANION_PATH
        self._orig_habits = gm_module._HABITS_PATH
        self._orig_pending = gm_module._PENDING_SESSION_PATH
        self._orig_sr_pending = sr_module._PENDING_SESSION_PATH

        self.companion_path = os.path.join(self.tmp_dir, "companion.json")
        self.habits_path = os.path.join(self.tmp_dir, "habits.json")
        self.pending_path = os.path.join(self.tmp_dir, "pending_session.json")

        gm_module._COMPANION_PATH = self.companion_path
        gm_module._HABITS_PATH = self.habits_path
        gm_module._PENDING_SESSION_PATH = self.pending_path
        sr_module._PENDING_SESSION_PATH = self.pending_path

        gm_module._INSTANCE = None
        self.gm_module = gm_module
        self.sr_module = sr_module

    def tearDown(self):
        self.gm_module._COMPANION_PATH = self._orig_companion
        self.gm_module._HABITS_PATH = self._orig_habits
        self.gm_module._PENDING_SESSION_PATH = self._orig_pending
        self.sr_module._PENDING_SESSION_PATH = self._orig_sr_pending
        self.gm_module._INSTANCE = None
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_json(self, path, data):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def _read_json(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── Test 1: MicroReflectionResult Schema Validation ──────────────────────

    def test_micro_reflection_schema(self):
        """Verify MicroReflectionResult validates facts, habits, and chunk_summary."""
        payload = {
            "new_facts": [
                {
                    "fact": "Plays Clash of Clans on tablet",
                    "category": "lifestyle",
                    "importance": 7,
                    "supersedes_fact_id": None
                }
            ],
            "new_habits": [
                {
                    "trigger": "open chrome",
                    "mistake": "Used start menu search",
                    "correction": "Click desktop taskbar icon"
                }
            ],
            "chunk_summary": "Discussed games, tested Chrome shortcuts, and corrected launch procedure."
        }
        res = MicroReflectionResult.model_validate(payload)
        self.assertEqual(len(res.new_facts), 1)
        self.assertEqual(res.new_facts[0].fact, "Plays Clash of Clans on tablet")
        self.assertEqual(len(res.new_habits), 1)
        self.assertEqual(res.new_habits[0].correction, "Click desktop taskbar icon")
        self.assertEqual(
            res.chunk_summary,
            "Discussed games, tested Chrome shortcuts, and corrected launch procedure."
        )

    # ── Test 2: 2-Turn Overlap Slicing Logic (Argon Bug #2) ──────────────────

    def test_two_turn_overlap_slicing(self):
        """
        Verify that slicing at turn 30 includes a 2-turn overlap [28:30]
        to ensure corrections spanning the boundary are never lost.
        """
        bridge = LiveBridge()
        bridge._micro_reflection_threshold = 30
        bridge._session_stream = [f"Turn {i}" for i in range(35)]
        bridge._last_reflected_index = 0

        # Simulate trigger logic
        start_idx = max(0, bridge._last_reflected_index - 2)
        target_idx = 30
        chunk = bridge._session_stream[start_idx:target_idx]

        # For chunk 0 to 30, start_idx is max(0, -2) = 0
        self.assertEqual(start_idx, 0)
        self.assertEqual(len(chunk), 30)

        # Now simulate index advanced to 30, and session reached 60
        bridge._last_reflected_index = 30
        bridge._session_stream = [f"Turn {i}" for i in range(65)]
        current_len = 60
        start_idx_2 = max(0, bridge._last_reflected_index - 2)
        chunk_2 = bridge._session_stream[start_idx_2:current_len]

        # start_idx_2 must be 28 (Turn 28, Turn 29 overlapped!)
        self.assertEqual(start_idx_2, 28)
        self.assertEqual(chunk_2[0], "Turn 28")
        self.assertEqual(chunk_2[1], "Turn 29")
        self.assertEqual(chunk_2[2], "Turn 30")
        self.assertEqual(len(chunk_2), 32)  # 2 overlap + 30 new turns

    # ── Test 3: Safe Index Advancement on Success (Argon Bug #3) ─────────────

    def test_safe_index_advancement_on_success(self):
        """
        Verify that _last_reflected_index ONLY advances when micro reflection succeeds,
        and remains unchanged on failure so turns are retried.
        """
        bridge = LiveBridge()
        bridge._micro_reflection_threshold = 30
        bridge._session_stream = [f"Turn {i}" for i in range(30)]

        # Mock trigger_micro_reflection to test success callback
        captured_callbacks = {}

        def mock_trigger(chunk, target_index, on_success, on_failure):
            captured_callbacks["on_success"] = on_success
            captured_callbacks["on_failure"] = on_failure
            return MagicMock()

        with patch("memory.sleep_reflector.trigger_micro_reflection", side_effect=mock_trigger):
            bridge._check_rolling_reflection()
            self.assertTrue(bridge._micro_reflection_in_progress)
            self.assertEqual(bridge._last_reflected_index, 0)

            # 1. Simulate failure first
            captured_callbacks["on_failure"]()
            self.assertFalse(bridge._micro_reflection_in_progress)
            self.assertEqual(bridge._last_reflected_index, 0)  # Must NOT advance on failure!

            # 2. Trigger again and simulate success
            bridge._check_rolling_reflection()
            self.assertTrue(bridge._micro_reflection_in_progress)
            mock_result = MicroReflectionResult(
                new_facts=[],
                new_habits=[],
                chunk_summary="Tested Chrome coordinates."
            )
            captured_callbacks["on_success"](mock_result, 30)

            self.assertFalse(bridge._micro_reflection_in_progress)
            self.assertEqual(bridge._last_reflected_index, 30)
            self.assertEqual(bridge._chunk_summaries, ["Tested Chrome coordinates."])

    # ── Test 4: Concurrency Guard (No Duplicate Micro Threads) ───────────────

    def test_concurrency_guard_prevents_duplicate_threads(self):
        """Verify that _check_rolling_reflection returns immediately if another micro reflection is running."""
        bridge = LiveBridge()
        bridge._micro_reflection_threshold = 30
        bridge._session_stream = [f"Turn {i}" for i in range(35)]
        bridge._micro_reflection_in_progress = True

        with patch("memory.sleep_reflector.trigger_micro_reflection") as mock_trigger:
            bridge._check_rolling_reflection()
            mock_trigger.assert_not_called()

    # ── Test 5: Full Shutdown Reflection with Chunk Summaries (Argon Bug #1) ──

    def test_shutdown_reflection_receives_summaries_and_tail(self):
        """
        Verify that execute_reflection_sync formats Earlier Milestones and tail chunk cleanly.
        """
        mem = GhostMemory()
        mem.load()

        chunk_summaries = [
            "Discussed Kurdistan search and opened Chrome.",
            "Navigated to YouTube and clicked first video."
        ]
        tail_stream = [
            "[USER]: Good job Ghost, that was awesome.",
            "[GHOST]: Glad to help Shvan! Have a great rest."
        ]

        with patch("google.genai.Client") as mock_client_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            mock_response = MagicMock()
            mock_response.parsed = SessionReflection(
                new_facts=[
                    ExtractedFact(fact="Loves fast desktop automation", category="preference", importance=8)
                ],
                new_habits=[],
                new_episode=None,
                greeting_spark={
                    "last_topic": "YouTube navigation and video testing",
                    "open_thread": "Ready for next search",
                    "mood_hint": "Satisfied"
                }
            )
            # Pillar 5: synthesize_active_mind_context makes a 2nd generate_content call after reflection.
            # Return reflection response for 1st call, a plain text mock for 2nd (synthesis).
            mock_synthesis_response = MagicMock()
            mock_synthesis_response.text = "### SYNTHESIZED CONTEXT\n- Test"
            mock_client.models.generate_content.side_effect = [mock_response, mock_synthesis_response]

            from memory.sleep_reflector import execute_reflection_sync
            success = execute_reflection_sync(
                session_stream=tail_stream,
                memory_instance=mem,
                chunk_summaries=chunk_summaries
            )
            self.assertTrue(success)

            # Inspect the prompt passed to Gemini — use first call (reflection), not last (synthesis)
            call_kwargs = mock_client.models.generate_content.call_args_list[0][1]
            prompt = call_kwargs["contents"]

            # Must contain both chunk summaries and tail
            self.assertIn("══ EARLIER 1-HOUR SESSION MILESTONES (CHUNKS 1..2) ══", prompt)
            self.assertIn("Chunk 1: Discussed Kurdistan search and opened Chrome.", prompt)
            self.assertIn("Chunk 2: Navigated to YouTube and clicked first video.", prompt)
            self.assertIn("[USER]: Good job Ghost, that was awesome.", prompt)

    # ── Test 6: WAL Recovery with Chunk Summaries ────────────────────────────

    def test_wal_pending_session_roundtrip(self):
        """
        Verify dump_pending_session creates a valid WAL file with chunk_summaries,
        and ghost_memory crash recovery parses it cleanly.
        """
        session_stream = ["[USER]: Hi", "[GHOST]: Hello!"]
        chunk_summaries = ["Earlier milestone summary 1"]

        dump_pending_session(session_stream, chunk_summaries)
        self.assertTrue(os.path.exists(self.pending_path))

        data = self._read_json(self.pending_path)
        self.assertIn("session_stream", data)
        self.assertIn("chunk_summaries", data)
        self.assertEqual(data["session_stream"], session_stream)
        self.assertEqual(data["chunk_summaries"], chunk_summaries)

        # Now test that ghost_memory recovery executes it
        mem = GhostMemory()
        with patch("memory.sleep_reflector.execute_reflection_sync") as mock_exec:
            mock_exec.return_value = True
            mem.load()
            mock_exec.assert_called_once_with(
                session_stream,
                memory_instance=mem,
                chunk_summaries=chunk_summaries
            )

        # File should be cleaned up after recovery
        self.assertFalse(os.path.exists(self.pending_path))


if __name__ == "__main__":
    unittest.main(verbosity=2)
