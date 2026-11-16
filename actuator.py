"""
Step 1: Sensor & Actuator Layer (The Physical Interface - Phase 3 Hardened)
High-speed screen capture with thread-local MSS, DPI-locked coordinate mapping,
and native Win32 SendInput motor actuation with 15ms frame-hold and KEYEVENTF_UNICODE typing.
"""

import ctypes
from ctypes import wintypes
import os
import sys
import time
import io
import base64
import threading
from typing import Tuple, List, Optional, Dict, Any

# 1. Attach Thread to Windows Interactive Input Desktop (Fixes BitBlt Access Denied)
def ensure_desktop_access():
    try:
        u32 = ctypes.windll.user32
        hdesk = u32.OpenInputDesktop(0, False, 0x01FF)  # GENERIC_ALL / DESKTOP_ALL
        if hdesk:
            u32.SetThreadDesktop(hdesk)
    except Exception:
        pass

ensure_desktop_access()

# 2. Lock Windows 10/11 Per-Monitor v2 DPI Awareness BEFORE importing GUI toolkits
try:
    ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
except Exception:
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

from PIL import Image, ImageGrab
import mss
import pyautogui
import pyperclip
import numpy as np

# Discover true physical screen dimensions
SCREEN_WIDTH, SCREEN_HEIGHT = pyautogui.size()

# 3. Hardened Win32 SendInput Structures & Constants
INPUT_MOUSE = 0
INPUT_KEYBOARD = 1

MOUSEEVENTF_MOVE     = 0x0001
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP   = 0x0004
MOUSEEVENTF_RIGHTDOWN= 0x0008
MOUSEEVENTF_RIGHTUP  = 0x0010
MOUSEEVENTF_MIDDLEDOWN = 0x0020
MOUSEEVENTF_MIDDLEUP   = 0x0040

KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_UNICODE     = 0x0004

class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))
    ]

class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD)
    ]

class INPUT(ctypes.Structure):
    class _I(ctypes.Union):
        _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]
    _anonymous_ = ("_i",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("_i", _I)
    ]

LPINPUT = ctypes.POINTER(INPUT)
SendInput = ctypes.windll.user32.SendInput
SetCursorPos = ctypes.windll.user32.SetCursorPos
GetCursorPos = ctypes.windll.user32.GetCursorPos


class SafetyInterlockException(RuntimeError):
    """Raised when an action violates safety guardrails (e.g. destructive Ctrl+A + Backspace on code editor)."""
    pass


class SafetyShield:
    """
    Editor Anti-Wipe Safety Shield (Pillar 3):
    Tracks temporal keystroke sequences and intercepts destructive editing patterns
    such as 'Ctrl+A' followed by 'Backspace' or 'Delete' on active code editors.
    """
    def __init__(self):
        self._last_select_all_time: float = 0.0
        self._last_select_all_hwnd: int = 0
        self._interlock_timeout: float = 3.0  # 3-second temporal window
        self._safety_enabled: bool = True

    def set_safety_enabled(self, enabled: bool) -> None:
        self._safety_enabled = enabled

    def is_safety_enabled(self) -> bool:
        return self._safety_enabled

    def check_hotkey(self, normalized_keys: List[str]) -> None:
        if not self._safety_enabled:
            return
        # Detect Ctrl+A or Control+A
        if len(normalized_keys) == 2 and "ctrl" in normalized_keys and "a" in normalized_keys:
            try:
                from skills import win32_window_utils
                fore = ctypes.windll.user32.GetForegroundWindow()
                if fore and win32_window_utils.is_editor_window(fore):
                    self._last_select_all_time = time.monotonic()
                    self._last_select_all_hwnd = fore
            except Exception:
                pass

    def check_key(self, normalized_key: str) -> None:
        if not self._safety_enabled:
            return
        if normalized_key in ("backspace", "delete"):
            now = time.monotonic()
            if (now - self._last_select_all_time) < self._interlock_timeout:
                try:
                    from skills import win32_window_utils
                    fore = ctypes.windll.user32.GetForegroundWindow()
                    # Trigger interlock if active window is the target editor or an editor window
                    if fore and (fore == self._last_select_all_hwnd or win32_window_utils.is_editor_window(fore)):
                        self._last_select_all_time = 0.0  # Disarm
                        raise SafetyInterlockException(
                            "SAFETY_INTERLOCK: Blocked destructive 'Ctrl+A + Backspace/Delete' sequence on active code editor. "
                            "Bulk editor destruction is strictly prevented. Use Sub-Agent B write_file or targeted edits instead."
                        )
                except SafetyInterlockException:
                    raise
                except Exception:
                    pass


