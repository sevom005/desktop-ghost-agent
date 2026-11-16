"""
Procedural Playbook: Telegram Desktop & Web Hybrid
Features:
- Dual-mode operation: auto-detects Telegram Desktop vs Telegram Web
- Graceful web fallback: launches https://web.telegram.org in default browser if desktop client is missing
- SPA load synchronization (waits for web DOM mount)
- Safe handoff to visual motor loop for chat and contact selection
"""

import os
import time
import subprocess
from typing import Dict, Any, Optional

from skills.base_skill import BaseSkill
from skills import win32_window_utils
import actuator


class TelegramSkill(BaseSkill):
    name = "telegram"
    description = "Hybrid Telegram automation (Desktop client with automatic Telegram Web fallback)"

    def __init__(self):
        self.desktop_exe = win32_window_utils.find_app_executable("telegram.exe")

    def is_available(self) -> bool:
        # Always available because of Telegram Web fallback
        return True

    def get_supported_actions(self) -> Dict[str, str]:
        return {
            "open_telegram": "Launch Telegram Desktop or open Telegram Web in browser",
            "search_chat": "Search for a contact or group by name",
            "send_message": "Type and send a message into the active chat"
        }

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        action = action.lower().strip()
        has_desktop = self.desktop_exe is not None and os.path.exists(self.desktop_exe)

        try:
            if action == "open_telegram":
                if has_desktop:
                    subprocess.Popen([self.desktop_exe])
                    hwnd = win32_window_utils.wait_for_visible_window(
                        title_keywords=["telegram"],
                        process_names=["telegram.exe"],
                        timeout=5.0
                    )
                    if hwnd:
                        win32_window_utils.force_foreground_window(hwnd)
                        win32_window_utils.maximize_window(hwnd)
                    return {
                        "status": "success",
                        "mode": "desktop",
                        "message": "Launched Telegram Desktop and brought window to front."
                    }
                else:
                    # Web Fallback: open https://web.telegram.org in primary browser
                    web_url = "https://web.telegram.org"
                    chrome_exe = win32_window_utils.find_app_executable("chrome.exe")
                    if chrome_exe and os.path.exists(chrome_exe):
                        subprocess.Popen([chrome_exe, web_url])
                    else:
                        os.startfile(web_url)

                    hwnd = win32_window_utils.wait_for_visible_window(
                        title_keywords=["telegram", "chrome"],
                        timeout=5.0
                    )
                    if hwnd:
                        win32_window_utils.force_foreground_window(hwnd)
                        win32_window_utils.maximize_window(hwnd)

                    # Allow 2.0s for Single-Page App DOM mount
                    time.sleep(2.0)
                    return {
                        "status": "success",
                        "mode": "web",
                        "message": "Telegram Desktop not detected; opened Telegram Web in browser. Ready for visual chat selection."
                    }

            elif action == "search_chat":
                contact = str(params.get("query") or params.get("contact", "")).strip()
                if not contact:
                    return {"status": "error", "message": "Missing 'query' or 'contact' parameter."}

                if has_desktop:
                    # In Desktop client: Ctrl+K opens quick switcher
                    actuator.execute_hotkey(["ctrl", "k"])
                    time.sleep(0.2)
                    actuator.execute_type(contact, press_enter=True)
                    time.sleep(0.5)
                    return {"status": "success", "message": f"Searched and opened chat '{contact}' in Telegram Desktop."}
                else:
                    # In Web client: Focus search via '/' key or clicking
                    actuator.execute_press_key("esc")
                    time.sleep(0.1)
                    actuator.execute_press_key("/")
                    time.sleep(0.15)
                    actuator.execute_type(contact, press_enter=True)
                    time.sleep(0.5)
                    return {"status": "success", "message": f"Typed search query '{contact}' in Telegram Web. Vision will confirm chat selection."}

            elif action == "send_message":
                text = str(params.get("text", "")).strip()
                if not text:
                    return {"status": "error", "message": "Missing 'text' parameter."}

                actuator.execute_type(text, press_enter=True)
                return {"status": "success", "message": f"Sent message: '{text}'"}

            else:
                return {"status": "error", "message": f"Unsupported action '{action}' for Telegram skill."}

        except Exception as e:
            return {"status": "error", "message": f"Telegram skill failed on '{action}': {e}"}
