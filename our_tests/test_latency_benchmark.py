import os
import sys
import time
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
import actuator
import key_rotator

load_dotenv("C:/Users/Administrator/Desktop/Computer_Use/.env")
rotator = key_rotator.KeyRotator()
client = genai.Client(api_key=rotator.get_current_key())

raw_bytes, _ = actuator.capture_desktop_screenshot(quality=80)
import io
img = Image.open(io.BytesIO(raw_bytes))

print("Testing Chat with accumulating images vs Pruned images...")

chat = client.chats.create(
    model="gemini-3.5-flash-lite",
    config=types.GenerateContentConfig(
        tools=[types.Tool(function_declarations=[
            types.FunctionDeclaration(
                name="click",
                description="Click x, y",
                parameters={"type": "OBJECT", "properties": {"x": {"type": "INTEGER"}, "y": {"type": "INTEGER"}}, "required": ["x", "y"]}
            )
        ])]
    )
)

# Turn 1
t0 = time.time()
r1 = chat.send_message(message=["Click the start button", img])
t1 = time.time()
print(f"Turn 1 Time (1 image in history): {t1 - t0:.2f}s")

# Let's inspect history
history = chat.get_history()
print(f"History length after Turn 1: {len(history)} messages")

# Turn 2
t0 = time.time()
r2 = chat.send_message(message=[
    types.Part.from_function_response(name="click", response={"status": "success"}),
    "Action done. Next?",
    img
])
t2 = time.time()
print(f"Turn 2 Time (2 images in history): {t2 - t0:.2f}s")

# Turn 3
t0 = time.time()
r3 = chat.send_message(message=[
    types.Part.from_function_response(name="click", response={"status": "success"}),
    "Action done. Next?",
    img
])
t3 = time.time()
print(f"Turn 3 Time (3 images in history): {t3 - t0:.2f}s")

# Let's see what happens if we replace older images in history with a text placeholder!
# Check the contents of history
history = chat.get_history()
print("\nInspecting history parts:")
total_images = 0
for idx, content in enumerate(history):
    for pidx, part in enumerate(content.parts):
        if part.inline_data:
            total_images += 1
            print(f"  Msg {idx}, Part {pidx}: Image ({len(part.inline_data.data)} bytes)")
print(f"Total accumulated images in history: {total_images}")
