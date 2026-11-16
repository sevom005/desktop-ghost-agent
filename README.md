# Desktop Ghost // Windows Autonomous Voice & Desktop Copilot

> **Created by Shvan**

Autonomous Windows desktop automation copilot powered by the **Google Gemini Live API** (`gemini-3.8-live` and `gemini-3.5-flash-lite`). Features a floating circular desktop companion avatar with real-time bidirectional voice, hardware-level Win32 actuation, background execution sub-agents, spatial editor awareness, and self-healing memory.

---

## ✨ Features

- 🎙️ **Real-Time Bidirectional Voice**: Ultra-low latency voice interaction powered by Google Gemini 3.8 Live over persistent WebSockets.
- 🤖 **Floating Desktop Companion**: Procedurally animated circular desktop widget with expressive eyes, blinks, glances, live speech sync, and single-click barge-in interruption.
- ⚡ **Sub-Agent B (Headless Task Execution)**: Offloads heavy coding, terminal, and browser jobs to an asynchronous background worker without locking your voice conversation.
- 🧠 **Continuous 3-Tier Memory**: Stanford Generative Agents inspired memory engine that remembers user preferences, learns from corrections, and consolidates sleep reflections.
- 🛡️ **Active Spatial Consciousness & Anti-Wipe Shield**: Auto-detects active files in VS Code / Notepad++ ("create an RNN in here") and bans dangerous wipe actions (Ctrl+A + Backspace).
- 🔄 **Dynamic Model Fallback Cascade**: Automatic failover (`gemini-3.5-flash-lite` → `gemini-3.1-flash-lite` → `gemini-3.5-flash`) on temporary 503 high-demand spikes.

---

## 🚀 Quick Start

### 1. Clone the Repository

```powershell
git clone https://github.com/sevom005/desktop-ghost-agent.git
cd desktop-ghost-agent
```

### 2. Install Required Libraries

```powershell
pip install google-genai pillow pyautogui mss python-dotenv pyperclip sounddevice numpy pytest
```

### 3. Configure Your Gemini API Key

Copy the environment template:
```powershell
copy .env.example .env
```

Open `.env` in any text editor and paste your [Google Gemini API Key](https://aistudio.google.com/app/apikey):
```ini
GEMINI_API_KEY=your_gemini_api_key_here
GHOST_VOICE=Puck
GHOST_THINKING_LEVEL=off
```

### 4. Launch Desktop Ghost

#### Option A: Floating Companion Widget (Recommended ✨)
```powershell
python floating_widget.py
```
*(Or simply double-click `start_ghost.bat`)*

- **Click the Avatar**: Starts the live voice session.
- **Click while Ghost Speaks**: Instant manual barge-in interruption (cuts off audio & unmutes mic).
- **Drag**: Drag the avatar anywhere on your desktop (clamps to screen edges).
- **Voice**: Speak freely; say *"sleep"* or *"goodbye"* to put Ghost in standby.

#### Option B: Terminal Voice Interface
```powershell
python run_live.py
```

---

## 🧪 Running the Test Suite

Run the full automated test suite (84 integration and unit tests):
```powershell
pytest tests/
```

---

## 🛡️ Emergency Failsafe (Safety Stop)

If you ever need to stop an automated mouse/keyboard action instantly:
- **Hardware Failsafe**: Slam your mouse cursor violently to the **top-left corner `(0, 0)`**.
- **Terminal Failsafe**: Press `Ctrl + C` in the console window to immediately release all inputs.

---

## 📄 License

MIT License — Created by Shvan. Feel free to use, modify, and contribute!
