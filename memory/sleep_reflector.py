"""
Desktop Ghost Live Agent v2 — Subconscious Sleep & Rolling Reflector
===================================================================
The deep background brain. Runs asynchronously:
  1. Mid-session: Rolling micro-reflections every ~30 turns (extracting facts, habits, chunk summary)
  2. Shutdown: Full session consolidation (using earlier chunk summaries + final tail turns)
  3. Startup crash recovery: Processes unclaimed pending_session WAL files

Key Capabilities:
  - Stanford Generative Agents: Extracts higher-level facts & scores importance (1-10)
  - Princeton Reflexion: Detects mistakes & user corrections -> induces habit rules
  - Mem0: Overwrites outdated beliefs via fact IDs ("supersedes_fact_id": "f_001")
  - Rolling Chunk Summaries: Prevents "Lost in the Middle" context decay over 1-hour sessions
  - 2-Turn Overlap: Prevents splitting actions & corrections across chunk boundaries
  - Multilingual: Accurately understands casual Kurdish, English, or code-switching
  - Zero Voice Lag: 100% disconnected from the active 16kHz WebSocket audio loop
  - Crash-Safe: Write-Ahead Log (WAL) claiming ensures no data loss or thread collisions
"""

import os
import json
import time
import threading
from typing import Any, Optional, List, Literal, Tuple, Callable
from pydantic import BaseModel, Field

from google import genai
from google.genai import types

# ── Paths ────────────────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_MEMORY_DIR = os.path.join(_BASE_DIR, "memory")
_PENDING_SESSION_PATH = os.path.join(_MEMORY_DIR, "pending_session.json")

from dotenv import load_dotenv
load_dotenv(os.path.join(_BASE_DIR, ".env"))

# Verified active model constant & dynamic fallback cascade
REFLECTION_PRIMARY_MODEL = os.getenv("REFLECTION_MODEL", "gemini-3.5-flash-lite")
REFLECTION_FALLBACK_MODELS = [
    REFLECTION_PRIMARY_MODEL,
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash",
]
REFLECTION_MODEL_CASCADE = list(dict.fromkeys(REFLECTION_FALLBACK_MODELS))
REFLECTION_MODEL = REFLECTION_PRIMARY_MODEL


def _generate_reflection_with_fallback(
    client: genai.Client,
    contents: Any,
    config: types.GenerateContentConfig,
    tag: str = "[SLEEP REFLECTOR]"
) -> types.GenerateContentResponse:
    """
    Attempts generation across REFLECTION_MODEL_CASCADE on 503/429/500 transient errors.
    """
    last_error = None
    for idx, model_name in enumerate(REFLECTION_MODEL_CASCADE):
        try:
            return client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )
        except Exception as e:
            err_str = str(e)
            is_transient = any(
                code in err_str
                for code in ["503", "429", "500", "UNAVAILABLE", "RESOURCE_EXHAUSTED", "high demand", "Server disconnected"]
            )
            last_error = e
            if is_transient and idx < len(REFLECTION_MODEL_CASCADE) - 1:
                next_model = REFLECTION_MODEL_CASCADE[idx + 1]
                print(f"{tag} ⚡ Model {model_name} busy ({e}). Auto-falling back to {next_model}...")
                continue
            else:
                raise e
    if last_error:
        raise last_error
    raise RuntimeError("No response from reflection model cascade.")


# ── Pydantic Structured Output Schemas (Argon Fix #4) ────────────────────────

class ExtractedFact(BaseModel):
    fact: str = Field(description="Clear statement of fact or user preference.")
    category: Literal["preference", "lifestyle", "technical", "personal"] = Field(
        default="preference",
        description="Category classification."
    )
    importance: int = Field(
        ge=1, le=10,
        description="Stanford salience score 1-10. 10=critical life/project milestone, 1=casual trivia."
    )
    supersedes_fact_id: Optional[str] = Field(
        default=None,
        description="ID of an existing fact to replace (e.g. 'f_001' if user changed their preference), or null."
    )


