import os
import sys
import io
from PIL import Image
sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
from google import genai
from google.genai import types
import actuator

load_dotenv("c:/Users/Administrator/Desktop/test/.env")
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Define full desktop tool schema
tools = [
    types.Tool(
        function_declarations=[
            types.FunctionDeclaration(
                name="click",
                description="Click at (x, y) coordinates on the screen. Coordinates are normalized from 0 to 1000 (0,0 is top-left, 1000,1000 is bottom-right).",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "x": {"type": "INTEGER", "description": "X coordinate normalized [0, 1000]"},
                        "y": {"type": "INTEGER", "description": "Y coordinate normalized [0, 1000]"},
                        "intent": {"type": "STRING", "description": "Purpose of the click"}
                    },
                    "required": ["x", "y", "intent"]
                }
            ),
            types.FunctionDeclaration(
                name="double_click",
                description="Double click at (x, y) coordinates normalized [0, 1000].",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "x": {"type": "INTEGER", "description": "X coordinate normalized [0, 1000]"},
                        "y": {"type": "INTEGER", "description": "Y coordinate normalized [0, 1000]"},
                        "intent": {"type": "STRING", "description": "Purpose of double click"}
                    },
                    "required": ["x", "y", "intent"]
                }
            ),
            types.FunctionDeclaration(
                name="type_text",
                description="Type text via keyboard into the active focus or application.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "text": {"type": "STRING", "description": "Text to type"},
                        "press_enter": {"type": "BOOLEAN", "description": "Whether to press Enter after typing"},
                        "intent": {"type": "STRING", "description": "Purpose of typing"}
                    },
                    "required": ["text", "intent"]
                }
            ),
            types.FunctionDeclaration(
                name="press_key",
                description="Press a keyboard key (e.g. 'enter', 'esc', 'backspace', 'win', 'tab', 'delete').",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "key": {"type": "STRING", "description": "Key name"},
                        "intent": {"type": "STRING", "description": "Purpose of pressing key"}
                    },
                    "required": ["key", "intent"]
                }
            ),
            types.FunctionDeclaration(
                name="hotkey",
                description="Press a combination of keys simultaneously (e.g. ['win', 'r'], ['ctrl', 'a']).",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "keys": {
                            "type": "ARRAY",
                            "items": {"type": "STRING"},
                            "description": "List of key names"
                        },
                        "intent": {"type": "STRING", "description": "Purpose of hotkey"}
                    },
                    "required": ["keys", "intent"]
                }
            ),
            types.FunctionDeclaration(
                name="wait",
                description="Wait for a specified number of seconds for the UI or application to open/respond.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "seconds": {"type": "NUMBER", "description": "Seconds to wait (0.5 to 5.0)"},
                        "intent": {"type": "STRING", "description": "Purpose of waiting"}
                    },
                    "required": ["seconds", "intent"]
                }
            ),
            types.FunctionDeclaration(
                name="task_complete",
                description="Call this function when the user's goal has been completely achieved.",
                parameters={
                    "type": "OBJECT",
                    "properties": {
                        "summary": {"type": "STRING", "description": "Summary of actions taken and final result"}
                    },
                    "required": ["summary"]
                }
            )
        ]
    )
]

raw_bytes, b64 = actuator.capture_desktop_screenshot(quality=80)
img = Image.open(io.BytesIO(raw_bytes))

system_prompt = (
    "You are The Desktop Ghost, an autonomous Windows desktop automation agent. "
    "You see the user's screen (resolution: 1366x768). "
    "All coordinates (x, y) MUST be normalized from 0 to 1000 (top-left is 0,0; bottom-right is 1000,1000). "
    "To achieve the user's goal, select the appropriate function call at each step. "
    "When the goal is fully achieved, call task_complete."
)

chat = client.chats.create(
    model="gemini-3.5-flash-lite",
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=tools,
        safety_settings=[
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HARASSMENT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_HATE_SPEECH, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT, threshold=types.HarmBlockThreshold.BLOCK_NONE),
            types.SafetySetting(category=types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT, threshold=types.HarmBlockThreshold.BLOCK_NONE)
        ]
    )
)

print("Sending goal with desktop screenshot to chat...")
resp = chat.send_message(
    message=[
        "Goal: Click the Windows Start button, type calc, press Enter, and calculate 25 * 4 =. What is the next action?",
        img
    ]
)

print("Response candidates:", len(resp.candidates))
for c in resp.candidates:
    for p in c.content.parts:
        if p.function_call:
            print(f"Function Call: {p.function_call.name} -> {p.function_call.args}")
        elif p.text:
            print(f"Text: {p.text}")
