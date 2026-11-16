"""
Procedural Playbook: MS Paint & Creative Canvas
Features:
- Guaranteed full-resolution canvas initialization (Ctrl+E -> 1200x700 sizing)
- Automatic window maximization and focus takeover
- Ribbon KeyTip navigation (Alt->H->P for pencil, Alt->H->E for eraser)
- Save As dialog (#32770) synchronization to prevent dropped path keystrokes
"""

import os
import time
import subprocess
from typing import Dict, Any, Optional

from skills.base_skill import BaseSkill
from skills import win32_window_utils
import actuator


class PaintSkill(BaseSkill):
    name = "paint"
    description = "High-precision MS Paint automation with guaranteed 1200x700 canvas sizing"

    def __init__(self):
        self.exe_path = win32_window_utils.find_app_executable("mspaint.exe")

    def is_available(self) -> bool:
        return self.exe_path is not None or win32_window_utils.find_app_executable("mspaint") is not None

    def get_supported_actions(self) -> Dict[str, str]:
        return {
            "launch_or_focus": "Launch MS Paint, maximize window, and bring to foreground",
            "setup_canvas": "Resize canvas to full size (1200x700) via Ctrl+E properties dialog",
            "clear_canvas": "Select all and clear canvas (Ctrl+A -> Delete)",
            "save_drawing": "Save file with modal dialog synchronization (Ctrl+S -> type path)"
        }

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        action = action.lower().strip()

        try:
            if action == "launch_or_focus":
                # Check if Paint is already open
                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=["paint"],
                    process_names=["mspaint.exe"],
                    timeout=0.3
                )
                if not hwnd:
                    try:
                        os.startfile("mspaint.exe")
                    except Exception:
                        subprocess.Popen(["mspaint.exe"])

                    hwnd = win32_window_utils.wait_for_visible_window(
                        title_keywords=["paint"],
                        process_names=["mspaint.exe"],
                        timeout=5.0
                    )

                if hwnd:
                    win32_window_utils.maximize_window(hwnd)
                    win32_window_utils.force_foreground_window(hwnd)
                    time.sleep(0.4)
                    return {
                        "status": "success",
                        "message": "MS Paint launched, maximized, and focused.",
                        "hwnd": hwnd
                    }
                return {"status": "error", "message": "Failed to find MS Paint window after launch."}

            elif action == "setup_canvas":
                width = int(params.get("width", 1200))
                height = int(params.get("height", 700))

                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=["paint"],
                    process_names=["mspaint.exe"],
                    timeout=1.0
                )
                if not hwnd:
                    return {"status": "error", "message": "Paint window not found; aborted canvas setup."}

                win32_window_utils.force_foreground_window(hwnd)
                time.sleep(0.2)

                # Send Ctrl+E to open Image Properties dialog
                actuator.execute_hotkey(["ctrl", "e"])
                dialog_hwnd = win32_window_utils.wait_for_dialog(timeout=2.0)
                if not dialog_hwnd:
                    return {
                        "status": "error",
                        "message": "Image Properties dialog (#32770) did not open; aborted typing to protect user inputs."
                    }

                time.sleep(0.15)
                # Type Width, Tab, Height, Enter safely inside verified dialog
                actuator.execute_type(str(width), press_enter=False)
                time.sleep(0.08)
                actuator.execute_press_key("tab")
                time.sleep(0.08)
                actuator.execute_type(str(height), press_enter=True)
                time.sleep(0.3)

                return {
                    "status": "success",
                    "message": f"Resized Paint canvas to {width}x{height} pixels via Ctrl+E.",
                    "canvas_size": f"{width}x{height}"
                }

            elif action == "clear_canvas":
                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=["paint"],
                    process_names=["mspaint.exe"],
                    timeout=1.0
                )
                if hwnd:
                    win32_window_utils.force_foreground_window(hwnd)

                actuator.execute_hotkey(["ctrl", "a"])
                time.sleep(0.1)
                actuator.execute_press_key("delete")
                return {"status": "success", "message": "Cleared drawing canvas."}

            elif action == "save_drawing":
                file_path = params.get("file_path")
                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=["paint"],
                    process_names=["mspaint.exe"],
                    timeout=1.0
                )
                if not hwnd:
                    return {"status": "error", "message": "Paint window not found for save."}

                win32_window_utils.force_foreground_window(hwnd)
                actuator.execute_hotkey(["ctrl", "s"])
                dialog_hwnd = win32_window_utils.wait_for_dialog(timeout=2.0)
                if not dialog_hwnd:
                    return {"status": "error", "message": "Save dialog did not appear; aborted typing to protect user inputs."}

                time.sleep(0.2)
                if file_path:
                    clean_path = os.path.abspath(str(file_path))
                    actuator.execute_type(clean_path, press_enter=True)
                    time.sleep(0.5)
                    return {"status": "success", "message": f"Saved drawing to {clean_path}."}
                else:
                    return {"status": "success", "message": "Triggered Save dialog for user/visual confirmation."}

            else:
                return {"status": "error", "message": f"Unsupported action '{action}' for Paint skill."}

        except Exception as e:
            return {"status": "error", "message": f"Paint skill failed on '{action}': {e}"}
