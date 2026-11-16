"""
Procedural Playbook: Windows File Explorer & Filesystem Management
Features:
- Instant directory navigation with alias expansion (Desktop, Downloads, Documents)
- Native file selection via 'explorer.exe /select,"path"'
- Deterministic folder creation and focus
"""

import os
import time
import subprocess
from typing import Dict, Any, Optional

from skills.base_skill import BaseSkill
from skills import win32_window_utils
import actuator


class ExplorerSkill(BaseSkill):
    name = "explorer"
    description = "High-speed Windows File Explorer navigation and filesystem management"

    def is_available(self) -> bool:
        return True

    def get_supported_actions(self) -> Dict[str, str]:
        return {
            "open_directory": "Open a folder in Explorer (supports 'desktop', 'downloads', 'documents', or full paths)",
            "select_file": "Open Explorer with a specific file highlighted and selected",
            "create_folder": "Create a new folder and open it in Explorer"
        }

    def _resolve_directory(self, alias: str) -> str:
        alias_clean = alias.strip().lower()
        user_profile = os.environ.get("USERPROFILE", "C:\\Users\\Administrator")

        if alias_clean in ("desktop", "desk"):
            return os.path.join(user_profile, "Desktop")
        elif alias_clean in ("downloads", "download"):
            return os.path.join(user_profile, "Downloads")
        elif alias_clean in ("documents", "doc", "docs"):
            return os.path.join(user_profile, "Documents")
        elif alias_clean in ("pictures", "pics"):
            return os.path.join(user_profile, "Pictures")
        
        # Absolute or relative path
        return os.path.abspath(os.path.expanduser(os.path.expandvars(alias)))

    def execute(self, action: str, params: Dict[str, Any]) -> Dict[str, Any]:
        action = action.lower().strip()

        try:
            if action == "open_directory":
                raw_path = params.get("path", "desktop")
                target_dir = self._resolve_directory(str(raw_path))

                if not os.path.exists(target_dir):
                    os.makedirs(target_dir, exist_ok=True)

                os.startfile(target_dir)

                folder_name = os.path.basename(target_dir)
                hwnd = win32_window_utils.wait_for_visible_window(
                    title_keywords=[folder_name.lower(), "explorer"],
                    timeout=3.5
                )
                if hwnd:
                    win32_window_utils.maximize_window(hwnd)
                    win32_window_utils.force_foreground_window(hwnd)

                return {
                    "status": "success",
                    "message": f"Opened directory '{target_dir}' in Explorer.",
                    "path": target_dir
                }

            elif action == "select_file":
                raw_file = str(params.get("file_path", "")).strip()
                if not raw_file:
                    return {"status": "error", "message": "Missing 'file_path' parameter."}

                target_file = os.path.abspath(os.path.expandvars(raw_file))
                if not os.path.exists(target_file):
                    return {"status": "error", "message": f"File does not exist: {target_file}"}

                subprocess.Popen(["explorer.exe", f"/select,{target_file}"])
                time.sleep(0.5)
                return {"status": "success", "message": f"Selected file in Explorer: {target_file}"}

            elif action == "create_folder":
                parent = self._resolve_directory(str(params.get("parent_dir", "desktop")))
                folder_name = str(params.get("folder_name", "New Folder")).strip()
                new_path = os.path.join(parent, folder_name)
                os.makedirs(new_path, exist_ok=True)
                os.startfile(new_path)
                time.sleep(0.4)
                return {"status": "success", "message": f"Created folder: {new_path}"}

            else:
                return {"status": "error", "message": f"Unsupported action '{action}' for Explorer skill."}

        except Exception as e:
            return {"status": "error", "message": f"Explorer skill failed on '{action}': {e}"}
