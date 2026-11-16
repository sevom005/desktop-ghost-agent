# Research Note 02: Reflexion (Shinn et al., 2023)
**Paper Title:** *Reflexion: Language Agents with Verbal Reinforcement Learning*  
**Authors:** Noah Shinn, Federico Cassano, Beck Labash, Ashwin Gopinath, Karthik Narasimhan, Shunyu Yao (Princeton University & MIT)  
**ArXiv:** [2303.11366](https://arxiv.org/abs/2303.11366)

---

## 1. Executive Summary & Core Breakthrough
Traditional reinforcement learning requires updating model weights via expensive backpropagation. *Reflexion* proved that an LLM agent can learn from its own mistakes in real-time by generating **verbal reflections** (textual heuristics) that it stores in episodic memory and retrieves on subsequent attempts.

---

## 2. The 3 Core Components of Reflexion

```
     ┌────────────────────────────────────────────────────────┐
     │                     ACTOR AGENT                        │
     │      Executes tool actions in the desktop environment  │
     └──────────────────────────┬─────────────────────────────┘
                                │ Trajectory (actions + results)
                                ▼
     ┌────────────────────────────────────────────────────────┐
     │                   EVALUATOR MODEL                      │
     │      Detects failures, user corrections, or errors     │
     └──────────────────────────┬─────────────────────────────┘
                                │ Failure Signal
                                ▼
     ┌────────────────────────────────────────────────────────┐
     │                SELF-REFLECTION ENGINE                  │
     │     "Why did I fail? What should I do differently?"    │
     └──────────────────────────┬─────────────────────────────┘
                                │ Learned Heuristic / Habit Rule
                                ▼
     ┌────────────────────────────────────────────────────────┐
     │                    HABIT REPOSITORY                    │
     │                memory/habits.json                      │
     └────────────────────────────────────────────────────────┘
```

### A. Failure Detection (The Evaluator)
Failures are detected through:
1. **Tool error returns:** (e.g. `error: Element not found`, `Process crashed`).
2. **Implicit User Corrections:** The user says:
   - *"No, not that one"*
   - *"Wait, close that window"*
   - *"I meant the desktop shortcut, not open_app"*

### B. Verbal Self-Reflection
Instead of continuing to retry blindly, the agent generates a self-reflection prompt:
> *"I attempted to launch Chrome via `open_app('chrome')`. This triggered the Chrome profile selection screen, interrupting Shvan's workflow. The correct behavior is to interact with the existing desktop or taskbar shortcut."*

### C. Habit Induction
This reflection is converted into an actionable **Habit Rule**:
- **Trigger:** `"open chrome"`
- **Mistake:** `"Used open_app which triggers profile selector"`
- **Correction:** `"Double-click desktop icon or target taskbar"`

---

## 3. Direct Translation to Desktop Ghost

* **The Problem Today:** Today, Shvan has to explicitly say: *"Ghost, learn habit: trigger X, mistake Y, correction Z"*.
* **The Reflexion Upgrade:** Ghost passively monitors the transcript for correction phrases (*"no, wrong window"*, *"close that"*, *"do this instead"*). During the session end / reflection phase, Ghost generates the habit rule automatically. Shvan never has to teach him like a programmer.
