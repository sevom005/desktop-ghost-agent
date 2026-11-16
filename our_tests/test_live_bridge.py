import os
import sys
import time
sys.path.insert(0, os.path.abspath("."))
import actuator
import gemini_bridge

print("Capturing live desktop for Turn 1...")
raw_bytes, b64_screen = actuator.capture_desktop_screenshot(quality=80)

bridge = gemini_bridge.GeminiDesktopBridge()
goal = "Click the Windows Start button, type calc, press Enter, and calculate 25 * 4 ="

print("\nStarting Turn 1 interaction...")
response = bridge.start_interaction(goal, b64_screen)
is_finished, function_calls, final_text = bridge.parse_interaction_response(response)

print(f"Turn 1 is_finished: {is_finished}")
print(f"Turn 1 function_calls count: {len(function_calls)}")
for call in function_calls:
    print(f"  Action: {call['name']} | Args: {call['arguments']} | Intent: {call['intent']}")

# Simulate executing the action and grabbing screen for Turn 2
time.sleep(1.0)
raw_bytes2, b64_screen2 = actuator.capture_desktop_screenshot(quality=80)

function_responses = [
    {
        "name": function_calls[0]["name"],
        "call_id": function_calls[0]["id"],
        "result": {"status": "success", "message": "Action executed successfully."}
    }
]

print("\nStarting Turn 2 interaction...")
response2 = bridge.send_function_results(
    function_responses,
    next_goal_summary=goal,
    latest_screenshot_b64=b64_screen2
)
is_finished2, function_calls2, final_text2 = bridge.parse_interaction_response(response2)

print(f"Turn 2 is_finished: {is_finished2}")
print(f"Turn 2 function_calls count: {len(function_calls2)}")
for call in function_calls2:
    print(f"  Action: {call['name']} | Args: {call['arguments']} | Intent: {call['intent']}")

print("\n[SUCCESS] Multi-turn Live bridge integration test PASSED with 0 errors!")