class ExtractedHabit(BaseModel):
    trigger: str = Field(description="Action phrase that triggers this habit (e.g. 'open chrome').")
    mistake: str = Field(description="What Ghost did wrong or what failed.")
    correction: str = Field(description="The exact corrected procedure Ghost must use instead.")


class ExtractedEpisode(BaseModel):
    title: str = Field(description="Concise 3-7 word title of the shared accomplishment.")
    summary: str = Field(description="1-2 sentences summarizing what was achieved or debugged.")
    importance: int = Field(ge=1, le=10, description="Salience score 1-10.")


class GreetingSpark(BaseModel):
    last_topic: str = Field(description="1 concise sentence summarizing what was discussed/worked on.")
    open_thread: str = Field(description="Any unfinished task or next step to follow up on next time.")
    mood_hint: str = Field(description="Brief user state cue (e.g. 'Tired after late coding', 'Energized').")


class SessionReflection(BaseModel):
    new_facts: List[ExtractedFact] = Field(default_factory=list)
    new_habits: List[ExtractedHabit] = Field(default_factory=list)
    new_episode: Optional[ExtractedEpisode] = Field(default=None)
    greeting_spark: GreetingSpark

# Alias for clarity
ShutdownReflectionResult = SessionReflection


class MicroReflectionResult(BaseModel):
    new_facts: List[ExtractedFact] = Field(
        default_factory=list,
        description="Newly revealed facts or changed preferences in this turn chunk."
    )
    new_habits: List[ExtractedHabit] = Field(
        default_factory=list,
        description="Procedural corrections or mistakes noticed in this chunk."
    )
    chunk_summary: str = Field(
        description="1 concise sentence summarizing what Shvan and Ghost discussed or accomplished in this chunk."
    )


# ── Active Mind Context Synthesizer (Pillar 5 Upgrade 1) ─────────────────────

_ACTIVE_MIND_PATH = os.path.join(_MEMORY_DIR, "active_mind_context.md")


def synthesize_active_mind_context(memory_instance=None) -> bool:
    """
    Pillar 5 Upgrade 1: Pre-computes a smart, decay-ranked Active Mind Context
    using gemini-3.5-flash-lite. Written to memory/active_mind_context.md so
    LiveBridge reads it at 0ms startup latency with no API call.

    Called after every successful reflection (micro + shutdown).
    """
    if memory_instance is None:
        from memory.ghost_memory import get_ghost_memory
        memory_instance = get_ghost_memory()
        memory_instance.load()

    try:
        # Gather all memory stores
        all_facts = memory_instance.get_existing_facts_for_prompt()
        all_habits = memory_instance._habits or []
        profile = memory_instance.get_profile()
        spark = memory_instance._companion.get("greeting_spark", {})

        facts_json = json.dumps(all_facts, indent=2, ensure_ascii=False) if all_facts else "[]"
        habits_json = json.dumps(
            [{"trigger": h.get("trigger", ""), "correction": h.get("correction", "")}
             for h in all_habits if isinstance(h, dict) and h.get("trigger")],
            indent=2, ensure_ascii=False
        ) if all_habits else "[]"
        spark_json = json.dumps(spark, indent=2, ensure_ascii=False) if spark else "{}"

        prompt = f"""You are Nova's pre-session mind synthesizer. Given the FULL memory below, write a
600-token ACTIVE MIND CONTEXT block in markdown that covers:
- Top 8 most important and recent facts about Shvan (rank by importance × recency — prefer high-importance recent facts over low-importance old ones)
- Top 5 most critical procedural habit corrections (the ones that prevent repeated mistakes)
- Current project status and open thread from Greeting Spark
- User profile summary (name, OS, communication style)

Format as a clean markdown block with ### headers. Be concise and information-dense.
Output ONLY the markdown block — no preamble, no explanation, no wrapping fences.

══ USER PROFILE ══
{json.dumps(profile, indent=2, ensure_ascii=False)}

══ ALL FACTS ({len(all_facts)} total) ══
{facts_json}

══ ALL HABIT CORRECTIONS ({len(all_habits)} total) ══
{habits_json}

══ GREETING SPARK (last session context) ══
{spark_json}
"""

        client = genai.Client()
        response = _generate_reflection_with_fallback(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0.1,
            ),
            tag="[ACTIVE MIND SYNTHESIS]"
        )

        if response and response.text:
            context_text = response.text.strip()
            # Atomic write
            tmp_path = f"{_ACTIVE_MIND_PATH}.tmp_{os.getpid()}_{threading.get_ident()}"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(context_text)
            os.replace(tmp_path, _ACTIVE_MIND_PATH)
            print(f"[SLEEP REFLECTOR] ✅ Active Mind Context synthesized → memory/active_mind_context.md ({len(context_text)} chars)")
            return True

    except Exception as e:
        print(f"[SLEEP REFLECTOR] ⚠️ Active Mind Context synthesis failed (non-fatal): {e}")

    return False


