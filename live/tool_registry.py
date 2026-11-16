"""
Desktop Ghost Live Agent v2 — Tool Registry
============================================
Defines all FunctionDeclarations exposed to gemini-3.8-live and handles
non-blocking dispatching to actuator.py and skills playbooks.

Design decisions:
  - All tools use behavior="NON_BLOCKING" (confirmed Behavior.NON_BLOCKING in SDK v2.32.0).
    The model speaks conversational fillers ("Opening YouTube!") while the tool runs.
  - Coordinate space: STRICTLY 0–1000 normalized.
    actuator.py converts (x/1000 * screen_width) to physical screen coordinates (1366x768).
  - Silent execution (Option B): Cursor crosshairs are NOT flicked on by default during
    actions to avoid visual flicker while talking to a voice assistant.
  - Trap #7 fix: take_screenshot does NOT return raw bytes in the function response;
    it returns a status text string, and the fresh frame is pushed via the screen streamer.
"""

import sys
import os
import time
from typing import Dict, Any, List

# Add workspace root to sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from google.genai import types
import actuator
from skills.skill_registry import get_skill_registry
from memory.ghost_memory import get_ghost_memory


# ─────────────────────────────────────────────────────────────────────────────
# 1. FUNCTION DECLARATIONS (What Gemini 3.8 Live Can Call)
# ─────────────────────────────────────────────────────────────────────────────

open_app_decl = types.FunctionDeclaration(
    name="open_app",
    description="Launch any Windows application (e.g. 'chrome', 'notepad', 'calc', 'paint') or open a URL directly (e.g. 'https://youtube.com').",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "app_name": types.Schema(
                type="STRING",
                description="Application name (e.g. 'notepad', 'chrome') or full URL (e.g. 'https://youtube.com')."
            )
        },
        required=["app_name"]
    ),
    behavior="NON_BLOCKING"
)

navigate_chrome_decl = types.FunctionDeclaration(
    name="navigate_chrome",
    description="Navigate to a web URL inside Google Chrome in a new or active tab.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "url": types.Schema(
                type="STRING",
                description="Target website URL (e.g. 'https://youtube.com', 'https://google.com')."
            )
        },
        required=["url"]
    ),
    behavior="NON_BLOCKING"
)

search_web_decl = types.FunctionDeclaration(
    name="search_web",
    description="Focus Google Chrome address bar and perform a search query.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "query": types.Schema(
                type="STRING",
                description="Search query to type into the omnibox (e.g. 'Peshawa YouTuber', 'weather today')."
            )
        },
        required=["query"]
    ),
    behavior="NON_BLOCKING"
)

click_decl = types.FunctionDeclaration(
    name="click",
    description="Click at normalized coordinates (0-1000) on the screen.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "x": types.Schema(
                type="NUMBER",
                description="X coordinate normalized from 0 to 1000 (0 = leftmost, 1000 = rightmost edge)."
            ),
            "y": types.Schema(
                type="NUMBER",
                description="Y coordinate normalized from 0 to 1000 (0 = topmost, 1000 = bottom edge)."
            ),
            "button": types.Schema(
                type="STRING",
                description="Mouse button: 'left', 'right', or 'middle'. Default is 'left'."
            )
        },
        required=["x", "y"]
    ),
    behavior="NON_BLOCKING"
)

double_click_decl = types.FunctionDeclaration(
    name="double_click",
    description="Double-click at normalized coordinates (0-1000) on the screen.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "x": types.Schema(
                type="NUMBER",
                description="X coordinate normalized from 0 to 1000."
            ),
            "y": types.Schema(
                type="NUMBER",
                description="Y coordinate normalized from 0 to 1000."
            )
        },
        required=["x", "y"]
    ),
    behavior="NON_BLOCKING"
)

right_click_decl = types.FunctionDeclaration(
    name="right_click",
    description="Right-click at normalized coordinates (0-1000) to open a context menu.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "x": types.Schema(type="NUMBER", description="X coordinate normalized from 0 to 1000."),
            "y": types.Schema(type="NUMBER", description="Y coordinate normalized from 0 to 1000.")
        },
        required=["x", "y"]
    ),
    behavior="NON_BLOCKING"
)

