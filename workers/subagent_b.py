"""
Desktop Ghost Live Agent v2 — Sub-Agent B (Headless System Worker)
==================================================================
Autonomous headless execution worker for Desktop Ghost.
Runs tasks silently in the background of Windows 10 without mouse or screen takeover.

Key Capabilities:
  - 100% Headless: PowerShell (-NonInteractive), Python, and native Windows telemetry.
  - Zero Voice Lag: Runs in detached threads powered by gemini-3.5-flash-lite.
  - Dual Rate-Limit Protection: Uses GEMINI_API_KEY2 to leave Nova's stream unimpeded.
  - Dual PID Friendly-Fire Protection:
      1. Protects Nova's Python process (os.getpid()), parents, and children.
      2. Protects active foreground window PID (Shvan's game, code editor, browser).
      3. Protects Windows core system processes (explorer, csrss, lsass, etc.).
  - Real-Time Blackboard Updates: Posts 1-line progress updates to TaskBlackboard in RAM.
  - Zero-Dependency Resilience: Native Windows ctypes & tasklist fallback if psutil is absent.
"""

import os
import sys
import csv
import re
import json
import time
import datetime
import shutil
import ctypes
import signal
import threading
import subprocess
import traceback
from ctypes import wintypes
from typing import Optional, List, Dict, Any, Tuple, Callable

# Add workspace root to sys.path
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(_BASE_DIR, ".env"))

from google import genai
from google.genai import types

from memory.task_blackboard import get_task_blackboard, TaskStatus

SUBAGENT_PRIMARY_MODEL = os.getenv("SUBAGENT_MODEL", "gemini-3.5-flash-lite")
SUBAGENT_FALLBACK_MODELS = [
    SUBAGENT_PRIMARY_MODEL,
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
]
SUBAGENT_MODEL_CASCADE = list(dict.fromkeys(SUBAGENT_FALLBACK_MODELS))
SUBAGENT_MODEL = SUBAGENT_PRIMARY_MODEL
MAX_STEPS = 5

SYSTEM_BLACKLIST_NAMES = {
    "explorer.exe", "csrss.exe", "lsass.exe", "winlogon.exe", "services.exe",
    "smss.exe", "svchost.exe", "system", "registry", "dwm.exe", "spoolsv.exe",
    "antigravity.exe"
}

# ── Process Tree Management & Cancellation ──────────────────────────────────
_active_subprocesses: Dict[str, subprocess.Popen] = {}
_cancel_events: Dict[str, threading.Event] = {}
_proc_lock = threading.Lock()


def _kill_proc_tree(pid: int) -> None:
    """Uses native Windows taskkill /F /T /PID to force-kill a process and its child tree."""
    try:
        subprocess.run(
            ["taskkill.exe", "/F", "/T", "/PID", str(pid)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
    except Exception:
        pass


def cancel_running_task(task_id: Optional[str] = None, reason: str = "User requested cancellation") -> bool:
    """
    Aborts a running background task:
    1. Sets its cooperative cancellation event.
    2. Tree-kills any active child subprocess via taskkill /F /T /PID.
    3. Marks the task CANCELLED on the TaskBlackboard.
    """
    board = get_task_blackboard()
    target_id = task_id or board._active_task_id
    if not target_id:
        return False

    with _proc_lock:
        ev = _cancel_events.get(target_id)
        if ev:
            ev.set()

        proc = _active_subprocesses.get(target_id)
        if proc and proc.poll() is None:
            _kill_proc_tree(proc.pid)

    return board.cancel_task(target_id, reason=reason)


# ── Windows ctypes Memory Status ─────────────────────────────────────────────

class _MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [
        ('dwLength', ctypes.c_ulong),
        ('dwMemoryLoad', ctypes.c_ulong),
        ('ullTotalPhys', ctypes.c_ulonglong),
        ('ullAvailPhys', ctypes.c_ulonglong),
        ('ullTotalPageFile', ctypes.c_ulonglong),
        ('ullAvailPageFile', ctypes.c_ulonglong),
        ('ullTotalVirtual', ctypes.c_ulonglong),
        ('ullAvailVirtual', ctypes.c_ulonglong),
        ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
    ]


class _FILETIME(ctypes.Structure):
    _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]


def _get_cpu_percent(sample_interval: float = 0.05) -> float:
    """Calculates instantaneous CPU load percentage via kernel32.GetSystemTimes."""
    try:
        def get_times():
            idle, kernel, user = _FILETIME(), _FILETIME(), _FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kernel), ctypes.byref(user))
            i = (idle.dwHighDateTime << 32) + idle.dwLowDateTime
            k = (kernel.dwHighDateTime << 32) + kernel.dwLowDateTime
            u = (user.dwHighDateTime << 32) + user.dwLowDateTime
            return i, k, u

        i1, k1, u1 = get_times()
        time.sleep(sample_interval)
        i2, k2, u2 = get_times()

        idle_delta = i2 - i1
        total_delta = (k2 - k1) + (u2 - u1)
        if total_delta > 0:
            pct = 100.0 * (1.0 - (idle_delta / total_delta))
            return round(max(0.0, min(100.0, pct)), 1)
    except Exception:
        pass
    return 0.0