# ── Write-Ahead Log (WAL) Helpers ────────────────────────────────────────────

def dump_pending_session(
    session_stream: Optional[List[str]] = None,
    chunk_summaries: Optional[List[str]] = None
) -> None:
    """
    Argon Fix #1: Atomically dumps raw session transcript and accumulated chunk summaries
    to disk BEFORE launching background thread. Guaranteed preserved even if OS kills thread.
    """
    if not session_stream and not chunk_summaries:
        return
    try:
        os.makedirs(_MEMORY_DIR, exist_ok=True)
        tmp_path = f"{_PENDING_SESSION_PATH}.tmp_{os.getpid()}_{threading.get_ident()}"
        payload = {
            "session_stream": session_stream or [],
            "chunk_summaries": chunk_summaries or []
        }
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, _PENDING_SESSION_PATH)
    except Exception as e:
        print(f"[SLEEP REFLECTOR] Warning: Failed to dump WAL session: {e}")


# ── Micro-Reflection Execution (Rolling Background) ──────────────────────────

def execute_micro_reflection_sync(
    chunk: List[str],
    memory_instance=None
) -> Tuple[bool, Optional[MicroReflectionResult]]:
    """
    Executes a mid-session rolling micro-reflection on a ~30-turn chunk.
    Extracts facts, habits, and a 1-sentence chunk summary using gemini-3.5-flash-lite.
    Retries once on error.
    """
    if not chunk:
        return False, None

    if memory_instance is None:
        from memory.ghost_memory import get_ghost_memory
        memory_instance = get_ghost_memory()

    existing_facts = memory_instance.get_existing_facts_for_prompt()
    existing_triggers = memory_instance.get_existing_habit_triggers()

    facts_context_str = json.dumps(existing_facts, indent=2) if existing_facts else "[]"
    habits_context_str = json.dumps(existing_triggers) if existing_triggers else "[]"
    transcript_text = "\n".join(chunk)

    prompt = f"""You are the Subconscious Rolling Memory Mind of Desktop Ghost, analyzing a recent ~30-turn chunk of live interaction with Shvan.
Your goal is to extract high-level facts, habit corrections, and a 1-sentence summary of this chunk.

══ KNOWN EXISTING FACTS (DO NOT DUPLICATE) ══
{facts_context_str}

══ KNOWN HABIT TRIGGERS ══
{habits_context_str}

══ RECENT CHUNK TRANSCRIPT ══
{transcript_text}

══ INSTRUCTIONS ══
1. USER FACTS & PREFERENCES:
   - Identify personal facts, preferences, or lifestyle cues Shvan revealed in this chunk.
   - Do NOT duplicate facts that already exist above.
   - If Shvan changed or contradicted an existing fact, set 'supersedes_fact_id' to that fact's ID (e.g. 'f_001').
   - Rate importance 1-10 (10=major milestone, 1=trivia).

2. PROCEDURAL CORRECTIONS (Princeton Reflexion):
   - Check if Ghost made a mistake, took the wrong action, or if Shvan corrected Ghost (e.g. "no, not that window", "don't use open_app", "click desktop shortcut").
   - Extract the 'trigger', 'mistake', and 'correction'.

3. CHUNK SUMMARY:
   - Write exactly 1 concise sentence summarizing what was discussed, searched, clicked, or accomplished in this chunk.

4. LANGUAGE:
   - Shvan may speak English, Kurdish, or mixed phrasing. Understand accurately and write in clean English.
"""

    for attempt in range(2):
        try:
            client = genai.Client()
            response = _generate_reflection_with_fallback(
                client=client,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MicroReflectionResult,
                    temperature=0.1,
                ),
                tag="[MICRO REFLECTION]"
            )
            parsed_data: MicroReflectionResult = response.parsed
            if parsed_data:
                memory_instance.apply_micro_reflection(parsed_data.model_dump())
                summary_preview = parsed_data.chunk_summary[:80] + "..." if len(parsed_data.chunk_summary) > 80 else parsed_data.chunk_summary
                print(f"[MICRO REFLECTION] Rolling reflection complete ({len(parsed_data.new_facts)} new facts, {len(parsed_data.new_habits)} habits). Summary: {summary_preview}")
                # Pillar 5 Upgrade 1: Refresh Active Mind Context after new facts/habits
                synthesize_active_mind_context(memory_instance)
                return True, parsed_data
        except Exception as e:
            if attempt == 0:
                print(f"[MICRO REFLECTION] Attempt 1 failed ({e}). Retrying once...")
            else:
                print(f"[MICRO REFLECTION] Rolling reflection call failed after retry: {e}")
                return False, None

    return False, None


