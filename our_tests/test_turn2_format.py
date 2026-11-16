import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
import io
import json
import base64
from PIL import Image
from google import genai
import gemini_bridge
import actuator

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# 1. Capture screen as PNG
raw_bytes, _ = actuator.capture_desktop_screenshot()
img = Image.open(io.BytesIO(raw_bytes))
buf_png = io.BytesIO()
img.save(buf_png, format="PNG")
png_b64 = base64.b64encode(buf_png.getvalue()).decode("utf-8")

print("1. Sending initial turn with PNG (gemini-3.8-flash)...")
tool = {"type": "computer_use", "environment": "desktop"}
interaction1 = client.interactions.create(
    model="gemini-3.8-flash",
    input=[
        {"type": "text", "text": "Click the Windows Start button to open it."},
        {"type": "image", "data": png_b64, "mime_type": "image/png"}
    ],
    tools=[tool]
)

calls = [s for s in interaction1.steps if s.type == "function_call"]
print(f"Turn 1 produced {len(calls)} call(s): {[c.name for c in calls]}")
call = calls[0]

print("2. Sending Turn 2 with function_result...")
resp = [{
    "type": "function_result",
    "name": call.name,
    "call_id": call.id,
    "result": [
        {"type": "text", "text": json.dumps({"status": "success"})},
        {"type": "image", "data": png_b64, "mime_type": "image/png"}
    ]
}]

interaction2 = client.interactions.create(
    model="gemini-3.8-flash",
    previous_interaction_id=interaction1.id,
    input=resp,
    tools=[tool]
)

steps2 = [s.type for s in interaction2.steps]
print("Turn 2 Response Steps:", steps2)
print("SUCCESS!")
