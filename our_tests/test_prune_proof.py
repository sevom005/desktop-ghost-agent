import os
import sys
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
from dotenv import load_dotenv
from google import genai
from google.genai import types
from PIL import Image
import actuator
import key_rotator
import io

load_dotenv("C:/Users/Administrator/Desktop/Computer_Use/.env")
rotator = key_rotator.KeyRotator()
client = genai.Client(api_key=rotator.get_current_key())

raw_bytes, _ = actuator.capture_desktop_screenshot(quality=65)
img = Image.open(io.BytesIO(raw_bytes))

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

print("Turn 1: Sending initial message with image...")
r1 = chat.send_message(message=["Click Start", img])

print(f"Curated history length after Turn 1: {len(chat._curated_history)}")
has_image_before = any(hasattr(p, "inline_data") and p.inline_data is not None for p in chat._curated_history[0].parts)
print(f"Msg 0 has image before prune: {has_image_before}")

# Prune images from _curated_history
for content in chat._curated_history:
    new_parts = []
    for part in content.parts:
        if hasattr(part, "inline_data") and part.inline_data is not None:
            new_parts.append(types.Part.from_text(text="[Prior screen verified]"))
        else:
            new_parts.append(part)
    content.parts = new_parts

has_image_after = any(hasattr(p, "inline_data") and p.inline_data is not None for p in chat._curated_history[0].parts)
print(f"Msg 0 has image after prune: {has_image_after}")
assert has_image_after is False, "Image was not pruned!"

print("Turn 2: Sending second message with new screenshot...")
r2 = chat.send_message(message=[
    types.Part.from_function_response(name="click", response={"status": "success"}),
    "Action done. Observe fresh screen.",
    img
])
print("Turn 2 succeeded with pruned history!")
print("\n[SUCCESS] Image pruning works 100% cleanly!")