def trigger_micro_reflection(
    chunk: List[str],
    target_index: int,
    on_success: Optional[Callable[[MicroReflectionResult, int], None]] = None,
    on_failure: Optional[Callable[[], None]] = None
) -> threading.Thread:
    """
    Spawns an asynchronous background daemon thread to reflect on a chunk.
    Invokes on_success(result, target_index) on completion to safely advance pointers.
    """
    def _worker():
        success, result = execute_micro_reflection_sync(chunk)
        if success and result is not None:
            if on_success:
                try:
                    on_success(result, target_index)
                except Exception as e:
                    print(f"[MICRO REFLECTION] on_success callback error: {e}")
        else:
            if on_failure:
                try:
                    on_failure()
                except Exception as e:
                    print(f"[MICRO REFLECTION] on_failure callback error: {e}")

    thread = threading.Thread(
        target=_worker,
        name="GhostMicroReflector",
        daemon=True
    )
    thread.start()
    return thread


# ── Full Shutdown Reflection Execution ───────────────────────────────────────

def execute_reflection_sync(
    session_stream: Optional[List[str]] = None,
    memory_instance=None,
    chunk_summaries: Optional[List[str]] = None
) -> bool:
    """
    Executes the Gemini reflection call synchronously at session shutdown.
    Synthesizes facts/habits from the final tail chunk, plus an episode and greeting spark
    from the full session using chunk_summaries.
    """
    if not session_stream and not chunk_summaries:
        return False

    if memory_instance is None:
        from memory.ghost_memory import get_ghost_memory
        memory_instance = get_ghost_memory()

    # Ingest existing context so Gemini knows what's already saved (Argon Fix #2)
    existing_facts = memory_instance.get_existing_facts_for_prompt()
    existing_triggers = memory_instance.get_existing_habit_triggers()

    facts_context_str = json.dumps(existing_facts, indent=2) if existing_facts else "[]"
    habits_context_str = json.dumps(existing_triggers) if existing_triggers else "[]"

    transcript_text = "\n".join(session_stream) if session_stream else ""

    summaries_section = ""
    if chunk_summaries:
        summaries_list = "\n".join(f"- Chunk {i+1}: {s}" for i, s in enumerate(chunk_summaries))
        summaries_section = f"\n══ EARLIER 1-HOUR SESSION MILESTONES (CHUNKS 1..{len(chunk_summaries)}) ══\n{summaries_list}\n"

    prompt = f"""You are the Subconscious Reflection Mind of Desktop Ghost, analyzing a finished session with Shvan.
Your goal is to extract long-term memory updates based on Stanford Generative Agents and Princeton Reflexion principles.

══ KNOWN EXISTING FACTS (DO NOT DUPLICATE) ══
{facts_context_str}

══ KNOWN HABIT TRIGGERS ══
{habits_context_str}
{summaries_section}
══ FINAL SESSION TRANSCRIPT TAIL ══
{transcript_text if transcript_text else "(No final unreflected turns - synthesize episode & greeting spark from the milestones above)"}

══ INSTRUCTIONS ══
1. USER FACTS & PREFERENCES:
   - Identify personal facts, preferences, or lifestyle cues Shvan revealed in the final transcript tail.
   - Do NOT duplicate facts that already exist above.
   - If Shvan changed or contradicted an existing fact, set 'supersedes_fact_id' to that fact's ID (e.g. 'f_001').
   - Rate importance 1-10 (10=major milestone, 1=trivia).

2. PROCEDURAL CORRECTIONS (Reflexion):
   - Check if Ghost made a mistake, took the wrong action, or if Shvan corrected Ghost in the final transcript tail.
   - Extract the 'trigger', the 'mistake', and the 'correction'.

3. FULL-SESSION EPISODIC MOMENT:
   - Synthesize a 'new_episode' representing the ENTIRE session (using the Earlier Session Milestones plus the final tail). If the session was meaningful, summarize the major accomplishment. If trivial, null.

4. GREETING SPARK:
   - Create a Greeting Spark for the NEXT session representing what was discussed/accomplished across the full session, any unfinished open thread, and a mood hint.

5. LANGUAGE:
   - Shvan may speak English, Kurdish, or mixed phrasing. Understand the meaning accurately and write the extracted notes in clean English.
"""

    try:
        client = genai.Client()
        response = _generate_reflection_with_fallback(
            client=client,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=SessionReflection,
                temperature=0.2,
            ),
            tag="[SLEEP REFLECTOR]"
        )

        parsed_data: SessionReflection = response.parsed
        if parsed_data:
            memory_instance.apply_reflection(parsed_data.model_dump())
            print(f"[SLEEP REFLECTOR] Subconscious reflection complete ({len(parsed_data.new_facts)} new facts, {len(parsed_data.new_habits)} habits).")
            # Pillar 5 Upgrade 1: Pre-compute Active Mind Context for next session
            synthesize_active_mind_context(memory_instance)
            return True

    except Exception as e:
        print(f"[SLEEP REFLECTOR] Reflection call error: {e}")
        return False

    return False