type_text_decl = types.FunctionDeclaration(
    name="type_text",
    description="Type text into the currently focused window or at an optional target coordinate.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "text": types.Schema(
                type="STRING",
                description="The string of text to type."
            ),
            "press_enter": types.Schema(
                type="BOOLEAN",
                description="Whether to press Enter after typing the text. Default is false."
            ),
            "x": types.Schema(
                type="NUMBER",
                description="Optional X coordinate (0-1000) to click and focus before typing."
            ),
            "y": types.Schema(
                type="NUMBER",
                description="Optional Y coordinate (0-1000) to click and focus before typing."
            )
        },
        required=["text"]
    ),
    behavior="NON_BLOCKING"
)

press_key_decl = types.FunctionDeclaration(
    name="press_key",
    description="Press a single keyboard key (e.g. 'enter', 'esc', 'tab', 'backspace', 'up', 'down', 'win').",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "key": types.Schema(
                type="STRING",
                description="Key name: 'enter', 'esc', 'tab', 'space', 'backspace', 'up', 'down', 'left', 'right', 'win', etc."
            )
        },
        required=["key"]
    ),
    behavior="NON_BLOCKING"
)

hotkey_decl = types.FunctionDeclaration(
    name="hotkey",
    description="Press a keyboard shortcut combination simultaneously (e.g. ['ctrl', 't'], ['ctrl', 'w'], ['win', 'd']).",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "keys": types.Schema(
                type="ARRAY",
                items=types.Schema(type="STRING"),
                description="List of keys to press together (e.g. ['ctrl', 't'] for new tab, ['alt', 'f4'] to close)."
            )
        },
        required=["keys"]
    ),
    behavior="NON_BLOCKING"
)

scroll_decl = types.FunctionDeclaration(
    name="scroll",
    description="Scroll the mouse wheel up or down at the current or specified coordinate.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "direction": types.Schema(
                type="STRING",
                description="'down' or 'up'. Default is 'down'."
            ),
            "magnitude": types.Schema(
                type="INTEGER",
                description="Scroll distance in pixels/clicks. Default is 300."
            ),
            "x": types.Schema(type="NUMBER", description="Optional X coordinate (0-1000) to position cursor before scrolling."),
            "y": types.Schema(type="NUMBER", description="Optional Y coordinate (0-1000) to position cursor before scrolling.")
        }
    ),
    behavior="NON_BLOCKING"
)

drag_decl = types.FunctionDeclaration(
    name="drag",
    description="Click and drag from a start position to an end position.",
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "start_x": types.Schema(type="NUMBER", description="Starting X coordinate (0-1000)."),
            "start_y": types.Schema(type="NUMBER", description="Starting Y coordinate (0-1000)."),
            "end_x": types.Schema(type="NUMBER", description="Ending X coordinate (0-1000)."),
            "end_y": types.Schema(type="NUMBER", description="Ending Y coordinate (0-1000).")
        },
        required=["start_x", "start_y", "end_x", "end_y"]
    ),
    behavior="NON_BLOCKING"
)

take_screenshot_decl = types.FunctionDeclaration(
    name="take_screenshot",
    description="Capture and inspect an updated high-resolution frame of the desktop.",
    parameters=types.Schema(
        type="OBJECT",
        properties={}
    ),
    behavior="NON_BLOCKING"
)

sleep_decl = types.FunctionDeclaration(
    name="sleep",
    description="Put the agent to sleep into standby mode when the user says 'sleep', 'goodbye', 'stop', or 'rest'.",
    parameters=types.Schema(
        type="OBJECT",
        properties={}
    ),
    behavior="NON_BLOCKING"
)

remember_fact_decl = types.FunctionDeclaration(
    name="remember_fact",
    description=(
        "Save or forget a fact, preference, or milestone about Shvan to permanent memory. "
        "Call this when Shvan explicitly asks you to remember or forget something about himself."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "fact": types.Schema(
                type="STRING",
                description="The fact, preference, or milestone text to remember or forget."
            ),
            "category": types.Schema(
                type="STRING",
                description="Category: 'fact' (default) or 'milestone'.",
                enum=["fact", "milestone"]
            ),
            "action": types.Schema(
                type="STRING",
                description="Action: 'add' (default) to save, 'forget' to remove.",
                enum=["add", "forget"]
            )
        },
        required=["fact"]
    ),
    behavior="NON_BLOCKING"
)

