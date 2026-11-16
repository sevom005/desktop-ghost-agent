"""
Pure Win32 Window Management and Process Resolution Utilities
Implemented entirely via native Windows ctypes (user32, kernel32, dwmapi)
Zero external pywin32 dependencies for 100% portable reliability.

Hardened for Windows 10/11:
- Bypasses LockSetForegroundWindow via VK_NONAME (0xFC) thread attachment
- Strict EnumWindows filtering (ignores invisible, tool, cloaked, or <100x100 windows)
- Multi-source application path resolution (Registry App Paths + PATH + AppData)
- Modal dialog synchronization (#32770)
- Native QueryFullProcessImageNameW for zero-dependency PID-to-executable resolution
"""

import os
import re
import sys
import time
import shutil
import winreg
import ctypes
from dataclasses import dataclass, field
from ctypes import wintypes
from typing import Optional, List, Tuple, Dict, Any

# Win32 API DLLs
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
dwmapi = ctypes.windll.dwmapi

# Win32 Constants
SW_MAXIMIZE = 3
SW_SHOW = 5
SW_RESTORE = 9
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
DWMWA_CLOAKED = 14
VK_NONAME = 0xFC
KEYEVENTF_KEYUP = 0x0002
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

# Win32 Structures
class RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long)
    ]

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)


def find_app_executable(app_name: str) -> Optional[str]:
    """
    Resolves the full path to a Windows executable across multiple registries and paths:
    1. System PATH
    2. Registry App Paths (HKCU and HKLM)
    3. Standard Local/Roaming AppData directories
    4. Program Files & Windows System directories
    """
    clean_name = app_name.strip().lower()
    if not clean_name.endswith(".exe") and "." not in clean_name:
        exe_name = f"{clean_name}.exe"
    else:
        exe_name = clean_name

    # 1. Check system PATH
    direct_path = shutil.which(exe_name) or shutil.which(clean_name)
    if direct_path and os.path.exists(direct_path):
        return os.path.abspath(direct_path)

    # 2. Check Windows Registry App Paths
    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for subkey in (
            rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}",
            rf"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths\{exe_name}"
        ):
            try:
                with winreg.OpenKey(root, subkey) as key:
                    val, _ = winreg.QueryValueEx(key, "")
                    if val:
                        val = val.strip('"\'' )
                        if os.path.exists(val):
                            return os.path.abspath(val)
            except Exception:
                pass

    # 3. Known application paths
    appdata = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    progfiles = os.environ.get("ProgramFiles", "C:\\Program Files")
    progfiles86 = os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")
    windir = os.environ.get("WINDIR", "C:\\Windows")

    candidates = [
        # Chrome
        os.path.join(progfiles, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(progfiles86, "Google", "Chrome", "Application", "chrome.exe"),
        os.path.join(localappdata, "Google", "Chrome", "Application", "chrome.exe"),
        # MS Paint
        os.path.join(windir, "system32", "mspaint.exe"),
        # Notepad
        os.path.join(windir, "system32", "notepad.exe"),
        os.path.join(windir, "notepad.exe"),
        # Explorer
        os.path.join(windir, "explorer.exe"),
        # Telegram
        os.path.join(appdata, "Telegram Desktop", "Telegram.exe"),
        os.path.join(localappdata, "Programs", "Telegram Desktop", "Telegram.exe"),
        # VS Code
        os.path.join(localappdata, "Programs", "Microsoft VS Code", "Code.exe"),
        # Notepad++
        os.path.join(progfiles, "Notepad++", "notepad++.exe"),
        os.path.join(progfiles86, "Notepad++", "notepad++.exe"),
        os.path.join(localappdata, "Programs", "Notepad++", "notepad++.exe"),
    ]

    for cand in candidates:
        if os.path.basename(cand).lower() == exe_name.lower() and os.path.exists(cand):
            return os.path.abspath(cand)

    return None


def get_process_image_path(pid: int) -> Optional[str]:
    """Returns the full executable path of a process ID via kernel32."""
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return None
    try:
        buff = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buff, ctypes.byref(size)):
            return buff.value
    finally:
        kernel32.CloseHandle(handle)
    return None


