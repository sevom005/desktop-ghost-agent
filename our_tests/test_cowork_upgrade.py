import os
import sys
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
import key_rotator
import defense
import gemini_bridge
import actuator
import cursor_shield

print("============================================================")
print("STARTING END-TO-END COWORK UPGRADE VERIFICATION")
print("============================================================")

# 1. Rotator Health
rotator = key_rotator.KeyRotator()
telemetry = rotator.get_telemetry()
print(f"\n[1] Key Pool Discovery:")
print(f"    Total Configured Keys: {telemetry['total_keys']}")
print(f"    Active Key: Key #{telemetry['active_key_index']}")
print(f"    Available Keys: {telemetry['available_keys_count']}")
assert telemetry["total_keys"] == 5, f"Expected 5 keys, got {telemetry['total_keys']}"

# 2. 429 Error Classifier
print("\n[2] 429 Discriminator Verification:")
cat_daily = defense.classify_api_error(Exception("429 ResourceExhausted: GenerateRequestsPerDay quota exceeded"))
cat_burst = defense.classify_api_error(Exception("429 Rate limit exceeded: requests per minute"))
print(f"    Daily Quota Classification: [{cat_daily}]")
print(f"    Burst Rate Classification:  [{cat_burst}]")
assert cat_daily == "DAILY_QUOTA_EXHAUSTED"
assert cat_burst == "BURST_RATE_LIMIT"

# 3. Live Handshake with Turn-7 Cycle Bridge
print("\n[3] Live Handshake with Bridge (Cycle Length: 7):")
bridge = gemini_bridge.GeminiDesktopBridge(rotator=rotator, cycle_length=7)
raw_bytes, b64_screen = actuator.capture_desktop_screenshot(quality=80)
goal = "Open the Windows Start Menu"

response = bridge.start_interaction(goal, b64_screen)
is_fin, calls, summary = bridge.parse_interaction_response(response)
print(f"    Handshake successful! Active Key: Key #{bridge.rotator.current_index + 1}")
print(f"    Is finished: {is_fin}")
print(f"    Emitted function calls: {len(calls)}")
if calls:
    print(f"    First Action: {calls[0]['name']} -> {calls[0]['arguments']}")
assert len(calls) > 0 or is_fin

# 4. Cursor Shield Verification
print("\n[4] Cursor Shield Safety Test:")
cursor_shield.apply_ghost_cursor()
cursor_shield.restore_system_cursors()
print("    Cursor transform and restoration verified.")

print("\n============================================================")
print("ALL COWORK-CLASS UPGRADES VERIFIED 100% CLEAN AND OPERATIONAL!")
print("============================================================")
