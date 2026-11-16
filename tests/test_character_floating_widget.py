"""
Tests for Floating Voice Widget Character Renderer and Avatar Interactions
===========================================================================
Validates:
  - Sprite sheet loading and slicing (7 state frames, 96x96).
  - Headless widget initialization with Tkinter transparency mask.
  - State transitions across idle, connecting, listening, and speaking.
  - Procedural animation tick loop.
"""

import os
import sys
import pytest
import tkinter as tk

from floating_widget import (
    GhostCharacterRenderer,
    FloatingGhostWidget,
    CyberHeadRenderer,
    StuntManager,
    LiveCursorManager,
    CANVAS_SIZE
)


@pytest.fixture(scope="module")
def tk_root():
    """Provides a headless hidden Tkinter root for UI testing."""
    root = tk.Tk()
    root.withdraw()
    yield root
    try:
        root.destroy()
    except Exception:
        pass


def test_ghost_character_renderer_loads_all_frames():
    """Verifies that all 7 character animation frames are loaded at 96x96 resolution."""
    renderer = GhostCharacterRenderer()
    expected_frames = [
        "idle",
        "idle_blink",
        "glance",
        "listening",
        "listening_blink",
        "speaking",
        "speaking_alt",
    ]
    for frame_name in expected_frames:
        assert frame_name in renderer.pil_frames
        img = renderer.pil_frames[frame_name]
        assert img.size == (CANVAS_SIZE, CANVAS_SIZE)


def test_ghost_character_renderer_fallback():
    """Verifies that fallback frames are generated cleanly if the sprite sheet is missing."""
    renderer = GhostCharacterRenderer(sheet_path="non_existent_file.png")
    assert len(renderer.pil_frames) == 7
    for name, img in renderer.pil_frames.items():
        assert img.size == (CANVAS_SIZE, CANVAS_SIZE)


def test_floating_widget_initialization_and_states(tk_root):
    """Verifies headless widget setup, state transitions, and animation ticks."""
    widget = FloatingGhostWidget(tk_root)
    assert widget.state == "idle"
    assert widget.circle_canvas is not None

    # Test state changes
    widget._set_ui_state("connecting")
    assert widget.state == "connecting"

    widget._set_ui_state("listening")
    assert widget.state == "listening"

    widget._set_ui_state("speaking")
    assert widget.state == "speaking"

    widget._set_ui_state("idle")
    assert widget.state == "idle"

    # Test hover events
    widget.on_circle_hover(None)
    assert widget._is_hovered is True

    widget.on_circle_leave(None)
    assert widget._is_hovered is False

    # Test animation tick execution
    widget._animate_tick()


def test_stunt_manager_transitions():
    """Verifies that StuntManager triggers, tracks progress, and auto-expires."""
    mgr = StuntManager()
    assert mgr.active_stunt == "none"
    assert mgr.update() == "none"

    mgr.trigger("laser_blaster", duration=0.1)
    assert mgr.active_stunt == "laser_blaster"
    assert mgr.update() == "laser_blaster"

    import time
    time.sleep(0.12)
    assert mgr.update() == "none"
    assert mgr.active_stunt == "none"


def test_cyber_head_renderer_stunts():
    """Verifies that CyberHeadRenderer generates valid 96x96 PIL images for all 4 stunts."""
    renderer = CyberHeadRenderer(size=CANVAS_SIZE)
    stunts = ["laser_blaster", "crying_tears", "heart_eyes", "dizzy_glitch"]

    for stunt in stunts:
        img = renderer.render(
            gaze_x=2.5,
            gaze_y=-1.5,
            eye_open_ratio=1.0,
            eye_squint=False,
            state="listening",
            is_hover=True,
            is_drag=False,
            stunt=stunt,
            stunt_time=0.5
        )
        assert img.size == (CANVAS_SIZE, CANVAS_SIZE)
        assert img.mode == "RGBA"


def test_floating_widget_stunt_triggers(tk_root):
    """Verifies right-click, double-click, and manual stunt triggers on FloatingGhostWidget."""
    widget = FloatingGhostWidget(tk_root)
    assert widget.stunt_mgr.active_stunt == "none"

    # Trigger laser blaster via right click
    widget.on_right_click(None)
    assert widget.stunt_mgr.active_stunt == "laser_blaster"

    # Trigger heart eyes
    widget.trigger_stunt("heart_eyes", duration=1.0)
    assert widget.stunt_mgr.active_stunt == "heart_eyes"

    # Trigger dizzy glitch
    widget.trigger_stunt("dizzy_glitch", duration=1.0)
    assert widget.stunt_mgr.active_stunt == "dizzy_glitch"

    # Trigger crying tears
    widget.trigger_stunt("crying_tears", duration=1.0)
    assert widget.stunt_mgr.active_stunt == "crying_tears"

    # Tick animation loop with active stunt
    widget._animate_tick()


def test_live_cursor_manager_lifecycle():
    """Verifies that LiveCursorManager pre-generates files and switches states cleanly."""
    mgr = LiveCursorManager(enabled=True)
    assert "listening" in mgr._cur_files
    assert "speaking" in mgr._cur_files

    # Test state switches
    mgr.set_live_cursor("listening")
    assert mgr.is_active is True
    assert mgr.current_state == "listening"

    mgr.set_live_cursor("speaking")
    assert mgr.is_active is True
    assert mgr.current_state == "speaking"

    mgr.restore()
    assert mgr.is_active is False
    assert mgr.current_state == "idle"


def test_voice_amplitude_extraction():
    """Verifies that AudioIO exposes voice_amplitude and LiveBridge forwards it."""
    from live.audio_io import AudioIO
    from live.live_bridge import LiveBridge

    audio = AudioIO()
    assert hasattr(audio, "voice_amplitude")
    assert audio.voice_amplitude == 0.0

    bridge = LiveBridge()
    assert hasattr(bridge, "get_voice_amplitude")
    assert bridge.get_voice_amplitude() == 0.0



