"""
tests/test_subagent_b_integration.py
====================================
Integration tests for Sub-Agent B and LiveBridge Master-Worker coordination:
  - Tool dispatching for delegate_background_task and get_task_status
  - LiveBridge queue_voice_alert callback handling
  - Proactive alert loop logic (Argon Trap #2)
  - Zero-latency Blackboard status querying
"""

import os
import sys
import time
import shutil
import asyncio
import tempfile
import unittest
from unittest.mock import MagicMock, patch, AsyncMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from live.tool_registry import dispatch_tool, get_live_tools
from live.live_bridge import LiveBridge, get_active_live_bridge
from memory.task_blackboard import TaskBlackboard


class TestSubAgentBIntegration(unittest.IsolatedAsyncioTestCase):
    """Verifies end-to-end Master-Worker coordination between Nova and Sub-Agent B."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.persistence_path = os.path.join(self.tmp_dir, "background_tasks.json")
        self.board = TaskBlackboard(persistence_path=self.persistence_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ── Test 1: Tool Declarations Registration ───────────────────────────────

    def test_live_tools_contain_background_tools(self):
        """Verify delegate_background_task and get_task_status exist in live tool list."""
        tools = get_live_tools()
        self.assertEqual(len(tools), 1)
        declarations = tools[0].function_declarations
        names = [d.name for d in declarations]
        self.assertIn("delegate_background_task", names)
        self.assertIn("get_task_status", names)

    # ── Test 2: Tool Dispatching for Background Tasks ────────────────────────

    def test_dispatch_tool_delegate_and_status(self):
        """Verify dispatch_tool successfully triggers tasks and queries status."""
        with patch("memory.task_blackboard.get_task_blackboard", return_value=self.board):
            with patch("workers.subagent_b.get_task_blackboard", return_value=self.board):
                with patch("workers.subagent_b.threading.Thread") as mock_thread:
                    res_delegate = dispatch_tool("delegate_background_task", {"task_description": "Clean RAM hogs"})
                    self.assertIn("Background task task_001 started", res_delegate)
                    mock_thread.assert_called_once()

                    # Query status while pending
                    res_status = dispatch_tool("get_task_status", {"task_id": "task_001"})
                    self.assertIn("Clean RAM hogs", res_status)
                    self.assertIn("PENDING", res_status)

                    # Update progress
                    self.board.update_progress("task_001", "Closing Chrome PID 4120...")
                    res_status_running = dispatch_tool("get_task_status", {})
                    self.assertIn("RUNNING", res_status_running)
                    self.assertIn("Closing Chrome PID 4120...", res_status_running)

                    # Complete task
                    self.board.complete_task("task_001", "Freed 3.8GB RAM.")
                    res_status_done = dispatch_tool("get_task_status", {"task_id": "task_001"})
                    self.assertIn("COMPLETED", res_status_done)
                    self.assertIn("Freed 3.8GB RAM.", res_status_done)

    # ── Test 3: LiveBridge Queue Voice Alert Callback ────────────────────────

    def test_live_bridge_queue_voice_alert(self):
        """Verify queue_voice_alert enqueues alerts on active LiveBridge instance."""
        bridge = LiveBridge()
        self.assertEqual(get_active_live_bridge(), bridge)

        bridge.queue_voice_alert("task_001", "Freed 3.8GB RAM successfully.")
        self.assertEqual(len(bridge._pending_voice_alerts), 1)
        self.assertEqual(bridge._pending_voice_alerts[0], "Freed 3.8GB RAM successfully.")

    # ── Test 4: Proactive Alert Loop Sends Client Content (Argon Trap #2) ───

    async def test_proactive_alert_loop_fires_when_idle(self):
        """
        Verify that _proactive_alert_loop calls session.send_client_content(..., turn_complete=True)
        only when audio is idle (not user speaking, not ghost speaking).
        """
        bridge = LiveBridge()
        bridge._running = True
        bridge._pending_voice_alerts.append("Killed background Chrome, freed 3.8GB RAM.")
        bridge._last_alert_time = 0.0  # Expired debounce
        bridge._ghost_speaking = False
        bridge._user_speaking = False

        mock_session = AsyncMock()

        # Run proactive alert loop for one short tick
        loop_task = asyncio.create_task(bridge._proactive_alert_loop(mock_session))
        await asyncio.sleep(0.4)
        bridge.request_stop()
        loop_task.cancel()
        try:
            await loop_task
        except asyncio.CancelledError:
            pass

        # Verify send_client_content was invoked with system notification
        mock_session.send_client_content.assert_called_once()
        call_kwargs = mock_session.send_client_content.call_args[1]
        self.assertTrue(call_kwargs.get("turn_complete"))
        sent_turns = call_kwargs.get("turns")
        self.assertEqual(len(sent_turns), 1)
        self.assertIn("[SYSTEM NOTIFICATION — BACKGROUND TASK FINISHED]", sent_turns[0].parts[0].text)
        self.assertIn("Killed background Chrome, freed 3.8GB RAM.", sent_turns[0].parts[0].text)

        # Pending alert must be popped
        self.assertEqual(len(bridge._pending_voice_alerts), 0)

    # ── Test 5: In-Place Redesign Target File Injection ──────────────────────

    def test_delegate_injects_last_artifact_for_redesign(self):
        """Verify that redesign tasks automatically append the last artifact path to edit in-place."""
        sample_file = os.path.join(self.tmp_dir, "table.html")
        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("<table>Initial</table>")

        self.board.record_artifact("task_001", sample_file)

        with patch("memory.task_blackboard.get_task_blackboard", return_value=self.board):
            with patch("workers.subagent_b.get_task_blackboard", return_value=self.board):
                with patch("workers.subagent_b.launch_background_task") as mock_launch:
                    mock_launch.return_value = "task_002"
                    res = dispatch_tool(
                        "delegate_background_task",
                        {"task_description": "Can you redesign that HTML file to have dark mode?"}
                    )
                    self.assertIn("Background task task_002 started", res)

                    # Verify launched task description had the artifact path injected
                    called_desc = mock_launch.call_args[0][0]
                    self.assertIn("Target File to edit in-place:", called_desc)
                    self.assertIn(os.path.abspath(sample_file), called_desc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
