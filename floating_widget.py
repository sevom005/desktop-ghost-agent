"""
Desktop Ghost Live Agent v2 — Floating Voice Widget (Cyber-Head Companion)
==========================================================================
A movable, always-on-top interactive robot head for the real-time voice copilot.
Powered by gemini-3.8-live over a persistent WebSocket.

Features:
  - Cyber-Head Avatar: Sleek dark helmet dome with glossy visor and glowing capsule eyes.
    (Clean silhouette: NO ear nubs, NO line-mouth).
  - Direct Mouse Gaze Tracking: Eyes directly, smoothly follow your cursor hovering across Windows.
  - Interactive Pure Vector Stunts:
      * Cyber-Blaster 🔫: Red crosshairs lock on mouse, turret emerges, fires laser pulses.
        (Trigger: Right-click or double-click face).
      * Heart Eyes 😍: Glowing parametric hearts pulse with warm heartbeat rhythm.
        (Trigger: Hover cursor steadily over face for >1.5s).
      * Digital Crying Tears 😭: Cascading cyan droplets stream down visor.
        (Trigger: Stop/Sleep session button ⏹).
      * Dizzy Glitch 😵: Spinning Archimedean spiral eyes with digital scanlines.
        (Trigger: Shake widget rapidly during mouse drag).
  - Life-Like Micro-Reactions:
      * Autonomous natural blinking (every 3-6s).
      * Joyful squint arches (^^) when your cursor hovers over the face.
      * Alert wide eyes when dragging.
  - Dynamic Voice State Indicator:
      * Idle:         Dark zinc rim with glowing ice-cyan capsule eyes.
      * Connecting:   Amber pulsing rim while establishing live socket connection.
      * Listening:    Terracotta orange glowing rim with attentive eyes.
      * Ghost speaks: Bright peach glowing rim with animated lively eye pulses.
  - Barge-In Interrupt (Quirk #8): Clicking the avatar while Ghost is speaking
    instantly cuts off playback and unmutes your mic.
  - Expanded mode: Shows real-time conversation transcripts as you talk.
  - Draggable anywhere on the desktop; clamps within screen bounds.
"""

import sys
import os
import math
import time
import random
import ctypes
import atexit
import tempfile
import threading
import asyncio
import tkinter as tk
from tkinter import font as tkfont
import winsound
from typing import Optional, Tuple, List
from PIL import Image, ImageDraw, ImageTk

# Live Cursor indicator feature flag (1 = Enabled, 0 = Disabled)
ENABLE_LIVE_CURSOR = os.environ.get("NOVA_LIVE_CURSOR", "1") == "1"

# Ensure project root is in sys.path
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from dotenv import load_dotenv
load_dotenv(os.path.join(BASE_DIR, ".env"))

from live.live_bridge import LiveBridge


# ─────────────────────────────────────────────────────────────────────────────
# UI THEME & PALETTES
# ─────────────────────────────────────────────────────────────────────────────
TRANSPARENT_KEY = "#010203"   # Color key for Windows desktop alpha transparency cut
CANVAS_SIZE     = 96          # Native character head frame size (96x96 px)

# Theme Colors (RGBA for Pillow drawing)
CLR_TRANSPARENT = (1, 2, 3, 255)
CLR_DOME_BG     = (22, 23, 27, 255)       # Zinc-900 (Dark Helmet Dome)
CLR_VISOR_BG    = (9, 10, 14, 255)        # Obsidian Dark Glass Visor
CLR_VISOR_GLOSS = (255, 255, 255, 45)     # Curved Glass Sheen Highlight

# Expanded Transcript Bar Palette
BG_COLOR         = "#18181b"   # Zinc-900
BORDER_COLOR     = "#3f3f46"   # Zinc-700
HOVER_BORDER     = "#f97316"   # Vibrant Orange-500
LISTENING_BORDER = "#ea580c"   # Terracotta Orange-600
SPEAKING_BORDER  = "#fb923c"   # Bright Amber-400
TEXT_COLOR       = "#f4f4f5"   # Zinc-100
SUBTEXT_COLOR    = "#a1a1aa"   # Zinc-400

# Visual States (Border rim & eye glow colors)
STATE_THEMES = {
    "idle": {
        "border": (70, 75, 88, 255),          # Sleek Zinc Titanium Rim
        "eye_core": (240, 252, 255, 255),      # Bright Ice-White Core
        "eye_glow": (56, 189, 248),            # Sky Blue Glow
        "badge_bg": "#27272a",
        "badge_fg": "#a1a1aa",
        "badge_text": "STANDBY"
    },
    "connecting": {
        "border": (245, 158, 11, 255),        # Amber-500
        "eye_core": (255, 250, 235, 255),
        "eye_glow": (251, 191, 36),            # Amber Glow
        "badge_bg": "#2a1408",
        "badge_fg": "#fed7aa",
        "badge_text": "CONNECTING"
    },
    "listening": {
        "border": (234, 88, 12, 255),         # Vibrant Terracotta Orange-600
        "eye_core": (245, 253, 255, 255),      # Crisp Glowing White
        "eye_glow": (56, 189, 248),            # Luminous Cyan Glow
        "badge_bg": "#431407",
        "badge_fg": "#fb923c",
        "badge_text": "● LIVE"
    },
    "speaking": {
        "border": (251, 146, 60, 255),        # Warm Peach-400
        "eye_core": (255, 255, 255, 255),
        "eye_glow": (253, 186, 116),           # Warm Glowing Peach
        "badge_bg": "#7c2d12",
        "badge_fg": "#fed7aa",
        "badge_text": "TALKING"
    },
    "sleep": {
        "border": (40, 42, 50, 255),
        "eye_core": (100, 116, 139, 255),
        "eye_glow": (71, 85, 105),             # Soft Dim Slate
        "badge_bg": "#18181b",
        "badge_fg": "#71717a",
        "badge_text": "SLEEPING"
    }
}

