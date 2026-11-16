"""
Desktop Ghost Live Agent v2 — Terminal Launcher
================================================
Single entry point to launch the real-time voice-driven desktop copilot
powered by gemini-3.8-live.

Usage:
    python run_live.py

Features:
  - Full-duplex voice conversation with instant (<300ms) audio playback
  - Continuous desktop screen perception (1 FPS + immediate post-action frames)
  - Non-blocking Windows app launch, web navigation, mouse clicking, and typing
  - Say "sleep" or "goodbye" to put the agent on standby
  - Emergency abort: Slam mouse violently to top-left corner (0,0) or press Ctrl+C
"""

import sys
import os
import asyncio

os.system("")  # Enable Windows ANSI escape codes
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

import sounddevice as sd
from live.live_bridge import LiveBridge


def print_banner():
    try:
        mic_info = sd.query_devices(kind="input")["name"]
        spk_info = sd.query_devices(kind="output")["name"]
    except Exception:
        mic_info = "Default Input"
        spk_info = "Default Output"

    ORANGE = "\033[38;2;234;88;12m"       # Claude terracotta-orange
    PEACH = "\033[38;2;251;146;60m"       # Soft peach accent
    WHITE = "\033[38;2;244;244;245m"
    DIM = "\033[38;2;161;161;170m"
    CYAN = "\033[38;2;56;189;248m"
    GREEN = "\033[38;2;52;211;153m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    print(f"""
{ORANGE}{BOLD}   ╭──────────────────────────────────────────────╮
   │   ✦ GHOST    Desktop Live Voice Copilot      │
   │  ( ✦ _ ✦ )   for Shvan • Always Listening    │
   ╰──────────────────────────────────────────────╯{RESET}
   {DIM}•{RESET} {WHITE}{BOLD}Engine:{RESET}   {CYAN}gemini-3.8-live{RESET} {DIM}(Zero Latency Voice){RESET}  {DIM}•{RESET} {WHITE}{BOLD}Voice:{RESET} {PEACH}Puck{RESET}
   {DIM}•{RESET} {WHITE}{BOLD}Memory:{RESET}   {GREEN}Stanford Generative Agents + Mem0 (Subconscious Active){RESET}
   {DIM}•{RESET} {WHITE}{BOLD}Audio:{RESET}    {DIM}Mic: {mic_info} | Speaker: {spk_info}{RESET}
   {DIM}•{RESET} {WHITE}{BOLD}Safety:{RESET}   {DIM}Move cursor to top-left (0,0) or Ctrl+C to abort{RESET}
   {ORANGE}──────────────────────────────────────────────────────────────────{RESET}
""")


async def main():
    print_banner()

    # Verify Gemini API key exists
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[ERROR] GEMINI_API_KEY is not set in your .env file!")
        return

    bridge = LiveBridge(
        on_standby=lambda: print("\n[STATUS] Ghost is now sleeping. Run again whenever you are ready!"),
        on_status=lambda s: print(f"[STATUS] State: {s.upper()}"),
    )

    try:
        await bridge.run()
    except KeyboardInterrupt:
        print("\n[USER ABORT] Ctrl+C detected. Shutting down...")
        bridge.request_stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[EXIT] Goodbye!")
