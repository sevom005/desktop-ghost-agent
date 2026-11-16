"""
Unified Skill Registry & Dispatcher
Features:
- Central registry for all application playbooks
- Dynamic Markdown catalog generation for Gemini's System Instruction
- Safe sandboxed action dispatching with structured error reporting
- Universal generic application launcher (launch_generic_app)
"""

import os
import re
import sys
import time
import shlex
import subprocess
from typing import Dict, Any, Optional, List

from skills.base_skill import BaseSkill
from skills.chrome_playbook import ChromeSkill
from skills.telegram_playbook import TelegramSkill
from skills.paint_playbook import PaintSkill
from skills.explorer_playbook import ExplorerSkill
from skills.notepad_playbook import NotepadSkill
from skills import win32_window_utils
from skills import skill_loader


class SkillRegistry:
    def __init__(self):
        self.skills: Dict[str, BaseSkill] = {}
        self._register_default_skills()

    def _register_default_skills(self):
        """Initializes and registers standard Windows playbooks."""
        skills_to_load = [
            ChromeSkill(),
            TelegramSkill(),
            PaintSkill(),
            ExplorerSkill(),
            NotepadSkill()
        ]
        for skill in skills_to_load:
            self.skills[skill.name.lower()] = skill

    def register_skill(self, skill: BaseSkill):
        """Allows registering custom or runtime playbooks."""
        self.skills[skill.name.lower()] = skill

    def get_catalog_prompt(self) -> str:
        """
        Builds a concise, structured markdown catalog of available skills
        for injection into the Gemini system instruction.
        """
        lines = [
            "AVAILABLE PROCEDURAL APPLICATION SKILLS (PREFER OVER PIXEL SEARCHING):",
            "Whenever the user objective requires opening an application, navigating to a URL, "
            "or opening a folder, ALWAYS invoke 'open_app' or 'navigate_chrome' on Turn 1! "
            "These execute deterministically at hardware speeds.",
            ""
        ]

        for name, skill in self.skills.items():
            avail = "Ready" if skill.is_available() else "Unavailable"
            lines.append(f"* Skill '{name}' [{avail}]: {skill.description}")
            actions = skill.get_supported_actions()
            for act_name, act_desc in actions.items():
                lines.append(f"    - action='{act_name}': {act_desc}")
            lines.append("")

        lines.append(
            "* Universal Tool 'open_app(app_name)': Launches ANY Windows application "
            "(e.g. 'chrome', 'mspaint', 'notepad', 'notepad++', 'vscode', 'calc') or URL directly and focuses its window."
        )
        lines.append("")

        # Append dynamic Markdown playbooks (Claude Code / Antigravity standard)
        md_catalog = skill_loader.get_skills_catalog_prompt()
        if md_catalog:
            lines.append(md_catalog)

        return "\n".join(lines)

    def dispatch(self, skill_name: str, action: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Safely dispatches an action to the target skill.
        """
        skill_key = skill_name.lower().strip()
        params = params or {}

        if skill_key not in self.skills:
            return {
                "status": "error",
                "code": "SKILL_NOT_FOUND",
                "message": f"Skill '{skill_name}' is not registered. Available: {list(self.skills.keys())}"
            }

        skill = self.skills[skill_key]
        try:
            return skill.execute(action, params)
        except Exception as e:
            return {
                "status": "error",
                "code": "SKILL_EXECUTION_EXCEPTION",
                "message": f"Exception in skill '{skill_name}' on action '{action}': {e}"
            }

    def launch_generic_app(
        self,
        app_name: str,
        args: Optional[str] = None,
        maximize: bool = True
    ) -> Dict[str, Any]:
        """
        Universal launcher for any Windows desktop application or URI.
        Resolves executable via Registry / PATH, spawns process, and forces foreground focus.
        """
        clean_app = app_name.strip()
        clean_args = (args or "").strip()

        # Auto-correct common path abbreviations (e.g. \Desktop\P100 -> \Desktop\Project %100)
        clean_app = re.sub(r"[/\\]Desktop[/\\]P100([/\\]|$)", r"\\Desktop\\Project %100\1", clean_app, flags=re.IGNORECASE)
        if clean_args:
            clean_args = re.sub(r"[/\\]Desktop[/\\]P100([/\\]|$)", r"\\Desktop\\Project %100\1", clean_args, flags=re.IGNORECASE)

        # If it's a URL or direct file path on disk, launch directly
        if clean_app.startswith("http://") or clean_app.startswith("https://") or os.path.exists(clean_app):
            try:
                os.startfile(clean_app)
                time.sleep(0.5)
                return {"status": "success", "message": f"Opened target: {clean_app}"}
            except Exception as e:
                return {"status": "error", "message": f"Failed to open '{clean_app}': {e}"}

        # Check if clean_app contains both executable and arguments (e.g., "notepad++.exe C:\...")
        if not os.path.exists(clean_app):
            try:
                tokens = shlex.split(clean_app, posix=False)
            except Exception:
                tokens = clean_app.split(maxsplit=1)

            if len(tokens) > 1:
                candidate_app = tokens[0].strip().strip("'\"")
                candidate_args = tokens[1:]
                found_exe = win32_window_utils.find_app_executable(candidate_app)
                clean_app = found_exe or candidate_app
                extra_args_str = " ".join(candidate_args)
                if clean_args:
                    clean_args = f"{extra_args_str} {clean_args}".strip()
                else:
                    clean_args = extra_args_str

        # Resolve executable
        exe_path = win32_window_utils.find_app_executable(clean_app)
        resolved_bin = exe_path or clean_app
        try:
            cmd = [resolved_bin]
            if clean_args:
                try:
                    cmd.extend(shlex.split(clean_args, posix=False))
                except Exception:
                    cmd.append(clean_args)

            subprocess.Popen(cmd)

            # Wait for visible window
            search_title = os.path.splitext(os.path.basename(resolved_bin))[0].lower()
            hwnd = win32_window_utils.wait_for_visible_window(
                title_keywords=[search_title],
                timeout=4.5
            )

            if hwnd:
                if maximize:
                    win32_window_utils.maximize_window(hwnd)
                win32_window_utils.force_foreground_window(hwnd)
                time.sleep(0.3)
                return {
                    "status": "success",
                    "message": f"Successfully launched and focused '{clean_app}'.",
                    "hwnd": hwnd
                }
            else:
                return {
                    "status": "success",
                    "message": f"Launched '{clean_app}' (window initializing in background)."
                }

        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to launch '{clean_app}': {e}"
            }


_GLOBAL_SKILL_REGISTRY: Optional[SkillRegistry] = None

def get_skill_registry() -> SkillRegistry:
    """Returns the singleton SkillRegistry instance."""
    global _GLOBAL_SKILL_REGISTRY
    if _GLOBAL_SKILL_REGISTRY is None:
        _GLOBAL_SKILL_REGISTRY = SkillRegistry()
    return _GLOBAL_SKILL_REGISTRY