# LiveBridge Voice Banter for Stunts
STUNT_VOICE_BANTER = {
    "laser_blaster": "Whoa step back bro! Don't make me vaporize that cursor! Pew pew pew!",
    "crying_tears": "Aww, don't leave me alone in the dark bro... catch you later!",
    "heart_eyes": "Haha thanks for the love bro! Feeling energized and ready to roll!",
    "dizzy_glitch": "Whoa whoa whoa, you're spinning my gyros man! Give me a second to recalibrate!",
}


# ─────────────────────────────────────────────────────────────────────────────
# VECTOR MATH HELPERS
# ─────────────────────────────────────────────────────────────────────────────
def get_heart_polygon(cx: float, cy: float, size_scale: float = 1.0, num_points: int = 36) -> List[Tuple[float, float]]:
    """Generates 2D coordinates of a parametric heart curve."""
    points = []
    for i in range(num_points):
        t = (2.0 * math.pi * i) / num_points
        x_raw = 16.0 * (math.sin(t) ** 3)
        y_raw = -(13.0 * math.cos(t) - 5.0 * math.cos(2.0 * t) - 2.0 * math.cos(3.0 * t) - math.cos(4.0 * t))
        px = cx + (x_raw * 1.05 * size_scale)
        py = cy + ((y_raw + 2.0) * 1.05 * size_scale)
        points.append((px, py))
    return points


def get_spiral_points(cx: float, cy: float, rot_angle: float, max_radius: float = 18.0, turns: float = 2.2, num_points: int = 40) -> List[Tuple[float, float]]:
    """Generates 2D coordinates of an Archimedean spiral."""
    points = []
    for i in range(num_points):
        frac = i / float(num_points - 1)
        theta = rot_angle + frac * turns * 2.0 * math.pi
        r = frac * max_radius
        px = cx + r * math.cos(theta)
        py = cy + r * math.sin(theta)
        points.append((px, py))
    return points


# ─────────────────────────────────────────────────────────────────────────────
# STUNT MANAGER
# ─────────────────────────────────────────────────────────────────────────────
class StuntManager:
    """Manages active stunt states, timers, and easing transitions."""
    def __init__(self):
        self.active_stunt: str = "none"
        self.stunt_start_time: float = 0.0
        self.stunt_duration: float = 0.0
        self.stunt_progress: float = 0.0

    def trigger(self, stunt_name: str, duration: float = 2.5):
        self.active_stunt = stunt_name
        self.stunt_start_time = time.time()
        self.stunt_duration = duration
        self.stunt_progress = 0.0

    def cancel(self):
        self.active_stunt = "none"
        self.stunt_progress = 0.0

    def update(self) -> str:
        """Call each tick; returns current active stunt name or 'none'."""
        if self.active_stunt == "none":
            return "none"
        now = time.time()
        elapsed = now - self.stunt_start_time
        if elapsed >= self.stunt_duration:
            self.active_stunt = "none"
            self.stunt_progress = 1.0
            return "none"
        self.stunt_progress = elapsed / self.stunt_duration
        return self.active_stunt

    def get_elapsed(self) -> float:
        if self.active_stunt == "none":
            return 0.0
        return time.time() - self.stunt_start_time


# ─────────────────────────────────────────────────────────────────────────────
# OS-WIDE LIVE INDICATOR MOUSE CURSOR (Style 2: Mini Cyber-Head)
# ─────────────────────────────────────────────────────────────────────────────
class LiveCursorManager:
    """Manages the Windows OS-wide custom mouse cursor indicating Nova is live."""
    OCR_NORMAL = 32512
    SPI_SETCURSORS = 0x0057

    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self.is_active = False
        self.current_state = "idle"
        self._user32 = ctypes.windll.user32
        self._cur_files = {}
        if self.enabled:
            self._pregenerate_cursors()
            atexit.register(self.restore)

    def _pregenerate_cursors(self):
        """Pre-generates .cur files for listening (orange rim) and speaking (peach rim)."""
        temp_dir = tempfile.gettempdir()
        states = {
            "listening": (234, 88, 12),   # Terracotta Orange
            "speaking": (251, 146, 60),   # Warm Peach
        }
        for st, color in states.items():
            try:
                # 32x32 cursor canvas
                img = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)

                # Precision top-left pointer arrow with hotspot at (0, 0)
                arrow_pts = [(0, 0), (0, 16), (4, 12), (7, 18), (10, 17), (7, 11), (13, 11)]
                draw.polygon(arrow_pts, fill=(24, 24, 27, 255), outline=(*color, 255), width=1)

                # Mini Nova Cyber-Head nestled at (20, 19)
                cx, cy = 20, 19
                r = 10
                # Outer dome ring
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(22, 23, 27, 255), outline=(*color, 255), width=2)
                # Obsidian visor
                draw.ellipse([cx - r + 2, cy - r + 2, cx + r - 2, cy + r - 2], fill=(9, 10, 14, 255))
                # Glowing cyan capsule eyes
                draw.rounded_rectangle([cx - 5, cy - 4, cx - 2, cy + 4], radius=2, fill=(56, 189, 248, 255))
                draw.rounded_rectangle([cx + 1, cy - 4, cx + 4, cy + 4], radius=2, fill=(56, 189, 248, 255))

                ico_path = os.path.join(temp_dir, f"nova_live_{st}.ico")
                cur_path = os.path.join(temp_dir, f"nova_live_{st}.cur")
                img.save(ico_path)
                with open(ico_path, "rb") as f:
                    data = bytearray(f.read())
                # Type = 2 (CUR)
                data[2] = 2
                data[3] = 0
                # Hotspot at (0, 0)
                data[10] = 0
                data[11] = 0
                data[12] = 0
                data[13] = 0
                with open(cur_path, "wb") as f:
                    f.write(data)
                try:
                    os.remove(ico_path)
                except Exception:
                    pass
                self._cur_files[st] = cur_path
            except Exception as e:
                print(f"[CURSOR ERROR] Pre-generating cursor {st} failed: {e}")

    def set_live_cursor(self, state: str = "listening"):
        """Activates the custom live cursor across Windows."""
        if not self.enabled:
            return
        if self.is_active and self.current_state == state:
            return
        cur_file = self._cur_files.get(state, self._cur_files.get("listening"))
        if not cur_file or not os.path.exists(cur_file):
            return
        try:
            hcur = self._user32.LoadCursorFromFileW(cur_file)
            if hcur:
                self._user32.SetSystemCursor(hcur, self.OCR_NORMAL)
                self.is_active = True
                self.current_state = state
        except Exception as e:
            print(f"[CURSOR ERROR] Failed to set system cursor: {e}")

    def restore(self):
        """Restores standard Windows system cursors."""
        if not self.is_active:
            return
        try:
            self._user32.SystemParametersInfoW(self.SPI_SETCURSORS, 0, None, 0)
            self.is_active = False
            self.current_state = "idle"
        except Exception as e:
            print(f"[CURSOR ERROR] Failed to restore system cursor: {e}")



