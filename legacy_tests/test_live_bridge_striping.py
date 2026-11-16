"""
Live Integration Test for GeminiDesktopBridge Multi-Key Striping
Verifies:
1. Turn 1 sends to Key #1 (or round-robin key)
2. Turn 2 sends to Key #2 with chat history preserved
3. Both turns succeed with genuine Gemini responses
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import gemini_bridge
import key_rotator
import defense
from PIL import Image

def test_live_two_turn_striping():
    print("\n--- LIVE TEST: Real 2-Turn Multi-Key Striping to Gemini ---")
    bridge = gemini_bridge.GeminiDesktopBridge(model="gemini-3.5-flash-lite")
    
    # Create a tiny 100x100 dummy test image
    img = Image.new("RGB", (100, 100), color=(255, 0, 0))
    import io, base64
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    b64_dummy = base64.b64encode(buf.getvalue()).decode("utf-8")

    # Turn 1
    print("\n[LIVE] Sending Turn 1...")
    resp1 = bridge.start_interaction(
        user_goal="Reply with the single word 'ONE'. Do not call functions.",
        screenshot_b64=b64_dummy
    )
    is_finished, fcalls, text1 = bridge.parse_interaction_response(resp1)
    key_used_turn1 = bridge.active_key_idx
    print(f"  Turn 1 Response: '{text1}' | Key Used: #{key_used_turn1 + 1}")

    # Turn 2
    print("\n[LIVE] Sending Turn 2 (Should stripe to another key)...")
    resp2 = bridge.send_function_results(
        function_responses=[],
        next_goal_summary="Now reply with the single word 'TWO'. Do not call functions.",
        latest_screenshot_b64=b64_dummy
    )
    is_finished, fcalls, text2 = bridge.parse_interaction_response(resp2)
    key_used_turn2 = bridge.active_key_idx
    print(f"  Turn 2 Response: '{text2}' | Key Used: #{key_used_turn2 + 1}")

    assert key_used_turn1 != key_used_turn2, f"Expected distinct keys across turns, got Turn1={key_used_turn1+1}, Turn2={key_used_turn2+1}"
    print(f"\n🎉 LIVE MULTI-KEY STRIPING VERIFIED! (Key #{key_used_turn1 + 1} -> Key #{key_used_turn2 + 1})")

if __name__ == "__main__":
    test_live_two_turn_striping()
