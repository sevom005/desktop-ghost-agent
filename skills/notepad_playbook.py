"""
Procedural Playbook: Windows Notepad & Text Scratchpad
Features:
- Fast text file opening and scratchpad creation
- Synchronized #32770 Save As dialog typing (no text corruption in document body)
- Unicode text injection via hardware SendInput
"""

import os
import time
import subprocess
from typing import Dict, Any, Optional

from skills.base_skill import BaseSkill
from skills import win32_window_utils
import actuator


class NotepadSkill(BaseSkill):
    name = "notepad"
    description = "Fast text editing, note-taking, and file saving in Windows Notepad"

    def __init__(self):
        self.exe_path = win32_window_utils.find_app_executable("notepad.exe")

    def is_available(self) -> bool:
        return self.exe_path is not None or win32_window_utils.find_app_executable("notepad") is not None

    def get_supported_actions(self) -> Dict[str, str]:
        return {
            "open_notepad": "Launch clean Notepad or open an existing text file",
            "write_text": "Type or append text into the active Notepad document",
            "save_file": "Save document with modal dialog synchronization (Ctrl+S -> type path)"
        }

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        action = action.lower().strip()

        try:
            if action == "open_notepad":
                file_path = params.get("file_path")
                if file_path:
                    clean_path = os.path.abspath(str(file_path))
                    subprocess.Popen(["notepad.exe", clean_path])
                else:
                    subprocess.Popen(["notepad.exe"])

                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=["notepad"],
                    process_names=["notepad.exe"],
                    timeout=4.0
                )
                if hwnd:
                    win32_window_utils.force_foreground_window(hwnd)
                    win32_window_utils.maximize_window(hwnd)
                    return {"status": "success", "message": "Opened Notepad.", "hwnd": hwnd}
                return {"status": "error", "message": "Failed to open Notepad window."}

            elif action == "write_text":
                text = str(params.get("text", ""))
                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=["notepad"],
                    process_names=["notepad.exe"],
                    timeout=1.0
                )
                if hwnd:
                    win32_window_utils.force_foreground_window(hwnd)

                actuator.execute_type(text, press_enter=bool(params.get("press_enter", True)))
                return {"status": "success", "message": f"Wrote {len(text)} characters into Notepad."}

            elif action == "save_file":
                file_path = params.get("file_path")
                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=["notepad"],
                    process_names=["notepad.exe"],
                    timeout=1.0
                )
                if not hwnd:
                    return {"status": "error", "message": "Notepad window not found for save."}

                win32_window_utils.force_foreground_window(hwnd)
                actuator.execute_hotkey(["ctrl", "s"])
                dialog_hwnd = win32_window_utils.wait_for_dialog(timeout=2.0)
                if not dialog_hwnd:
                    return {"status": "error", "message": "Save dialog did not appear; aborted typing to protect user inputs."}

                time.sleep(0.2)
                if file_path:
                    clean_path = os.path.abspath(str(file_path))
                    actuator.execute_type(clean_path, press_enter=True)
                    time.sleep(0.4)
                    return {"status": "success", "message": f"Saved file to {clean_path}."}
                else:
                    return {"status": "success", "message": "Triggered Save dialog in Notepad."}

            else:
                return {"status": "error", "message": f"Unsupported action '{action}' for Notepad skill."}

        except Exception as e:
            return {"status": "error", "message": f"Notepad skill failed on '{action}': {e}"}