_SAFETY_SHIELD = SafetyShield()


def get_safety_shield() -> SafetyShield:
    return _SAFETY_SHIELD


def _check_failsafe():
    """Failsafe Interlock: Slamming mouse to (0,0) immediately triggers emergency abort."""
    pt = wintypes.POINT()
    GetCursorPos(ctypes.byref(pt))
    if pt.x <= 1 and pt.y <= 1:
        raise pyautogui.FailSafeException("Emergency failsafe triggered at top-left corner (0,0)!")


def _send_mouse_event(flags: int):
    """Sends a relative mouse hardware packet via SendInput."""
    _check_failsafe()
    inp = INPUT(type=INPUT_MOUSE, mi=MOUSEINPUT(dwFlags=flags))
    SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


# 4. Coordinate Transformer & Anti-Suicide Clamping
def denormalize_x(norm_x: float) -> int:
    """Converts coordinate to physical pixel X. Clamps safely away from (0,0)."""
    try:
        val = float(norm_x)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid non-numeric coordinate for X: {norm_x}")
    if val > 1000.0:
        pixel = int(val)
    elif val <= 1.0 and isinstance(norm_x, float):
        pixel = int(val * SCREEN_WIDTH)
    else:
        pixel = int((val / 1000.0) * SCREEN_WIDTH)
    return max(2, min(SCREEN_WIDTH - 2, pixel))


def denormalize_y(norm_y: float) -> int:
    """Converts coordinate to physical pixel Y. Clamps safely away from (0,0)."""
    try:
        val = float(norm_y)
    except (TypeError, ValueError):
        raise ValueError(f"Invalid non-numeric coordinate for Y: {norm_y}")
    if val > 1000.0:
        pixel = int(val)
    elif val <= 1.0 and isinstance(norm_y, float):
        pixel = int(val * SCREEN_HEIGHT)
    else:
        pixel = int((val / 1000.0) * SCREEN_HEIGHT)
    return max(2, min(SCREEN_HEIGHT - 2, pixel))


# 5. Thread-Local MSS Instance (Fixes Windows GDI Device Context cross-thread BitBlt crash)
_thread_local = threading.local()

def get_thread_mss():
    """Returns a thread-safe, thread-local MSS instance."""
    if not hasattr(_thread_local, "sct"):
        ensure_desktop_access()
        _thread_local.sct = mss.MSS()
    return _thread_local.sct


def capture_desktop_screenshot(quality: int = 65) -> Tuple[bytes, str]:
    """
    Captures primary desktop buffer via thread-safe MSS (~20ms) and encodes directly to JPEG.
    Returns (raw_jpeg_bytes, base64_utf8_string).
    """
    ensure_desktop_access()
    img = None
    try:
        sct = get_thread_mss()
        monitor = sct.monitors[1]  # Primary monitor
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception:
        # Fallback to ImageGrab if GDI direct blit has issues
        img = ImageGrab.grab()

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    raw_bytes = buf.getvalue()
    b64_str = base64.b64encode(raw_bytes).decode("utf-8")
    return raw_bytes, b64_str


def capture_desktop_screenshot_adaptive(
    quality: int = 65,
    last_thumb: Optional[bytes] = None,
    force_encode: bool = False,
    diff_threshold: float = 2.0
) -> Tuple[Optional[bytes], bytes, bool]:
    """
    Perceptual Delta Screenshot Capture:
    1. Grabs primary monitor buffer via thread-safe MSS (~20ms).
    2. Computes 32x18 grayscale thumbnail to check visual delta.
    3. If visual difference < diff_threshold and not force_encode:
       Skips JPEG encoding entirely, saving 80% CPU and network bandwidth.
    4. If changed or force_encode:
       Encodes full desktop to JPEG at requested quality.

    Returns: (raw_jpeg_bytes_or_None, new_thumb_bytes, is_changed)
    """
    ensure_desktop_access()
    try:
        sct = get_thread_mss()
        monitor = sct.monitors[1]
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
    except Exception:
        img = ImageGrab.grab()

    # Fast 32x18 thumbnail for delta comparison
    thumb = img.resize((32, 18), Image.Resampling.BILINEAR).convert("L")
    new_thumb_bytes = thumb.tobytes()

    is_changed = True
    if last_thumb is not None and not force_encode:
        arr1 = np.frombuffer(new_thumb_bytes, dtype=np.uint8)
        arr2 = np.frombuffer(last_thumb, dtype=np.uint8)
        mean_diff = float(np.mean(np.abs(arr1.astype(np.int16) - arr2.astype(np.int16))))
        if mean_diff < diff_threshold:
            is_changed = False

    if not is_changed and not force_encode:
        return None, new_thumb_bytes, False

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue(), new_thumb_bytes, True


