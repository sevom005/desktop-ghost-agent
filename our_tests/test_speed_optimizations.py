import os
import sys
import io
sys.path.insert(0, os.path.abspath("C:/Users/Administrator/Desktop/Computer_Use"))
from PIL import Image
import actuator
import gemini_bridge
import key_rotator

print("============================================================")
print("STARTING SPEED OPTIMIZATION VERIFICATION SUITE")
print("============================================================")

# 1. Vision Compression Check
print("\n--- [1] Vision Sensor Quality 65% Payload Check ---")
raw_bytes, b64_str = actuator.capture_desktop_screenshot(quality=65)
kb_size = len(raw_bytes) / 1024
print(f"Captured JPEG size: {kb_size:.1f} KB")
assert kb_size < 200, f"Expected < 200KB, got {kb_size:.1f}KB"
print("  [PASS] Quality 65% compression verified.")

# 2. History Image Pruning Verification
print("\n--- [2] Historical Image Pruner Verification ---")
rotator = key_rotator.KeyRotator()
bridge = gemini_bridge.GeminiDesktopBridge(rotator=rotator)
bridge._create_chat_session()

# Mock a user content with an image in chat._curated_history
from google.genai import types
mock_image_part = types.Part(inline_data=types.Blob(mime_type="image/jpeg", data=raw_bytes))
mock_text_part = types.Part.from_text(text="Action summary")
mock_content = types.Content(role="user", parts=[mock_image_part, mock_text_part])
bridge.chat._curated_history.append(mock_content)

print(f"History length before prune: {len(bridge.chat._curated_history)}")
has_image_before = any(p.inline_data is not None for p in bridge.chat._curated_history[0].parts)
assert has_image_before is True

bridge._prune_history_images()

has_image_after = any(p.inline_data is not None for p in bridge.chat._curated_history[0].parts)
print(f"History after prune: image removed = {not has_image_after}")
assert has_image_after is False
# Verify text remains intact
assert bridge.chat._curated_history[0].parts[1].text == "Action summary"
print("  [PASS] Historical image pruning stripped bytes while preserving textual reasoning.")

# 3. Batch Action Response Parsing Check
print("\n--- [3] Multi-Action Batch Parser Verification ---")
class MockCall:
    def __init__(self, name, args):
        self.name = name
        self.id = name + "_id"
        self.args = args

class MockResponse:
    def __init__(self, calls):
        self.function_calls = calls
        self.candidates = []

mock_batch = MockResponse([
    MockCall("hotkey", {"keys": ["win"], "intent": "Open Start"}),
    MockCall("type_text", {"text": "calc", "press_enter": True, "intent": "Launch Calc"}),
    MockCall("wait", {"seconds": 1.0, "intent": "Wait for window"}),
    MockCall("task_complete", {"summary": "Batch task completed successfully."})
])

is_fin, calls, summary = bridge.parse_interaction_response(mock_batch)
print(f"Is Finished: {is_fin}")
print(f"Motor calls to execute: {len(calls)}")
print(f"Final Summary: {summary}")

assert is_fin is True, "Expected is_finished to be True"
assert len(calls) == 3, f"Expected 3 motor calls before completion, got {len(calls)}"
assert summary == "Batch task completed successfully."
print("  [PASS] Multi-action batch with embedded completion cleanly parsed.")

print("\n============================================================")
print("ALL SPEED OPTIMIZATION TESTS PASSED 100%!")
print("============================================================")
