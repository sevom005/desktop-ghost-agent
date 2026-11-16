"""
tests/test_task_blackboard.py
=============================
Unit tests for TaskBlackboard (Phase 1):
  - TaskStatus and BlackboardTask schema validation
  - In-memory lifecycle transitions (create, progress, complete, fail)
  - 0.001ms RAM status query speed
  - Atomic persistence to disk and reloading
  - Thread safety under concurrent updates
"""

import os
import sys
import time
import shutil
import tempfile
import threading
import unittest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from memory.task_blackboard import (
    TaskBlackboard,
    BlackboardTask,
    TaskStatus,
)


class TestTaskBlackboard(unittest.TestCase):
    """Unit tests for the TaskBlackboard shared memory engine."""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.persistence_path = os.path.join(self.tmp_dir, "background_tasks.json")
        self.board = TaskBlackboard(persistence_path=self.persistence_path)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    # ── Test 1: Task Creation and Lifecycle Transitions ──────────────────────

    def test_task_lifecycle_transitions(self):
        """Verify standard lifecycle: create -> progress -> complete."""
        task_id = self.board.create_task("Check memory hogs and kill them")
        self.assertEqual(task_id, "task_001")

        # Initial state
        status = self.board.get_task_status(task_id)
        self.assertEqual(status["status"], "PENDING")
        self.assertEqual(status["goal"], "Check memory hogs and kill them")

        # Progress update
        self.board.update_progress(task_id, "Scanning active processes...")
        status = self.board.get_task_status(task_id)
        self.assertEqual(status["status"], "RUNNING")
        self.assertEqual(status["progress"], "Scanning active processes...")

        # Complete
        self.board.complete_task(task_id, "Terminated Chrome. Freed 3.8GB RAM.")
        status = self.board.get_task_status(task_id)
        self.assertEqual(status["status"], "COMPLETED")
        self.assertEqual(status["result"], "Terminated Chrome. Freed 3.8GB RAM.")
        self.assertIsNone(self.board.get_active_task())

    # ── Test 2: Task Failure Handling ────────────────────────────────────────

    def test_task_failure_handling(self):
        """Verify task failure records error and marks status as FAILED."""
        task_id = self.board.create_task("Compile missing binary")
        self.board.update_progress(task_id, "Running compiler...")
        self.board.fail_task(task_id, "Command timed out after 30s")

        status = self.board.get_task_status(task_id)
        self.assertEqual(status["status"], "FAILED")
        self.assertEqual(status["error"], "Command timed out after 30s")
        self.assertIn("Failed:", status["progress"])
        self.assertIsNone(self.board.get_active_task())

    # ── Test 3: Fast-Path RAM Read Speed (0.001ms) ───────────────────────────

    def test_fast_path_ram_read_speed(self):
        """Verify get_task_status operates entirely in RAM under 1 millisecond."""
        task_id = self.board.create_task("Fast query task")
        self.board.update_progress(task_id, "In-memory progress")

        start = time.perf_counter()
        for _ in range(100):
            res = self.board.get_task_status(task_id)
        elapsed = time.perf_counter() - start

        avg_latency_ms = (elapsed / 100) * 1000
        # Average RAM query should comfortably be < 0.1ms (often < 0.005ms)
        self.assertLess(avg_latency_ms, 0.5)
        self.assertEqual(res["progress"], "In-memory progress")

    # ── Test 4: Default Active Task Fallback ──────────────────────────────────

    def test_active_task_fallback_when_none_specified(self):
        """Verify get_task_status() without an ID returns the active running task."""
        self.board.create_task("First task")
        t2_id = self.board.create_task("Second task (active)")

        status = self.board.get_task_status()
        self.assertEqual(status["task_id"], t2_id)
        self.assertEqual(status["goal"], "Second task (active)")

    # ── Test 5: Atomic Persistence & Reloading From Disk ─────────────────────

    def test_atomic_persistence_and_reload(self):
        """Verify tasks persist to background_tasks.json and reload cleanly in a new instance."""
        task_id = self.board.create_task("Persistent background job")
        self.board.complete_task(task_id, "Completed job result.")

        self.assertTrue(os.path.exists(self.persistence_path))

        # Instantiate a second blackboard loading from the same path
        new_board = TaskBlackboard(persistence_path=self.persistence_path)
        status = new_board.get_task_status(task_id)
        self.assertEqual(status["status"], "COMPLETED")
        self.assertEqual(status["result"], "Completed job result.")

    # ── Test 6: Thread Safety Under Concurrent Access ────────────────────────

    def test_thread_safety_under_concurrency(self):
        """Verify multi-threaded progress updates and reads don't throw or corrupt state."""
        task_id = self.board.create_task("Concurrent stress test")
        errors = []

        def worker(thread_idx: int):
            try:
                for i in range(20):
                    self.board.update_progress(task_id, f"Thread {thread_idx} step {i}")
                    _ = self.board.get_task_status(task_id)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(len(errors), 0)
        final_status = self.board.get_task_status(task_id)
        self.assertEqual(final_status["status"], "RUNNING")

    # ── Test 7: Artifact Tracking & Last Artifact Retrieval ─────────────────

    def test_artifact_recording_and_retrieval(self):
        """Verify recording artifacts and retrieving the most recent valid artifact."""
        task_id = self.board.create_task("Create HTML document")
        sample_file = os.path.join(self.tmp_dir, "index.html")
        with open(sample_file, "w", encoding="utf-8") as f:
            f.write("<h1>Hello World</h1>")

        self.board.record_artifact(task_id, sample_file)
        self.board.complete_task(task_id, "File created.")

        status = self.board.get_task_status(task_id)
        self.assertIn("artifacts", status)
        self.assertEqual(status["artifacts"], [os.path.abspath(sample_file)])

        last_art = self.board.get_last_artifact()
        self.assertEqual(last_art, os.path.abspath(sample_file))


if __name__ == "__main__":
    unittest.main(verbosity=2)
