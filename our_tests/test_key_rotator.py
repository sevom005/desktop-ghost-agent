import os
import sys
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
import key_rotator

print("============================================================")
print("STARTING STEP 1 KEY ROTATOR TESTS")
print("============================================================")

# Test 1: Real .env loading
print("\n--- [1] Live .env Discovery Test ---")
rotator = key_rotator.KeyRotator()
telemetry = rotator.get_telemetry()
print(f"Total keys discovered: {telemetry['total_keys']}")
print(f"Active key index: {telemetry['active_key_index']}")
print(f"Available keys count: {telemetry['available_keys_count']}")

assert telemetry["total_keys"] >= 5, f"Expected at least 5 keys, got {telemetry['total_keys']}"
assert telemetry["exhausted_keys_count"] == 0
print("  [PASS] Successfully discovered and verified all 5 configured API keys.")

# Test 2: Round-Robin Rotation Simulation
print("\n--- [2] Round-Robin Rotation Sequence ---")
key1 = rotator.get_current_key()
key2 = rotator.rotate_to_next(reason="Simulation turn 2")
key3 = rotator.rotate_to_next(reason="Simulation turn 3")

assert key1 != key2, "Key 1 and Key 2 should be different"
assert key2 != key3, "Key 2 and Key 3 should be different"
print("  [PASS] Round-robin rotation advances sequentially through pool.")

# Test 3: Exhaustion Handling
print("\n--- [3] Exhaustion Trap & Failover ---")
# Reset to index 0
rotator.current_index = 0
rotator.exhausted_indices.clear()

# Mark key 0 exhausted
next_key = rotator.mark_current_exhausted(reason="Simulated 500 RPD exhaustion")
assert rotator.current_index == 1
assert 0 in rotator.exhausted_indices
print(f"  Successfully failed over to Key #{rotator.current_index + 1}")

# Test 4: All Keys Exhausted Ceiling
print("\n--- [4] All Keys Exhausted Trap ---")
for i in range(len(rotator.keys)):
    rotator.exhausted_indices.add(i)

all_exhausted_triggered = False
try:
    rotator.get_current_key()
except RuntimeError as e:
    all_exhausted_triggered = True
    print(f"  Safely intercepted all-exhausted condition: {e}")

assert all_exhausted_triggered, "Expected RuntimeError when all keys exhausted"
print("  [PASS] All keys exhausted trap safely terminates execution.")

print("\n============================================================")
print("ALL STEP 1 KEY ROTATOR TESTS PASSED 100%!")
print("============================================================")