# 6. Key Mapping Dictionary (Gemini API Key Names -> PyAutoGUI Keys)
GEMINI_KEY_MAP = {
    "return": "enter",
    "enter": "enter",
    "escape": "esc",
    "esc": "esc",
    "backspace": "backspace",
    "tab": "tab",
    "space": "space",
    "delete": "delete",
    "up": "up",
    "down": "down",
    "left": "left",
    "right": "right",
    "home": "home",
    "end": "end",
    "pageup": "pageup",
    "pagedown": "pagedown",
    "win": "win",
    "windows": "win",
    "super": "win",
    "meta": "win",
    "ctrl": "ctrl",
    "control": "ctrl",
    "alt": "alt",
    "shift": "shift",
}

def normalize_key_name(key: str) -> str:
    cleaned = str(key).strip().lower()
    return GEMINI_KEY_MAP.get(cleaned, cleaned)


# 7. Native Unicode Hardware Typing via KEYEVENTF_UNICODE
def win32_type_unicode_char(char: str):
    """Sends a single UTF-16 character via hardware SendInput without virtual key mapping."""
    _check_failsafe()
    code = ord(char)
    inp_down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wScan=code, dwFlags=KEYEVENTF_UNICODE))
    inp_up = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(wScan=code, dwFlags=KEYEVENTF_UNICODE | KEYEVENTF_KEYUP))
    inputs = (INPUT * 2)(inp_down, inp_up)
    SendInput(2, inputs, ctypes.sizeof(INPUT))


def execute_paste(text: str, press_enter: bool = False, x: Optional[float] = None, y: Optional[float] = None):
    """
    Instant Windows Clipboard Injection (<15ms):
    - Sets text to Windows clipboard via pyperclip.
    - Sends native Win32 hardware Ctrl+V.
    - Completely eliminates IDE auto-indentation doubling (VS Code, Notepad++, PyCharm).
    - Preserves exact code structure, indentation, and Unicode characters.
    """
    ensure_desktop_access()
    _check_failsafe()
    if x is not None and y is not None:
        execute_click(x, y)
        time.sleep(0.08)

    # Normalize line endings to prevent Windows CRLF duplication
    clean_text = text.replace("\r\n", "\n").replace("\r", "\n")
    pyperclip.copy(clean_text)
    time.sleep(0.03)  # OS clipboard settle delay
    execute_hotkey(["ctrl", "v"])
    time.sleep(0.03)

    if press_enter:
        time.sleep(0.02)
        execute_press_key("enter")


def execute_type(text: str, press_enter: bool = False, x: Optional[float] = None, y: Optional[float] = None):
    """
    Intelligent adaptive typing:
    - For multi-line text (containing '\n' or '\t') or long blocks (>30 chars),
      automatically routes to execute_paste() to prevent IDE auto-indentation corruption.
    - For short single-line strings, uses KEYEVENTF_UNICODE hardware keystrokes.
    - Gracefully falls back to keystrokes if the Windows clipboard is locked.
    """
    ensure_desktop_access()

    # Fast path: use clipboard paste for multi-line or long code blocks
    if "\n" in text or "\t" in text or len(text) > 30:
        try:
            execute_paste(text, press_enter=press_enter, x=x, y=y)
            return
        except Exception:
            # Fall back to keystroke typing if clipboard is locked
            pass

    if x is not None and y is not None:
        execute_click(x, y)
        time.sleep(0.08)

    for ch in text:
        if ch == "\n":
            execute_press_key("enter")
        elif ch == "\t":
            execute_press_key("tab")
        else:
            win32_type_unicode_char(ch)
            time.sleep(0.005)

    if press_enter:
        time.sleep(0.02)
        execute_press_key("enter")


