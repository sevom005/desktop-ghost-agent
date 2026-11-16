# Research Note 01: Stanford Generative Agents (Park et al., 2023)
**Paper Title:** *Generative Agents: Interactive Simulacra of Human Behavior*  
**Authors:** Joon Sung Park, Joseph C. O'Hanlon, Carrie J. Cai, Meredith Ringel Morris, Percy Liang, Michael S. Bernstein (Stanford University & Google Research)  
**ArXiv:** [2304.03442](https://arxiv.org/abs/2304.03442)

---

## 1. Executive Summary & Core Breakthrough
The Stanford paper revolutionized AI agent memory by moving away from simple prompt-history stuffing. Instead, it introduced an **organic, human-like memory system** that allows autonomous agents to:
1. Remember past interactions without requiring explicit "save" commands.
2. Form relationships and opinions about people over time.
3. Synthesize high-level reflections from low-level daily observations.

---

## 2. The 3-Part Architecture

```
                    ┌────────────────────────────────────────┐
                    │             MEMORY STREAM              │
                    │   Chronological record of experiences  │
                    └───────────────────┬────────────────────┘
                                        │
                 ┌──────────────────────┴──────────────────────┐
                 ▼                                             ▼
     ┌───────────────────────┐                     ┌───────────────────────┐
     │   RETRIEVAL ENGINE    │                     │   REFLECTION ENGINE   │
     │  Recency × Importance │                     │ Synthesizes insights  │
     │      × Relevance      │                     │ during idle / "sleep" │
     └───────────────────────┘                     └───────────────────────┘
```

### A. The Memory Stream (Observation Log)
- A comprehensive, timestamped record of everything the agent perceives, says, or does.
- Format: Natural language observation objects.
- *In Desktop Ghost:* The audio transcript chunks already captured during conversation turns (`_append_user_speech` and `_append_ghost_speech`).

### B. The Reflection Engine (The "Sleep / Subconscious" Phase)
- **The Problem:** Raw memory streams quickly grow too large and full of mundane details (e.g., *"Shvan said hello"*, *"Shvan clicked Chrome"*).
- **The Solution:** Periodic **Reflection**. When agents are idle or go to sleep, the system prompts an LLM to review recent events and extract **higher-level thoughts**:
  - *Input:* 15 dialogue lines about being tired, staying up late, drinking tea.
  - *Reflection Prompt:* *"Given the recent observations, what high-level insights or habits can we infer about the user?"*
  - *Output:* *"Insight: Shvan often works late night hours and relies on tea to focus."*
- These synthesized reflections are written into long-term memory so future sessions start with deep contextual awareness.

### C. Retrieval Scoring Function
When deciding what to keep in working context:
$$\text{Score} = \alpha_{\text{recency}} \cdot \text{Recency} + \alpha_{\text{importance}} \cdot \text{Importance} + \alpha_{\text{relevance}} \cdot \text{Relevance}$$
- **Recency:** Exponential decay over hours/days.
- **Importance:** Salience score (1-10) — fixing a major bug is 9/10, asking the time is 1/10.
- **Relevance:** Contextual fit to current user intent.

---

## 3. Direct Translation to Desktop Ghost

1. **Zero Voice Lag Rule:** The Memory Stream is recorded silently during the live call.
2. **The "Sleep Trigger":** When Shvan says *"Ghost, sleep"* or closes the widget, Ghost closes the audio connection, and in the background kicks off a **Reflection Task** over the session transcript.
3. **Auto-Synthesis:** Ghost extracts user facts and preferences without Shvan ever saying *"Ghost, remember this"*.