# ── Process Protection Helpers ───────────────────────────────────────────────

def get_foreground_process_info() -> Tuple[Optional[int], Optional[str]]:
    """Returns (pid, process_name) of the currently active focused foreground window."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None, None
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        fg_pid = pid.value
        if fg_pid > 0:
            name = get_process_name_by_pid(fg_pid)
            return fg_pid, name
    except Exception:
        pass
    return None, None


def get_process_name_by_pid(pid: int) -> Optional[str]:
    """Resolves a process name given its PID."""
    if pid <= 0:
        return None
    try:
        # Fast native tasklist check
        out = subprocess.check_output(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            text=True,
            errors="replace"
        )
        reader = csv.reader(out.strip().splitlines())
        for row in reader:
            if len(row) >= 2 and row[1].strip() == str(pid):
                return row[0].strip().lower()
    except Exception:
        pass
    return None


def get_protected_entities() -> Tuple[set[int], set[str]]:
    """
    Returns (protected_pids, protected_process_names).
    Covers:
      1. Nova's own Python process and parent shell.
      2. Active foreground window (e.g. Shvan's active game or editor).
      3. Critical Windows system processes.
    """
    protected_pids: set[int] = set()
    protected_names: set[str] = set(SYSTEM_BLACKLIST_NAMES)

    # 1. Nova's process
    my_pid = os.getpid()
    protected_pids.add(my_pid)
    protected_names.add("python.exe")

    # 2. Foreground window
    fg_pid, fg_name = get_foreground_process_info()
    if fg_pid and fg_pid > 0:
        protected_pids.add(fg_pid)
    if fg_name:
        protected_names.add(fg_name.lower())

    return protected_pids, protected_names


def is_protected(pid: Optional[int] = None, name: Optional[str] = None) -> Tuple[bool, str]:
    """Checks if a PID or process name is protected from termination."""
    protected_pids, protected_names = get_protected_entities()
    if pid is not None and pid in protected_pids:
        return True, f"PID {pid} is protected (Nova copilot or active foreground window)."
    if name is not None:
        clean_name = name.lower().strip()
        if not clean_name.endswith(".exe"):
            clean_name += ".exe"
        if clean_name in protected_names or name.lower() in protected_names:
            return True, f"Process '{name}' is protected (System process, Nova, or active foreground game)."
    return False, ""


# ── Native Headless Tools ────────────────────────────────────────────────────

def get_system_telemetry() -> str:
    """Returns CPU, RAM, Disk utilization and top memory processes with protection flags."""
    try:
        cpu_pct = _get_cpu_percent(sample_interval=0.05)

        # RAM usage via GlobalMemoryStatusEx
        stat = _MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(_MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))

        ram_load = stat.dwMemoryLoad
        total_ram_gb = round(stat.ullTotalPhys / (1024**3), 1)
        used_ram_gb = round((stat.ullTotalPhys - stat.ullAvailPhys) / (1024**3), 1)

        # Disk usage via shutil
        du = shutil.disk_usage("C:\\")
        disk_free_gb = round(du.free / (1024**3), 1)

        protected_pids, protected_names = get_protected_entities()

        # Top processes via tasklist CSV
        out = subprocess.check_output(
            ["tasklist", "/FO", "CSV", "/NH"],
            creationflags=subprocess.CREATE_NO_WINDOW,
            text=True,
            errors="replace"
        )
        procs = []
        reader = csv.reader(out.strip().splitlines())
        for row in reader:
            if len(row) >= 5:
                name = row[0].strip()
                try:
                    pid = int(row[1].strip())
                except ValueError:
                    continue
                mem_str = re.sub(r"[^\d]", "", row[4])
                mem_kb = int(mem_str) if mem_str else 0
                mem_mb = round(mem_kb / 1024, 1)

                is_prot = (pid in protected_pids) or (name.lower() in protected_names)
                procs.append({
                    "pid": pid,
                    "name": name,
                    "mem_mb": mem_mb,
                    "protected": is_prot
                })

        procs.sort(key=lambda x: x["mem_mb"], reverse=True)
        top_ram = procs[:6]

        lines = [
            "══ SYSTEM TELEMETRY ══",
            f"CPU Load: {cpu_pct}%",
            f"RAM Usage: {ram_load}% ({used_ram_gb}GB / {total_ram_gb}GB used)",
            f"Disk C: Free: {disk_free_gb}GB",
            "\nTop Processes by RAM:"
        ]
        for p in top_ram:
            prot_flag = " [PROTECTED — DO NOT KILL]" if p["protected"] else ""
            lines.append(f"  • PID {p['pid']:<6} {p['name']:<22} {p['mem_mb']}MB{prot_flag}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error gathering telemetry: {e}"


def kill_process(pid: int) -> str:
    """Terminates an unneeded process by numeric PID if it is not protected."""
    try:
        pid = int(pid)
    except (ValueError, TypeError):
        return f"ERROR: Invalid PID '{pid}'."

    prot, reason = is_protected(pid=pid)
    if prot:
        return f"DENIED: Cannot terminate PID {pid}: {reason}"

    proc_name = get_process_name_by_pid(pid)
    if proc_name:
        prot_name, reason_name = is_protected(name=proc_name)
        if prot_name:
            return f"DENIED: Cannot terminate '{proc_name}': {reason_name}"

    try:
        # Use taskkill on Windows
        res = subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if res.returncode == 0:
            return f"SUCCESS: Terminated process (PID {pid})."
        else:
            return f"ERROR: taskkill failed: {res.stderr.strip() or res.stdout.strip()}"
    except Exception as e:
        return f"ERROR terminating PID {pid}: {e}"


def run_powershell(command: str, task_id: Optional[str] = None) -> str:
    """
    Executes a silent PowerShell command with -NonInteractive and 30s timeout.
    Prevents termination of protected processes by name or PID.
    """
    cmd_lower = command.lower()

    # Friendly-fire guard against process killing commands in PowerShell
    if "stop-process" in cmd_lower or "taskkill" in cmd_lower:
        protected_pids, protected_names = get_protected_entities()
        for pn in protected_names:
            base_name = pn.replace(".exe", "")
            if f"-name {base_name}" in cmd_lower or f"-name {pn}" in cmd_lower or f"/im {pn}" in cmd_lower:
                return f"DENIED: Command targets protected process '{pn}'. Use kill_process(pid) instead."
        for p in protected_pids:
            if f"-id {p}" in cmd_lower or f"/pid {p}" in cmd_lower:
                return f"DENIED: Command targets protected PID {p}."

    proc = None
    try:
        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-Command", command
        ]
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if task_id:
            with _proc_lock:
                _active_subprocesses[task_id] = proc

        stdout, stderr = proc.communicate(timeout=30)
        out = (stdout or "") + (stderr or "")
        if len(out) > 1000:
            out = out[:1000] + "... [truncated]"
        return out.strip() if out.strip() else "(command completed with no output)"
    except subprocess.TimeoutExpired:
        if proc:
            _kill_proc_tree(proc.pid)
        return "ERROR: PowerShell command timed out after 30 seconds."
    except Exception as e:
        return f"ERROR running PowerShell: {e}"
    finally:
        if task_id:
            with _proc_lock:
                _active_subprocesses.pop(task_id, None)


def run_python_script(code: str, task_id: Optional[str] = None) -> str:
    """Executes a Python code snippet in the background with a 30s timeout and cancellation tracking."""
    proc = None
    try:
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        if task_id:
            with _proc_lock:
                _active_subprocesses[task_id] = proc

        stdout, stderr = proc.communicate(timeout=30)
        out = (stdout or "") + (stderr or "")
        if len(out) > 1000:
            out = out[:1000] + "... [truncated]"
        return out.strip() if out.strip() else "(script completed with no output)"
    except subprocess.TimeoutExpired:
        if proc:
            _kill_proc_tree(proc.pid)
        return "ERROR: Python script timed out after 30 seconds."
    except Exception as e:
        return f"ERROR running Python script: {e}"
    finally:
        if task_id:
            with _proc_lock:
                _active_subprocesses.pop(task_id, None)


# Standard workspace directory for Sub-Agent B artifacts
_WORKER_WORKSPACE_DIR = os.path.join(_BASE_DIR, "workers", "workspace_worker")


def resolve_workspace_path(path: str) -> str:
    """
    Standardizes and resolves file paths for Sub-Agent B into workers/workspace_worker/.
    Routes by extension unless an absolute path or explicit path is provided:
      - .html, .htm, .css, .js -> workers/workspace_worker/html/
      - .txt, .md, .json, .csv -> workers/workspace_worker/notes/
      - .py, .ps1, .bat, .sh   -> workers/workspace_worker/scripts/
      - other extensions       -> workers/workspace_worker/outputs/
    """
    clean = path.strip().strip("'\"")
    expanded = os.path.expanduser(clean)

    # 1. If absolute path provided, preserve it exactly
    if os.path.isabs(expanded):
        return os.path.abspath(expanded)

    # 2. If path already specifies workspace_worker explicitly, resolve against _BASE_DIR
    norm = expanded.replace("/", "\\")
    if norm.startswith("workers\\workspace_worker") or norm.startswith(".\\workers\\workspace_worker"):
        return os.path.abspath(os.path.join(_BASE_DIR, expanded))

    # 3. Determine target subfolder by file extension
    base_name = os.path.basename(expanded)
    _, ext = os.path.splitext(base_name.lower())

    if ext in (".html", ".htm", ".css", ".js"):
        sub = "html"
    elif ext in (".txt", ".md", ".json", ".csv"):
        sub = "notes"
    elif ext in (".py", ".ps1", ".bat", ".sh"):
        sub = "scripts"
    else:
        sub = "outputs"

    target_dir = os.path.join(_WORKER_WORKSPACE_DIR, sub)
    # If a subpath was specified, keep it under target_dir, else just base_name
    rel_subpath = expanded if os.path.dirname(expanded) else base_name
    return os.path.abspath(os.path.join(target_dir, rel_subpath))


def read_file(path: str) -> str:
    """Reads a text file from disk, checking workspace_worker and project root."""
    try:
        resolved = resolve_workspace_path(path)
        # If resolved doesn't exist, but relative to _BASE_DIR exists, prefer that
        raw_full = os.path.join(_BASE_DIR, os.path.expanduser(path.strip().strip("'\"")))
        if not os.path.exists(resolved) and os.path.exists(raw_full):
            full_path = raw_full
        else:
            full_path = resolved

        with open(full_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        if len(content) > 2000:
            content = content[:2000] + "... [truncated]"
        return content
    except Exception as e:
        return f"ERROR reading {path}: {e}"


def write_file(path: str, content: str, task_id: Optional[str] = None) -> str:
    """
    Writes text content to a file in workers/workspace_worker/ (or absolute path).
    Records the resulting artifact in TaskBlackboard.
    Creates an atomic pre-edit backup snapshot if the file already exists and has content.
    """
    try:
        full_path = resolve_workspace_path(path)
        os.makedirs(os.path.dirname(os.path.abspath(full_path)), exist_ok=True)

        # Pre-Edit Atomic Backup Snapshot (Pillar 3 Anti-Wipe Shield)
        if os.path.exists(full_path) and os.path.getsize(full_path) > 0:
            try:
                backup_dir = os.path.join(_WORKER_WORKSPACE_DIR, ".backups")
                os.makedirs(backup_dir, exist_ok=True)
                ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                base_name = os.path.basename(full_path)
                backup_file = os.path.join(backup_dir, f"{base_name}.{ts}.bak")
                shutil.copy2(full_path, backup_file)
            except Exception as e:
                print(f"[SUB-AGENT B] Warning: pre-edit backup snapshot failed: {e}")

        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Record artifact on TaskBlackboard
        try:
            board = get_task_blackboard()
            board.record_artifact(task_id or "", full_path)
        except Exception as e:
            print(f"[SUB-AGENT B] Warning: failed to record artifact: {e}")

        return f"SUCCESS: Wrote {len(content)} characters to {full_path}"
    except Exception as e:
        return f"ERROR writing to {path}: {e}"


# ── Tool Registry for Sub-Agent B ────────────────────────────────────────────

SUBAGENT_TOOL_DECLARATIONS = [
    types.FunctionDeclaration(
        name="get_system_telemetry",
        description="Inspects RAM usage %, and lists top processes by RAM with protection flags.",
        parameters=types.Schema(type="OBJECT", properties={})
    ),
    types.FunctionDeclaration(
        name="kill_process",
        description="Terminates an unneeded process by numeric PID. Strictly prevents terminating Nova or the active foreground window.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "pid": types.Schema(type="INTEGER", description="The numeric Process ID (PID) to terminate.")
            },
            required=["pid"]
        )
    ),
    types.FunctionDeclaration(
        name="run_powershell",
        description="Executes a non-interactive PowerShell command in the background. Use kill_process instead of Stop-Process.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "command": types.Schema(type="STRING", description="The PowerShell command line to execute.")
            },
            required=["command"]
        )
    ),
    types.FunctionDeclaration(
        name="run_python_script",
        description="Executes a Python code snippet safely in the background with a 30s timeout.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "code": types.Schema(type="STRING", description="Python code string to execute.")
            },
            required=["code"]
        )
    ),
    types.FunctionDeclaration(
        name="read_file",
        description="Reads the text contents of a file on disk.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(type="STRING", description="File path to read.")
            },
            required=["path"]
        )
    ),
    types.FunctionDeclaration(
        name="write_file",
        description="Writes text content to a file on disk.",
        parameters=types.Schema(
            type="OBJECT",
            properties={
                "path": types.Schema(type="STRING", description="Destination file path."),
                "content": types.Schema(type="STRING", description="Text content to write.")
            },
            required=["path", "content"]
        )
    )
]

SUBAGENT_TOOLS = types.Tool(function_declarations=SUBAGENT_TOOL_DECLARATIONS)


def dispatch_subagent_tool(name: str, args: Dict[str, Any], task_id: Optional[str] = None) -> str:
    """Dispatches a tool call from Sub-Agent B locally."""
    try:
        if name == "get_system_telemetry":
            return get_system_telemetry()
        elif name == "kill_process":
            return kill_process(args.get("pid", 0))
        elif name == "run_powershell":
            return run_powershell(args.get("command", ""), task_id=task_id)
        elif name == "run_python_script":
            return run_python_script(args.get("code", ""), task_id=task_id)
        elif name == "read_file":
            return read_file(args.get("path", ""))
        elif name == "write_file":
            return write_file(args.get("path", ""), args.get("content", ""), task_id=task_id)
        else:
            return f"Unknown tool: {name}"
    except Exception as e:
        return f"Tool execution error ({name}): {e}"


# ── Sub-Agent B Execution Engine ─────────────────────────────────────────────

SYSTEM_PROMPT = """
You are Sub-Agent B, the headless background execution worker for Desktop Ghost, assisting Shvan.
You run silently in the background of Windows 10 without taking over the mouse, screen, or keyboard.

YOUR MISSION:
Execute Shvan's requested task efficiently using your headless system tools.

WORKSPACE & ARTIFACT RULES:
1. All generated files are automatically organized inside the standard workspace directory:
   - Web / HTML files (.html, .css, .js) -> 'workers/workspace_worker/html/'
   - Notes / Research (.txt, .md, .json, .csv) -> 'workers/workspace_worker/notes/'
   - Scripts (.py, .ps1, .bat) -> 'workers/workspace_worker/scripts/'
   - Miscellaneous / Outputs -> 'workers/workspace_worker/outputs/'
2. IN-PLACE REDESIGN / UPDATE:
   When asked to redesign, modify, update, or improve an existing file, ALWAYS edit the existing file IN-PLACE at its exact path.
   Do NOT create new duplicate files in other locations. This ensures when Shvan refreshes his browser (F5), the updated version renders immediately.

CORE RULES:
1. NEVER touch or terminate protected processes marked with [PROTECTED — DO NOT KILL] (Nova, Shvan's active game/app, or Windows system).
2. For closing processes, ALWAYS prefer 'kill_process(pid=...)' over raw PowerShell Stop-Process commands.
3. Be concise and purposeful. Complete the task in 1–3 tool steps whenever possible.
4. When finished, provide a clean, 1–2 sentence conversational summary of what was accomplished and the full file path if a file was created or edited, so Nova can speak it to Shvan.
""".strip()


class SubAgentB:
    """
    Sub-Agent B headless execution worker.
    Runs ReAct loop on gemini-3.5-flash-lite and updates TaskBlackboard.
    """

    def __init__(self) -> None:
        # Separate API key to eliminate rate limit contention with Nova's live stream
        api_key = os.getenv("GEMINI_API_KEY2") or os.getenv("GEMINI_API_KEY")
        self.client = genai.Client(api_key=api_key)
        self.blackboard = get_task_blackboard()

    def _generate_with_fallback(
        self,
        contents: Any,
        config: types.GenerateContentConfig,
        task_id: str = ""
    ) -> Any:
        """
        Attempts generation across SUBAGENT_MODEL_CASCADE.
        Automatically catches 503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED, 500 INTERNAL,
        logs failover, updates Blackboard, and retries on the next candidate model.
        """
        last_error = None
        for idx, model_name in enumerate(SUBAGENT_MODEL_CASCADE):
            try:
                response = self.client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config
                )
                return response
            except Exception as e:
                err_str = str(e)
                is_transient = any(
                    code in err_str
                    for code in ["503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "high demand", "Server disconnected"]
                )
                last_error = e
                if is_transient and idx < len(SUBAGENT_MODEL_CASCADE) - 1:
                    next_model = SUBAGENT_MODEL_CASCADE[idx + 1]
                    warn_msg = f"[SUB-AGENT B] ⚡ Model {model_name} busy ({e}). Auto-falling back to {next_model}..."
                    print(warn_msg)
                    if task_id and hasattr(self, "blackboard"):
                        try:
                            self.blackboard.update_progress(task_id, f"Model {model_name} busy (503). Retrying on {next_model}...")
                        except Exception:
                            pass
                    continue
                else:
                    raise e
        if last_error:
            raise last_error
        raise RuntimeError("No response returned from model cascade.")

    def execute_task_sync(
        self,
        task_id: str,
        goal: str,
        on_complete: Optional[Callable[[str, str], None]] = None
    ) -> str:
        """
        Executes a background task synchronously in up to MAX_STEPS ReAct steps.
        Updates the TaskBlackboard after each step.
        """
        self.blackboard.update_progress(task_id, "Analyzing task and planning execution...")
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"Task Goal: {goal}")]
            )
        ]

        cancel_event = threading.Event()
        with _proc_lock:
            _cancel_events[task_id] = cancel_event

        step = 0
        final_summary = ""

        try:
            while step < MAX_STEPS:
                if self.blackboard.is_cancelled(task_id) or cancel_event.is_set():
                    print(f"[SUB-AGENT B] Task {task_id} cancellation detected. Aborting loop.")
                    return "Task was cancelled by user."

                step += 1
                response = self._generate_with_fallback(
                    contents=contents,
                    config=types.GenerateContentConfig(
                        system_instruction=SYSTEM_PROMPT,
                        tools=[SUBAGENT_TOOLS],
                        temperature=0.1
                    ),
                    task_id=task_id
                )

                candidate = response.candidates[0] if response.candidates else None
                if not candidate:
                    break

                # If model called tools, dispatch them
                function_calls = getattr(response, "function_calls", None)
                if function_calls:
                    contents.append(candidate.content)
                    response_parts = []
                    for call in function_calls:
                        c_name = getattr(call, "name", "unknown")
                        c_args = getattr(call, "args", {}) or {}
                        # Update Blackboard with human progress
                        if c_name == "get_system_telemetry":
                            self.blackboard.update_progress(task_id, "Inspecting system CPU and RAM telemetry...")
                        elif c_name == "kill_process":
                            self.blackboard.update_progress(task_id, f"Terminating process PID {c_args.get('pid')}...")
                        elif c_name == "run_powershell":
                            self.blackboard.update_progress(task_id, "Running background PowerShell command...")
                        elif c_name == "run_python_script":
                            self.blackboard.update_progress(task_id, "Executing background Python script...")
                        elif c_name == "write_file":
                            self.blackboard.update_progress(task_id, f"Writing output file {c_args.get('path')}...")

                        tool_result = dispatch_subagent_tool(c_name, c_args, task_id=task_id)
                        response_parts.append(
                            types.Part.from_function_response(
                                name=c_name,
                                response={"output": tool_result}
                            )
                        )

                        if self.blackboard.is_cancelled(task_id) or cancel_event.is_set():
                            print(f"[SUB-AGENT B] Task {task_id} cancellation detected after {c_name}. Aborting.")
                            return "Task was cancelled by user."

                    contents.append(types.Content(role="user", parts=response_parts))
                else:
                    # Model produced its final response text
                    final_summary = response.text.strip() if response.text else "Task completed."
                    break

            if self.blackboard.is_cancelled(task_id) or cancel_event.is_set():
                return "Task was cancelled by user."

            # Ensure created artifacts are clearly reported in the summary & voice alert
            task_status = self.blackboard.get_task_status(task_id)
            artifacts = task_status.get("artifacts") or []
            if artifacts:
                art_str = f" Created: {', '.join(artifacts)}"
                if not final_summary or final_summary == "Background task completed.":
                    final_summary = f"Task completed successfully.{art_str}"
                elif not any(a in final_summary for a in artifacts):
                    final_summary += f"{art_str}"
            elif not final_summary:
                final_summary = "Background task completed."

            self.blackboard.complete_task(task_id, final_summary)
            if on_complete:
                try:
                    on_complete(task_id, final_summary)
                except Exception as e:
                    print(f"[SUB-AGENT B] on_complete callback error: {e}")
            return final_summary

        except Exception as e:
            if self.blackboard.is_cancelled(task_id) or cancel_event.is_set():
                return "Task was cancelled by user."
            err_msg = f"Task execution failed: {e}"
            print(f"[SUB-AGENT B ERROR] {err_msg}")
            traceback.print_exc()
            self.blackboard.fail_task(task_id, err_msg)
            if on_complete:
                try:
                    on_complete(task_id, f"Error: {err_msg}")
                except Exception:
                    pass
            return err_msg
        finally:
            with _proc_lock:
                _cancel_events.pop(task_id, None)
                _active_subprocesses.pop(task_id, None)


# ── Asynchronous Launch Helper ───────────────────────────────────────────────

def launch_background_task(
    goal: str,
    on_complete: Optional[Callable[[str, str], None]] = None
) -> str:
    """
    Creates a new task on the Blackboard and launches Sub-Agent B in a background thread.
    Returns the task_id immediately.
    """
    board = get_task_blackboard()
    task_id = board.create_task(goal)

    def _worker():
        worker_instance = SubAgentB()
        worker_instance.execute_task_sync(task_id, goal, on_complete=on_complete)

    t = threading.Thread(
        target=_worker,
        name=f"SubAgentB-{task_id}",
        daemon=True
    )
    t.start()
    return task_id