learn_habit_decl = types.FunctionDeclaration(
    name="learn_habit",
    description=(
        "Record a corrected behavior so Ghost never repeats the same mistake. "
        "Call this when Shvan explicitly corrects a repeated action or workflow."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "trigger": types.Schema(
                type="STRING",
                description="The phrase or action that caused the mistake (e.g. 'open chrome')."
            ),
            "mistake": types.Schema(
                type="STRING",
                description="What was done wrong (e.g. 'Used open_app which opens Chrome profile selector')."
            ),
            "correction": types.Schema(
                type="STRING",
                description="The correct action to take instead (e.g. 'Double-click Chrome on the desktop')."
            )
        },
        required=["trigger", "mistake", "correction"]
    ),
    behavior="NON_BLOCKING"
)

delegate_background_task_decl = types.FunctionDeclaration(
    name="delegate_background_task",
    description=(
        "Delegate a long-running, CPU/RAM inspection, or terminal task to Sub-Agent B in the background. "
        "Does NOT take over mouse or screen. Use for cleaning lag, running scripts, or system tasks."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "task_description": types.Schema(
                type="STRING",
                description="Detailed goal or instruction for Sub-Agent B (e.g. 'check RAM usage and kill hogs', 'run python build script')."
            )
        },
        required=["task_description"]
    ),
    behavior="NON_BLOCKING"
)

get_task_status_decl = types.FunctionDeclaration(
    name="get_task_status",
    description=(
        "Quickly check the live progress and status of active or recent background tasks from the Task Blackboard in RAM (0.001ms read). "
        "Call when Shvan asks 'where are we with the task?' or 'how is the background task going?'."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "task_id": types.Schema(
                type="STRING",
                description="Optional specific task ID (e.g. 'task_001'). If omitted, checks the active or most recent task."
            )
        }
    ),
    behavior="NON_BLOCKING"
)

cancel_background_task_decl = types.FunctionDeclaration(
    name="cancel_background_task",
    description=(
        "Immediately stops or cancels an active background task (e.g. when Shvan says 'stop the task', "
        "'cancel background task', 'stop surveillance', or 'abort'). Halts Sub-Agent B and terminates running processes."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={
            "task_id": types.Schema(
                type="STRING",
                description="Optional task ID to cancel (e.g. 'task_001'). If omitted, cancels the active task."
            ),
            "reason": types.Schema(
                type="STRING",
                description="Optional reason for cancellation."
            )
        }
    ),
    behavior="NON_BLOCKING"
)

get_active_window_context_decl = types.FunctionDeclaration(
    name="get_active_window_context",
    description=(
        "Inspects the active foreground window to detect the currently open file, code editor (VS Code, Notepad++, etc.), "
        "workspace, and window title breadcrumbs. Use when Shvan says 'in here', 'this file', 'this code', 'run this', "
        "or asks what he is currently looking at."
    ),
    parameters=types.Schema(
        type="OBJECT",
        properties={}
    ),
    behavior="NON_BLOCKING"
)


# ─────────────────────────────────────────────────────────────────────────────
# 2. ALL FUNCTION DECLARATIONS LIST & LIVE TOOLS GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

ALL_FUNCTION_DECLARATIONS = [
    open_app_decl,
    navigate_chrome_decl,
    search_web_decl,
    click_decl,
    double_click_decl,
    right_click_decl,
    type_text_decl,
    press_key_decl,
    hotkey_decl,
    scroll_decl,
    drag_decl,
    take_screenshot_decl,
    sleep_decl,
    remember_fact_decl,
    learn_habit_decl,
    delegate_background_task_decl,
    get_task_status_decl,
    cancel_background_task_decl,
    get_active_window_context_decl,
]


def get_live_tools() -> List[types.Tool]:
    """Returns the list of Tool objects configured for types.LiveConnectConfig."""
    return [types.Tool(function_declarations=ALL_FUNCTION_DECLARATIONS)]


