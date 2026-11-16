"""
Unit and Integration Tests for Pillar 2: Markdown Skills & Universal Launcher
=============================================================================
Verifies:
  1. Discovery and YAML frontmatter parsing of SKILL.md playbooks
  2. Fuzzy skill resolution by trigger, binary name, or skill name
  3. Dynamic Markdown skills catalog generation for System Instructions
  4. Executable discovery for Notepad++ and other applications
  5. Universal launcher command token splitting (shlex) eliminating [WinError 2]
"""

import os
import unittest
from unittest.mock import patch
from skills import skill_loader
from skills import win32_window_utils
from skills.skill_registry import SkillRegistry


class TestMarkdownSkillsAndLauncher(unittest.TestCase):
    def setUp(self):
        self.skills = skill_loader.load_all_skills(force_reload=True)

    def test_skills_discovery_and_frontmatter_parsing(self):
        """Verify all 4 core SKILL.md playbooks are discovered and parsed."""
        expected_skills = {"notepad_plus_plus", "vscode", "chrome", "notepad"}
        self.assertTrue(expected_skills.issubset(set(self.skills.keys())))

        # Test Notepad++ specific properties
        npp = self.skills["notepad_plus_plus"]
        self.assertEqual(npp.name, "notepad_plus_plus")
        self.assertIn("notepad++", npp.triggers)
        self.assertIn("notepad++.exe", npp.executable_names)
        self.assertTrue(len(npp.description) > 10)
        self.assertIn("Notepad++ Skill Guide", npp.content)
        self.assertIn("Ctrl+G", npp.content)

        # Test VS Code specific properties
        vsc = self.skills["vscode"]
        self.assertEqual(vsc.name, "vscode")
        self.assertIn("code", vsc.triggers)
        self.assertIn("code.exe", vsc.executable_names)
        self.assertIn("Ctrl+Shift+P", vsc.content)

    def test_fuzzy_skill_resolution(self):
        """Test resolving skills via executable name, trigger alias, or direct name."""
        # By executable name
        self.assertEqual(skill_loader.find_skill_for_app("notepad++.exe").name, "notepad_plus_plus")
        self.assertEqual(skill_loader.find_skill_for_app("code.exe").name, "vscode")
        self.assertEqual(skill_loader.find_skill_for_app("chrome.exe").name, "chrome")
        self.assertEqual(skill_loader.find_skill_for_app("notepad.exe").name, "notepad")

        # By alias or trigger
        self.assertEqual(skill_loader.find_skill_for_app("npp").name, "notepad_plus_plus")
        self.assertEqual(skill_loader.find_skill_for_app("visual studio code").name, "vscode")
        self.assertEqual(skill_loader.find_skill_for_app("browser").name, "chrome")

    def test_catalog_prompt_generation(self):
        """Verify dynamic prompt catalog generation contains all loaded skills."""
        catalog = skill_loader.get_skills_catalog_prompt()
        self.assertIn("EXTENDED MARKDOWN APPLICATION PLAYBOOKS", catalog)
        self.assertIn("notepad_plus_plus", catalog)
        self.assertIn("vscode", catalog)
        self.assertIn("chrome", catalog)
        self.assertIn("notepad", catalog)

        # Verify integration into SkillRegistry.get_catalog_prompt()
        registry = SkillRegistry()
        reg_catalog = registry.get_catalog_prompt()
        self.assertIn("EXTENDED MARKDOWN APPLICATION PLAYBOOKS", reg_catalog)
        self.assertIn("notepad_plus_plus", reg_catalog)

    def test_notepad_plus_plus_executable_discovery(self):
        """Verify win32_window_utils discovers Notepad++ installed in Program Files."""
        exe_path = win32_window_utils.find_app_executable("notepad++")
        self.assertIsNotNone(exe_path)
        self.assertTrue(os.path.exists(exe_path))
        self.assertTrue(exe_path.lower().endswith("notepad++.exe"))

    @patch("subprocess.Popen")
    @patch("skills.win32_window_utils.wait_for_visible_window")
    def test_launch_generic_app_shlex_splitting(self, mock_wait_window, mock_popen):
        """Verify launch_generic_app safely splits command strings and arguments."""
        mock_wait_window.return_value = 12345
        registry = SkillRegistry()

        # Case 1: app_name with embedded argument
        res = registry.launch_generic_app("notepad++.exe C:\\Users\\Test\\script.py")
        self.assertEqual(res["status"], "success")
        self.assertTrue(mock_popen.called)

        # Inspect the command passed to Popen
        cmd_called = mock_popen.call_args[0][0]
        # First element must be resolved binary or clean binary, NOT combined with arg
        self.assertTrue(cmd_called[0].lower().endswith("notepad++.exe"))
        # Second element must be the path argument
        self.assertIn("script.py", cmd_called[1])

        # Case 2: app_name and separate args
        mock_popen.reset_mock()
        res2 = registry.launch_generic_app("notepad++", "C:\\temp\\file.txt --multi-instance")
        self.assertEqual(res2["status"], "success")
        cmd_called2 = mock_popen.call_args[0][0]
        self.assertTrue(cmd_called2[0].lower().endswith("notepad++.exe"))
        self.assertIn("file.txt", cmd_called2[1])
        self.assertEqual(cmd_called2[2], "--multi-instance")


if __name__ == "__main__":
    unittest.main()
