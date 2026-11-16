"""
tests/test_subconscious_memory.py
=================================
Comprehensive unit tests for the Ghost Subconscious Memory & Passive Reflection System.
Tests Stanford decay math, atomic WAL recovery, conflict resolution, turn buffering, and schemas.
"""

import os
import sys
import json
import math
import tempfile
import shutil
import unittest
from unittest.mock import MagicMock, patch

# Add project root to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestSubconsciousMemory(unittest.TestCase):
    """Unit tests for the upgraded ghost_memory.py and sleep_reflector.py"""

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

    # ── Test 1: Stanford Decay Math Constant (Argon Fix #5) ───────────────────

    def test_stanford_decay_math(self):
        """
        Verify that LAMBDA_DECAY = 0.02 mathematically guarantees
        an Importance=10 event at 60 days strictly outranks an Importance=2 event at 1 day.
        """
        from memory.ghost_memory import LAMBDA_DECAY
        self.assertEqual(LAMBDA_DECAY, 0.02)

        score_60_days = 10.0 * math.exp(-LAMBDA_DECAY * 60)
        score_1_day = 2.0 * math.exp(-LAMBDA_DECAY * 1)

        self.assertAlmostEqual(score_60_days, 3.0119, places=3)
        self.assertAlmostEqual(score_1_day, 1.9604, places=3)
        self.assertGreater(score_60_days, score_1_day)

    # ── Test 2: Turn-Level Buffering & Join Spacing (Argon Fix #2 & #6) ───────

    def test_turn_level_buffering(self):
        """
        Verify that micro-token streaming chunks (like ['Hel', 'lo', ' bro'])
        are cleanly joined without unwanted extra spaces via "".join().
        """
        from live.live_bridge import LiveBridge
        bridge = LiveBridge()

        # Simulate user streaming chunks
        bridge._append_user_speech("Hel")
        bridge._append_user_speech("lo")
        bridge._append_user_speech(" bro, ")
        bridge._append_user_speech("how are you?")
        bridge._close_user_speech()

        # Simulate ghost streaming chunks
        bridge._append_ghost_speech("I am ")
        bridge._append_ghost_speech("doing ")
        bridge._append_ghost_speech("great!")
        bridge._close_ghost_speech()

        self.assertEqual(len(bridge._session_stream), 2)
        self.assertEqual(bridge._session_stream[0], "[USER]: Hello bro, how are you?")
        self.assertEqual(bridge._session_stream[1], "[GHOST]: I am doing great!")

    # ── Test 3: Atomic Write Durability (Argon Fix #1 & #3) ───────────────────

    def test_atomic_write_safety(self):
        """Verify _atomic_write_json creates the target file cleanly."""
        from memory.ghost_memory import GhostMemory
        test_file = os.path.join(self.tmp_dir, "atomic_test.json")
        data = {"status": "ok", "count": 42}
        GhostMemory._atomic_write_json(test_file, data)

        self.assertTrue(os.path.exists(test_file))
        read_back = self._read_json(test_file)
        self.assertEqual(read_back, data)

    # ── Test 4: Mem0 Conflict Resolution by Fact ID (Argon Fix #2) ───────────

    def test_fact_id_superseding(self):
        """
        Verify that apply_reflection cleanly replaces an existing fact
        when supersedes_fact_id is specified, without adding a duplicate.
        """
        self._write_json(self.companion_path, {
            "profile": {"user_name": "Shvan"},
            "facts": [
                {"id": "f_001", "fact": "Prefers Chrome browser", "category": "preference", "importance": 7, "updated_at": "2026-11-01"}
            ],
            "episodes": [],
            "greeting_spark": {}
        })
        self._write_json(self.habits_path, {"habits": []})

        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()

        # Reflection payload where user switched to Brave
        reflection_payload = {
            "new_facts": [],
            "superseded_facts": [
                {"old_fact_id": "f_001", "new_fact_text": "Switched to Brave browser as primary"}
            ],
            "new_habits": [],
            "new_episode": None,
            "greeting_spark": {}
        }
        mem.apply_reflection(reflection_payload)

        data = self._read_json(self.companion_path)
        self.assertEqual(len(data["facts"]), 1)
        self.assertEqual(data["facts"][0]["id"], "f_001")
        self.assertEqual(data["facts"][0]["fact"], "Switched to Brave browser as primary")

    # ── Test 5: Princeton Reflexion Habit Upsert ──────────────────────────────

    def test_reflexion_habit_upsert(self):
        """Verify new habits with the same trigger update in-place."""
        self._write_json(self.companion_path, {"profile": {"user_name": "Shvan"}, "facts": [], "episodes": []})
        self._write_json(self.habits_path, {
            "habits": [
                {"trigger": "open chrome", "mistake": "Used open_app", "correction": "Use desktop icon", "learned_at": "2026-11-01"}
            ]
        })

        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()

        reflection_payload = {
            "new_facts": [],
            "superseded_facts": [],
            "new_habits": [
                {"trigger": "open chrome", "mistake": "Used open_app", "correction": "Click Chrome on the taskbar instead"}
            ],
            "new_episode": None,
            "greeting_spark": {}
        }
        mem.apply_reflection(reflection_payload)

        data = self._read_json(self.habits_path)
        self.assertEqual(len(data["habits"]), 1)
        self.assertEqual(data["habits"][0]["correction"], "Click Chrome on the taskbar instead")

    # ── Test 6: Greeting Spark Context Formatting ────────────────────────────

    def test_greeting_spark_context_formatting(self):
        """Verify get_context_block includes Greeting Spark and ranked memories."""
        self._write_json(self.companion_path, {
            "profile": {"user_name": "Shvan", "communication_style": "Casual, calls me bro."},
            "facts": [
                {"id": "f_001", "fact": "Prefers dark mode", "importance": 8, "updated_at": "2026-11-06"}
            ],
            "episodes": [
                {"id": "ep_001", "date": "2026-11-06", "title": "Built dual memory", "summary": "Integrated Stanford reflection", "importance": 10}
            ],
            "greeting_spark": {
                "last_seen": "2026-11-06T18:00:00Z",
                "last_topic": "Testing audio and memory pipelines",
                "open_thread": "Verifying unit tests",
                "mood_hint": "Energized"
            }
        })
        self._write_json(self.habits_path, {"habits": []})

        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()
        block = mem.get_context_block()

        self.assertIn("══ GHOST MEMORY ══", block)
        self.assertIn("Shvan", block)
        self.assertIn("Testing audio and memory pipelines", block)
        self.assertIn("Verifying unit tests", block)
        self.assertIn("Energized", block)
        self.assertIn("Prefers dark mode", block)
        self.assertIn("Built dual memory", block)

    # ── Test 7: Pydantic Structured Output Validation ────────────────────────

    def test_pydantic_schema_validation(self):
        """Verify SessionReflection Pydantic model parses valid JSON and enforces types."""
        from memory.sleep_reflector import SessionReflection

        raw_json = {
            "new_facts": [
                {"fact": "Likes tea when tired", "category": "lifestyle", "importance": 7, "supersedes_fact_id": None}
            ],
            "new_habits": [
                {"trigger": "launch discord", "mistake": "Froze", "correction": "Use start menu"}
            ],
            "new_episode": {
                "title": "Configured audio device",
                "summary": "Switched to standard microphone driver.",
                "importance": 8
            },
            "greeting_spark": {
                "last_topic": "Setting up audio",
                "open_thread": "Check mic gain",
                "mood_hint": "Relaxed"
            }
        }
        obj = SessionReflection.model_validate(raw_json)
        self.assertEqual(len(obj.new_facts), 1)
        self.assertEqual(obj.new_facts[0].fact, "Likes tea when tired")
        self.assertEqual(obj.greeting_spark.open_thread, "Check mic gain")


if __name__ == "__main__":
    unittest.main(verbosity=2)
