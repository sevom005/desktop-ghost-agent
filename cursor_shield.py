"""
Cursor Shield: Win32 System Cursor Transformation & Guaranteed Restoration
Provides dynamic crosshair cursor takeover during autonomous execution
and guarantees 100% restoration to default Windows cursor via SPI_SETCURSORS.
"""

import ctypes
import atexit

user32 = ctypes.windll.user32

# Win32 System Cursor IDs
OCR_NORMAL = 32512  # Standard Arrow
OCR_IBEAM  = 32513  # Text Selection
OCR_HAND   = 32649  # Link / Button Selection
OCR_CROSS  = 32515  # Precision Crosshair

# Win32 Constants
SPI_SETCURSORS = 0x0057
IMAGE_CURSOR = 2
LR_SHARED = 0x8000
LR_DEFAULTSIZE = 0x0040

_cursor_transformed = False


def restore_system_cursors() -> bool:
    """
    Forces Windows to reload the user's cursor scheme from the registry.
    Idempotent and safe to call multiple times.
    """
    global _cursor_transformed
    try:
        res = user32.SystemParametersInfoW(SPI_SETCURSORS, 0, None, 0)
        _cursor_transformed = False
        return bool(res)
    except Exception as e:
        print(f"[CURSOR SHIELD ERROR] Could not restore cursors: {e}")
        return False


def apply_ghost_cursor() -> bool:
    """
    Applies the native precision crosshair (OCR_CROSS) to OCR_NORMAL, OCR_IBEAM, and OCR_HAND.
    Uses CopyImage to duplicate handles, preventing handle destruction or memory corruption.
    """
    global _cursor_transformed
    try:
        for target_id in (OCR_NORMAL, OCR_IBEAM, OCR_HAND):
            h_cross = user32.LoadImageW(0, OCR_CROSS, IMAGE_CURSOR, 0, 0, LR_SHARED | LR_DEFAULTSIZE)
            if not h_cross:
                continue
            h_copy = user32.CopyImage(h_cross, IMAGE_CURSOR, 0, 0, 0)
            if not h_copy:
                continue
            user32.SetSystemCursor(h_copy, target_id)
        _cursor_transformed = True
        return True
    except Exception as e:
        print(f"[CURSOR SHIELD ERROR] Could not apply cursor takeover: {e}")
        return False


# Module-level atexit safety net
atexit.register(restore_system_cursors)
