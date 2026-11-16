"""
Desktop Ghost Live Agent v2 — Markdown Skill Loader
===================================================
Standardized Markdown-based procedural skills conforming to the
Claude Code / Antigravity SKILL.md specification.

Features:
- Dynamic discovery of skills/<name>/SKILL.md
- YAML frontmatter parsing (name, description, triggers, executable_names)
- Markdown prompt catalog generation for Gemini system instructions
- High-speed lookup by skill name, natural language trigger, or executable name
"""

import os
import re
import yaml
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple


@dataclass
class MarkdownSkill:
    """Represents a procedural application skill parsed from SKILL.md."""
    name: str
    description: str
    triggers: List[str] = field(default_factory=list)
    executable_names: List[str] = field(default_factory=list)
    content: str = ""
    path: str = ""
    frontmatter: Dict[str, Any] = field(default_factory=dict)


# In-memory registry cache
_LOADED_SKILLS: Dict[str, MarkdownSkill] = {}


def _parse_frontmatter(raw_text: str) -> Tuple[Dict[str, Any], str]:
    """
    Extracts YAML frontmatter enclosed in '---' from markdown content.
    Returns (frontmatter_dict, markdown_body).
    """
    pattern = r"^---\s*\r?\n(.*?)\r?\n---\s*\r?\n(.*)$"
    match = re.search(pattern, raw_text, re.DOTALL)
    if not match:
        return {}, raw_text

    fm_raw = match.group(1)
    body = match.group(2)

    try:
        data = yaml.safe_load(fm_raw)
        if isinstance(data, dict):
            return data, body.strip()
    except Exception as e:
        print(f"[SKILL_LOADER] Warning: failed to parse YAML frontmatter: {e}")

    # Fallback key-value parser if PyYAML encounters custom constructs
    fallback: Dict[str, Any] = {}
    current_key = None
    for line in fm_raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line and not line.startswith("-"):
            k, v = line.split(":", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if v:
                fallback[k] = v
                current_key = None
            else:
                fallback[k] = []
                current_key = k
        elif line.startswith("-") and current_key:
            item = line.lstrip("- ").strip().strip("'\"")
            if isinstance(fallback.get(current_key), list):
                fallback[current_key].append(item)

    return fallback, body.strip()


def load_skill_file(filepath: str) -> Optional[MarkdownSkill]:
    """Parses a single SKILL.md file into a MarkdownSkill instance."""
    if not os.path.exists(filepath):
        return None

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_text = f.read()

        fm, body = _parse_frontmatter(raw_text)
        name = str(fm.get("name") or os.path.basename(os.path.dirname(filepath))).strip().lower()
        desc = str(fm.get("description") or "").strip()

        triggers_raw = fm.get("triggers", [])
        if isinstance(triggers_raw, list):
            triggers = [str(t).strip().lower() for t in triggers_raw if t]
        elif isinstance(triggers_raw, str):
            triggers = [t.strip().lower() for t in triggers_raw.split(",") if t.strip()]
        else:
            triggers = []

        exes_raw = fm.get("executable_names", [])
        if isinstance(exes_raw, list):
            exes = [str(e).strip().lower() for e in exes_raw if e]
        elif isinstance(exes_raw, str):
            exes = [e.strip().lower() for e in exes_raw.split(",") if e.strip()]
        else:
            exes = []

        return MarkdownSkill(
            name=name,
            description=desc,
            triggers=triggers,
            executable_names=exes,
            content=body,
            path=os.path.abspath(filepath),
            frontmatter=fm
        )
    except Exception as e:
        print(f"[SKILL_LOADER] Error loading skill from '{filepath}': {e}")
        return None


def load_all_skills(skills_dir: Optional[str] = None, force_reload: bool = False) -> Dict[str, MarkdownSkill]:
    """
    Discovers and parses all SKILL.md files located in skills/<skill_name>/SKILL.md.
    Caches parsed skills in memory.
    """
    global _LOADED_SKILLS
    if _LOADED_SKILLS and not force_reload:
        return _LOADED_SKILLS

    if skills_dir is None:
        skills_dir = os.path.dirname(os.path.abspath(__file__))

    loaded: Dict[str, MarkdownSkill] = {}

    if os.path.isdir(skills_dir):
        for entry in os.listdir(skills_dir):
            sub_dir = os.path.join(skills_dir, entry)
            if os.path.isdir(sub_dir):
                skill_file = os.path.join(sub_dir, "SKILL.md")
                if os.path.isfile(skill_file):
                    skill = load_skill_file(skill_file)
                    if skill:
                        loaded[skill.name] = skill

    _LOADED_SKILLS = loaded
    return _LOADED_SKILLS


def get_skill_by_name(name: str) -> Optional[MarkdownSkill]:
    """Finds a loaded skill by its exact name."""
    skills = load_all_skills()
    return skills.get(name.strip().lower())


def find_skill_for_app(app_name_or_exe: str) -> Optional[MarkdownSkill]:
    """
    Fuzzy resolves a skill based on:
      1. Exact skill name match
      2. Trigger keyword match
      3. Target executable name match (e.g. 'notepad++.exe' -> notepad_plus_plus)
    """
    clean_target = app_name_or_exe.strip().lower()
    base_exe = os.path.basename(clean_target)
    root_name = os.path.splitext(base_exe)[0]

    skills = load_all_skills()

    # 1. Exact name match
    if clean_target in skills:
        return skills[clean_target]
    if root_name in skills:
        return skills[root_name]

    # 2. Executable name match
    for skill in skills.values():
        for exe in skill.executable_names:
            if base_exe == exe or clean_target == exe or root_name == os.path.splitext(exe)[0]:
                return skill

    # 3. Trigger keyword match
    for skill in skills.values():
        for trigger in skill.triggers:
            if trigger in clean_target or clean_target in trigger:
                return skill

    return None


def get_skills_catalog_prompt() -> str:
    """
    Generates a concise Markdown catalog of all loaded skills for injection
    into Gemini's system instructions.
    """
    skills = load_all_skills()
    if not skills:
        return ""

    lines = [
        "EXTENDED MARKDOWN APPLICATION PLAYBOOKS (Claude Code / Antigravity Standard):",
        "Refer to these specialized application playbooks for keyboard shortcuts and automation heuristics:"
    ]

    for name, skill in sorted(skills.items()):
        triggers_str = ", ".join(skill.triggers[:3]) if skill.triggers else name
        exes_str = ", ".join(skill.executable_names) if skill.executable_names else f"{name}.exe"
        lines.append(f"* Skill `{name}` (triggers: {triggers_str} | binary: {exes_str}):")
        lines.append(f"  {skill.description}")

    return "\n".join(lines)
