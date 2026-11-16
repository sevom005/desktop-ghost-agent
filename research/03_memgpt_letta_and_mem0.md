# Research Note 03: MemGPT / Letta & Mem0 (Packer et al., 2023 / Mem0, 2024)
**Papers / Frameworks:**  
- *MemGPT: Towards LLMs as Operating Systems* (UC Berkeley) — [ArXiv:2310.08560](https://arxiv.org/abs/2310.08560)  
- *Mem0: The Memory Layer for Personalized AI Applications* (2024)

---

## 1. Executive Summary & Core Breakthrough

LLM context windows act like **RAM** (fast, limited, temporary). The file system acts like **Hard Disk Storage** (persistent, large, permanent).
*MemGPT* and *Mem0* demonstrated how to bridge these two layers without manual prompt engineering by establishing:
1. **Tiered Context Paging:** Working context vs. Archival storage.
2. **Autonomous Fact Extraction:** Identifying user attributes (preferences, goals, biographical facts) organically from casual chat.
3. **Conflict Resolution & Entity De-duplication:** Overwriting outdated facts when new facts arrive, avoiding contradictory memory pollution.

---

## 2. Memory Tiering Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    TIER 1: WORKING RAM (LIVE)                   │
│   • SYSTEM_INSTRUCTION (System rules + Top 10 Facts + Habits)   │
│   • Current turn audio/transcription buffer                     │
└────────────────────────────────┬────────────────────────────────┘
                                 │
           Startup: Paged IN ◄───┴───► Sleep: Consolidated & Written
                                 │
┌────────────────────────────────▼────────────────────────────────┐
│                TIER 2: LOCAL DISK ARCHIVE (OFFLINE)             │
│   • memory/companion.json (User facts, milestones, style)       │
│   • memory/habits.json (Learned procedural corrections)         │
│   • memory/sessions/*.json (Raw conversation stream logs)       │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. Conflict Resolution & Auto-Overwriting (Mem0 Principle)

Human beliefs change over time. If memory is append-only, the model gets confused:
* *Day 1:* *"Shvan prefers Chrome."*
* *Day 10:* *"Shvan switched to Brave as his primary browser."*

**The Mem0 Resolution Rule:**
When an extracted fact updates or contradicts an existing entry:
1. Identify existing related entries in `companion.json["facts"]`.
2. Replace or consolidate the old fact rather than adding a second contradictory fact.
3. Keep the most recent preference dominant.

---

## 4. Direct Translation to Desktop Ghost

1. Ghost keeps his working context concise: capped at the **Top 10 most relevant facts and habits** to prevent token bloating.
2. New facts extracted in the background pass through a conflict checker before being written to `companion.json`.
3. The system remains 100% local JSON files—no external vector database or cloud dependencies required.
