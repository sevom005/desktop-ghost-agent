"""
memory/unified_memory.py
=========================
Pillar 4: Unified 3-Tier Memory Manager & Sleep Hygiene for Desktop Ghost (Nova).
Synthesizes:
  - Stanford Generative Agents (Park et al., 2023): Recency decay + Importance scoring
  - MemGPT / Letta (Packer et al., 2023): Working Memory (RAM) vs. External Storage & Token Budgeting
  - Princeton Reflexion (Shinn et al., 2023): Autonomous procedural habit triggers
  - IBM ARIES (Mohan et al., 1992): Write-Ahead Log crash recovery & stale lock scavenging
  - Acoustic Lexical Biasing (Amazon Science / ISCA 2023/2024): Phonetic speech drift normalization
"""

import os
import sys
import re
import json
import time
import ctypes
import threading
from typing import Optional, Dict, Any, List, Tuple

# Add workspace root to sys.path
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BASE_DIR not in sys.path:
    sys.path.insert(0, _BASE_DIR)

from memory.ghost_memory import get_ghost_memory, GhostMemory
from memory.task_blackboard import get_task_blackboard, TaskBlackboard, TaskStatus

_MEMORY_DIR = os.path.join(_BASE_DIR, "memory")

# ── Process Liveness Verification (Zero-Dependency Windows + POSIX) ──────────

def is_pid_alive(pid: int) -> bool:
    """
    Checks whether a process with the given PID is currently active.
    Uses native Windows kernel32.OpenProcess on Windows, with os.kill(pid, 0) fallback.
    """
    if pid <= 0:
        return False
    if pid == os.getpid():
        return True

    # Try psutil if present
    try:
        import psutil
        return psutil.pid_exists(pid)
    except ImportError:
        pass

    # Windows native check
    if os.name == "nt":
        try:
            kernel32 = ctypes.windll.kernel32
            # 0x1000 = PROCESS_QUERY_LIMITED_INFORMATION
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            err = kernel32.GetLastError()
            # 5 = ERROR_ACCESS_DENIED (process exists but owned by elevated/different user)
            return err == 5
        except Exception:
            return False
    else:
        # POSIX standard check
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False


# ── Acoustic Lexical Biasing & Phonetic Speech Aliases ───────────────────────

# Regular expressions for live speech-to-text drift mapping
_PHONETIC_REPLACEMENTS = [
    # Sub-Agent B misrecognitions
    (re.compile(r"\b(salvation\s*agent|sales\s*agent|surveillance\s*worker|surveillance\s*agent|surveillance|headless\s*agent|salvation)\b", re.IGNORECASE), "Sub-Agent B"),
    
    # Project %100 misrecognitions
    (re.compile(r"\b(p\s*100|project\s*100|project\s*hundred)\b", re.IGNORECASE), "Project %100"),
    
    # Editor & App name misrecognitions
    (re.compile(r"\b(notepad\s*plus\s*plus|notepad\s*plus)\b", re.IGNORECASE), "Notepad++"),
    (re.compile(r"\b(vs\s*code|v\s*s\s*code)\b", re.IGNORECASE), "VS Code"),
]


def normalize_phonetic_speech(text: str) -> str:
    """
    Normalizes speech-to-text misrecognitions and acoustic drift using
    contextual lexical biasing and phonetic alias rules.
    """
    if not text:
        return ""
    normalized = text
    for pattern, replacement in _PHONETIC_REPLACEMENTS:
        normalized = pattern.sub(replacement, normalized)
    return normalized


# ── Unified Memory Manager ───────────────────────────────────────────────────

