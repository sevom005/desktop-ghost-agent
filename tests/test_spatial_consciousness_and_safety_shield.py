"""
Unit and Integration Tests for Pillar 3:
1. Active Spatial Consciousness & Breadcrumb Parsing (VS Code, Notepad++, Notepad)
2. Workspace File Resolution
3. Editor Anti-Wipe Safety Shield (Ctrl+A + Backspace interlock)
4. Sub-Agent B Pre-Edit Atomic Backup Snapshots
5. Tool Registry get_active_window_context Dispatching
"""

import os
import time
import shutil
import unittest
from unittest.mock import patch, MagicMock

from skills import win32_window_utils
from actuator import SafetyShield, SafetyInterlockException
from workers import subagent_b
from live.tool_registry import dispatch_tool


class TestSpatialConsciousnessAndSafetyShield(unittest.TestCase):
    def setUp(self):
        self.workspace_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    # ── 1. VS Code Breadcrumb Parsing ──────────────────────────────────────────

    def test_vscode_breadcrumb_parsing_clean(self):
        """Verify parsing of clean VS Code window title."""
        title = "main.py - Computer_Use - Visual Studio Code"
        ctx = win32_window_utils.parse_window_breadcrumbs(title, "code.exe", self.workspace_root)
        self.assertEqual(ctx.app_name, "code.exe")
        self.assertTrue(ctx.is_editor)
        self.assertFalse(ctx.is_dirty)
        self.assertEqual(ctx.file_name, "main.py")
        self.assertEqual(ctx.workspace_name, "Computer_Use")
        self.assertIsNotNone(ctx.file_path)
        self.assertTrue(ctx.file_path.endswith("main.py"))
        self.assertTrue(ctx.confidence >= 0.90)

    def test_vscode_breadcrumb_parsing_dirty_and_admin(self):
        """Verify parsing of dirty (●) buffer and [Administrator] tag."""
        title = "● train_rnn.py - Project %100 - Visual Studio Code [Administrator]"
        ctx = win32_window_utils.parse_window_breadcrumbs(title, "code.exe", self.workspace_root)
        self.assertEqual(ctx.app_name, "code.exe")
        self.assertTrue(ctx.is_editor)
        self.assertTrue(ctx.is_dirty)
        self.assertEqual(ctx.file_name, "train_rnn.py")
        self.assertEqual(ctx.workspace_name, "Project %100")

    def test_vscode_folder_only_view(self):
        """Verify parsing when VS Code has a folder open without an active file."""
        title = "Computer_Use - Visual Studio Code"
        ctx = win32_window_utils.parse_window_breadcrumbs(title, "code.exe", self.workspace_root)
        self.assertEqual(ctx.app_name, "code.exe")
        self.assertTrue(ctx.is_editor)
        self.assertIsNone(ctx.file_name)
        self.assertEqual(ctx.workspace_name, "Computer_Use")

    # ── 2. Notepad++ Breadcrumb Parsing ────────────────────────────────────────

    def test_notepad_plus_plus_absolute_path_and_dirty(self):
        """Verify parsing of Notepad++ full path and dirty marker (*)."""
        title = r"*C:\Users\Administrator\Desktop\Project %100\Computer_Use\model.py - Notepad++"
        ctx = win32_window_utils.parse_window_breadcrumbs(title, "notepad++.exe", self.workspace_root)
        self.assertEqual(ctx.app_name, "notepad++.exe")
        self.assertTrue(ctx.is_editor)
        self.assertTrue(ctx.is_dirty)
        self.assertEqual(ctx.file_name, "model.py")
        self.assertEqual(ctx.file_path, r"C:\Users\Administrator\Desktop\Project %100\Computer_Use\model.py")
        self.assertEqual(ctx.confidence, 1.0)

    def test_notepad_plus_plus_scratch_buffer(self):
        """Verify parsing of Notepad++ scratch buffers (new 1)."""
        title = "new 1 - Notepad++"
        ctx = win32_window_utils.parse_window_breadcrumbs(title, "notepad++.exe", self.workspace_root)
        self.assertEqual(ctx.app_name, "notepad++.exe")
        self.assertTrue(ctx.is_editor)
        self.assertFalse(ctx.is_dirty)
        self.assertEqual(ctx.file_name, "new 1")
        self.assertTrue(ctx.confidence >= 0.80)

    # ── 3. Windows Notepad Breadcrumb Parsing ──────────────────────────────────

    def test_notepad_breadcrumb_parsing(self):
        """Verify parsing of Windows Notepad files."""
        title = "*quick_notes.txt - Notepad"
        ctx = win32_window_utils.parse_window_breadcrumbs(title, "notepad.exe", self.workspace_root)
        self.assertEqual(ctx.app_name, "notepad.exe")
        self.assertTrue(ctx.is_editor)
        self.assertTrue(ctx.is_dirty)
        self.assertEqual(ctx.file_name, "quick_notes.txt")

    # ── 4. Workspace File Resolution ───────────────────────────────────────────

    def test_workspace_file_resolution_existing_file(self):
        """Verify resolving an existing file in workspace tree yields absolute path."""
        # 'actuator.py' exists in the workspace root
        ctx = win32_window_utils.parse_window_breadcrumbs("actuator.py - Computer_Use - Visual Studio Code", "code.exe", self.workspace_root)
        self.assertIsNotNone(ctx.file_path)
        self.assertTrue(os.path.isfile(ctx.file_path))
        self.assertEqual(os.path.basename(ctx.file_path).lower(), "actuator.py")
        self.assertEqual(ctx.confidence, 0.98)

    # ── 5. Editor Anti-Wipe Safety Shield ──────────────────────────────────────

    def test_anti_wipe_shield_blocks_ctrl_a_backspace_on_editor(self):
        """Verify that Ctrl+A followed by Backspace on an editor raises SafetyInterlockException."""
        shield = SafetyShield()
        shield._interlock_timeout = 3.0

        with patch("skills.win32_window_utils.is_editor_window", return_value=True), \
             patch("ctypes.windll.user32.GetForegroundWindow", return_value=9999):

            # 1. Execute Ctrl+A on editor window
            shield.check_hotkey(["ctrl", "a"])
            self.assertTrue(shield._last_select_all_time > 0.0)

            # 2. Immediate Backspace must trigger hard interlock!
            with self.assertRaises(SafetyInterlockException) as cm:
                shield.check_key("backspace")

            self.assertIn("SAFETY_INTERLOCK", str(cm.exception))
            self.assertIn("Ctrl+A + Backspace", str(cm.exception))

    def test_anti_wipe_shield_allows_normal_backspace(self):
        """Verify that normal Backspace without preceding Ctrl+A is allowed."""
        shield = SafetyShield()
        with patch("skills.win32_window_utils.is_editor_window", return_value=True):
            # Backspace without Ctrl+A should not raise
            try:
                shield.check_key("backspace")
            except SafetyInterlockException:
                self.fail("check_key raised SafetyInterlockException on normal backspace!")

    def test_anti_wipe_shield_allows_backspace_after_timeout(self):
        """Verify that Backspace after timeout (>3.0s) is not blocked."""
        shield = SafetyShield()
        shield._interlock_timeout = 0.1  # Short timeout for testing

        with patch("skills.win32_window_utils.is_editor_window", return_value=True), \
             patch("ctypes.windll.user32.GetForegroundWindow", return_value=9999):

            shield.check_hotkey(["ctrl", "a"])
            time.sleep(0.15)  # Wait for timeout to expire

            # Should not raise after timeout
            try:
                shield.check_key("backspace")
            except SafetyInterlockException:
                self.fail("check_key raised SafetyInterlockException after timeout!")

    # ── 6. Sub-Agent B Pre-Edit Atomic Backup Snapshot ─────────────────────────

    def test_subagent_b_atomic_backup_snapshot(self):
        """Verify that modifying an existing file creates a .bak snapshot in .backups/."""
        test_filename = "test_shield_snapshot.py"
        test_path = subagent_b.resolve_workspace_path(test_filename)
        backup_dir = os.path.join(subagent_b._WORKER_WORKSPACE_DIR, ".backups")

        try:
            # 1. Write initial version
            subagent_b.write_file(test_filename, "# Version 1 - Initial Code\ndef foo(): pass\n")
            self.assertTrue(os.path.exists(test_path))

            # 2. Overwrite with Version 2 (triggers pre-edit backup)
            subagent_b.write_file(test_filename, "# Version 2 - Overwritten Code\ndef bar(): pass\n")

            # 3. Verify backup file was created
            self.assertTrue(os.path.isdir(backup_dir))
            backups = [f for f in os.listdir(backup_dir) if f.startswith(test_filename) and f.endswith(".bak")]
            self.assertTrue(len(backups) >= 1, "Pre-edit backup snapshot was not created!")

            # 4. Verify backup contains Version 1 content
            latest_bak = os.path.join(backup_dir, sorted(backups)[-1])
            with open(latest_bak, "r", encoding="utf-8") as f:
                bak_content = f.read()
            self.assertIn("Version 1", bak_content)

        finally:
            # Cleanup test files
            if os.path.exists(test_path):
                os.remove(test_path)
            if os.path.isdir(backup_dir):
                for f in os.listdir(backup_dir):
                    if f.startswith(test_filename):
                        try:
                            os.remove(os.path.join(backup_dir, f))
                        except Exception:
                            pass

    # ── 7. Tool Registry get_active_window_context Dispatch ───────────────────

    def test_tool_registry_get_active_window_context_dispatch(self):
        """Verify tool registry dispatches get_active_window_context cleanly."""
        res = dispatch_tool("get_active_window_context", {})
        self.assertIsInstance(res, str)
        self.assertTrue(len(res) > 0)


if __name__ == "__main__":
    unittest.main()
