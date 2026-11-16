"""
tests/test_subagent_b.py
========================
Unit tests for Sub-Agent B (Phase 2):
  - Dual PID and Process Name Protection (Argon Trap #1)
  - Safe PowerShell execution with -NonInteractive (Argon Trap #3)
  - System telemetry gathering with psutil
  - Safe file read and write tools
  - ReAct execution loop integration with TaskBlackboard
"""

import os
import sys
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from workers.subagent_b import (
    is_protected,
    kill_process,
    run_powershell,
    run_python_script,
    get_system_telemetry,
    read_file,
    write_file,
    resolve_workspace_path,
    SubAgentB,
    launch_background_task,
)
from memory.task_blackboard import TaskBlackboard


class TestSubAgentB(unittest.TestCase):
    """Unit tests for Sub-Agent B headless worker and safeguards."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.persistence_path = os.path.join(self.tmp_dir, "background_tasks.json")
        self.board = TaskBlackboard(persistence_path=self.persistence_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ── Test 1: Friendly-Fire Protection Guard (Argon Trap #1) ───────────────

    def test_friendly_fire_protection_guard(self):
        """Verify that Nova's own PID and critical system names are strictly protected."""
        my_pid = os.getpid()

        # 1. Check PID protection
        prot_pid, reason_pid = is_protected(pid=my_pid)
        self.assertTrue(prot_pid)
        self.assertIn("Nova", reason_pid)

        # 2. Check Process Name protection
        prot_name, reason_name = is_protected(name="explorer.exe")
        self.assertTrue(prot_name)
        self.assertIn("protected", reason_name.lower())

        prot_name_csrss, _ = is_protected(name="csrss.exe")
        self.assertTrue(prot_name_csrss)

        # 3. kill_process denies killing own PID
        res = kill_process(my_pid)
        self.assertIn("DENIED", res)

        # 4. run_powershell denies killing protected processes by name
        ps_res = run_powershell("Stop-Process -Name explorer -Force")
        self.assertIn("DENIED", ps_res)

        ps_res_py = run_powershell("Stop-Process -Name python -Force")
        self.assertIn("DENIED", ps_res_py)

    # ── Test 2: System Telemetry Output ──────────────────────────────────────

    def test_system_telemetry_gathering(self):
        """Verify get_system_telemetry returns CPU, RAM, and protected processes."""
        telemetry = get_system_telemetry()
        self.assertIn("CPU Load:", telemetry)
        self.assertIn("RAM Usage:", telemetry)
        self.assertIn("Top Processes by RAM:", telemetry)
        # Should flag at least one protected process
        self.assertIn("[PROTECTED", telemetry)

    # ── Test 3: PowerShell Non-Interactive Execution (Argon Trap #3) ─────────

    def test_powershell_non_interactive_execution(self):
        """Verify PowerShell executes quietly without popup windows or hangs."""
        output = run_powershell("Write-Output 'Ghost Worker Test'")
        self.assertEqual(output.strip(), "Ghost Worker Test")

    # ── Test 4: Python Script Execution ──────────────────────────────────────

    def test_python_script_execution(self):
        """Verify run_python_script runs snippets cleanly."""
        output = run_python_script("print(100 * 5)")
        self.assertEqual(output.strip(), "500")

    # ── Test 5: File Read and Write Tools ────────────────────────────────────

    def test_file_read_write_tools(self):
        """Verify read_file and write_file operate safely."""
        test_file = os.path.join(self.tmp_dir, "notes.txt")
        w_res = write_file(test_file, "Study summary content")
        self.assertIn("SUCCESS", w_res)

        r_res = read_file(test_file)
        self.assertEqual(r_res, "Study summary content")

    # ── Test 6: SubAgentB Execution Loop with Blackboard Integration ─────────

    def test_subagent_b_react_loop_with_blackboard(self):
        """Verify SubAgentB updates Blackboard and invokes completion callback."""
        with patch("workers.subagent_b.get_task_blackboard", return_value=self.board):
            task_id = self.board.create_task("Test task execution")

            # Mock client to simulate a fast 1-turn response
            worker = SubAgentB()
            worker.blackboard = self.board

            mock_response = MagicMock()
            mock_response.function_calls = None
            mock_response.text = "Freed 1.2GB RAM successfully."
            mock_response.candidates = [MagicMock()]

            with patch.object(worker.client.models, "generate_content", return_value=mock_response):
                completed_payload = {}

                def on_done(tid, summary):
                    completed_payload["tid"] = tid
                    completed_payload["summary"] = summary

                summary = worker.execute_task_sync(task_id, "Clean RAM", on_complete=on_done)

                self.assertEqual(summary, "Freed 1.2GB RAM successfully.")
                self.assertEqual(completed_payload["tid"], task_id)
                self.assertEqual(completed_payload["summary"], "Freed 1.2GB RAM successfully.")

                status = self.board.get_task_status(task_id)
                self.assertEqual(status["status"], "COMPLETED")
                self.assertEqual(status["result"], "Freed 1.2GB RAM successfully.")

    # ── Test 7: Workspace Path Resolution by File Extension ─────────────────

    def test_workspace_worker_path_resolution(self):
        """Verify resolve_workspace_path routes extensions to proper subfolders."""
        html_p = resolve_workspace_path("preview.html")
        self.assertTrue(html_p.endswith(os.path.join("workspace_worker", "html", "preview.html")))

        css_p = resolve_workspace_path("styles.css")
        self.assertTrue(css_p.endswith(os.path.join("workspace_worker", "html", "styles.css")))

        notes_p = resolve_workspace_path("summary.txt")
        self.assertTrue(notes_p.endswith(os.path.join("workspace_worker", "notes", "summary.txt")))

        json_p = resolve_workspace_path("data.json")
        self.assertTrue(json_p.endswith(os.path.join("workspace_worker", "notes", "data.json")))

        py_p = resolve_workspace_path("automation.py")
        self.assertTrue(py_p.endswith(os.path.join("workspace_worker", "scripts", "automation.py")))

        out_p = resolve_workspace_path("archive.bin")
        self.assertTrue(out_p.endswith(os.path.join("workspace_worker", "outputs", "archive.bin")))

    # ── Test 8: Write File Records Artifact on Blackboard ────────────────────

    def test_write_file_records_artifact(self):
        """Verify write_file writes to workspace_worker and registers artifact on Blackboard."""
        with patch("workers.subagent_b.get_task_blackboard", return_value=self.board):
            task_id = self.board.create_task("Generate HTML component")
            filename = "component_test.html"
            expected_path = resolve_workspace_path(filename)

            try:
                res = write_file(filename, "<div>Component</div>", task_id=task_id)
                self.assertIn("SUCCESS", res)
                self.assertTrue(os.path.exists(expected_path))

                # Check artifact registration
                status = self.board.get_task_status(task_id)
                self.assertIn(expected_path, status["artifacts"])
                self.assertEqual(self.board.get_last_artifact(), expected_path)
            finally:
                if os.path.exists(expected_path):
                    os.remove(expected_path)


if __name__ == "__main__":
    unittest.main(verbosity=2)
