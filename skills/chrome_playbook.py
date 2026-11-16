"""
Procedural Playbook: Google Chrome & Web Navigation
Features:
- Multi-window & active-process awareness (detects existing Chrome instance)
- Profile & session preservation (never creates ephemeral guest profiles)
- Instant tab creation, navigation, omnibox search, and tab closure
- URL validation and sanitization
"""

import os
import time
import subprocess
import urllib.parse
from typing import Dict, Any, Optional

from skills.base_skill import BaseSkill
from skills import win32_window_utils
import actuator


class ChromeSkill(BaseSkill):
    name = "chrome"
    description = "High-speed navigation, tab management, and search in Google Chrome"

    def __init__(self):
        self.exe_path = win32_window_utils.find_app_executable("chrome.exe")

    def is_available(self) -> bool:
        return self.exe_path is not None or win32_window_utils.find_app_executable("chrome") is not None

    def get_supported_actions(self) -> Dict[str, str]:
        return {
            "navigate": "Open or navigate to a URL (preserves active logins and sessions)",
            "new_tab": "Open a new browser tab with optional target URL",
            "close_tab": "Close the currently active tab (Ctrl+W)",
            "focus_search": "Focus the address bar (Ctrl+L) and optionally search a query",
            "zoom_reset": "Reset page zoom to 100% (Ctrl+0)"
        }

    def _sanitize_url(self, raw_url: str) -> str:
        """Ensures URL has standard scheme and prevents argument injection."""
        url = raw_url.strip()
        if not url:
            return "https://www.google.com"
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("file://")):
            url = f"https://{url}"
        return url

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        action = action.lower().strip()

        # Check existing Chrome window
        existing_hwnd = win32_window_utils.wait_for_visible_window(
            title_keywords=["chrome", "google chrome"],
            process_names=["chrome.exe"],
            timeout=0.2
        )

        try:
            if action == "navigate":
                target_url = self._sanitize_url(str(params.get("url", "https://www.google.com")))
                
                if existing_hwnd:
                    # Chrome is already running: bring forward and navigate directly
                    win32_window_utils.force_foreground_window(existing_hwnd)
                    time.sleep(0.1)
                    # Open new tab to avoid destroying user's existing work
                    actuator.execute_hotkey(["ctrl", "t"])
                    time.sleep(0.15)
                    actuator.execute_type(target_url, press_enter=True)
                    time.sleep(0.5)
                    return {
                        "status": "success",
                        "message": f"Navigated to {target_url} in active Chrome instance (new tab).",
                        "url": target_url
                    }
                else:
                    # Launch Chrome cleanly
                    if self.exe_path and os.path.exists(self.exe_path):
                        subprocess.Popen([self.exe_path, target_url])
                    else:
                        os.startfile(target_url)

                    new_hwnd = win32_window_utils.wait_for_visible_window(
                        title_keywords=["chrome", "google chrome"],
                        process_names=["chrome.exe"],
                        timeout=5.0
                    )
                    if new_hwnd:
                        win32_window_utils.maximize_window(new_hwnd)
                        win32_window_utils.force_foreground_window(new_hwnd)
                        time.sleep(0.5)
                        return {
                            "status": "success",
                            "message": f"Launched Chrome and navigated to {target_url}.",
                            "hwnd": new_hwnd
                        }
                    else:
                        return {
                            "status": "success",
                            "message": f"Launched Chrome with {target_url} (window rendering asynchronously)."
                        }

            elif action == "new_tab":
                if existing_hwnd:
                    win32_window_utils.force_foreground_window(existing_hwnd)
                actuator.execute_hotkey(["ctrl", "t"])
                time.sleep(0.15)
                target_url = params.get("url")
                if target_url:
                    clean_url = self._sanitize_url(str(target_url))
                    actuator.execute_type(clean_url, press_enter=True)
                return {"status": "success", "message": "Opened new tab."}

            elif action == "close_tab":
                if existing_hwnd:
                    win32_window_utils.force_foreground_window(existing_hwnd)
                actuator.execute_hotkey(["ctrl", "w"])
                return {"status": "success", "message": "Closed active tab."}

            elif action == "focus_search":
                if existing_hwnd:
                    win32_window_utils.force_foreground_window(existing_hwnd)
                actuator.execute_hotkey(["ctrl", "l"])
                time.sleep(0.1)
                query = params.get("query")
                if query:
                    actuator.execute_type(str(query), press_enter=True)
                return {"status": "success", "message": "Focused search bar and executed query."}

            elif action == "zoom_reset":
                if existing_hwnd:
                    win32_window_utils.force_foreground_window(existing_hwnd)
                actuator.execute_hotkey(["ctrl", "0"])
                return {"status": "success", "message": "Reset zoom to 100%."}

            else:
                return {
                    "status": "error",
                    "message": f"Unsupported action '{action}' for Chrome skill."
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Chrome skill failed on action '{action}': {e}"
            }