def _background_worker(claim_path: str) -> None:
    """Background worker that claims and processes the WAL session file."""
    try:
        with open(claim_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            session_stream = data.get("session_stream", [])
            chunk_summaries = data.get("chunk_summaries", [])
        elif isinstance(data, list):
            session_stream = data
            chunk_summaries = []
        else:
            session_stream = []
            chunk_summaries = []

        success = execute_reflection_sync(session_stream, chunk_summaries=chunk_summaries)
        if success and os.path.exists(claim_path):
            os.remove(claim_path)
    except Exception as e:
        print(f"[SLEEP REFLECTOR] Background worker error: {e}")
        # Leave claim_path so next startup can recover it


def trigger_sleep_reflection(
    session_stream: Optional[List[str]] = None,
    chunk_summaries: Optional[List[str]] = None
) -> None:
    """
    Spawns an asynchronous background thread to reflect on the session.
    Argon Fix #1 & #3: Claims the WAL file so threads / new sessions don't collide.
    """
    if (session_stream and len(session_stream) > 0) or (chunk_summaries and len(chunk_summaries) > 0):
        dump_pending_session(session_stream, chunk_summaries)

    if not os.path.exists(_PENDING_SESSION_PATH):
        return

    # Claim the file atomically by renaming to thread-specific claim
    claim_path = f"{_PENDING_SESSION_PATH}.processing_{os.getpid()}_{threading.get_ident()}"
    try:
        os.replace(_PENDING_SESSION_PATH, claim_path)
    except OSError:
        # Already claimed by another worker
        return

    thread = threading.Thread(
        target=_background_worker,
        args=(claim_path,),
        name="GhostSleepReflector",
        daemon=False  # Finish writing before app exits
    )
    thread.start()
