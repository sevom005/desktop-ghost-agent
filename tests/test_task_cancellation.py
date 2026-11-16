"""
Unit and Integration Tests for Pillar 1: Task Cancellation & Control Engine
===========================================================================
Verifies:
  1. Task Blackboard status transition to CANCELLED and atomic persistence
  2. Sub-Agent B process tree termination via taskkill /F /T /PID
  3. Live Tool Registry dispatching of cancel_background_task
"""

import time
import threading
import unittest
from memory.task_blackboard import get_task_blackboard, TaskStatus
from workers import subagent_b
from live.tool_registry import dispatch_tool


class TestTaskCancellation(unittest.TestCase):
    def setUp(self):
        self.blackboard = get_task_blackboard()

    def test_blackboard_cancellation_lifecycle(self):
        """Test that task transitions to CANCELLED and fast-path RAM checks work."""
        task_id = self.blackboard.create_task("Test Cancellation Lifecycle")

        # Verify active and not cancelled initially
        self.assertFalse(self.blackboard.is_cancelled(task_id))
        status_info = self.blackboard.get_task_status(task_id)
        self.assertIn(status_info["status"], (TaskStatus.PENDING.value, TaskStatus.RUNNING.value))

        # Cancel task
        cancelled = self.blackboard.cancel_task(task_id, reason="User requested abort")
        self.assertTrue(cancelled)

        # Verify cancellation state in RAM & Blackboard
        self.assertTrue(self.blackboard.is_cancelled(task_id))
        status_after = self.blackboard.get_task_status(task_id)
        self.assertEqual(status_after["status"], TaskStatus.CANCELLED.value)
        self.assertIn("User requested abort", status_after["progress"])

        # Subsequent cancel should return False (already cancelled)
        second_cancel = self.blackboard.cancel_task(task_id)
        self.assertFalse(second_cancel)

    def test_subagent_b_process_tree_cancellation(self):
        """Test that a long-running subprocess is forcibly killed upon task cancellation."""
        task_id = self.blackboard.create_task("Process tree sleep task")

        # Launch a python script that sleeps for 15 seconds in a thread
        result_holder = {}

        def _worker():
            res = subagent_b.run_python_script(
                "import time\ntime.sleep(15)\nprint('finished')",
                task_id=task_id
            )
            result_holder["output"] = res

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()

        # Wait briefly for process to spawn
        time.sleep(0.5)

        # Confirm process is tracked
        with subagent_b._proc_lock:
            proc = subagent_b._active_subprocesses.get(task_id)
            self.assertIsNotNone(proc, "Subprocess should be registered in _active_subprocesses")

        # Cancel running task
        success = subagent_b.cancel_running_task(task_id, reason="Kill test process")
        self.assertTrue(success)

        # Wait for thread to exit
        thread.join(timeout=3.0)
        self.assertFalse(thread.is_alive(), "Worker thread should exit after process cancellation")

        # Check blackboard
        self.assertTrue(self.blackboard.is_cancelled(task_id))

    def test_cancel_background_task_tool_dispatch(self):
        """Test dispatching cancel_background_task via tool registry."""
        task_id = self.blackboard.create_task("Dispatch Cancel Test")

        # Dispatch tool
        res = dispatch_tool("cancel_background_task", {"task_id": task_id, "reason": "Test dispatch"})
        self.assertIn(task_id, res)
        self.assertIn("cancelled", res.lower())

        # Verify status
        status = self.blackboard.get_task_status(task_id)
        self.assertEqual(status["status"], TaskStatus.CANCELLED.value)


if __name__ == "__main__":
    unittest.main()