def get_window_title(hwnd: int) -> str:
    """Gets window title string via user32."""
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0:
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value
    return ""


def get_window_class(hwnd: int) -> str:
    """Gets window class name string via user32."""
    buff = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buff, 256)
    return buff.value


def is_window_valid_target(hwnd: int) -> bool:
    """
    Filters out invisible, cloaked, tool windows, or tiny helper surfaces.
    Ensures only interactive, renderable application windows are matched.
    """
    if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
        return False

    # Check window dimensions (must be > 100x100 to exclude hidden helper surfaces)
    rect = RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return False
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    if width < 100 or height < 100:
        return False

    # Exclude tool windows (tooltips, tray popups)
    try:
        ex_style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        if ex_style & WS_EX_TOOLWINDOW:
            return False
    except Exception:
        pass

    # Check DWM Cloaking (Windows 10/11 Virtual Desktops & UWP suspensions)
    try:
        cloaked = wintypes.DWORD()
        res = dwmapi.DwmGetWindowAttribute(
            wintypes.HWND(hwnd),
            wintypes.DWORD(DWMWA_CLOAKED),
            ctypes.byref(cloaked),
            ctypes.sizeof(cloaked)
        )
        if res == 0 and cloaked.value != 0:
            return False
    except Exception:
        pass

    return True


def force_foreground_window(hwnd: int) -> bool:
    """
    Bypasses Windows 10/11 LockSetForegroundWindow restrictions.
    Uses VK_NONAME (0xFC) paired keystrokes and AttachThreadInput to ensure
    the target window receives immediate focus without sticking the Alt key.
    """
    if not hwnd or not user32.IsWindow(hwnd):
        return False

    try:
        # If minimized, restore first
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        fore_hwnd = user32.GetForegroundWindow()
        if fore_hwnd == hwnd:
            return True

        fore_pid = wintypes.DWORD()
        fore_thread = user32.GetWindowThreadProcessId(fore_hwnd, ctypes.byref(fore_pid))

        target_pid = wintypes.DWORD()
        target_thread = user32.GetWindowThreadProcessId(hwnd, ctypes.byref(target_pid))

        cur_thread = kernel32.GetCurrentThreadId()

        attached_fore = False
        attached_target = False

        if fore_thread and fore_thread != cur_thread:
            try:
                user32.AttachThreadInput(cur_thread, fore_thread, True)
                attached_fore = True
            except Exception:
                pass

        if target_thread and target_thread != cur_thread:
            try:
                user32.AttachThreadInput(cur_thread, target_thread, True)
                attached_target = True
            except Exception:
                pass

        # Safe synthetic keystroke: VK_NONAME (0xFC) paired DOWN then UP
        user32.keybd_event(VK_NONAME, 0, 0, 0)
        user32.keybd_event(VK_NONAME, 0, KEYEVENTF_KEYUP, 0)

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

        # Cleanup thread attachment
        if attached_fore:
            try:
                user32.AttachThreadInput(cur_thread, fore_thread, False)
            except Exception:
                pass
        if attached_target:
            try:
                user32.AttachThreadInput(cur_thread, target_thread, False)
            except Exception:
                pass

        return True
    except Exception:
        try:
            user32.SetForegroundWindow(hwnd)
            return True
        except Exception:
            return False


def wait_for_visible_window(
    title_keywords: Optional[List[str]] = None,
    process_names: Optional[List[str]] = None,
    timeout: float = 4.0
) -> Optional[int]:
    """
    Polls top-level windows until a matching, visible, non-cloaked application window appears.
    Returns the target HWND or None if timed out.
    """
    start_time = time.time()
    title_keywords = [k.lower() for k in (title_keywords or [])]
    process_names = [p.lower() for p in (process_names or [])]

    while time.time() - start_time < timeout:
        matches = []

        def enum_cb(hwnd, lparam):
            if not is_window_valid_target(hwnd):
                return True

            title = get_window_title(hwnd).strip().lower()
            
            # Check title match
            if title_keywords and any(k in title for k in title_keywords):
                matches.append(hwnd)
                return False

            # Check process name match
            if process_names:
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                if pid.value:
                    exe_path = get_process_image_path(pid.value)
                    if exe_path:
                        exe_name = os.path.basename(exe_path).lower()
                        if any(p in exe_name for p in process_names):
                            matches.append(hwnd)
                            return False

            return True

        cb = WNDENUMPROC(enum_cb)
        user32.EnumWindows(cb, 0)

        if matches:
            return matches[0]

        time.sleep(0.08)

    return None