# ─────────────────────────────────────────────────────────────────────────────
# 3. DISPATCHER (Executes Called Tools via actuator.py & skills)
# ─────────────────────────────────────────────────────────────────────────────

def dispatch_tool(name: str, args: Dict[str, Any]) -> str:
    """
    Synchronous dispatcher executing the called tool against Windows hardware.
    Called in an asyncio executor to prevent blocking the WebSocket thread.

    Returns a concise result string passed back to the model in FunctionResponse.
    """
    args = args or {}
    tool_name = name.lower().strip()
    registry = get_skill_registry()

    try:
        if tool_name == "open_app":
            app = str(args.get("app_name", "")).strip()
            if not app:
                return "error: Missing app_name parameter"
            res = registry.launch_generic_app(app)
            return res.get("message", f"Launched {app}")

        elif tool_name == "navigate_chrome":
            url = str(args.get("url", "https://www.google.com")).strip()
            res = registry.dispatch("chrome", "navigate", {"url": url})
            return res.get("message", f"Navigated to {url}")

        elif tool_name == "search_web":
            query = str(args.get("query", "")).strip()
            res = registry.dispatch("chrome", "focus_search", {"query": query})
            return res.get("message", f"Searched for '{query}'")

        elif tool_name == "click":
            x = float(args["x"])
            y = float(args["y"])
            btn = str(args.get("button", "left")).lower()
            actuator.execute_click(x, y, button=btn)
            return f"Clicked {btn} button at ({x:.1f}, {y:.1f})"

        elif tool_name == "double_click":
            x = float(args["x"])
            y = float(args["y"])
            actuator.execute_double_click(x, y)
            return f"Double-clicked at ({x:.1f}, {y:.1f})"

        elif tool_name == "right_click":
            x = float(args["x"])
            y = float(args["y"])
            actuator.execute_right_click(x, y)
            return f"Right-clicked at ({x:.1f}, {y:.1f})"

        elif tool_name == "type_text":
            text = str(args.get("text", ""))
            press_enter = bool(args.get("press_enter", False))
            x = float(args["x"]) if "x" in args and args["x"] is not None else None
            y = float(args["y"]) if "y" in args and args["y"] is not None else None
            actuator.execute_type(text, press_enter=press_enter, x=x, y=y)
            return f"Typed {len(text)} characters (press_enter={press_enter})"

        elif tool_name == "press_key":
            key = str(args.get("key", "")).strip()
            actuator.execute_press_key(key)
            return f"Pressed key '{key}'"

        elif tool_name == "hotkey":
            keys = args.get("keys", [])
            if isinstance(keys, list):
                clean_keys = [str(k) for k in keys]
                actuator.execute_hotkey(clean_keys)
                return f"Pressed hotkey: {' + '.join(clean_keys)}"
            return "error: 'keys' must be a list of strings"

        elif tool_name == "scroll":
            direction = str(args.get("direction", "down")).lower()
            magnitude = int(args.get("magnitude", 300))
            x = float(args["x"]) if "x" in args and args["x"] is not None else None
            y = float(args["y"]) if "y" in args and args["y"] is not None else None
            actuator.execute_scroll(x=x, y=y, direction=direction, magnitude=magnitude)
            return f"Scrolled {direction} by {magnitude}"

        elif tool_name == "drag":
            sx = float(args["start_x"])
            sy = float(args["start_y"])
            ex = float(args["end_x"])
            ey = float(args["end_y"])
            actuator.execute_drag_and_drop(sx, sy, ex, ey)
            return f"Dragged from ({sx:.1f}, {sy:.1f}) to ({ex:.1f}, {ey:.1f})"

        elif tool_name == "take_screenshot":
            # Screen frame injection is triggered separately by the caller via screen_streamer.inject_now()
            return "Captured high-res screen update."

        elif tool_name == "sleep":
            return "Standby sleep requested."

        elif tool_name == "remember_fact":
            fact = str(args.get("fact", "")).strip()
            if not fact:
                return "error: Missing 'fact' parameter"
            category = str(args.get("category", "preference")).lower()
            action = str(args.get("action", "add")).lower()
            mem = get_ghost_memory()
            if action == "forget":
                removed = mem.remove_fact(fact)
                mem.save_companion()
                return f"Forgotten: '{fact}'" if removed else f"No matching fact found for '{fact}'"
            else:
                mem.add_fact(fact, category=category)
                mem.save_companion()
                return "Remembered."

        elif tool_name == "learn_habit":
            trigger = str(args.get("trigger", "")).strip()
            mistake = str(args.get("mistake", "")).strip()
            correction = str(args.get("correction", "")).strip()
            if not trigger or not correction:
                return "error: Missing 'trigger' or 'correction' parameter"
            mem = get_ghost_memory()
            mem.add_habit(trigger, mistake, correction)
            mem.save_habits()
            return "Habit learned."

        elif tool_name == "delegate_background_task":
            task_desc = str(args.get("task_description", "")).strip()
            if not task_desc:
                return "error: Missing 'task_description' parameter"
            from workers.subagent_b import launch_background_task
            from live.live_bridge import get_active_live_bridge
            from memory.task_blackboard import get_task_blackboard

            # If task indicates redesigning/updating an existing file, inject the last artifact path
            lower_desc = task_desc.lower()
            update_keywords = ("redesign", "update", "modify", "edit", "change that", "that html", "that file", "improve that")
            if any(k in lower_desc for k in update_keywords):
                board = get_task_blackboard()
                last_art = board.get_last_artifact()
                if last_art and os.path.exists(last_art):
                    if last_art.lower() not in lower_desc:
                        task_desc += f"\nTarget File to edit in-place: {last_art}"

            bridge = get_active_live_bridge()
            on_complete = bridge.queue_voice_alert if bridge else None
            tid = launch_background_task(task_desc, on_complete=on_complete)
            return f"Background task {tid} started: '{task_desc}'."

        elif tool_name == "get_task_status":
            from memory.task_blackboard import get_task_blackboard
            board = get_task_blackboard()
            st = board.get_task_status(args.get("task_id"))
            if st.get("status") == "IDLE":
                return "No background tasks are currently running or recorded."
            elif st.get("status") == "RUNNING":
                return f"Task '{st.get('goal')}' is RUNNING. Progress: {st.get('progress')}"
            elif st.get("status") == "COMPLETED":
                return f"Task '{st.get('goal')}' is COMPLETED. Result: {st.get('result')}"
            elif st.get("status") == "FAILED":
                return f"Task '{st.get('goal')}' FAILED. Error: {st.get('error')}"
            elif st.get("status") == "CANCELLED":
                return f"Task '{st.get('goal')}' was CANCELLED. Reason: {st.get('error')}"
            else:
                return f"Task '{st.get('goal')}' status: {st.get('status')}. Progress: {st.get('progress')}"

        elif tool_name == "cancel_background_task":
            from workers.subagent_b import cancel_running_task
            t_id = args.get("task_id")
            reason = str(args.get("reason", "User requested cancellation")).strip()
            ok = cancel_running_task(task_id=t_id, reason=reason)
            if ok:
                target_str = f"'{t_id}' " if t_id else ""
                return f"Cancelled background task {target_str}({reason})."
            else:
                return "No active background task found to cancel."

        elif tool_name == "get_active_window_context":
            from skills import win32_window_utils
            ctx = win32_window_utils.get_active_spatial_context()
            parts = []
            if ctx.app_name:
                parts.append(f"App: {ctx.app_name}")
            if ctx.file_name:
                parts.append(f"File: {ctx.file_name}")
            if ctx.file_path:
                parts.append(f"Path: {ctx.file_path}")
            if ctx.workspace_name:
                parts.append(f"Workspace: {ctx.workspace_name}")
            if ctx.is_editor:
                parts.append("Type: Code Editor")
            if ctx.is_dirty:
                parts.append("Status: Unsaved Modifications")
            if ctx.window_title:
                parts.append(f"Title: '{ctx.window_title}'")
            return " | ".join(parts) if parts else "No active window or document detected."

        else:
            return f"error: Unknown tool '{name}'"

    except actuator.SafetyInterlockException as e:
        return f"SAFETY REFUSAL: {e}"
    except Exception as e:
        return f"error: Exception executing '{name}': {e}"
