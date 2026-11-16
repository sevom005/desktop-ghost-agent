"""
tests/test_dual_memory.py
=========================
Unit tests for the Ghost Dual-Memory System.
Run with: python -m pytest tests/test_dual_memory.py -v
"""

import os
import sys
import json
import datetime
import tempfile
import shutil
import unittest

# Add project root to path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestGhostMemory(unittest.TestCase):
    """Unit tests for memory/ghost_memory.py"""

    def setUp(self):
        """Create a temporary memory directory and patch paths before each test."""
        self.tmp_dir = tempfile.mkdtemp()
        # Patch the module paths to use temp directory
        import memory.ghost_memory as gm_module
        self._orig_companion = gm_module._COMPANION_PATH
        self._orig_habits = gm_module._HABITS_PATH
        gm_module._COMPANION_PATH = os.path.join(self.tmp_dir, "companion.json")
        gm_module._HABITS_PATH = os.path.join(self.tmp_dir, "habits.json")
        # Reset singleton for each test
        gm_module._INSTANCE = None
        self.gm_module = gm_module

    def tearDown(self):
        """Restore original paths and clean up temp dir."""
        self.gm_module._COMPANION_PATH = self._orig_companion
        self.gm_module._HABITS_PATH = self._orig_habits
        self.gm_module._INSTANCE = None
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def _write_companion(self, data: dict):
        path = os.path.join(self.tmp_dir, "companion.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _write_habits(self, data: dict):
        path = os.path.join(self.tmp_dir, "habits.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _read_companion(self) -> dict:
        path = os.path.join(self.tmp_dir, "companion.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _read_habits(self) -> dict:
        path = os.path.join(self.tmp_dir, "habits.json")
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    # ── Test 1: Load defaults when files are missing ─────────────────────────

    def test_load_defaults_if_missing(self):
        """Missing JSON files must fall back to defaults gracefully."""
        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()  # No files exist in temp dir
        self.assertEqual(mem._companion["user_name"], "Shvan")
        self.assertIsInstance(mem._habits, list)
        self.assertEqual(len(mem._habits), 0)

    # ── Test 2: Load from existing companion file ────────────────────────────

    def test_load_existing_companion(self):
        """Correctly reads facts, milestones, and style from companion.json."""
        self._write_companion({
            "user_name": "Shvan",
            "facts": ["Likes dark mode", "Uses Windows 11"],
            "milestones": ["First 20-min session"],
            "communication_style": "Casual.",
            "last_seen": None
        })
        self._write_habits({"habits": []})
        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()
        self.assertEqual(mem._companion["user_name"], "Shvan")
        fact_texts = [f["fact"] if isinstance(f, dict) else f for f in mem._companion["facts"]]
        self.assertIn("Likes dark mode", fact_texts)

    # ── Test 3: add_fact deduplication ───────────────────────────────────────

    def test_add_fact_deduplication(self):
        """Adding the same fact twice must not create a duplicate."""
        self._write_companion({"user_name": "Shvan", "facts": [], "milestones": [], "communication_style": "", "last_seen": None})
        self._write_habits({"habits": []})
        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()
        mem.add_fact("Likes dark mode")
        mem.add_fact("Likes dark mode")  # duplicate
        mem.add_fact("LIKES DARK MODE")  # case-insensitive duplicate
        self.assertEqual(len(mem._companion["facts"]), 1)
        fact_item = mem._companion["facts"][0]
        self.assertEqual(fact_item["fact"] if isinstance(fact_item, dict) else fact_item, "Likes dark mode")

    # ── Test 4: remove_fact ───────────────────────────────────────────────────

    def test_remove_fact(self):
        """remove_fact should remove any fact containing the keyword (case-insensitive)."""
        self._write_companion({
            "user_name": "Shvan",
            "facts": ["Likes dark mode", "Prefers Puck voice", "Uses Windows 11"],
            "milestones": [],
            "communication_style": "",
            "last_seen": None
        })
        self._write_habits({"habits": []})
        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()
        removed = mem.remove_fact("dark mode")
        self.assertTrue(removed)
        self.assertEqual(len(mem._companion["facts"]), 2)
        self.assertNotIn("Likes dark mode", mem._companion["facts"])

    # ── Test 5: add_habit upsert ─────────────────────────────────────────────

    def test_add_habit_upsert(self):
        """Adding a habit with the same trigger updates in place, not duplicates."""
        self._write_companion({"user_name": "Shvan", "facts": [], "milestones": [], "communication_style": "", "last_seen": None})
        self._write_habits({"habits": []})
        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()
        mem.add_habit("open chrome", "Used open_app", "Double-click desktop shortcut")
        mem.add_habit("open chrome", "Used open_app", "Use the taskbar shortcut instead")  # update
        self.assertEqual(len(mem._habits), 1)
        self.assertEqual(mem._habits[0]["correction"], "Use the taskbar shortcut instead")

    # ── Test 6: get_context_block formatting ─────────────────────────────────

    def test_context_block_formatting(self):
        """Context block must contain expected headers and content."""
        self._write_companion({
            "user_name": "Shvan",
            "facts": ["Likes dark mode"],
            "milestones": ["First 20-min session"],
            "communication_style": "Casual.",
            "last_seen": None
        })
        self._write_habits({"habits": [
            {"trigger": "open chrome", "mistake": "Used open_app", "correction": "Double-click desktop"}
        ]})
        from memory.ghost_memory import GhostMemory
        mem = GhostMemory()
        mem.load()
        block = mem.get_context_block()
        self.assertIn("GHOST MEMORY", block)
        self.assertIn("Shvan", block)
        self.assertIn("Likes dark mode", block)
        self.assertIn("First 20-min session", block)
        self.assertIn("open chrome", block)
        self.assertIn("Double-click desktop", block)

    # ── Test 7: dispatch_tool remember_fact ──────────────────────────────────

    def test_dispatch_remember_fact_add(self):
        """dispatch_tool('remember_fact', ...) saves a fact and returns 'Remembered.'"""
        self._write_companion({"user_name": "Shvan", "facts": [], "milestones": [], "communication_style": "", "last_seen": None})
        self._write_habits({"habits": []})
        from memory.ghost_memory import get_ghost_memory
        get_ghost_memory().load()

        from live.tool_registry import dispatch_tool
        result = dispatch_tool("remember_fact", {"fact": "Prefers dark mode", "category": "fact", "action": "add"})
        self.assertEqual(result, "Remembered.")
        data = self._read_companion()
        fact_texts = [f["fact"] if isinstance(f, dict) else f for f in data["facts"]]
        self.assertIn("Prefers dark mode", fact_texts)

    # ── Test 8: dispatch_tool learn_habit ────────────────────────────────────

    def test_dispatch_learn_habit(self):
        """dispatch_tool('learn_habit', ...) saves a habit and returns 'Habit learned.'"""
        self._write_companion({"user_name": "Shvan", "facts": [], "milestones": [], "communication_style": "", "last_seen": None})
        self._write_habits({"habits": []})
        from memory.ghost_memory import get_ghost_memory
        get_ghost_memory().load()

        from live.tool_registry import dispatch_tool
        result = dispatch_tool("learn_habit", {
            "trigger": "open chrome",
            "mistake": "Used open_app — opens profile selector",
            "correction": "Double-click Chrome on desktop"
        })
        self.assertEqual(result, "Habit learned.")
        data = self._read_habits()
        self.assertEqual(len(data["habits"]), 1)
        self.assertEqual(data["habits"][0]["trigger"], "open chrome")


if __name__ == "__main__":
    unittest.main(verbosity=2)
