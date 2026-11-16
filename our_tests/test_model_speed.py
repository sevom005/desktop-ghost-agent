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

raw_bytes, _ = actuator.capture_desktop_screenshot(quality=70)
import io
img = Image.open(io.BytesIO(raw_bytes))

test_models = ["gemini-3.5-flash-lite", "gemini-2.5-flash"]

for m in test_models:
    print(f"\n--- Testing model: {m} ---")
    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=m,
            contents=["Describe this desktop screenshot in one sentence.", img]
        )
        t1 = time.time()
        print(f"  Success in {t1 - t0:.2f}s! Text: {resp.text.strip()[:60]}...")
    except Exception as e:
        print(f"  Failed in {time.time() - t0:.2f}s: {e}")
