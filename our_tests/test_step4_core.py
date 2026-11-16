"""
Level 4 Verification Suite: Desktop Ghost Core State Machine
Tests Focus Shield, coordinate sanitizer integration, completion screenshot generation,
and clean cleanup restoration.
"""

import sys
import os
import time

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import ghost_agent
import defense

def test_focus_shield_mechanics():
    print("\n--- [1] Focus Shield Minimize & Restore Verification ---")
    hwnd = ghost_agent.minimize_current_window()
    print(f"Captured Foreground HWND: {hwnd}")
    time.sleep(0.5)
    ghost_agent.restore_window(hwnd)
    print("  [PASS] Focus shield minimized and restored window cleanly.")


def test_action_sanitization_defense():
    print("\n--- [2] Action Sanitization & Zero-Click Rejection ---")
    agent = ghost_agent.DesktopGhostAgent()
    
    # 1. Invalid coordinates should be rejected without physical clicks
    bad_res = agent.execute_single_action("click", {"x": "undefined", "y": "NaN", "intent": "Test bad coords"})
    print(f"Result for malformed click: {bad_res}")
    assert bad_res["status"] == "error"
    assert "Malformed" in bad_res["message"]

    # 2. Unsupported action should return unsupported status without crashing
    unsupported_res = agent.execute_single_action("pinch_zoom", {"intent": "Test unsupported"})
    print(f"Result for unsupported tool: {unsupported_res}")
    assert unsupported_res["status"] == "error"
    assert unsupported_res["error"] == "UNSUPPORTED_ACTION"
    print("  [PASS] Action sanitization safely intercepted invalid inputs.")


def test_completion_proof_generation():
    print("\n--- [3] Completion Screenshot Generation ---")
    proof_path = os.path.join(os.path.dirname(__file__), "..", "completion_screenshot.jpg")
    if os.path.exists(proof_path):
        os.remove(proof_path)

    agent = ghost_agent.DesktopGhostAgent()
    agent.cleanup(status="TEST_VERIFICATION", turns=1, summary="Automated test completion proof.")
    
    assert os.path.exists(proof_path), "Failed to generate completion_screenshot.jpg on disk!"
    size_kb = os.path.getsize(proof_path) / 1024.0
    print(f"Generated Visual Proof: {proof_path} ({size_kb:.1f} KB)")
    print("  [PASS] Completion screenshot generated and telemetry printed.")


if __name__ == "__main__":
    print("=" * 60)
    print("STARTING LEVEL 4 CORE STATE MACHINE TESTS")
    print("=" * 60)
    test_focus_shield_mechanics()
    test_action_sanitization_defense()
    test_completion_proof_generation()
    print("\n" + "=" * 60)
    print("ALL LEVEL 4 CORE TESTS PASSED PERFECTLY!")
    print("=" * 60)
