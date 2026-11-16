import os
import sys
import time
import io
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
import actuator
import key_rotator
import gemini_bridge

load_dotenv("C:/Users/Administrator/Desktop/Computer_Use/.env")
rotator = key_rotator.KeyRotator()
client = genai.Client(api_key=rotator.get_current_key())

raw_bytes, _ = actuator.capture_desktop_screenshot(quality=70)
img = Image.open(io.BytesIO(raw_bytes))

system_prompt = (
    "You are The Desktop Ghost, an autonomous Windows desktop agent. "
    "SPEED OPTIMIZATION: To complete tasks in the fewest turns possible, "
    "you SHOULD emit multiple sequential function calls in a single turn for predictable steps! "
    "For example, to launch an app, emit hotkey(['win']), then type_text('notepad', press_enter=True), then wait(1.0). "
    "All coordinates (x, y) are normalized [0, 1000]."
)

print("Testing Action Batching on Turn 1...")
t0 = time.time()
resp = client.models.generate_content(
    model="gemini-3.5-flash-lite",
    contents=[
        "Goal: Open Notepad, type 'Fast Ghost Test', and save to desktop. Choose the first batch of actions.",
        img
    ],
    config=types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=gemini_bridge.DESKTOP_TOOLS,
        safety_settings=gemini_bridge.PERMISSIVE_SAFETY_SETTINGS
    )
)
t1 = time.time()
print(f"API Response in {t1 - t0:.2f}s!")
print(f"Number of function calls emitted: {len(resp.function_calls or [])}")
for idx, call in enumerate(resp.function_calls or []):
    print(f"  Step {idx + 1}: {call.name} -> {call.args}")