def wait_for_dialog(timeout: float = 2.0) -> Optional[int]:
    """
    Polls until a Windows modal dialog (#32770, e.g. 'Save As', 'Open') appears and has focus.
    Returns dialog HWND or None.
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        fore = user32.GetForegroundWindow()
        if fore and user32.IsWindow(fore):
            cls_name = get_window_class(fore)
            if cls_name == "#32770":
                return fore
        time.sleep(0.06)
    return None


def maximize_window(hwnd: int) -> bool:
    """Maximizes the target window."""
    try:
        if hwnd and user32.IsWindow(hwnd):
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            return True
    except Exception:
        pass
    return False


def get_window_rect(hwnd: int) -> Optional[Tuple[int, int, int, int]]:
    """Returns (left, top, right, bottom) of target window."""
    try:
        if hwnd and user32.IsWindow(hwnd):
            rect = RECT()
            if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    return None


# ── Spatial Consciousness & Editor Breadcrumb Resolution (Pillar 3) ────────

KNOWN_EDITOR_PROCESSES = {
    "code.exe",
    "notepad++.exe",
    "notepad.exe",
    "sublime_text.exe",
    "devenv.exe",
    "pycharm64.exe",
    "idea64.exe",
}

# Regex patterns for breadcrumb extraction
_VSCODE_FILE_RE = re.compile(
    r"^(?:●\s*)?([^\-\\\/]+\.[a-zA-Z0-9_\-]+)\s+-\s+(?:([^\-]+?)\s+-\s+)?Visual Studio Code",
    re.IGNORECASE
)
_VSCODE_WORKSPACE_RE = re.compile(
    r"^([^\-\\\/]+)\s+-\s+Visual Studio Code",
    re.IGNORECASE
)
_NOTEPAD_PP_FULLPATH_RE = re.compile(
    r"^(?:\*\s*)?([a-zA-Z]:\\[^\-\r\n]+?\.[a-zA-Z0-9_\-]+)\s+-\s+Notepad\+\+",
    re.IGNORECASE
)
_NOTEPAD_PP_NAME_RE = re.compile(
    r"^(?:\*\s*)?([^\-\\\/]+(?:\.[a-zA-Z0-9_\-]+)?)\s+-\s+Notepad\+\+",
    re.IGNORECASE
)
_NOTEPAD_RE = re.compile(
    r"^(?:\*\s*)?([^\-\\\/]+(?:\.[a-zA-Z0-9_\-]+)?)\s+-\s+Notepad",
    re.IGNORECASE
)


@dataclass
class ActiveSpatialContext:
    hwnd: int = 0
    app_name: str = ""                  # e.g. "code.exe", "notepad++.exe", "chrome.exe"
    window_title: str = ""              # Raw title bar text
    window_class: str = ""              # e.g. "Chrome_WidgetWin_1", "Notepad++"
    file_name: Optional[str] = None     # e.g. "train_rnn.py"
    file_path: Optional[str] = None     # e.g. "C:\Users\...\train_rnn.py"
    workspace_name: Optional[str] = None # e.g. "Computer_Use"
    workspace_dir: Optional[str] = None  # e.g. "C:\Users\...\Computer_Use"
    is_editor: bool = False             # True if window is a code editor
    is_dirty: bool = False              # True if file has unsaved changes
    confidence: float = 0.0             # 0.0 to 1.0 confidence score


def is_editor_window(hwnd: int) -> bool:
    """Returns True if the given window belongs to a recognized code/text editor."""
    if not hwnd or not user32.IsWindow(hwnd):
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    if pid.value:
        exe_path = get_process_image_path(pid.value)
        if exe_path:
            base_exe = os.path.basename(exe_path).lower()
            if base_exe in KNOWN_EDITOR_PROCESSES:
                return True
    cls_name = get_window_class(hwnd)
    if cls_name in ("Notepad++", "Notepad"):
        return True
    title = get_window_title(hwnd).lower()
    if "visual studio code" in title or "notepad++" in title or title.endswith(" - notepad"):
        return True
    return False


def _find_file_in_workspace(file_name: str, workspace_root: str) -> Optional[str]:
    """Finds an existing file by name within the workspace tree in <5ms."""
    if not workspace_root or not os.path.isdir(workspace_root):
        return None

    # 1. Direct check in root
    direct_path = os.path.join(workspace_root, file_name)
    if os.path.isfile(direct_path):
        return os.path.abspath(direct_path)

    # 2. Shallow directory walk (skip large/irrelevant directories)
    skip_dirs = {".git", "__pycache__", "venv", ".venv", "node_modules", "build", "dist", ".gemini"}
    for root, dirs, files in os.walk(workspace_root):
        dirs[:] = [d for d in dirs if d.lower() not in skip_dirs and not d.startswith(".")]
        if file_name in files:
            return os.path.abspath(os.path.join(root, file_name))

    return None


def parse_window_breadcrumbs(
    title: str,
    exe_name: str = "",
    workspace_root: Optional[str] = None
) -> ActiveSpatialContext:
    """
    Parses application breadcrumbs from window title and resolves open file paths.
    Supports VS Code, Notepad++, and Windows Notepad.
    """
    clean_title = (title or "").strip()
    clean_exe = (exe_name or "").lower()
    base_exe = os.path.basename(clean_exe) if clean_exe else ""

    ctx = ActiveSpatialContext(
        window_title=clean_title,
        app_name=base_exe
    )

    if not clean_title:
        return ctx

    # Determine default workspace directory
    base_dir = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ctx.workspace_dir = os.path.abspath(base_dir) if os.path.exists(base_dir) else base_dir
    ctx.workspace_name = os.path.basename(ctx.workspace_dir)

    is_editor = (
        base_exe in KNOWN_EDITOR_PROCESSES
        or "visual studio code" in clean_title.lower()
        or "notepad++" in clean_title.lower()
        or clean_title.lower().endswith(" - notepad")
    )
    ctx.is_editor = is_editor

    # 1. Visual Studio Code
    if "visual studio code" in clean_title.lower() or base_exe == "code.exe":
        ctx.app_name = "code.exe"
        ctx.is_editor = True
        ctx.is_dirty = clean_title.startswith("●") or "●" in clean_title

        m_file = _VSCODE_FILE_RE.match(clean_title)
        if m_file:
            ctx.file_name = m_file.group(1).strip()
            ws_name = m_file.group(2)
            if ws_name:
                ctx.workspace_name = ws_name.strip()

            # Resolve file path
            found_path = _find_file_in_workspace(ctx.file_name, ctx.workspace_dir)
            if found_path:
                ctx.file_path = found_path
                ctx.confidence = 0.98
            else:
                ctx.file_path = os.path.join(ctx.workspace_dir, ctx.file_name)
                ctx.confidence = 0.90
            return ctx

        # Check workspace/folder-only view in VS Code
        m_ws = _VSCODE_WORKSPACE_RE.match(clean_title)
        if m_ws:
            ctx.workspace_name = m_ws.group(1).strip()
            ctx.confidence = 0.70
            return ctx

    # 2. Notepad++
    if "notepad++" in clean_title.lower() or base_exe == "notepad++.exe":
        ctx.app_name = "notepad++.exe"
        ctx.is_editor = True
        ctx.is_dirty = clean_title.startswith("*")

        # Check full path match first
        m_full = _NOTEPAD_PP_FULLPATH_RE.match(clean_title)
        if m_full:
            full_path = m_full.group(1).strip()
            ctx.file_path = os.path.abspath(full_path)
            ctx.file_name = os.path.basename(ctx.file_path)
            ctx.confidence = 1.0
            return ctx

        # Check simple filename or scratch buffer
        m_name = _NOTEPAD_PP_NAME_RE.match(clean_title)
        if m_name:
            fname = m_name.group(1).strip()
            ctx.file_name = fname
            if fname.lower().startswith("new "):
                ctx.confidence = 0.80
                ctx.file_path = os.path.join(ctx.workspace_dir, f"{fname.replace(' ', '_')}.txt")
            else:
                found_path = _find_file_in_workspace(fname, ctx.workspace_dir)
                ctx.file_path = found_path or os.path.join(ctx.workspace_dir, fname)
                ctx.confidence = 0.92 if found_path else 0.85
            return ctx

    # 3. Windows Notepad
    if clean_title.lower().endswith(" - notepad") or base_exe == "notepad.exe":
        ctx.app_name = "notepad.exe"
        ctx.is_editor = True
        ctx.is_dirty = clean_title.startswith("*")
        m_np = _NOTEPAD_RE.match(clean_title)
        if m_np:
            fname = m_np.group(1).strip()
            ctx.file_name = fname
            if fname.lower() == "untitled":
                ctx.confidence = 0.75
                ctx.file_path = os.path.join(ctx.workspace_dir, "untitled.txt")
            else:
                found_path = _find_file_in_workspace(fname, ctx.workspace_dir)
                ctx.file_path = found_path or os.path.join(ctx.workspace_dir, fname)
                ctx.confidence = 0.90 if found_path else 0.80
            return ctx

    # 4. Google Chrome
    if " - google chrome" in clean_title.lower() or base_exe == "chrome.exe":
        ctx.app_name = "chrome.exe"
        ctx.confidence = 0.60
        return ctx

    ctx.confidence = 0.30
    return ctx


def get_active_spatial_context(workspace_root: Optional[str] = None) -> ActiveSpatialContext:
    """
    Returns the ActiveSpatialContext of the active foreground window.
    Falls back gracefully to enumerating interactive windows on Desktop 'Default'
    if running in a detached desktop session.
    """
    fore_hwnd = user32.GetForegroundWindow()
    target_hwnd = fore_hwnd if (fore_hwnd and user32.IsWindow(fore_hwnd) and is_window_valid_target(fore_hwnd)) else 0

    # Fallback if foreground HWND is 0 (e.g. running from background task)
    if not target_hwnd:
        # Check if Default desktop has an active editor
        h_desk = user32.OpenDesktopW("Default", 0, False, 0x0100)
        candidate_hwnds = []
        if h_desk:
            def enum_cb(h, lparam):
                if is_window_valid_target(h):
                    candidate_hwnds.append(h)
                return True
            cb_proc = WNDENUMPROC(enum_cb)
            user32.EnumDesktopWindows(h_desk, cb_proc, 0)
            user32.CloseDesktop(h_desk)

            # Prioritize editor windows first
            for h in candidate_hwnds:
                if is_editor_window(h):
                    target_hwnd = h
                    break
            if not target_hwnd and candidate_hwnds:
                target_hwnd = candidate_hwnds[0]

    if not target_hwnd:
        base_dir = workspace_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return ActiveSpatialContext(
            workspace_dir=os.path.abspath(base_dir),
            workspace_name=os.path.basename(base_dir)
        )

    title = get_window_title(target_hwnd)
    cls_name = get_window_class(target_hwnd)
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(target_hwnd, ctypes.byref(pid))
    exe_path = get_process_image_path(pid.value) if pid.value else None
    base_exe = os.path.basename(exe_path).lower() if exe_path else ""

    ctx = parse_window_breadcrumbs(title, base_exe, workspace_root=workspace_root)
    ctx.hwnd = target_hwnd
    ctx.window_class = cls_name
    if not ctx.app_name and base_exe:
        ctx.app_name = base_exe
    return ctx
