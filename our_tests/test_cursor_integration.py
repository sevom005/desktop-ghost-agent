import os
import sys
import time
sys.path.insert(0, os.path.abspath("."))
import cursor_shield

print("--- [TEST 1] Testing apply_ghost_cursor() ---")
res_apply = cursor_shield.apply_ghost_cursor()
print(f"Apply result: {res_apply}")
assert res_apply is True, "apply_ghost_cursor failed"
assert cursor_shield._cursor_transformed is True

print("Cursor transformed. Sleeping 1 second...")
time.sleep(1.0)

print("--- [TEST 2] Testing restore_system_cursors() ---")
res_restore = cursor_shield.restore_system_cursors()
print(f"Restore result: {res_restore}")
assert res_restore is True, "restore_system_cursors failed"
assert cursor_shield._cursor_transformed is False

print("--- [TEST 3] Testing Idempotency (multiple restores) ---")
res_restore2 = cursor_shield.restore_system_cursors()
print(f"Second Restore result: {res_restore2}")
assert res_restore2 is True

print("\n[SUCCESS] cursor_shield tests PASSED cleanly with 0 errors!")
