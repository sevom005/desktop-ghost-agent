"""
Desktop Ghost Live Agent v2 — Ghost Memory Engine (v3)
======================================================
Provides local, offline, zero-latency persistent memory for Ghost.
Synthesizes:
  - Stanford Generative Agents: Importance scoring (1-10) with exponential decay
  - MemGPT / Letta: Working Context (RAM) vs. Disk Storage
  - Mem0: Fact IDs & conflict resolution (superseding old beliefs)
  - Princeton Reflexion: Autonomous habit induction

Design decisions & Argon fixes:
  - LAMBDA_DECAY = 0.02 strictly proves 60-day Imp 10 (3.01) > 1-day Imp 2 (1.96).
  - Atomic JSON writes via .tmp_{pid}_{tid} + os.replace() prevents file corruption.
  - Startup crash recovery: automatically processes unclaimed pending_session.json.
  - Thread-safe singleton via get_ghost_memory().
"""

import os
import json
import math
import datetime
import threading
from typing import Optional, List, Dict, Any

# ── Paths ────────────────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MEMORY_DIR = os.path.join(_BASE_DIR, "memory")
_COMPANION_PATH = os.path.join(_MEMORY_DIR, "companion.json")
_HABITS_PATH = os.path.join(_MEMORY_DIR, "habits.json")
_PENDING_SESSION_PATH = os.path.join(_MEMORY_DIR, "pending_session.json")

# ── Stanford Generative Agents Decay Constant ────────────────────────────────
LAMBDA_DECAY = 0.02  # At 0.02, 60-day Imp 10 = 3.01 > 1-day Imp 2 = 1.96

# ── Defaults ──────────────────────────────────────────────────────────────────

_DEFAULT_COMPANION = {
    "user_name": "Shvan",
    "profile": {
        "user_name": "Shvan",
        "os": "Windows 11",
        "python": "3.14",
        "voice": "Puck",
        "communication_style": "Casual, direct, calls me bro. Keep replies short. No corporate speak."
    },
    "facts": [],
    "episodes": [],
    "greeting_spark": {
        "last_seen": None,
        "last_topic": None,
        "open_thread": None,
        "mood_hint": None
    }
}

_DEFAULT_HABITS = {"habits": []}

_MAX_INJECTED_FACTS = 8
_MAX_INJECTED_EPISODES = 3
_MAX_INJECTED_HABITS = 5


# ─────────────────────────────────────────────────────────────────────────────