# ─────────────────────────────────────────────────────────────────────────────
# DIRECT MOUSE GAZE TRACKING (Locked onto cursor hovering)
# ─────────────────────────────────────────────────────────────────────────────
class POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class GazeController:
    """Tracks global mouse position and directly, smoothly points eyes at cursor."""
    MAX_GAZE_RADIUS = 7.5   # Maximum eye pupil offset in pixels
    LERP_SPEED      = 0.24  # Snappy, organic damping factor

    def __init__(self):
        self._pt = POINT()
        self.gaze_x = 0.0
        self.gaze_y = 0.0
        self.target_x = 0.0
        self.target_y = 0.0
        self.cursor_dist = 999.0
        self.is_hovering_face = False

    def update(self, widget_screen_x: int, widget_screen_y: int, is_hover: bool):
        """Call each animation frame with widget top-left screen position."""
        self.is_hovering_face = is_hover
        ctypes.windll.user32.GetCursorPos(ctypes.byref(self._pt))

        center_x = widget_screen_x + (CANVAS_SIZE // 2)
        center_y = widget_screen_y + (CANVAS_SIZE // 2)

        dx = float(self._pt.x - center_x)
        dy = float(self._pt.y - center_y)
        self.cursor_dist = math.hypot(dx, dy)

        if self.cursor_dist > 0.1:
            reach = min(self.cursor_dist / 320.0, 1.0)
            self.target_x = (dx / self.cursor_dist) * reach * self.MAX_GAZE_RADIUS
            self.target_y = (dy / self.cursor_dist) * reach * self.MAX_GAZE_RADIUS
        else:
            self.target_x = 0.0
            self.target_y = 0.0

        # Organic smooth damping directly toward mouse
        self.gaze_x += (self.target_x - self.gaze_x) * self.LERP_SPEED
        self.gaze_y += (self.target_y - self.gaze_y) * self.LERP_SPEED


# ─────────────────────────────────────────────────────────────────────────────
# CYBER-HEAD RENDERER (Clean Dark Helmet + Visor + Glowing Pill Eyes + Stunts)
# ─────────────────────────────────────────────────────────────────────────────
class CyberHeadRenderer:
    """Renders the minimalist cyber robot head (NO ears, NO line-mouth) with vector stunts."""
    def __init__(self, size: int = CANVAS_SIZE):
        self.size = size

    def render(
        self,
        gaze_x: float = 0.0,
        gaze_y: float = 0.0,
        eye_open_ratio: float = 1.0,
        eye_squint: bool = False,
        state: str = "idle",
        is_hover: bool = False,
        is_drag: bool = False,
        speech_pulse: float = 1.0,
        stunt: str = "none",
        stunt_time: float = 0.0
    ) -> Image.Image:
        scale = 2  # 2x supersampling for silky-smooth anti-aliased edges
        w = self.size * scale
        h = self.size * scale

        img = Image.new("RGBA", (w, h), CLR_TRANSPARENT)
        draw = ImageDraw.Draw(img)

        theme = STATE_THEMES.get(state, STATE_THEMES["idle"])
        border_col = (249, 115, 22, 255) if is_hover else theme["border"]

        # Dynamic stunt border rim overrides
        if stunt == "laser_blaster":
            pulse = 0.5 + 0.5 * math.sin(stunt_time * 16.0)
            r = int(200 + 55 * pulse)
            border_col = (r, 30, 30, 255)
        elif stunt == "heart_eyes":
            border_col = (251, 113, 133, 255)
        elif stunt == "crying_tears":
            border_col = (56, 189, 248, 255)
        elif stunt == "dizzy_glitch":
            border_col = (168, 85, 247, 255)

        # Micro-tremble / shiver for crying tears or dizzy overload
        shiver_x, shiver_y = 0, 0
        if stunt == "crying_tears":
            shiver_x = int(math.sin(stunt_time * 40.0) * 1.8)
        elif stunt == "dizzy_glitch":
            shiver_x = int(math.sin(stunt_time * 25.0) * 2.2)
            shiver_y = int(math.cos(stunt_time * 20.0) * 1.8)

        cx_center = w // 2 + shiver_x
        cy_center = h // 2 + shiver_y

        # ── 1. Outer Dark Dome Helmet Bezel ──────────────────────────────────
        draw.ellipse(
            [14 + shiver_x, 14 + shiver_y, w - 14 + shiver_x, h - 14 + shiver_y],
            fill=(22, 23, 27, 255),
            outline=border_col,
            width=5
        )

        # ── 2. Inner Bezel Contrast Ring ─────────────────────────────────────
        draw.ellipse(
            [20 + shiver_x, 20 + shiver_y, w - 20 + shiver_x, h - 20 + shiver_y],
            fill=(16, 17, 21, 255),
            outline=(35, 37, 45, 255),
            width=2
        )

        # ── 3. Obsidian Dark Glass Visor ─────────────────────────────────────
        draw.ellipse(
            [25 + shiver_x, 25 + shiver_y, w - 25 + shiver_x, h - 25 + shiver_y],
            fill=(9, 10, 14, 255)
        )

        # ── 4. Visor Gloss Reflection Sheen ──────────────────────────────────
        draw.arc(
            [30 + shiver_x, 30 + shiver_y, w - 30 + shiver_x, h - 30 + shiver_y],
            start=195, end=255, fill=(255, 255, 255, 45), width=4
        )
        draw.arc(
            [33 + shiver_x, 33 + shiver_y, w - 33 + shiver_x, h - 33 + shiver_y],
            start=205, end=245, fill=(255, 255, 255, 75), width=2
        )

        # Eye Positions (with supersampled scaling and gaze offset)
        gx = int(gaze_x * scale)
        gy = int(gaze_y * scale)
        lx, ly = 74 + gx + shiver_x, 96 + gy + shiver_y
        rx, ry = 118 + gx + shiver_x, 96 + gy + shiver_y

        # ── 5. Stunt Rendering or Natural Capsule Eyes ────────────────────────
        if stunt == "laser_blaster":
            # Aim angle towards cursor
            angle = math.atan2(
                gaze_y if abs(gaze_y) > 0.01 else -0.3,
                gaze_x if abs(gaze_x) > 0.01 else 0.8
            )

            # Laser Turret on outer bezel edge
            bezel_r = 80.0
            bx = cx_center + bezel_r * math.cos(angle)
            by = cy_center + bezel_r * math.sin(angle)
            barrel_len = 22.0
            ex = bx + barrel_len * math.cos(angle)
            ey = by + barrel_len * math.sin(angle)

            # Turret gun barrel
            draw.line([(bx, by), (ex, ey)], fill=(60, 65, 75, 255), width=7)
            draw.line([(bx, by), (ex, ey)], fill=(239, 68, 68, 255), width=3)

            # High-intensity laser beam shooting towards cursor
            beam_len = 90.0
            fx = ex + beam_len * math.cos(angle)
            fy = ey + beam_len * math.sin(angle)

            beam_pulse = 0.6 + 0.4 * math.sin(stunt_time * 30.0)
            draw.line([(ex, ey), (fx, fy)], fill=(239, 68, 68, int(70 * beam_pulse)), width=6)
            draw.line([(ex, ey), (fx, fy)], fill=(254, 202, 202, int(230 * beam_pulse)), width=2)

            # Muzzle flash
            draw.ellipse([ex - 5, ey - 5, ex + 5, ey + 5], fill=(255, 255, 255, 220))
            draw.ellipse([ex - 8, ey - 8, ex + 8, ey + 8], outline=(239, 68, 68, 180), width=2)

            # Tactical Red Crosshair Targeting Reticles
            for (cx, cy) in [(lx, ly), (rx, ry)]:
                draw.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=(239, 68, 68, 35))
                draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline=(239, 68, 68, 200), width=3)
                draw.line([(cx - 17, cy), (cx - 5, cy)], fill=(255, 200, 200, 255), width=2)
                draw.line([(cx + 5, cy), (cx + 17, cy)], fill=(255, 200, 200, 255), width=2)
                draw.line([(cx, cy - 17), (cx, cy - 5)], fill=(255, 200, 200, 255), width=2)
                draw.line([(cx, cy + 5), (cx, cy + 17)], fill=(255, 200, 200, 255), width=2)
                draw.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(255, 255, 255, 255))

        elif stunt == "crying_tears":
            # 1. Weeping sad eyes (angled droop bars)
            for (cx, cy, dir_side) in [(lx, ly, -1), (rx, ry, 1)]:
                draw.line([(cx - 13, cy + dir_side * 2), (cx + 13, cy - dir_side * 2)], fill=(56, 189, 248, 120), width=7)
                draw.line([(cx - 11, cy + dir_side * 2), (cx + 11, cy - dir_side * 2)], fill=(224, 242, 254, 255), width=4)

            # 2. Cascading digital tear droplets
            tear_bottom = 156 + shiver_y
            for (cx, start_y) in [(lx, ly + 8), (rx, ry + 8)]:
                for k in range(3):
                    tau = ((stunt_time * 1.5) + (k * 0.35)) % 1.0
                    ty = start_y + (tau ** 2) * (tear_bottom - start_y)
                    tx = cx + math.sin(tau * 3.0 + k) * 2.0

                    tail_len = 8.0 * tau + 3.0
                    alpha = int(220 * (1.0 - 0.2 * tau))
                    draw.line([(tx, max(start_y, ty - tail_len)), (tx, ty)], fill=(56, 189, 248, alpha), width=4)
                    draw.line([(tx, max(start_y, ty - tail_len + 2)), (tx, ty)], fill=(255, 255, 255, alpha), width=2)
                    draw.ellipse([tx - 3, ty - 3, tx + 3, ty + 3], fill=(224, 242, 254, alpha))

                    if tau > 0.8:
                        ripple_r = 8.0 * ((tau - 0.8) / 0.2)
                        r_alpha = int(180 * (1.0 - (tau - 0.8) / 0.2))
                        draw.ellipse(
                            [tx - ripple_r, tear_bottom - 2, tx + ripple_r, tear_bottom + 2],
                            outline=(56, 189, 248, r_alpha),
                            width=2
                        )

        elif stunt == "heart_eyes":
            # Parametric glowing heart eyes with heartbeat pulse
            hb = math.sin(stunt_time * 7.0)
            pulse = 1.0 + 0.15 * max(0.0, hb) + 0.08 * max(0.0, math.sin(stunt_time * 7.0 - 0.5))

            for (cx, cy) in [(lx, ly), (rx, ry)]:
                # Layer 1: Ambient Pink Aura
                p1 = get_heart_polygon(cx, cy, size_scale=1.35 * pulse)
                draw.polygon(p1, fill=(244, 63, 94, 35))
                # Layer 2: Glowing Magenta Bloom
                p2 = get_heart_polygon(cx, cy, size_scale=1.12 * pulse)
                draw.polygon(p2, fill=(244, 63, 94, 110))
                # Layer 3: Solid Crisp Cream Core
                p3 = get_heart_polygon(cx, cy, size_scale=0.92 * pulse)
                draw.polygon(p3, fill=(255, 235, 240, 255))

        elif stunt == "dizzy_glitch":
            # Rotating Archimedean spirals
            rot_l = stunt_time * 9.0
            rot_r = -stunt_time * 9.0

            pts_l = get_spiral_points(lx, ly, rot_l, max_radius=17, turns=2.2)
            pts_r = get_spiral_points(rx, ry, rot_r, max_radius=17, turns=2.2)

            for pts in [pts_l, pts_r]:
                for i in range(len(pts) - 1):
                    draw.line([pts[i], pts[i+1]], fill=(168, 85, 247, 90), width=6)
                    draw.line([pts[i], pts[i+1]], fill=(240, 252, 255, 255), width=3)

            # Digital scanline glitch bars
            if int(stunt_time * 15) % 3 == 0:
                for g_y in [70 + shiver_y, 110 + shiver_y]:
                    draw.line([(35, g_y), (w - 35, g_y)], fill=(168, 85, 247, 120), width=2)
                    draw.line([(40, g_y + 4), (w - 40, g_y + 4)], fill=(56, 189, 248, 90), width=1)

        else:
            # Normal Natural Capsule Eyes
            ew = 20  # 10px in 96px frame
            eh = max(4, int(46 * eye_open_ratio))  # 23px in 96px frame

            if is_drag:
                ew = 24
                eh = 54

            glow_rgb = theme["eye_glow"]
            eye_core = theme["eye_core"]

            if eye_squint:
                # Joyful squint arcs (^ ^) on hover
                for (cx, cy) in [(lx, ly), (rx, ry)]:
                    draw.arc([cx - 16, cy - 14, cx + 16, cy + 14], start=195, end=345, fill=(*glow_rgb, 90), width=8)
                    draw.arc([cx - 15, cy - 13, cx + 15, cy + 13], start=195, end=345, fill=eye_core, width=5)
            elif eh <= 6:
                # Clean horizontal blink slit
                for (cx, cy) in [(lx, ly), (rx, ry)]:
                    draw.line([(cx - 12, cy), (cx + 12, cy)], fill=(*glow_rgb, 100), width=6)
                    draw.line([(cx - 10, cy), (cx + 10, cy)], fill=eye_core, width=3)
            else:
                # Luminous 3-Layer OLED Capsule Eyes (Soft natural glow, no muddy outlines)
                for (cx, cy) in [(lx, ly), (rx, ry)]:
                    # Layer 1: Ambient Soft Aura
                    draw.rounded_rectangle(
                        [cx - ew // 2 - 8, cy - eh // 2 - 8, cx + ew // 2 + 8, cy + eh // 2 + 8],
                        radius=(ew + 16) // 2,
                        fill=(*glow_rgb, 30)
                    )
                    # Layer 2: Glowing Neon Bloom
                    draw.rounded_rectangle(
                        [cx - ew // 2 - 4, cy - eh // 2 - 4, cx + ew // 2 + 4, cy + eh // 2 + 4],
                        radius=(ew + 8) // 2,
                        fill=(*glow_rgb, 95)
                    )
                    # Layer 3: Saturated Crisp Core Pill
                    draw.rounded_rectangle(
                        [cx - ew // 2, cy - eh // 2, cx + ew // 2, cy + eh // 2],
                        radius=ew // 2,
                        fill=eye_core
                    )

        # Downsample with Lanczos anti-aliasing for silky smooth edges
        return img.resize((self.size, self.size), Image.Resampling.LANCZOS)


# ─────────────────────────────────────────────────────────────────────────────
# BACKWARD COMPATIBILITY SPRITE ADAPTER (For existing tests)
# ─────────────────────────────────────────────────────────────────────────────
class GhostCharacterRenderer:
    FRAME_NAMES = [
        "idle",
        "idle_blink",
        "glance",
        "listening",
        "listening_blink",
        "speaking",
        "speaking_alt",
    ]
    TILE_SIZE = CANVAS_SIZE

    def __init__(self, sheet_path: Optional[str] = None):
        self.pil_frames = {}
        self.tk_photos = {}
        head_r = CyberHeadRenderer(size=CANVAS_SIZE)

        configs = {
            "idle": dict(gaze_x=0.0, gaze_y=0.0, eye_open_ratio=1.0, state="idle"),
            "idle_blink": dict(gaze_x=0.0, gaze_y=0.0, eye_open_ratio=0.05, state="idle"),
            "glance": dict(gaze_x=4.0, gaze_y=-2.0, eye_open_ratio=1.0, state="idle"),
            "listening": dict(gaze_x=0.0, gaze_y=0.0, eye_open_ratio=1.0, state="listening"),
            "listening_blink": dict(gaze_x=0.0, gaze_y=0.0, eye_open_ratio=0.05, state="listening"),
            "speaking": dict(gaze_x=0.0, gaze_y=0.0, eye_open_ratio=1.0, eye_squint=True, state="speaking"),
            "speaking_alt": dict(gaze_x=0.0, gaze_y=0.0, eye_open_ratio=1.0, speech_pulse=1.12, state="speaking"),
        }
        for name in self.FRAME_NAMES:
            cfg = configs.get(name, configs["idle"])
            self.pil_frames[name] = head_r.render(
                gaze_x=cfg.get("gaze_x", 0.0),
                gaze_y=cfg.get("gaze_y", 0.0),
                eye_open_ratio=cfg.get("eye_open_ratio", 1.0),
                eye_squint=cfg.get("eye_squint", False),
                state=cfg.get("state", "idle"),
                is_hover=False,
                is_drag=False,
                speech_pulse=cfg.get("speech_pulse", 1.0)
            )

    def get_tk_photo(self, frame_name: str) -> Optional[ImageTk.PhotoImage]:
        if frame_name not in self.tk_photos:
            img = self.pil_frames.get(frame_name, self.pil_frames.get("idle"))
            if img:
                self.tk_photos[frame_name] = ImageTk.PhotoImage(img)
        return self.tk_photos.get(frame_name)


# ─────────────────────────────────────────────────────────────────────────────
# FLOATING GHOST COMPANION WIDGET
# ─────────────────────────────────────────────────────────────────────────────
class FloatingGhostWidget:
    """Floating Desktop Copilot with real-time interactive cyber-head face & stunts."""
    def __init__(self, root: tk.Tk):
        self.root = root
        self.is_expanded = False
        self.state = "idle"  # "idle" | "connecting" | "listening" | "speaking"

        # Drag & Shake tracking
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._has_dragged = False
        self._is_dragging = False
        self._prev_dx = 0
        self._prev_dy = 0
        self._shake_reversals = 0
        self._last_motion_time = time.time()
        self._last_reversal_reset = time.time()

        # Hover timer for Heart Eyes
        self._hover_start_time = 0.0
        self._hover_stunt_triggered = False

        # Screen position (default top-right corner)
        screen_w = self.root.winfo_screenwidth()
        self.pos_x = screen_w - 140
        self.pos_y = 120

        # Subsystems
        self.gaze = GazeController()
        self.renderer = CyberHeadRenderer(size=CANVAS_SIZE)
        self.stunt_mgr = StuntManager()
        self.cursor_mgr = LiveCursorManager(enabled=ENABLE_LIVE_CURSOR)
        self._current_photo: Optional[ImageTk.PhotoImage] = None

        # Animation states
        self.eye_open_ratio = 1.0
        self.is_blinking = False
        self._blink_counter = 0
        self._next_blink_time = time.time() + random.uniform(3.0, 6.0)
        self._is_hovered = False
        self._last_ghost_speech_time = 0.0

        # Background LiveBridge handle and thread
        self.bridge: Optional[LiveBridge] = None
        self._bridge_thread: Optional[threading.Thread] = None
        self._bridge_loop: Optional[asyncio.AbstractEventLoop] = None

        # Configure Root Window
        self.root.overrideredirect(True)                              # Frameless
        self.root.wm_attributes("-topmost", True)                     # Always on top
        self.root.wm_attributes("-transparentcolor", TRANSPARENT_KEY) # Windows Desktop Alpha Cut
        self.root.config(bg=TRANSPARENT_KEY)

        # Build UI layout & start tick loop
        self.setup_ui()
        self.show_collapsed()
        self.root.after(16, self._anim_tick)

    def setup_ui(self):
        """Constructs UI container widgets."""
        # ── 1. Cyber Head Canvas (Collapsed Character View) ──────────────────
        self.face_canvas = tk.Canvas(
            self.root,
            width=CANVAS_SIZE,
            height=CANVAS_SIZE,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
            cursor="hand2"
        )
        self.canvas_img_item = self.face_canvas.create_image(
            CANVAS_SIZE // 2, CANVAS_SIZE // 2, image=None
        )

        # Mouse event bindings
        self.face_canvas.bind("<ButtonPress-1>", self.on_press)
        self.face_canvas.bind("<B1-Motion>", self.on_motion)
        self.face_canvas.bind("<ButtonRelease-1>", self.on_release)
        self.face_canvas.bind("<ButtonPress-3>", self.on_right_click)      # Right-click: Cyber-Blaster 🔫
        self.face_canvas.bind("<Enter>", self.on_face_enter)
        self.face_canvas.bind("<Leave>", self.on_face_leave)

        # Backward compatibility aliases for tests and external callers
        self.circle_canvas = self.face_canvas
        self.avatar_img_item = self.canvas_img_item
        self.on_circle_hover = self.on_face_enter
        self.on_circle_leave = self.on_face_leave
        self._animate_tick = self._anim_tick

        # ── 2. Expanded Transcript Bar (Active Voice Mode) ───────────────────
        self.expand_frame = tk.Frame(
            self.root,
            bg=BG_COLOR,
            highlightbackground=BORDER_COLOR,
            highlightcolor=HOVER_BORDER,
            highlightthickness=1,
        )

        # Status badge ([LIVE], [CONNECTING], [STANDBY])
        self.badge_lbl = tk.Label(
            self.expand_frame,
            text="STANDBY",
            font=("Segoe UI", 9, "bold"),
            bg="#27272a",
            fg=SUBTEXT_COLOR,
            padx=6,
            pady=2
        )
        self.badge_lbl.pack(side="left", padx=(10, 6), pady=8)

        # Live Transcript display text
        self.transcript_lbl = tk.Label(
            self.expand_frame,
            text="Listening for voice... Speak anytime!",
            font=("Segoe UI", 10),
            bg=BG_COLOR,
            fg=TEXT_COLOR,
            anchor="w",
        )
        self.transcript_lbl.pack(side="left", padx=(4, 8), pady=8, fill="x", expand=True)

        # Stop/Sleep Button (⏹)
        self.stop_btn = tk.Button(
            self.expand_frame,
            text="⏹",
            font=("Segoe UI", 10, "bold"),
            bg="#27272a",
            fg="#f87171",
            activebackground="#3f3f46",
            activeforeground="#ef4444",
            relief="flat",
            cursor="hand2",
            command=self.stop_session,
            padx=8,
            pady=2
        )
        self.stop_btn.pack(side="left", padx=(0, 6), pady=8)

        # Collapse Button (—)
        self.collapse_btn = tk.Button(
            self.expand_frame,
            text="—",
            font=("Segoe UI", 10, "bold"),
            bg=BG_COLOR,
            fg=SUBTEXT_COLOR,
            activebackground=BG_COLOR,
            activeforeground=TEXT_COLOR,
            relief="flat",
            cursor="hand2",
            command=self.show_collapsed,
            padx=6,
            pady=2
        )
        self.collapse_btn.pack(side="left", padx=(0, 4), pady=8)

        # Quit Button (✕)
        self.exit_btn = tk.Button(
            self.expand_frame,
            text="✕",
            font=("Segoe UI", 10, "bold"),
            bg=BG_COLOR,
            fg="#ef4444",
            activebackground=BG_COLOR,
            activeforeground="#f87171",
            relief="flat",
            cursor="hand2",
            command=self.quit_app,
            padx=6,
            pady=2
        )
        self.exit_btn.pack(side="left", padx=(0, 10), pady=8)

    # ── Interactive Vector Stunt Trigger ─────────────────────────────────────
    def trigger_stunt(self, stunt_name: str, duration: float = 2.5):
        """Triggers a procedural character stunt (100% visual vector animation)."""
        print(f"[WIDGET] Triggering interactive stunt: {stunt_name}")
        self.stunt_mgr.trigger(stunt_name, duration)

    # ── 60 FPS Real-Time Animation Loop ──────────────────────────────────────
    def _anim_tick(self):
        """Executes every 16ms to update gaze, blinking, stunt animations, and rendering."""
        now = time.time()

        # 1. Update Gaze Tracking (Directly looks at cursor hovering)
        self.gaze.update(self.pos_x, self.pos_y, self._is_hovered)

        # 2. Update Active Vector Stunt
        active_stunt = self.stunt_mgr.update()
        stunt_time = self.stunt_mgr.get_elapsed()

        # Hover timer for Heart Eyes (>1.5s steady hover, one-shot per hover session)
        if (
            self._is_hovered
            and not self._is_dragging
            and not self._hover_stunt_triggered
            and active_stunt == "none"
            and self.state != "sleep"
        ):
            if self._hover_start_time > 0 and (now - self._hover_start_time >= 1.5):
                self._hover_stunt_triggered = True
                self.trigger_stunt("heart_eyes", duration=2.5)

        # 3. Autonomous Blinking Logic (Paused during active stunts)
        if active_stunt == "none":
            if not self.is_blinking:
                if now >= self._next_blink_time and not self._is_dragging:
                    self.is_blinking = True
                    self._blink_counter = 0
                    self._next_blink_time = now + random.uniform(3.0, 6.0)
            else:
                self._blink_counter += 1
                if self._blink_counter <= 4:
                    self.eye_open_ratio = max(0.05, 1.0 - (self._blink_counter / 4.0))
                elif self._blink_counter <= 8:
                    self.eye_open_ratio = min(1.0, (self._blink_counter - 4) / 4.0)
                else:
                    self.eye_open_ratio = 1.0
                    self.is_blinking = False
        else:
            self.eye_open_ratio = 1.0
            self.is_blinking = False

        # 4. Auto-recover from speaking to listening when Ghost finishes talking
        if self.state == "speaking":
            audio_playing = False
            if self.bridge and hasattr(self.bridge, "audio_io") and self.bridge.audio_io:
                audio_playing = self.bridge.audio_io.is_playing
            if not audio_playing and (now - self._last_ghost_speech_time > 0.8):
                self._set_ui_state("listening")

        # 5. Squint / Expression
        eye_squint = False
        if self._is_hovered and not self._is_dragging and self.state != "sleep" and active_stunt == "none":
            eye_squint = True  # Happy squint arcs on mouse hover
        elif self.state == "sleep":
            self.eye_open_ratio = 0.05

        # 6. Render Frame if in collapsed character mode
        if not self.is_expanded:
            frame = self.renderer.render(
                gaze_x=self.gaze.gaze_x,
                gaze_y=self.gaze.gaze_y,
                eye_open_ratio=self.eye_open_ratio,
                eye_squint=eye_squint,
                state=self.state,
                is_hover=self._is_hovered,
                is_drag=self._is_dragging,
                stunt=active_stunt,
                stunt_time=stunt_time
            )
            self._current_photo = ImageTk.PhotoImage(frame)
            self.face_canvas.itemconfig(self.canvas_img_item, image=self._current_photo)

        # Schedule next tick (~60 FPS)
        self.root.after(16, self._anim_tick)

    # ── Interaction & Dragging ───────────────────────────────────────────────
    def on_face_enter(self, event):
        self._is_hovered = True
        self._hover_start_time = time.time()
        self._hover_stunt_triggered = False

    def on_face_leave(self, event):
        self._is_hovered = False
        self._hover_start_time = 0.0
        self._hover_stunt_triggered = False
        if self.stunt_mgr.active_stunt == "heart_eyes":
            self.stunt_mgr.cancel()

    def on_right_click(self, event):
        """Right-click triggers the Cyber-Blaster laser defense stunt."""
        self.trigger_stunt("laser_blaster", duration=2.5)

    def on_double_click(self, event):
        """Double-click triggers the Cyber-Blaster laser defense stunt."""
        self.trigger_stunt("laser_blaster", duration=2.5)

    def on_press(self, event):
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._has_dragged = False
        self._is_dragging = False
        self._prev_dx = 0
        self._prev_dy = 0
        self._shake_reversals = 0
        self._last_motion_time = time.time()
        self._last_reversal_reset = time.time()

    def on_motion(self, event):
        dx = event.x_root - self._drag_start_x
        dy = event.y_root - self._drag_start_y

        if abs(dx) > 3 or abs(dy) > 3:
            self._has_dragged = True
            self._is_dragging = True

        # Shake detection for Dizzy Glitch stunt
        now = time.time()
        dt = now - self._last_motion_time
        self._last_motion_time = now

        if dt > 0.001 and self._has_dragged:
            speed = math.hypot(dx, dy) / dt
            # Check for sudden directional reversal
            if (dx * self._prev_dx < -10) or (dy * self._prev_dy < -10):
                self._shake_reversals += 1
                if self._shake_reversals >= 3 and speed > 700:
                    self.trigger_stunt("dizzy_glitch", duration=2.2)
                    self._shake_reversals = 0

            if now - self._last_reversal_reset > 0.6:
                self._shake_reversals = 0
                self._last_reversal_reset = now

        self._prev_dx = dx
        self._prev_dy = dy

        self.pos_x += dx
        self.pos_y += dy
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root

        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        self.pos_x = max(10, min(screen_w - CANVAS_SIZE - 10, self.pos_x))
        self.pos_y = max(10, min(screen_h - CANVAS_SIZE - 10, self.pos_y))

        self.root.geometry(f"+{self.pos_x}+{self.pos_y}")

    def on_release(self, event):
        self._is_dragging = False
        if not self._has_dragged:
            # If a stunt is actively animating, clicks are absorbed by the stunt
            if self.stunt_mgr.active_stunt != "none":
                return

            if self.state == "idle":
                self.start_session()
            elif self.state == "speaking":
                # Manual barge-in interrupt: cut Ghost off and unmute mic
                if self.bridge:
                    print("[WIDGET] Manual interrupt triggered via click.")
                    self.bridge.manual_interrupt()
            else:
                # Toggle expanded/collapsed transcript
                if self.is_expanded:
                    self.show_collapsed()
                else:
                    self.show_expanded()

    # ── Session Management ───────────────────────────────────────────────────
    def start_session(self):
        """Starts a live gemini-3.8-live session in a dedicated background thread."""
        if self.state in ("active", "connecting"):
            return

        self._set_ui_state("connecting")
        self.show_expanded()

        self.bridge = LiveBridge(
            on_standby=self._on_bridge_standby,
            on_status=self._on_bridge_status,
            on_transcript=self._on_bridge_transcript,
        )

        self._bridge_thread = threading.Thread(
            target=self._run_bridge_loop,
            daemon=True
        )
        self._bridge_thread.start()

    def _run_bridge_loop(self):
        """Worker thread hosting the asyncio event loop for the live session."""
        self._bridge_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._bridge_loop)
        try:
            self._bridge_loop.run_until_complete(self.bridge.run())
        except Exception as e:
            print(f"[WIDGET ERROR] Bridge run exception: {e}")
        finally:
            try:
                pending = [t for t in asyncio.all_tasks(self._bridge_loop) if not t.done()]
                for task in pending:
                    task.cancel()
                if pending:
                    self._bridge_loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                self._bridge_loop.run_until_complete(self._bridge_loop.shutdown_asyncgens())
            except Exception:
                pass
            try:
                if not self._bridge_loop.is_closed():
                    self._bridge_loop.close()
            except Exception:
                pass
            self._bridge_loop = None

    def stop_session(self):
        """Stops the active live session and triggers crying tears before settling into standby."""
        if self.bridge:
            self.bridge.request_stop()
        self.cursor_mgr.restore()
        self.show_collapsed()
        # Trigger crying tears stunt
        self.trigger_stunt("crying_tears", duration=2.2)
        # Settle to idle/sleep after crying animation
        self.root.after(2200, lambda: self._set_ui_state("idle"))

    def quit_app(self):
        """Cleanly terminates the widget and application."""
        print("[WIDGET] Closing Floating Character Ghost.")
        self.cursor_mgr.restore()
        self.stop_session()
        self.root.destroy()
        sys.exit(0)

    # ── Bridge Callbacks (Thread-Safe via root.after) ─────────────────────────
    def _on_bridge_status(self, status: str):
        """Called by LiveBridge on connection state changes."""
        def update():
            if status == "active":
                self._set_ui_state("listening")
            elif status in ("idle", "error"):
                self._set_ui_state("idle")
                self.show_collapsed()
        self.root.after(0, update)

    def _on_bridge_standby(self):
        """Called by LiveBridge when sleep tool is invoked."""
        def update():
            self.show_collapsed()
            self.trigger_stunt("crying_tears", duration=2.2)
            self.root.after(2200, lambda: self._set_ui_state("sleep"))
            try:
                winsound.MessageBeep(winsound.MB_ICONASTERISK)
            except Exception:
                pass
        self.root.after(0, update)

    def _on_bridge_transcript(self, speaker: str, text: str):
        """Updates the transcript label live as user or Ghost speaks."""
        def update():
            prefix = "You: " if speaker == "user" else "Ghost: "
            color = "#a7f3d0" if speaker == "user" else "#c7d2fe"
            self.transcript_lbl.config(text=f"{prefix}{text}", fg=color)

            if speaker == "ghost":
                self._last_ghost_speech_time = time.time()
                self._set_ui_state("speaking")
            else:
                self._set_ui_state("listening")
        self.root.after(0, update)

    # ── Visual State Handler ─────────────────────────────────────────────────
    def _set_ui_state(self, state: str):
        """Updates UI state, badges, colors, and system mouse cursor."""
        self.state = state
        theme = STATE_THEMES.get(state, STATE_THEMES["idle"])
        self.badge_lbl.config(
            text=theme["badge_text"],
            bg=theme["badge_bg"],
            fg=theme["badge_fg"]
        )
        if state == "idle":
            self.expand_frame.config(highlightbackground=BORDER_COLOR)
        elif state == "connecting":
            self.expand_frame.config(highlightbackground=HOVER_BORDER)
        elif state == "listening":
            self.expand_frame.config(highlightbackground=LISTENING_BORDER)
        elif state == "speaking":
            self.expand_frame.config(highlightbackground=SPEAKING_BORDER)

        # Synchronize OS-Wide Mouse Cursor with Nova Live state
        if state in ("listening", "speaking"):
            self.cursor_mgr.set_live_cursor(state)
        elif state in ("idle", "sleep", "connecting"):
            self.cursor_mgr.restore()

    def show_collapsed(self):
        """Switches to compact character face view."""
        self.is_expanded = False
        self.expand_frame.pack_forget()
        self.face_canvas.pack()
        self.root.geometry(f"{CANVAS_SIZE}x{CANVAS_SIZE}+{self.pos_x}+{self.pos_y}")

    def show_expanded(self):
        """Expands into full transcript bar."""
        self.is_expanded = True
        self.face_canvas.pack_forget()
        self.expand_frame.pack(fill="both", expand=True)

        w, h = 480, 50
        screen_w = self.root.winfo_screenwidth()
        if self.pos_x + w > screen_w - 20:
            adj_x = screen_w - w - 20
        else:
            adj_x = self.pos_x

        self.root.geometry(f"{w}x{h}+{adj_x}+{self.pos_y}")


def main():
    os.system("")  # Enable Windows ANSI escape codes
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    try:
        from run_live import print_banner
        print_banner()
    except Exception:
        pass

    root = tk.Tk()
    app = FloatingGhostWidget(root)

    # Signal check for clean Ctrl+C termination
    def check_signals():
        root.after(300, check_signals)

    root.after(300, check_signals)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        print("\n[WIDGET] Interrupted by Ctrl+C. Exiting cleanly...")
        try:
            app.stop_session()
        except Exception:
            pass
        try:
            root.destroy()
        except Exception:
            pass
        os._exit(0)


if __name__ == "__main__":
    main()
