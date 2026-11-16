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

load_dotenv("C:/Users/Administrator/Desktop/Computer_Use/.env")
rotator = key_rotator.KeyRotator()
client = genai.Client(api_key=rotator.get_current_key())

raw_bytes, _ = actuator.capture_desktop_screenshot(quality=65)
img = Image.open(io.BytesIO(raw_bytes))
print(f"Captured screenshot at quality 65: {len(raw_bytes) / 1024:.1f} KB")

# Test 1: Standard call with thinking_budget=0 (Disables extended thinking overhead)
print("\n--- Test 1: With thinking_budget=0 ---")
t0 = time.time()
try:
    resp = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=["Observe the desktop and give the 1 next action.", img],
        config=types.GenerateContentConfig(
            thinking_config=types.ThinkingConfig(thinking_budget=0)
        )
    )
    t1 = time.time()
    print(f"  Success in {t1 - t0:.2f}s! Tokens/Text: {resp.text[:60].strip()}...")
except Exception as e:
    print(f"  Error with thinking_budget: {e}")

# Test 2: Standard call with default config
print("\n--- Test 2: Default Config ---")
t0 = time.time()
try:
    resp2 = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=["Observe the desktop and give the 1 next action.", img]
    )
    t2 = time.time()
    print(f"  Success in {t2 - t0:.2f}s! Text: {resp2.text[:60].strip()}...")
except Exception as e:
    print(f"  Error with default: {e}")
