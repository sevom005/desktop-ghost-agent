"""
Level 2 Verification Suite: API Bridge & Quota Defense Integration
Tests Pacific Time sync, dHash structural hashing, 15 RPM pacer,
and performs a live single-turn visual handshake with Gemini 3.5 Flash-Lite.
"""

import sys
import os
import time

# Ensure parent directory is in path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image
import defense
import actuator
import gemini_bridge

def test_pacific_time_quota():
    print("\n--- [1] Pacific Timezone Daily Quota Sync ---")
    pt_date = defense.get_pacific_date_string()
    print(f"Current Google Quota Date (Pacific Time): {pt_date}")
    assert len(pt_date) == 10 and "-" in pt_date
    
    state = defense.load_quota_state()
    print(f"Loaded Quota State: {state}")
    assert state.get("daily_limit") == 500
    assert state.get("date") == pt_date
    
    ok, msg = defense.check_daily_quota_available()
    print(f"Quota Status: {msg}")
    assert ok is True
    print("  [PASS] Pacific Time synchronization verified.")


def test_dhash_algorithm():
    print("\n--- [2] dHash UI Structural Difference Test ---")
    # Identical images
    img1 = Image.new("RGB", (200, 200), color=(50, 50, 50))
    img2 = Image.new("RGB", (200, 200), color=(50, 50, 50))
    h1 = defense.compute_dhash(img1)
    h2 = defense.compute_dhash(img2)
    dist_same = defense.hamming_distance(h1, h2)
    print(f"Hamming distance of identical images: {dist_same}")
    assert dist_same == 0

    # Patterned image with vertical stripes (multiple gradient transitions)
    img3 = Image.new("RGB", (200, 200), color=(0, 0, 0))
    for x in range(0, 200, 20):
        for y in range(200):
            img3.putpixel((x, y), (255, 255, 255))
    h3 = defense.compute_dhash(img3)
    dist_diff = defense.hamming_distance(h1, h3)
    print(f"Hamming distance of striped vs solid image: {dist_diff}")
    assert dist_diff > 5
    print("  [PASS] dHash structural hashing is accurate and fast.")


def test_rate_limit_pacer():
    print("\n--- [3] 15 RPM Mathematical Pacer Verification ---")
    pacer = defense.RateLimitPacer()
    t0 = time.monotonic()
    pacer.wait()  # First wait is instant
    first_duration = time.monotonic() - t0
    assert first_duration < 0.1

    print("Simulating back-to-back turn (should sleep ~4.2s)...")
    t1 = time.monotonic()
    pacer.wait()  # Second wait should sleep ~4.2s
    second_duration = time.monotonic() - t1
    print(f"Second call delay: {second_duration:.2f}s")
    assert second_duration >= 4.1, f"Pacer failed to enforce 4.2s minimum interval! Got: {second_duration:.2f}s"
    print("  [PASS] 15 RPM pacer strictly enforced.")


def test_live_gemini_handshake():
    print("\n--- [4] Live Single-Turn Handshake (Gemini 3.5 Flash-Lite) ---")
    print("Capturing live desktop screen...")
    raw_bytes, b64_str = actuator.capture_desktop_screenshot(quality=80)
    print(f"Screenshot captured: {len(raw_bytes)/1024:.1f} KB")

    bridge = gemini_bridge.GeminiDesktopBridge()
    goal = "Observe this screen. Locate the Windows taskbar or Start button and output a single click action to click it."
    
    t0 = time.time()
    interaction = bridge.start_interaction(goal, b64_str)
    latency = time.time() - t0
    print(f"API Roundtrip Time (TTFT): {latency:.2f}s")

    is_finished, function_calls, final_text = bridge.parse_interaction_response(interaction)
    print(f"Is Finished: {is_finished}")
    print(f"Emitted Function Calls ({len(function_calls)}):")
    for call in function_calls:
        print(f"  -> Name:     {call['name']}")
        print(f"     Call ID:  {call['id']}")
        print(f"     Intent:   {call['intent']}")
        print(f"     Args:     {call['arguments']}")
        print(f"     Safety:   {call['safety_decision']}")

    assert len(function_calls) > 0, "Expected Gemini to emit at least 1 computer_use function_call!"
    assert function_calls[0]["id"], "Missing call_id in response!"
    print("\n  [PASS] Live Gemini 3.5 Flash-Lite handshake succeeded with valid tool call!")


if __name__ == "__main__":
    print("=" * 60)
    print("STARTING LEVEL 2 INTEGRATION VERIFICATION SUITE")
    print("=" * 60)
    test_pacific_time_quota()
    test_dhash_algorithm()
    test_rate_limit_pacer()
    test_live_gemini_handshake()
    print("\n" + "=" * 60)
    print("ALL LEVEL 2 TESTS PASSED PERFECTLY!")
    print("=" * 60)
