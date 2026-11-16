import os
import sys
import io
sys.path.insert(0, os.path.abspath("."))
from dotenv import load_dotenv
from google import genai
from PIL import Image
import mss

load_dotenv("c:/Users/Administrator/Desktop/test/.env")
api_key = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=api_key)

print("Capturing live desktop...")
import actuator
raw_bytes, b64 = actuator.capture_desktop_screenshot(quality=80)
img = Image.open(io.BytesIO(raw_bytes))
print(f"Captured {len(b64)} chars base64 ({img.size})")

# Test 1: Interactions with computer_use and disabled_safety_policies
policies = [
    "financial_transactions",
    "sensitive_data_modification",
    "communication_tool",
    "account_creation",
    "data_modification",
    "user_consent_management",
    "legal_terms_and_agreements"
]

print("\n--- Test 1: computer_use with disabled_safety_policies ---")
try:
    resp = client.interactions.create(
        model="gemini-3.5-flash-lite",
        input=[
            {"type": "text", "text": "Click the Windows Start button, type calc, press Enter, and calculate 25 * 4 ="},
            {"type": "image", "data": b64, "mime_type": "image/jpeg"}
        ],
        tools=[{
            "type": "computer_use",
            "environment": "desktop",
            "disabled_safety_policies": policies
        }]
    )
    print("Test 1 SUCCESS! Steps:", len(resp.steps))
    for s in resp.steps:
        print(s)
except Exception as e:
    print("Test 1 FAILED:", e)

# Test 2: Standard generate_content with tools (Function Calling)
print("\n--- Test 2: Function calling via models.generate_content ---")
click_tool = {
    "function_declarations": [
        {
            "name": "click",
            "description": "Click coordinates x, y on screen",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "x": {"type": "INTEGER", "description": "X coordinate"},
                    "y": {"type": "INTEGER", "description": "Y coordinate"},
                    "intent": {"type": "STRING", "description": "Reason for clicking"}
                },
                "required": ["x", "y"]
            }
        },
        {
            "name": "type_text",
            "description": "Type text into current focused element",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "text": {"type": "STRING", "description": "Text to type"},
                    "press_enter": {"type": "BOOLEAN", "description": "Whether to press Enter"}
                },
                "required": ["text"]
            }
        },
        {
            "name": "press_key",
            "description": "Press a special key like Enter, Esc, Win, etc.",
            "parameters": {
                "type": "OBJECT",
                "properties": {
                    "key": {"type": "STRING", "description": "Key name"}
                },
                "required": ["key"]
            }
        }
    ]
}

try:
    resp2 = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=[
            "Goal: Click the Windows Start button, type calc, press Enter, and calculate 25 * 4 =. What is the next action?",
            img
        ],
        config=dict(
            tools=[click_tool],
            safety_settings=[
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
        )
    )
    print("Test 2 SUCCESS! Candidates:")
    for c in resp2.candidates:
        for p in c.content.parts:
            if p.function_call:
                print(f"  Function call: {p.function_call.name} {p.function_call.args}")
            elif p.text:
                print(f"  Text: {p.text}")
except Exception as e:
    print("Test 2 FAILED:", e)