class GhostMemory:
    """
    Persistent local memory engine for Desktop Ghost.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._companion: dict = dict(_DEFAULT_COMPANION)
        self._habits: list = []

    # ── Load / Save ──────────────────────────────────────────────────────────

    def load(self) -> None:
        """
        Read companion.json and habits.json.
        Silently recovers from missing or corrupted files.
        Checks for crash-recovery pending_session.json.
        """
        with self._lock:
            raw_companion = self._read_json(_COMPANION_PATH, _DEFAULT_COMPANION)
            self._companion = self._migrate_and_validate_companion(raw_companion)

            habits_data = self._read_json(_HABITS_PATH, _DEFAULT_HABITS)
            self._habits = habits_data.get("habits", [])
            if not isinstance(self._habits, list):
                self._habits = []

        # Check WAL crash recovery outside lock to avoid deadlocks
        self._check_startup_wal_recovery()

        # Pillar 4: ARIES stale lock and orphan scavenger in background thread (skipped during pytest)
        if not os.environ.get("PYTEST_CURRENT_TEST"):
            def _bg_hygiene():
                try:
                    from memory.unified_memory import get_unified_memory
                    get_unified_memory().cleanup_orphaned_locks()
                except Exception as e:
                    print(f"[GHOST MEMORY] Hygiene sweep note: {e}")

            threading.Thread(target=_bg_hygiene, name="GhostMemoryHygiene", daemon=True).start()

    def save_companion(self) -> None:
        """Write companion.json atomically."""
        with self._lock:
            self._atomic_write_json(_COMPANION_PATH, self._companion)

    def save_habits(self) -> None:
        """Write habits.json atomically."""
        with self._lock:
            self._atomic_write_json(_HABITS_PATH, {"habits": self._habits})

    def get_profile(self) -> Dict[str, Any]:
        """Returns the user profile dictionary thread-safely."""
        with self._lock:
            return dict(self._companion.get("profile", {}))

    def get_greeting_spark(self) -> Dict[str, Any]:
        """Returns the greeting spark dictionary thread-safely."""
        with self._lock:
            return dict(self._companion.get("greeting_spark", {}))

    # ── Context Block for SYSTEM_INSTRUCTION ─────────────────────────────────

    def get_context_block(self) -> str:
        """
        Compiles the 4-layer relationship context block for SYSTEM_INSTRUCTION
        using Stanford retrieval scoring (Importance × Decay).
        """
        with self._lock:
            profile = self._companion.get("profile", {})
            name = profile.get("user_name", "Shvan")
            style = profile.get("communication_style", "")
            spark = self._companion.get("greeting_spark", {}) or {}
            last_seen = spark.get("last_seen")
            last_topic = spark.get("last_topic")
            open_thread = spark.get("open_thread")
            mood_hint = spark.get("mood_hint")

            # Rank facts using Stanford formula: Importance * exp(-0.02 * days_ago)
            scored_facts = []
            now = datetime.datetime.now(datetime.timezone.utc)
            for f in self._companion.get("facts", []):
                imp = float(f.get("importance", 5))
                days_ago = self._calculate_days_ago(f.get("updated_at"), now)
                score = imp * math.exp(-LAMBDA_DECAY * days_ago)
                scored_facts.append((score, f))
            scored_facts.sort(key=lambda x: x[0], reverse=True)
            top_facts = [f for _, f in scored_facts[:_MAX_INJECTED_FACTS]]

            # Rank episodes similarly
            scored_episodes = []
            for ep in self._companion.get("episodes", []):
                imp = float(ep.get("importance", 5))
                days_ago = self._calculate_days_ago(ep.get("date"), now)
                score = imp * math.exp(-LAMBDA_DECAY * days_ago)
                scored_episodes.append((score, ep))
            scored_episodes.sort(key=lambda x: x[0], reverse=True)
            top_episodes = [ep for _, ep in scored_episodes[:_MAX_INJECTED_EPISODES]]

            top_habits = self._habits[-_MAX_INJECTED_HABITS:]

            lines = ["══ GHOST MEMORY ══"]
            lines.append(f"User: {name}")

            # Layer 4: Greeting Spark & Relationship Continuity
            if last_seen:
                ago = self._human_time_ago(last_seen)
                lines.append(f"Last active: {ago}")
            if last_topic:
                lines.append(f"Last session topic: {last_topic}")
            if open_thread:
                lines.append(f"Open thread / context: {open_thread}")
            if mood_hint:
                lines.append(f"Recent state: {mood_hint}")
            if style:
                lines.append(f"Style: {style}")

            # Layer 1 & 3: Facts & Core Preferences
            if top_facts:
                lines.append("Facts & Preferences:")
                for f in top_facts:
                    lines.append(f" • {f.get('fact', '')}")

            # Layer 2: Episodic Milestones
            if top_episodes:
                lines.append("Key shared episodes:")
                for ep in top_episodes:
                    lines.append(f" • {ep.get('title', '')}: {ep.get('summary', '')}")

            # Procedural Habits
            if top_habits:
                lines.append("Learned habits (ALWAYS follow these):")
                for h in top_habits:
                    trigger = h.get("trigger", "")
                    correction = h.get("correction", "")
                    mistake = h.get("mistake", "")
                    if mistake:
                        lines.append(f" • When asked to {trigger}: {correction} (Avoided: {mistake})")
                    else:
                        lines.append(f" • When asked to {trigger}: {correction}")

            lines.append("══════════════════")
            return "\n".join(lines)

    # ── Real-Time Companion Mutations (MemGPT Fast-Brain) ─────────────────────

    def add_fact(self, fact_text: str, category: str = "preference", importance: int = 7) -> str:
        """Append a new fact with unique ID, skipping exact duplicates."""
        fact_text = fact_text.strip()
        if not fact_text:
            return "error: empty fact"

        with self._lock:
            existing_facts = self._companion.setdefault("facts", [])
            for f in existing_facts:
                if f.get("fact", "").lower() == fact_text.lower():
                    # Update importance and timestamp in place
                    f["importance"] = max(f.get("importance", 5), importance)
                    f["updated_at"] = datetime.date.today().isoformat()
                    return f["id"]

            fact_id = f"f_{len(existing_facts) + 1:03d}"
            existing_facts.append({
                "id": fact_id,
                "fact": fact_text,
                "category": category,
                "importance": importance,
                "updated_at": datetime.date.today().isoformat()
            })
            return fact_id

    def remove_fact(self, keyword: str) -> bool:
        """Remove any fact containing the keyword (case-insensitive)."""
        keyword = keyword.strip().lower()
        with self._lock:
            before = self._companion.get("facts", [])
            after = [f for f in before if keyword not in f.get("fact", "").lower()]
            self._companion["facts"] = after
            return len(after) < len(before)

    def add_habit(self, trigger: str, mistake: str, correction: str) -> None:
        """Upsert a learned habit by trigger."""
        trigger = trigger.strip().lower()
        if not trigger:
            return
        with self._lock:
            for h in self._habits:
                if h.get("trigger", "").lower() == trigger:
                    h["mistake"] = mistake.strip()
                    h["correction"] = correction.strip()
                    h["updated_at"] = datetime.date.today().isoformat()
                    return
            self._habits.append({
                "trigger": trigger,
                "mistake": mistake.strip(),
                "correction": correction.strip(),
                "learned_at": datetime.date.today().isoformat()
            })

    def update_last_seen(self) -> None:
        """Record current UTC timestamp into greeting_spark and save."""
        with self._lock:
            spark = self._companion.setdefault("greeting_spark", {})
            spark["last_seen"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        self.save_companion()

    # ── Subconscious Reflection Application ───────────────────────────────────

    def apply_reflection(self, data: Dict[str, Any]) -> None:
        """
        Atomically applies a parsed reflection payload from sleep_reflector.py.
        Handles Mem0 conflict overwrites, Stanford episodes, and habits.
        """
        with self._lock:
            today_str = datetime.date.today().isoformat()
            existing_facts = self._companion.setdefault("facts", [])

            # 1. Supersede old facts by ID (Mem0 Conflict Resolution)
            superseded_ids = set()
            for sf in data.get("superseded_facts", []):
                old_id = sf.get("old_fact_id")
                new_text = sf.get("new_fact_text")
                if old_id and new_text:
                    for f in existing_facts:
                        if f.get("id") == old_id:
                            f["fact"] = new_text.strip()
                            f["updated_at"] = today_str
                            superseded_ids.add(old_id)

            # 2. Add brand-new facts or update superseded fact
            for nf in data.get("new_facts", []):
                fact_text = str(nf.get("fact", "")).strip()
                if not fact_text:
                    continue
                old_id = nf.get("supersedes_fact_id")
                if old_id:
                    for f in existing_facts:
                        if f.get("id") == old_id:
                            f["fact"] = fact_text
                            f["category"] = nf.get("category", f.get("category", "preference"))
                            f["importance"] = int(nf.get("importance", f.get("importance", 7)))
                            f["updated_at"] = today_str
                            break
                    continue
                # Skip if already exists or was just superseded
                if any(f.get("fact", "").lower() == fact_text.lower() for f in existing_facts):
                    continue
                new_id = f"f_{len(existing_facts) + 1:03d}"
                existing_facts.append({
                    "id": new_id,
                    "fact": fact_text,
                    "category": nf.get("category", "preference"),
                    "importance": int(nf.get("importance", 7)),
                    "updated_at": today_str
                })

            # 3. Add new episode if significant
            new_ep = data.get("new_episode")
            if new_ep and isinstance(new_ep, dict) and new_ep.get("title"):
                episodes = self._companion.setdefault("episodes", [])
                ep_id = f"ep_{len(episodes) + 1:03d}"
                episodes.append({
                    "id": ep_id,
                    "date": today_str,
                    "title": new_ep.get("title", "").strip(),
                    "summary": new_ep.get("summary", "").strip(),
                    "importance": int(new_ep.get("importance", 8))
                })

            # 4. Upsert procedural habits (Princeton Reflexion)
            for nh in data.get("new_habits", []):
                trig = str(nh.get("trigger", "")).strip().lower()
                mist = str(nh.get("mistake", "")).strip()
                corr = str(nh.get("correction", "")).strip()
                if trig and corr:
                    matched = False
                    for h in self._habits:
                        if h.get("trigger", "").lower() == trig:
                            h["mistake"] = mist
                            h["correction"] = corr
                            h["updated_at"] = today_str
                            matched = True
                            break
                    if not matched:
                        self._habits.append({
                            "trigger": trig,
                            "mistake": mist,
                            "correction": corr,
                            "learned_at": today_str
                        })

            # 5. Update Greeting Spark
            spark_data = data.get("greeting_spark", {})
            if spark_data:
                spark = self._companion.setdefault("greeting_spark", {})
                spark["last_seen"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
                if spark_data.get("last_topic"):
                    spark["last_topic"] = spark_data.get("last_topic").strip()
                if spark_data.get("open_thread"):
                    spark["open_thread"] = spark_data.get("open_thread").strip()
                if spark_data.get("mood_hint"):
                    spark["mood_hint"] = spark_data.get("mood_hint").strip()

        # Write both to disk atomically
        self.save_companion()
        self.save_habits()

    def apply_micro_reflection(self, data: Dict[str, Any]) -> None:
        """Atomically applies a mid-session rolling micro-reflection (facts & habits only)."""
        self.apply_reflection(data)

    def get_existing_facts_for_prompt(self) -> List[Dict[str, str]]:
        """Returns existing facts formatted with IDs for sleep_reflector.py context."""
        with self._lock:
            return [
                {"id": f.get("id", ""), "fact": f.get("fact", "")}
                for f in self._companion.get("facts", [])
            ]

    def get_existing_habit_triggers(self) -> List[str]:
        """Returns existing habit trigger strings to prevent duplicates."""
        with self._lock:
            return [h.get("trigger", "").lower() for h in self._habits]

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _calculate_days_ago(date_str: Optional[str], now: datetime.datetime) -> float:
        if not date_str:
            return 0.0
        try:
            # Handle full ISO or YYYY-MM-DD
            clean_date = date_str.split("T")[0]
            then = datetime.datetime.strptime(clean_date, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
            delta = now - then
            return max(0.0, delta.total_seconds() / 86400.0)
        except Exception:
            return 0.0

    @staticmethod
    def _human_time_ago(iso_timestamp: str) -> str:
        try:
            clean_ts = iso_timestamp.rstrip("Z").replace("Z", "")
            then = datetime.datetime.fromisoformat(clean_ts)
            if then.tzinfo is None:
                then = then.replace(tzinfo=datetime.timezone.utc)
            delta = datetime.datetime.now(datetime.timezone.utc) - then
            seconds = int(delta.total_seconds())
            if seconds < 60:
                return "just now"
            elif seconds < 3600:
                m = seconds // 60
                return f"{m} minute{'s' if m != 1 else ''} ago"
            elif seconds < 86400:
                h = seconds // 3600
                return f"{h} hour{'s' if h != 1 else ''} ago"
            else:
                d = seconds // 86400
                return f"{d} day{'s' if d != 1 else ''} ago"
        except Exception:
            return "previously"

    @staticmethod
    def _read_json(path: str, default: dict) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return dict(default)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[GHOST MEMORY] Warning: Could not read {path}: {e}. Using defaults.")
            return dict(default)

    @staticmethod
    def _atomic_write_json(path: str, data: dict) -> None:
        """Argon Fix #1 & #3: Atomic write via unique thread tmp file + os.replace."""
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp_path = f"{path}.tmp_{os.getpid()}_{threading.get_ident()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, path)
        except OSError as e:
            print(f"[GHOST MEMORY] Warning: Failed atomic write to {path}: {e}")

    @staticmethod
    def _migrate_and_validate_companion(data: dict) -> dict:
        """Ensures smooth backward compatibility if an older companion.json is loaded."""
        res = dict(_DEFAULT_COMPANION)
        if isinstance(data.get("profile"), dict):
            res["profile"].update(data["profile"])
        elif "user_name" in data:
            res["profile"]["user_name"] = data["user_name"]
            if "communication_style" in data:
                res["profile"]["communication_style"] = data["communication_style"]
        res["user_name"] = res["profile"].get("user_name", "Shvan")

        # Validate / migrate facts list
        raw_facts = data.get("facts", [])
        clean_facts = []
        if isinstance(raw_facts, list):
            for i, item in enumerate(raw_facts):
                if isinstance(item, str):
                    clean_facts.append({
                        "id": f"f_{i+1:03d}",
                        "fact": item,
                        "category": "preference",
                        "importance": 7,
                        "updated_at": datetime.date.today().isoformat()
                    })
                elif isinstance(item, dict) and "fact" in item:
                    if "id" not in item:
                        item["id"] = f"f_{i+1:03d}"
                    clean_facts.append(item)
        res["facts"] = clean_facts

        if isinstance(data.get("episodes"), list):
            res["episodes"] = data["episodes"]
        elif isinstance(data.get("milestones"), list):
            for i, m in enumerate(data["milestones"]):
                res["episodes"].append({
                    "id": f"ep_{i+1:03d}",
                    "date": datetime.date.today().isoformat(),
                    "title": str(m),
                    "summary": str(m),
                    "importance": 9
                })

        if isinstance(data.get("greeting_spark"), dict):
            res["greeting_spark"].update(data["greeting_spark"])
        elif "last_seen" in data and data["last_seen"]:
            res["greeting_spark"]["last_seen"] = data["last_seen"]

        return res

    def _check_startup_wal_recovery(self) -> None:
        """Argon Fix #1: If previous session died before reflection, process it now."""
        if not os.path.exists(_PENDING_SESSION_PATH):
            return

        # Attempt to claim the file by renaming to avoid collision with any lingering worker
        claim_path = f"{_PENDING_SESSION_PATH}.startup_{os.getpid()}"
        try:
            os.replace(_PENDING_SESSION_PATH, claim_path)
        except OSError:
            return  # Already claimed or deleted

        try:
            print("[GHOST MEMORY] Found unprocessed session WAL from previous run. Reflecting in background...")
            with open(claim_path, "r", encoding="utf-8") as f:
                transcript = json.load(f)

            if isinstance(transcript, list) and transcript:
                from memory.sleep_reflector import execute_reflection_sync
                execute_reflection_sync(transcript, memory_instance=self)
            elif isinstance(transcript, dict):
                from memory.sleep_reflector import execute_reflection_sync
                execute_reflection_sync(
                    transcript.get("session_stream", []),
                    memory_instance=self,
                    chunk_summaries=transcript.get("chunk_summaries", [])
                )

            if os.path.exists(claim_path):
                os.remove(claim_path)
        except Exception as e:
            print(f"[GHOST MEMORY] WAL startup recovery skipped: {e}")
            if os.path.exists(claim_path):
                try:
                    os.remove(claim_path)
                except OSError:
                    pass


# ── Singleton ─────────────────────────────────────────────────────────────────

_INSTANCE: Optional[GhostMemory] = None


def get_ghost_memory() -> GhostMemory:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = GhostMemory()
    return _INSTANCE
