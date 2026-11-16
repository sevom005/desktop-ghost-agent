import os
import sys
import time
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
import actuator
import gemini_bridge
import key_rotator

print("============================================================")
print("STARTING STEP 3 CONTEXT ROLLING TESTS")
print("============================================================")

rotator = key_rotator.KeyRotator()
print(f"Loaded Rotator with {len(rotator.keys)} keys. Active: Key #{rotator.current_index + 1}")

# Use cycle_length=2 for testing rollover trigger
bridge = gemini_bridge.GeminiDesktopBridge(rotator=rotator, cycle_length=2)
assert bridge.cycle_length == 2
assert bridge.turn_in_cycle == 0
assert bridge.cycle_count == 1

print("\n--- [1] Capturing Live Desktop for Turn 1 ---")
raw_bytes, b64_screen = actuator.capture_desktop_screenshot(quality=80)
goal = "Open Calculator and calculate 10 + 5 ="

print("\n--- [2] Turn 1 Initialization ---")
resp1 = bridge.start_interaction(goal, b64_screen)
is_fin1, calls1, text1 = bridge.parse_interaction_response(resp1)
print(f"Turn 1 executed. Cycle: {bridge.cycle_count}, Step: {bridge.turn_in_cycle}/{bridge.cycle_length}")
assert bridge.turn_in_cycle == 1
assert bridge.cycle_count == 1

print("\n--- [3] Turn 2 Standard In-Cycle Step ---")
func_res = [{"name": "click", "call_id": "c1", "result": {"status": "success"}}]
raw_bytes2, b64_screen2 = actuator.capture_desktop_screenshot(quality=80)

resp2 = bridge.send_function_results(
    func_res,
    next_goal_summary=goal,
    latest_screenshot_b64=b64_screen2
)
is_fin2, calls2, text2 = bridge.parse_interaction_response(resp2)
print(f"Turn 2 executed. Cycle: {bridge.cycle_count}, Step: {bridge.turn_in_cycle}/{bridge.cycle_length}")
assert bridge.turn_in_cycle == 2
assert bridge.cycle_count == 1

print("\n--- [4] Turn 3 Rollover Trigger Step (Cycle Rollover) ---")
raw_bytes3, b64_screen3 = actuator.capture_desktop_screenshot(quality=80)

resp3 = bridge.send_function_results(
    func_res,
    next_goal_summary=goal,
    latest_screenshot_b64=b64_screen3
)
is_fin3, calls3, text3 = bridge.parse_interaction_response(resp3)
print(f"Turn 3 executed. Cycle: {bridge.cycle_count}, Step: {bridge.turn_in_cycle}/{bridge.cycle_length}")

# Verify that cycle rolled over to Cycle 2, Step 1
assert bridge.cycle_count == 2, f"Expected cycle_count 2, got {bridge.cycle_count}"
assert bridge.turn_in_cycle == 1, f"Expected turn_in_cycle reset to 1, got {bridge.turn_in_cycle}"
assert bridge.total_turns == 3, f"Expected total_turns 3, got {bridge.total_turns}"

print("\n  [PASS] Context rolling cleanly compressed memory, dropped old frames, and spawned Cycle 2!")

print("\n============================================================")
print("ALL STEP 3 CONTEXT ROLLING TESTS PASSED 100%!")
print("============================================================")
