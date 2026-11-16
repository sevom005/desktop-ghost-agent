import os
import sys
import time
import ctypes
import atexit

user32 = ctypes.windll.user32

OCR_NORMAL = 32512
OCR_IBEAM = 32513
OCR_HAND = 32649
OCR_CROSS = 32515

SPI_SETCURSORS = 0x0057
IMAGE_CURSOR = 2
LR_SHARED = 0x8000
LR_DEFAULTSIZE = 0x0040

def restore_cursors():
    """Forces Windows to reload user cursor scheme from registry."""
    print("[CURSOR SHIELD] Restoring system cursors via SPI_SETCURSORS...")
    res = user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
    print(f"[CURSOR SHIELD] Restoration result: {res}")
    return bool(res)

def apply_precision_ghost_cursor():
    """
    Safely overrides OCR_NORMAL, OCR_IBEAM, and OCR_HAND with OCR_CROSS
    using CopyImage to avoid pointer destruction.
    """
    print("[CURSOR SHIELD] Applying precision Ghost cursor to NORMAL, IBEAM, HAND...")
    for target_id in (OCR_NORMAL, OCR_IBEAM, OCR_HAND):
        h_cross = user32.LoadImageW(0, OCR_CROSS, IMAGE_CURSOR, 0, 0, LR_SHARED | LR_DEFAULTSIZE)
        if not h_cross:
            print(f"[WARN] Failed to load OCR_CROSS for target {target_id}")
            continue
        h_copy = user32.CopyImage(h_cross, IMAGE_CURSOR, 0, 0, 0)
        if not h_copy:
            print(f"[WARN] Failed to CopyImage for target {target_id}")
            continue
        success = user32.SetSystemCursor(h_copy, target_id)
        if not success:
            print(f"[WARN] SetSystemCursor failed for target {target_id}")

print("--- [TEST 1] Testing Cursor Swap for 2 seconds ---")
atexit.register(restore_cursors)

try:
    apply_precision_ghost_cursor()
    print("Cursor successfully changed to precision crosshair. Sleeping 2 seconds...")
    time.sleep(2.0)
finally:
    restore_cursors()

print("--- [TEST 1 COMPLETE] Cursor restored to default Windows scheme. ---")