class UnifiedMemoryManager:
    """
    Central cognitive memory facade for Desktop Ghost (Nova).
    Coordinates:
      - Tier 1: Working Memory (Live turns, active window breadcrumbs, blackboard tasks)
      - Tier 2: Episodic Memory (Session WAL, rolling micro-reflections, session milestones)
      - Tier 3: Semantic Long-Term Memory (Decay-scored facts, Reflexion habits, profile)
    """

    def __init__(self, memory_dir: Optional[str] = None) -> None:
        self.memory_dir = memory_dir or _MEMORY_DIR
        self._lock = threading.Lock()
        self._ghost_memory: GhostMemory = get_ghost_memory()
        self._ghost_memory.load()
        self._task_blackboard: TaskBlackboard = get_task_blackboard()
        self._cached_context: str = ""
        self._cached_max_tokens: int = 1200
        self._cache_timestamp: float = 0.0
        self._cache_ttl: float = 0.5  # 500ms cache TTL for responsive sub-ms retrieval

    # ── Context Block Assembly (MemGPT Token-Budgeted Paging) ────────────────

    def get_system_context_block(
        self,
        max_tokens: int = 1200,
        spatial_context: Optional[Any] = None
    ) -> str:
        """
        Assembles a prioritized markdown block containing Tier 1, 2, and 3 memory.
        Enforces a strict token budget (~4 chars per token) to keep Gemini Live latency low.
        """
        now = time.monotonic()
        # Fast path if cached and no spatial context override with matching budget
        if (
            spatial_context is None
            and self._cached_context
            and self._cached_max_tokens == max_tokens
            and (now - self._cache_timestamp < self._cache_ttl)
        ):
            return self._cached_context

        with self._lock:
            # Approx character budget: max_tokens * 4 chars
            char_budget = max_tokens * 4
            sections: List[str] = []

            # 1. Core Profile & Persona Tone (Fixed ~150 tokens)
            profile = self._ghost_memory.get_profile()
            user_name = profile.get("user_name", "Shvan")
            comm_style = profile.get("communication_style", "Casual, direct, calls me bro. Keep replies short.")
            sections.append(
                f"### ══ CORE IDENTITY & USER PREFERENCES ══\n"
                f"- User: {user_name} (Windows 11, Python 3.14)\n"
                f"- Communication Style: {comm_style}"
            )

            # 2. Tier 1: Active Spatial Window & Task Context (Fast RAM / ~150 tokens)
            t1_parts: List[str] = []
            if spatial_context is not None:
                app_name = getattr(spatial_context, "app_name", "")
                resolved_file = getattr(spatial_context, "file_name", "") or getattr(spatial_context, "file_path", "") or getattr(spatial_context, "resolved_file", "")
                active_workspace = getattr(spatial_context, "workspace_name", "") or getattr(spatial_context, "workspace_dir", "") or getattr(spatial_context, "active_workspace", "")
                window_title = getattr(spatial_context, "window_title", "")
                if app_name or resolved_file:
                    t1_parts.append(
                        f"• Foreground Window: '{window_title}'\n"
                        f"  App: {app_name} | Active File: {resolved_file or 'None'} | Workspace: {active_workspace or 'None'}"
                    )
            
            # Active background tasks from Blackboard
            try:
                active_tasks = self._task_blackboard.get_active_tasks()
                if active_tasks:
                    task_lines = [f"  - [{t['task_id']}] {t['description']} ({t['status']}): {t['progress']}" for t in active_tasks[:2]]
                    t1_parts.append("• Active Background Tasks (Sub-Agent B):\n" + "\n".join(task_lines))
            except Exception:
                pass

            if t1_parts:
                sections.append("### ══ TIER 1: ACTIVE SPATIAL & TASK CONSCIOUSNESS ══\n" + "\n".join(t1_parts))

            # 3. Tier 3: Semantic Facts (Stanford Generative Agents Decay Scoring / ~450 tokens)
            facts = self._ghost_memory.get_existing_facts_for_prompt()
            if facts:
                fact_lines = [f"- {f.get('fact')}" for f in facts[:6]]
                sections.append("### ══ TIER 3: USER FACTS & HABITS (STANFORD DECAY RANKED) ══\n" + "\n".join(fact_lines))

            # 4. Tier 3: Princeton Reflexion Habit Triggers (~300 tokens)
            habits = self._ghost_memory._habits
            if habits:
                habit_lines = [
                    f"- When '{h.get('trigger')}': {h.get('correction')}"
                    for h in habits[-4:]
                    if isinstance(h, dict) and h.get("trigger") and h.get("correction")
                ]
                if habit_lines:
                    sections.append("### ══ PROCEDURAL CORRECTIONS (PRINCETON REFLEXION) ══\n" + "\n".join(habit_lines))

            # 5. Tier 2: Greeting Spark & Episodic Continuity (~150 tokens)
            spark = self._ghost_memory._companion.get("greeting_spark", {})
            last_topic = spark.get("last_topic")
            open_thread = spark.get("open_thread")
            if last_topic or open_thread:
                spark_lines = []
                if last_topic:
                    spark_lines.append(f"• Previous Session Topic: {last_topic}")
                if open_thread:
                    spark_lines.append(f"• Open Unfinished Thread: {open_thread}")
                sections.append("### ══ TIER 2: EPISODIC CONTINUITY & GREETING SPARK ══\n" + "\n".join(spark_lines))

            # Assemble and enforce token budget
            full_block = "\n\n".join(sections)
            if len(full_block) > char_budget:
                suffix = "\n...(context trimmed to fit token budget)"
                trim_len = max(0, char_budget - len(suffix))
                full_block = full_block[:trim_len] + suffix

            self._cached_context = full_block
            self._cached_max_tokens = max_tokens
            self._cache_timestamp = now
            return full_block

    # ── ARIES Crash Recovery & Stale Lock Hygiene ────────────────────────────

    def cleanup_orphaned_locks(self) -> int:
        """
        IBM ARIES-inspired crash recovery and stale lock scavenger:
        1. Scans memory/ for pending_session.json.processing_<pid>_<tid> and .tmp_* files.
        2. Checks owner PID liveness using is_pid_alive(pid).
        3. If PID is dead, recovers any uncommitted session interaction turns,
           merges them, triggers background reflection, and cleanly deletes the lock file.
        4. Cleans any stale .tmp_* files older than 60 seconds.

        Returns total number of cleaned files.
        """
        cleaned_count = 0
        if not os.path.exists(self.memory_dir):
            return 0

        processing_pattern = re.compile(r"^pending_session\.json\.processing_(\d+)_(\d+)$")
        tmp_pattern = re.compile(r"^.*\.tmp_(\d+)_(\d+)$")
        now = time.time()

        for filename in os.listdir(self.memory_dir):
            file_path = os.path.join(self.memory_dir, filename)
            if not os.path.isfile(file_path):
                continue

            # Case A: Orphaned .processing_<pid>_<tid> lock files
            proc_match = processing_pattern.match(filename)
            if proc_match:
                owner_pid = int(proc_match.group(1))
                alive = is_pid_alive(owner_pid)
                file_age = now - os.path.getmtime(file_path)

                # If process is dead OR file is older than 2 hours (stranded)
                if not alive or file_age > 7200:
                    print(f"[MEMORY HYGIENE] Salvaging orphaned lock from dead PID {owner_pid}: {filename} (Age: {file_age:.1f}s)")
                    try:
                        # Attempt to salvage uncommitted interaction data
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        stream = []
                        summaries = []
                        if isinstance(data, dict):
                            stream = data.get("session_stream", [])
                            summaries = data.get("chunk_summaries", [])
                        elif isinstance(data, list):
                            stream = data

                        # If meaningful unreflected turns exist, salvage them
                        if stream or summaries:
                            try:
                                from memory.sleep_reflector import execute_reflection_sync
                                execute_reflection_sync(
                                    session_stream=stream,
                                    memory_instance=self._ghost_memory,
                                    chunk_summaries=summaries
                                )
                                print(f"[MEMORY HYGIENE] Successfully reflected {len(stream)} turns from {filename}.")
                            except Exception as ref_err:
                                print(f"[MEMORY HYGIENE] Could not reflect data from {filename}: {ref_err}")

                    except Exception as read_err:
                        print(f"[MEMORY HYGIENE] Error reading stranded file {filename}: {read_err}")
                    finally:
                        try:
                            os.remove(file_path)
                            cleaned_count += 1
                        except OSError as e:
                            print(f"[MEMORY HYGIENE] Failed to remove {filename}: {e}")

            # Case B: Stale temporary write files (.tmp_<pid>_<tid>)
            tmp_match = tmp_pattern.match(filename)
            if tmp_match:
                tmp_pid = int(tmp_match.group(1))
                file_age = now - os.path.getmtime(file_path)
                if (not is_pid_alive(tmp_pid)) or file_age > 60:
                    try:
                        os.remove(file_path)
                        cleaned_count += 1
                    except OSError:
                        pass

        if cleaned_count > 0:
            print(f"[MEMORY HYGIENE] Cleaned {cleaned_count} orphaned lock/tmp file(s).")
        return cleaned_count


# ── Singleton Accessor ───────────────────────────────────────────────────────

_UNIFIED_INSTANCE: Optional[UnifiedMemoryManager] = None
_INIT_LOCK = threading.Lock()


def get_unified_memory() -> UnifiedMemoryManager:
    """Returns the singleton instance of UnifiedMemoryManager."""
    global _UNIFIED_INSTANCE
    if _UNIFIED_INSTANCE is None:
        with _INIT_LOCK:
            if _UNIFIED_INSTANCE is None:
                _UNIFIED_INSTANCE = UnifiedMemoryManager()
    return _UNIFIED_INSTANCE
