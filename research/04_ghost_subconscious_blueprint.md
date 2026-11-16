# Research Note 04: Desktop Ghost Subconscious Memory Blueprint
**System:** Desktop Ghost Live Agent v2 — Autonomous Subconscious Reflection Engine

---

## 1. The Design Challenge: Zero Live Latency
Desktop Ghost is a real-time, 16kHz audio-streaming companion. 
* Any API calls, heavy semantic calculations, or file parsing *during* active speech would induce audio latency (> 1000ms), breaking the conversational magic.
* **The Solution:** Decouple the **Conversation Stream** (instant) from the **Subconscious Reflection** (background/asynchronous).

---

## 2. The Two-Brain Architecture

```
                  ┌──────────────────────────────────────────────┐
                  │                 FAST BRAIN                   │
                  │              (Live Bridge)                   │
                  │   • Real-time WebSocket audio (16kHz/24kHz)  │
                  │   • 0ms extra latency                        │
                  │   • Appends dialogue turns to SessionBuffer  │
                  └──────────────────────┬───────────────────────┘
                                         │ Session Ends / Sleep
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │              SUBCONSCIOUS BRAIN              │
                  │           (Background Reflector)             │
                  │   • Runs outside the WebSocket connection    │
                  │   • Reviews SessionBuffer                    │
                  │   • Extracts:                                │
                  │       - Personal facts & preferences         │
                  │       - Corrections & mistakes made          │
                  │   • Auto-updates companion.json & habits.json│
                  └──────────────────────┬───────────────────────┘
                                         │ Next Boot
                                         ▼
                  ┌──────────────────────────────────────────────┐
                  │            PERSISTENT COMPANION              │
                  │   • Reads updated memory context at startup  │
                  │   • Welcomes Shvan naturally with full recall│
                  └──────────────────────────────────────────────┘
```

---

## 3. The Subconscious Reflection Pipeline

When `LiveBridge.run()` exits or `sleep()` is triggered:

1. **Dump Session Buffer:** Collect all user utterances and Ghost actions from the active session into a clean structured transcript.
2. **Evaluation & Extraction Prompt:** Send the transcript to a fast, non-streaming Gemini model (e.g. `gemini-2.5-flash` or background standard API call):
   ```json
   {
     "new_facts": [
       "Drinks tea when tired",
       "Codes late night hours"
     ],
     "new_habits": [
       {
         "trigger": "open chrome",
         "mistake": "Opened profile selector window",
         "correction": "Double-click desktop shortcut"
       }
     ],
     "session_summary": "Tested live agent audio and discussed memory architecture"
   }
   ```
3. **Merge & Conflict Resolution:**
   - In `ghost_memory.py`:
     - Compare `new_facts` against existing facts. Update/replace outdated items.
     - Upsert `new_habits` into `habits.json`.
     - Record `session_summary` under `last_activity`.
4. **Clean Exit:** The process terminates quietly. The next session opens with complete relationship continuity.