# 8. Turbo Atomic Motor Actuators (SetCursorPos + 15ms Electron-Safe Click)
def execute_click(x: float, y: float, button: str = "left", duration: float = 0.0):
    """
    Instant physical click:
    - SetCursorPos to exact pixel coordinate (avoids 0-65535 normalization drift)
    - 15ms frame-hold so Chromium, Electron, and Win11 apps never drop the click
    """
    ensure_desktop_access()
    _check_failsafe()
    px = denormalize_x(x)
    py = denormalize_y(y)
    
    SetCursorPos(px, py)
    
    if button == "right":
        down_flag, up_flag = MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP
    elif button == "middle":
        down_flag, up_flag = MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP
    else:
        down_flag, up_flag = MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP

    _send_mouse_event(down_flag)
    time.sleep(0.015)  # 15ms frame-hold for 60Hz UI message loops
    _send_mouse_event(up_flag)


def execute_double_click(x: float, y: float, duration: float = 0.0):
    """Executes high-speed double click with 60ms inter-click interval."""
    execute_click(x, y)
    time.sleep(0.06)
    execute_click(x, y)


def execute_triple_click(x: float, y: float, duration: float = 0.0):
    execute_click(x, y)
    time.sleep(0.06)
    execute_click(x, y)
    time.sleep(0.06)
    execute_click(x, y)


def execute_right_click(x: float, y: float, duration: float = 0.0):
    execute_click(x, y, button="right", duration=duration)


def execute_middle_click(x: float, y: float, duration: float = 0.0):
    execute_click(x, y, button="middle", duration=duration)


def execute_move(x: float, y: float, duration: float = 0.0):
    ensure_desktop_access()
    _check_failsafe()
    px = denormalize_x(x)
    py = denormalize_y(y)
    SetCursorPos(px, py)


def execute_press_key(key: str):
    ensure_desktop_access()
    _check_failsafe()
    k = normalize_key_name(key)
    _SAFETY_SHIELD.check_key(k)
    pyautogui.press(k)


def execute_hotkey(keys: List[str]):
    ensure_desktop_access()
    _check_failsafe()
    normalized = [normalize_key_name(k) for k in keys]
    _SAFETY_SHIELD.check_hotkey(normalized)
    pyautogui.hotkey(*normalized)


def execute_scroll(x: Optional[float] = None, y: Optional[float] = None, direction: str = "down", magnitude: int = 300):
    ensure_desktop_access()
    _check_failsafe()
    if x is not None and y is not None:
        px = denormalize_x(x)
        py = denormalize_y(y)
        SetCursorPos(px, py)
        time.sleep(0.05)
    
    clicks = int(magnitude) if int(magnitude) > 0 else 300
    scroll_amount = clicks if direction.lower() == "up" else -clicks
    pyautogui.scroll(scroll_amount)


def execute_drag_and_drop(start_x: float, start_y: float, end_x: float, end_y: float, duration: float = 0.3):
    """
    Precision Hardware Drag and Drop:
    Moves to start, presses left button, interpolates smoothly to end, and releases.
    """
    ensure_desktop_access()
    _check_failsafe()
    sx = denormalize_x(start_x)
    sy = denormalize_y(start_y)
    ex = denormalize_x(end_x)
    ey = denormalize_y(end_y)
    
    SetCursorPos(sx, sy)
    time.sleep(0.05)
    _send_mouse_event(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.02)
    
    steps = max(8, int(duration * 60))
    for i in range(1, steps + 1):
        _check_failsafe()
        t = i / steps
        ease_t = 1.0 - (1.0 - t) * (1.0 - t)
        cur_x = int(sx + (ex - sx) * ease_t)
        cur_y = int(sy + (ey - sy) * ease_t)
        SetCursorPos(cur_x, cur_y)
        time.sleep(duration / steps)
    
    SetCursorPos(ex, ey)
    time.sleep(0.02)
    _send_mouse_event(MOUSEEVENTF_LEFTUP)


def execute_wait(seconds: float = 1.0):
    time.sleep(max(0.05, min(10.0, float(seconds))))
