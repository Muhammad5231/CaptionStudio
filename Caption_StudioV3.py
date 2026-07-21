import os
import sys
import math
import time
import queue
import textwrap
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from tkinter.font import families as tk_font_families
from tkinter.scrolledtext import ScrolledText

import numpy as np
import pysrt
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter, ImageTk

# ==============================================================================
# ARCHITECTURAL PROFILE SYSTEM STRUCTURES
# ==============================================================================

@dataclass
class VideoProfile:
    width: int = 1920
    height: int = 1080
    fps: int = 30
    bg_mode: str = "Green"  # Green, Blue, Black, White, Custom
    bg_custom_hex: str = "#00FF00"
    codec: str = "libx264"
    pix_fmt: str = "yuv420p"
    crf: int = 18
    preset: str = "medium"

    def get_rgba(self) -> Tuple[int, int, int, int]:
        modes = {
            "Green": (0, 255, 0, 255),
            "Blue": (0, 0, 255, 255),
            "Black": (0, 0, 0, 255),
            "White": (255, 255, 255, 255)
        }
        if self.bg_mode in modes:
            return modes[self.bg_mode]
        h = self.bg_custom_hex.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)
        except Exception:
            return (0, 255, 0, 255)

@dataclass
class TextStyleProfile:
    font_family: str = "Arial"
    font_size: int = 75
    bold: bool = True
    italic: bool = False
    underline: bool = False
    case_mode: str = "Uppercase"  # Normal, Uppercase, Lowercase, Sentence Case
    letter_spacing: int = 2
    line_spacing_px: int = 15
    text_color: str = "#FFFFFF"
    text_opacity: float = 1.0

    def get_text_rgba(self) -> Tuple[int, int, int, int]:
        h = self.text_color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.text_opacity))
        except Exception:
            return (255, 255, 255, int(255 * self.text_opacity))

@dataclass
class OutlineProfile:
    enabled: bool = True
    width: int = 8
    color: str = "#000000"
    opacity: float = 1.0

    def get_rgba(self) -> Tuple[int, int, int, int]:
        h = self.color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.opacity))
        except Exception:
            return (0, 0, 0, int(255 * self.opacity))

@dataclass
class ShadowProfile:
    enabled: bool = True
    offset_x: int = 8
    offset_y: int = 8
    blur: int = 2
    color: str = "#000000"
    opacity: float = 0.8

    def get_rgba(self) -> Tuple[int, int, int, int]:
        h = self.color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.opacity))
        except Exception:
            return (0, 0, 0, int(255 * self.opacity))

@dataclass
class GlowProfile:
    enabled: bool = False
    size: int = 12
    color: str = "#FFFF00"
    opacity: float = 0.7

    def get_rgba(self) -> Tuple[int, int, int, int]:
        h = self.color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.opacity))
        except Exception:
            return (255, 255, 0, int(255 * self.opacity))

@dataclass
class AnimationProfile:
    type_name: str = "Pop"  # None, Fade, Zoom, Pop, Bounce, Slide Left, Slide Right, Pulse, Shake, Typewriter
    speed_ms: int = 120

@dataclass
class LayoutProfile:
    anchor: str = "Bottom Center"
    custom_positioning: bool = False
    custom_x_pct: float = 0.5
    custom_y_pct: float = 0.82
    max_lines: int = 2
    max_width_pct: float = 0.85

@dataclass
class EffectsProfile:
    mode: str = "Standard"  # Standard, Gradient Gold, Gradient Silver, Neon, Rainbow, 3D
    intensity: float = 1.0

# ==============================================================================
# ENGINE PLUGINS & PLUG MANAGERS
# ==============================================================================

class FontManager:
    _cache: Dict[str, str] = {}

    @classmethod
    def scan_system_fonts(cls) -> List[str]:
        try:
            fonts = list(set(tk_font_families()))
            fonts.sort()
            priorities = ["Impact", "Arial", "Segoe UI", "Montserrat", "Poppins", "Roboto", "Anton", "Bebas Neue"]
            available = [f for f in priorities if f in fonts]
            remainder = [f for f in fonts if f not in priorities]
            return available + remainder
        except Exception:
            return ["Arial", "Courier New", "Georgia"]

    @classmethod
    def get_font_path(cls, family: str) -> str:
        if family in cls._cache: return cls._cache[family]
        search_paths = []
        if sys.platform.startswith("win"):
            search_paths.append(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"))
        elif sys.platform == "darwin":
            search_paths.extend(["/Library/Fonts", "/System/Library/Fonts/Supplemental"])
        else:
            search_paths.extend(["/usr/share/fonts/truetype", "/usr/local/share/fonts"])

        lookup_name = family.lower().replace(" ", "")
        for base_path in search_paths:
            if os.path.exists(base_path):
                for root, _, files in os.walk(base_path):
                    for f in files:
                        if f.lower().endswith((".ttf", ".otf")):
                            f_clean = os.path.splitext(f)[0].lower().replace("-", "").replace("_", "")
                            if lookup_name in f_clean:
                                path = os.path.join(root, f)
                                cls._cache[family] = path
                                return path
        if sys.platform.startswith("win"):
            return os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "impact.ttf")
        return ""


class StyleManager:
    """Central repository holding premium inbuilt system presets and custom user parameters maps."""
    _custom_presets: Dict[str, Dict[str, Any]] = {}
    
    _inbuilt_catalog: Dict[str, Dict[str, Any]] = {
        "Hyper Kinetic Beast": {
            "ts_font_family": "Impact", "ts_font_size": 85, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FFCC00", "ts_letter_spacing": 3, "out_enabled": True, "out_width": 10,
            "out_color": "#000000", "sh_enabled": True, "sh_offset_x": 8, "sh_offset_y": 8, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 12, "gl_color": "#FFFF00", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Hormozi Power Fuel": {
            "ts_font_family": "Impact", "ts_font_size": 80, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FFFFFF", "ts_letter_spacing": 1, "out_enabled": True, "out_width": 8,
            "out_color": "#000000", "sh_enabled": True, "sh_offset_x": 6, "sh_offset_y": 6, "sh_blur": 2,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 12, "gl_color": "#FFFF00", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Cyber Crimson Glow": {
            "ts_font_family": "Arial", "ts_font_size": 75, "ts_bold": True, "ts_case_mode": "Normal",
            "ts_text_color": "#FFFFFF", "ts_letter_spacing": 2, "out_enabled": False, "out_width": 0,
            "out_color": "#000000", "sh_enabled": False, "sh_offset_x": 0, "sh_offset_y": 0, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": True, "gl_size": 20, "gl_color": "#FF0055", "ep_mode": "Neon", "lp_anchor": "Bottom Center"
        },
        "Cinematic Clean Epic": {
            "ts_font_family": "Georgia", "ts_font_size": 65, "ts_bold": False, "ts_case_mode": "Normal",
            "ts_text_color": "#FFF9E6", "ts_letter_spacing": 0, "out_enabled": False, "out_width": 0,
            "out_color": "#000000", "sh_enabled": True, "sh_offset_x": 0, "sh_offset_y": 4, "sh_blur": 10,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 12, "gl_color": "#FFFF00", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Viral Luxury Amber": {
            "ts_font_family": "Impact", "ts_font_size": 80, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FFFFFF", "ts_letter_spacing": 2, "out_enabled": True, "out_width": 6,
            "out_color": "#000000", "sh_enabled": False, "sh_offset_x": 0, "sh_offset_y": 0, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 12, "gl_color": "#FFFF00", "ep_mode": "Gradient Gold", "lp_anchor": "Bottom Center"
        },
        "Minimalist Editorial": {
            "ts_font_family": "Segoe UI", "ts_font_size": 70, "ts_bold": True, "ts_case_mode": "Normal",
            "ts_text_color": "#FFFFFF", "ts_letter_spacing": 1, "out_enabled": True, "out_width": 3,
            "out_color": "#1C1C1E", "sh_enabled": True, "sh_offset_x": 0, "sh_offset_y": 3, "sh_blur": 6,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 12, "gl_color": "#FFFF00", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        }
    }

    @classmethod
    def get_all_presets_names(cls) -> List[str]:
        return list(cls._inbuilt_catalog.keys()) + list(cls._custom_presets.keys())

    @classmethod
    def apply(cls, name: str, ts: TextStyleProfile, out: OutlineProfile, 
              sh: ShadowProfile, gl: GlowProfile, ep: EffectsProfile, lp: LayoutProfile):
        data = cls._inbuilt_catalog.get(name) or cls._custom_presets.get(name)
        if not data: return
        
        ts.font_family = data["ts_font_family"]
        ts.font_size = data["ts_font_size"]
        ts.bold = data.get("ts_bold", True)
        ts.case_mode = data["ts_case_mode"]
        ts.text_color = data["ts_text_color"]
        ts.letter_spacing = data["ts_letter_spacing"]
        
        out.enabled = data["out_enabled"]
        out.width = data["out_width"]
        out.color = data["out_color"]
        
        sh.enabled = data["sh_enabled"]
        sh.offset_x = data["sh_offset_x"]
        sh.offset_y = data["sh_offset_y"]
        sh.blur = data["sh_blur"]
        sh.color = data.get("sh_color", "#000000")
        
        gl.enabled = data["gl_enabled"]
        gl.size = data.get("gl_size", 12)  # SAFE IMMUTABLE FALLBACK TO PREVENT KEYERRORS
        gl.color = data.get("gl_color", "#FFFF00")
        
        ep.mode = data["ep_mode"]
        lp.anchor = data["lp_anchor"]

    @classmethod
    def save_custom(cls, name: str, ts: TextStyleProfile, out: OutlineProfile, 
                    sh: ShadowProfile, gl: GlowProfile, ep: EffectsProfile, lp: LayoutProfile):
        cls._custom_presets[name] = {
            "ts_font_family": ts.font_family, "ts_font_size": ts.font_size, "ts_bold": ts.bold, "ts_case_mode": ts.case_mode,
            "ts_text_color": ts.text_color, "ts_letter_spacing": ts.letter_spacing, "out_enabled": out.enabled, "out_width": out.width,
            "out_color": out.color, "sh_enabled": sh.enabled, "sh_offset_x": sh.offset_x, "sh_offset_y": sh.offset_y, "sh_blur": sh.blur,
            "sh_color": sh.color, "gl_enabled": gl.enabled, "gl_size": gl.size, "gl_color": gl.color, "ep_mode": ep.mode, "lp_anchor": lp.anchor
        }


class AnimationManager:
    @staticmethod
    def get_animations() -> List[str]:
        return ["None", "Fade", "Zoom", "Pop", "Bounce", "Slide Left", "Slide Right", "Pulse", "Shake", "Typewriter"]

    @staticmethod
    def evaluate(anim_type: str, time_from_start_ms: float, time_to_end_ms: float, duration_ms: float, speed_ms: int) -> Dict[str, Any]:
        res = {"alpha_factor": 1.0, "scale_factor": 1.0, "offset_x": 0.0, "offset_y": 0.0, "char_visible_pct": 1.0}
        if anim_type == "None" or duration_ms <= 0: return res
        
        fade_in = min(float(speed_ms), duration_ms / 2.0)
        fade_out = min(float(speed_ms), duration_ms / 2.0)

        if time_from_start_ms < fade_in and fade_in > 0:
            t = time_from_start_ms / fade_in
            if anim_type == "Fade": res["alpha_factor"] = t
            elif anim_type == "Zoom": res["alpha_factor"] = t; res["scale_factor"] = 0.6 + (0.4 * t)
            elif anim_type == "Pop": res["scale_factor"] = 0.3 + 0.8 * math.sin(t * math.pi / 2)
            elif anim_type == "Bounce": res["offset_y"] = -120.0 * abs(math.cos(t * math.pi * 1.5)) * (1.0 - t)
            elif anim_type == "Slide Left": res["offset_x"] = -250.0 * (1.0 - t); res["alpha_factor"] = t
            elif anim_type == "Slide Right": res["offset_x"] = 250.0 * (1.0 - t); res["alpha_factor"] = t
            elif anim_type == "Typewriter": res["char_visible_pct"] = t
        elif time_to_end_ms < fade_out and fade_out > 0:
            t = time_to_end_ms / fade_out
            if anim_type in ["Fade", "Slide Left", "Slide Right"]: res["alpha_factor"] = t
            elif anim_type == "Zoom": res["scale_factor"] = 0.8 + (0.2 * t); res["alpha_factor"] = t
            elif anim_type == "Pop": res["scale_factor"] = t; res["alpha_factor"] = t
        
        if anim_type == "Pulse":
            c = (time_from_start_ms / 450.0) * math.pi
            res["scale_factor"] = 1.0 + 0.04 * math.sin(c)
        elif anim_type == "Shake" and time_from_start_ms < 350:
            c = (time_from_start_ms / 45.0) * math.pi
            res["offset_x"] = 6.0 * math.sin(c)
            
        return res


class EffectManager:
    @staticmethod
    def apply(base_img: Image.Image, mode: str) -> Image.Image:
        if mode == "Standard": return base_img
        w, h = base_img.size
        
        if mode in ["Gradient Gold", "Gradient Silver", "Rainbow"]:
            grad = Image.new("RGBA", (w, h))
            draw = ImageDraw.Draw(grad)
            for y in range(h):
                p = y / max(1, h)
                if mode == "Gradient Gold": r, g, b = int(255 - 65*p), int(215 - 75*p), int(15*p)
                elif mode == "Gradient Silver": v = int(245 - 90*p); r, g, b = v, v, v
                else:
                    freq = 3 * math.pi / h
                    r = int(math.sin(freq * y + 0) * 127 + 128)
                    g = int(math.sin(freq * y + 2) * 127 + 128)
                    b = int(math.sin(freq * y + 4) * 127 + 128)
                draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
            return Image.composite(grad, base_img, base_img)
        elif mode == "Neon":
            a = base_img.split()[3]
            glow = a.filter(ImageFilter.GaussianBlur(3))
            mask = Image.new("RGBA", (w, h), (255, 20, 147, 255))
            gl_img = Image.composite(mask, Image.new("RGBA", (w, h)), glow)
            return Image.alpha_composite(gl_img, base_img)
        elif mode == "3D":
            off = 5
            l_lay = base_img.transform((w, h), Image.Transform.AFFINE, (1, 0, off, 0, 1, 0))
            r_lay = base_img.transform((w, h), Image.Transform.AFFINE, (1, 0, -off, 0, 1, 0))
            cyan = Image.merge("RGBA", [Image.new("L", (w, h), 0), l_lay.split()[1], l_lay.split()[2], l_lay.split()[3]])
            red = Image.merge("RGBA", [r_lay.split()[0], Image.new("L", (w, h), 0), Image.new("L", (w, h), 0), r_lay.split()[3]])
            return Image.alpha_composite(Image.alpha_composite(cyan, red), base_img)
        return base_img


class PositionManager:
    @staticmethod
    def calculate(anchor: str, tw: int, th: int, sw: int, sh: int, 
                  custom: bool, cx: float, cy: float, ox: float, oy: float) -> Tuple[int, int]:
        if custom: return int((sw * cx) - (tw // 2) + ox), int((sh * cy) - (th // 2) + oy)
        mx, my = int(sw * 0.08), int(sh * 0.08)
        if "Left" in anchor: x = mx
        elif "Right" in anchor: x = sw - tw - mx
        else: x = (sw - tw) // 2
        
        if "Top" in anchor: y = my
        elif "Bottom" in anchor: y = sh - th - my
        else: y = (sh - th) // 2
        return int(x + ox), int(y + oy)

# ==============================================================================
# PIPELINE RENDER ENGINE WRAPPER WITH HARD CACHING
# ==============================================================================

class SubtitleRenderer:
    def __init__(self):
        self._font_cache: Dict[Tuple[str, int, bool, bool, bool], ImageFont.FreeTypeFont] = {}
        self._overlay_cache: Dict[Tuple[str, float, int], Tuple[Image.Image, int, int]] = {}

    def clear_caches(self):
        self._font_cache.clear()
        self._overlay_cache.clear()

    def get_font(self, family: str, size: int, bold: bool, italic: bool, underline: bool) -> ImageFont.FreeTypeFont:
        key = (family, size, bold, italic, underline)
        if key in self._font_cache: return self._font_cache[key]
        path = FontManager.get_font_path(family)
        try:
            f = ImageFont.truetype(path if path else "arial.ttf", size)
            self._font_cache[key] = f
            return f
        except Exception:
            return ImageFont.load_default()

    def _wrap(self, text: str, font: ImageFont.FreeTypeFont, max_w: int, max_lines: int) -> List[str]:
        words = text.split()
        lines = []
        curr = []
        for w in words:
            test = " ".join(curr + [w]) if curr else w
            if (font.getbbox(test)[2] - font.getbbox(test)[0]) <= max_w: curr.append(w)
            else:
                if curr: lines.append(" ".join(curr)); curr = [w]
                else: lines.append(w); curr = []
        if curr: lines.append(" ".join(curr))
        return lines[:max_lines]

    def render_text_overlay(self, text: str, ts: TextStyleProfile, out: OutlineProfile, 
                            anim: Dict[str, Any], ep: EffectsProfile) -> Tuple[Image.Image, int, int]:
        if ts.case_mode == "Uppercase": text = text.upper()
        elif ts.case_mode == "Lowercase": text = text.lower()
        elif ts.case_mode == "Sentence Case": text = ". ".join([s.strip().capitalize() for s in text.split(".") if s.strip()])
        
        if anim["char_visible_pct"] < 1.0:
            text = text[:int(len(text) * anim["char_visible_pct"])]

        ckey = (text, anim["alpha_factor"], hash(f"{ts.text_color}_{out.color}_{out.width}_{ep.mode}_{ts.letter_spacing}"))
        if ckey in self._overlay_cache: return self._overlay_cache[ckey]

        font = self.get_font(ts.font_family, ts.font_size, ts.bold, ts.italic, ts.underline)
        lines = text.split("\n")
        
        metrics = []
        total_w, total_h = 0, 0
        for l in lines:
            bbox = font.getbbox(l)
            lw = (bbox[2] - bbox[0]) + (len(l) * ts.letter_spacing)
            lh = (bbox[3] - bbox[1]) + ts.line_spacing_px
            metrics.append((lw, lh))
            if lw > total_w: total_w = lw
            total_h += lh

        pad = 60 + (out.width * 2)
        cw, ch = total_w + pad, total_h + pad
        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        f_rgba = (ts.get_text_rgba()[0], ts.get_text_rgba()[1], ts.get_text_rgba()[2], int(ts.get_text_rgba()[3] * anim["alpha_factor"]))
        o_rgba = (out.get_rgba()[0], out.get_rgba()[1], out.get_rgba()[2], int(out.get_rgba()[3] * anim["alpha_factor"]))

        curr_y = pad // 2
        for idx, l in enumerate(lines):
            lw, lh = metrics[idx]
            curr_x = (cw - lw) // 2
            
            draw.text((curr_x, curr_y), l, font=font, fill=f_rgba, 
                      stroke_width=out.width if out.enabled else 0, stroke_fill=o_rgba)
            if ts.underline:
                uy = curr_y + lh - ts.line_spacing_px + 2
                draw.line([(curr_x, uy), (curr_x + lw, uy)], fill=f_rgba, width=4)
            curr_y += lh

        overlay = EffectManager.apply(overlay, ep.mode)
        self._overlay_cache[ckey] = (overlay, cw, ch)
        return overlay, cw, ch

    def compose_full_frame(self, text: str, vp: VideoProfile, ts: TextStyleProfile, 
                           out: OutlineProfile, sh: ShadowProfile, gl: GlowProfile, 
                           ap: AnimationProfile, lp: LayoutProfile, ep: EffectsProfile, 
                           t_start_ms: float, t_end_ms: float, dur_ms: float) -> Image.Image:
        frame = Image.new("RGBA", (vp.width, vp.height), vp.get_rgba())
        if not text.strip(): return frame

        anim = AnimationManager.evaluate(ap.type_name, t_start_ms, t_end_ms, dur_ms, ap.speed_ms)
        font = self.get_font(ts.font_family, ts.font_size, ts.bold, ts.italic, ts.underline)
        
        max_pw = int(vp.width * lp.max_width_pct)
        wrapped = self._wrap(text, font, max_pw, lp.max_lines)
        w_text = "\n".join(wrapped)

        overlay, ow, oh = self.render_text_overlay(w_text, ts, out, anim, ep)
        
        sf = anim["scale_factor"]
        if sf != 1.0 and ow > 0 and oh > 0:
            nw, nh = max(1, int(ow * sf)), max(1, int(oh * sf))
            overlay = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
            ow, oh = nw, nh

        fx, fy = PositionManager.calculate(lp.anchor, ow, oh, vp.width, vp.height, 
                                           lp.custom_positioning, lp.custom_x_pct, lp.custom_y_pct, 
                                           anim["offset_x"], anim["offset_y"])

        comp = Image.new("RGBA", (vp.width, vp.height), (0, 0, 0, 0))

        if gl.enabled and anim["alpha_factor"] > 0:
            g_rgba = (gl.get_rgba()[0], gl.get_rgba()[1], gl.get_rgba()[2], int(gl.get_rgba()[3] * anim["alpha_factor"]))
            glow_mask = overlay.split()[3].filter(ImageFilter.GaussianBlur(gl.size))
            glow_sol = Image.new("RGBA", (ow, oh), g_rgba)
            glow_b = Image.composite(glow_sol, Image.new("RGBA", (ow, oh)), glow_mask)
            comp.paste(glow_b, (fx, fy), glow_b)

        if sh.enabled and anim["alpha_factor"] > 0:
            s_rgba = (sh.get_rgba()[0], sh.get_rgba()[1], sh.get_rgba()[2], int(sh.get_rgba()[3] * anim["alpha_factor"]))
            sh_mask = overlay.split()[3]
            if sh.blur > 0: sh_mask = sh_mask.filter(ImageFilter.GaussianBlur(sh.blur))
            sh_sol = Image.new("RGBA", (ow, oh), s_rgba)
            sh_b = Image.composite(sh_sol, Image.new("RGBA", (ow, oh)), sh_mask)
            comp.paste(sh_b, (fx + sh.offset_x, fy + sh.offset_y), sh_b)

        comp.paste(overlay, (fx, fy), overlay)
        return Image.alpha_composite(frame, comp)

# ==============================================================================
# PIPED STREAMING SUBPROCESS & WORKER TIMELINES
# ==============================================================================

class FFmpegStreamWriter:
    def __init__(self, path: str, vp: VideoProfile):
        self.path, self.vp, self.proc = path, vp, None

    def start(self):
        cmd = ["ffmpeg", "-y", "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
               "-s", f"{self.vp.width}x{self.vp.height}", "-r", str(self.vp.fps), "-i", "-",
               "-c:v", self.vp.codec, "-pix_fmt", self.vp.pix_fmt, "-preset", self.vp.preset, "-crf", str(self.vp.crf), self.path]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def write(self, img: Image.Image):
        if self.proc and self.proc.stdin: self.proc.stdin.write(img.convert("RGB").tobytes())

    def close(self) -> Optional[str]:
        if not self.proc: return None
        logs = None
        try:
            if self.proc.stdin: self.proc.stdin.close()
            _, stderr = self.proc.communicate(timeout=15)
            if self.proc.returncode != 0: logs = stderr.decode("utf-8", errors="ignore")
        except Exception as e: logs = str(e)
        finally:
            if self.proc: self.proc.kill(); self.proc = None
        return logs


class RenderWorker(threading.Thread):
    def __init__(self, srt: str, out: str, vp: VideoProfile, ts: TextStyleProfile, out_p: OutlineProfile,
                 sh: ShadowProfile, gl: GlowProfile, ap: AnimationProfile, lp: LayoutProfile, ep: EffectsProfile,
                 q: queue.Queue, cancel: threading.Event):
        super().__init__()
        self.srt, self.out, self.vp, self.ts, self.out_p, self.sh, self.gl, self.ap, self.lp, self.ep, self.q, self.cancel = srt, out, vp, ts, out_p, sh, gl, ap, lp, ep, q, cancel
        self.renderer = SubtitleRenderer()

    def run(self):
        writer = None
        base = os.path.splitext(os.path.basename(self.srt))[0]
        target = os.path.join(self.out, f"{base}_studio_output.mp4")
        try:
            self.q.put(("LOG", ("Parsing SRT structural layout records...", "INFO")))
            try: subs = pysrt.open(self.srt, encoding="utf-8")
            except Exception: subs = pysrt.open(self.srt, encoding="latin-1")
            
            if not subs:
                self.q.put(("ERROR", "The selected SRT script file holds no active track keys."))
                return

            self.q.put(("LOG", (f"Successfully loaded {len(subs)} subtitle records into workspace.", "SUCCESS")))
            writer = FFmpegStreamWriter(target, self.vp)
            writer.start()

            total_sec = (subs[-1].end.ordinal / 1000.0) + 1.0
            total_frames = math.ceil(total_sec * self.vp.fps)
            cursor = 0
            start_t = time.time()
            last_ui = 0.0

            for f in range(total_frames):
                if self.cancel.is_set(): break
                cm = (f / float(self.vp.fps)) * 1000.0
                while cursor < len(subs) and cm > subs[cursor].end.ordinal: cursor += 1
                
                txt, ts, te, d = "", 0.0, 0.0, 0.0
                if cursor < len(subs) and subs[cursor].start.ordinal <= cm <= subs[cursor].end.ordinal:
                    txt = subs[cursor].text
                    ts, te = subs[cursor].start.ordinal, subs[cursor].end.ordinal
                    d = te - ts

                f_img = self.renderer.compose_full_frame(txt, self.vp, self.ts, self.out_p, self.sh, self.gl, self.ap, self.lp, self.ep, cm - ts, te - cm, d)
                writer.write(f_img)

                now = time.time()
                if now - last_ui > 0.12 or f == total_frames - 1:
                    last_ui = now
                    el = now - start_t
                    fps = (f + 1) / el if el > 0 else 0.0
                    eta = (total_frames - (f + 1)) / fps if fps > 0 else 0.0
                    self.q.put(("PROGRESS", {"pct": ((f+1)/total_frames)*100, "f": f+1, "tf": total_frames, "speed": fps, "el": el, "eta": eta, "txt": txt}))

            errs = writer.close()
            self.renderer.clear_caches()
            if self.cancel.is_set():
                if os.path.exists(target): os.remove(target)
                self.q.put(("CANCELLED", "Operational queue aborted safely."))
            elif errs: self.q.put(("ERROR", f"FFmpeg error logged:\n{errs}"))
            else: self.q.put(("COMPLETE", target))
        except Exception as e:
            if writer: writer.close()
            self.q.put(("ERROR", f"Critical processing engine fault:\n{str(e)}"))

# ==============================================================================
# CANVA / CAPCUT HIGHER-LEVEL WORKSPACE STUDIO INTERFACE
# ==============================================================================

class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CaptionStudio Studio Suite Pro V3")
        # RESOLVED GEOMETRY SPECIFIER FORM TYPOS
        self.root.geometry("1280x860")
        self.root.minimum_size = (1180, 800)

        # Profiles State Binding Matrix
        self.vp, self.ts, self.out_p, self.sh, self.gl, self.ap, self.lp, self.ep = VideoProfile(), TextStyleProfile(), OutlineProfile(), ShadowProfile(), GlowProfile(), AnimationProfile(), LayoutProfile(), EffectsProfile()
        self.q, self.cancel, self.worker = queue.Queue(), threading.Event(), None
        self.preview_renderer = SubtitleRenderer()
        self.block_updates = False
        self.preset_buttons: Dict[str, tk.Button] = {}

        self._apply_theme_tokens()
        self._assemble_layout_grid()
        self._sync_profiles_into_ui()
        self.trigger_live_preview()

    def _apply_theme_tokens(self):
        self.c_bg = "#F6F8FA"
        self.c_card = "#FFFFFF"
        self.c_text = "#1F2328"
        self.c_muted = "#57606A"
        self.c_accent = "#0969DA"
        self.c_accent_l = "#DDF4FF"
        self.c_border = "#D0D7DE"

        self.root.configure(bg=self.c_bg)
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 10))
        s.configure("Card.TFrame", background=self.c_card, relief="flat")
        s.configure("TLabel", background=self.c_bg, foreground=self.c_text)
        s.configure("Card.TLabel", background=self.c_card, foreground=self.c_text)
        s.configure("Logo.TLabel", background=self.c_card, foreground=self.c_accent, font=("Segoe UI", 18, "bold"))
        s.configure("Section.TLabel", background=self.c_card, foreground=self.c_text, font=("Segoe UI", 11, "bold"))
        s.configure("Muted.TLabel", background=self.c_card, foreground=self.c_muted, font=("Segoe UI", 9))
        s.configure("TCheckbutton", background=self.c_card, foreground=self.c_text)
        s.configure("TCombobox", fieldbackground=self.c_bg, background=self.c_bg, arrowcolor=self.c_text)
        s.configure("TSpinbox", fieldbackground=self.c_bg, background=self.c_bg, arrowcolor=self.c_text)
        s.configure("Horizontal.TProgressbar", background=self.c_accent, troughcolor=self.c_bg, thickness=8)
        s.configure("TButton", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 9, "bold"), padding=5, borderwidth=1)
        s.map("TButton", background=[("active", self.c_accent_l)], foreground=[("active", self.c_accent)])
        s.configure("Action.TButton", background=self.c_accent, foreground="#FFFFFF", font=("Segoe UI", 10, "bold"), padding=8)
        s.map("Action.TButton", background=[("active", "#0550AE")])
        s.configure("Cancel.TButton", background="#CF222E", foreground="#FFFFFF", font=("Segoe UI", 10, "bold"), padding=8)
        s.map("Cancel.TButton", background=[("active", "#A40E1B")])

    def _assemble_layout_grid(self):
        paned = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=self.c_border, bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True)

        left_box = ttk.Frame(paned)
        left_box.pack(fill=tk.BOTH, expand=True)
        canv = tk.Canvas(left_box, bg=self.c_bg, highlightthickness=0)
        sb = ttk.Scrollbar(left_box, orient="vertical", command=canv.yview)
        self.scroll_f = ttk.Frame(canv, padding=12)
        
        self.scroll_f.bind("<Configure>", lambda e: canv.configure(scrollregion=canv.bbox("all")))
        canv.create_window((0, 0), window=self.scroll_f, anchor="nw")
        canv.configure(yscrollcommand=sb.set)
        canv.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        canv.bind("<Configure>", lambda e: canv.itemconfig(1, width=e.width))

        right_box = ttk.Frame(paned, padding=12)
        right_box.pack(fill=tk.BOTH, expand=True)

        paned.add(left_box, minsize=530, stretch="always")
        paned.add(right_box, minsize=590, stretch="always")

        self._build_header_logo_card()
        self._build_io_card()
        self._build_visual_presets_grid_card()  
        self._build_typography_card()
        self._build_layout_card()
        self._build_effects_card()
        self._build_shadow_glow_card()

        self._build_preview_panel(right_box)
        self._build_progress_panel(right_box)
        self._build_logger_panel(right_box)

    # --------------------------------------------------------------------------
    # SIDEBAR PANEL CARDS INTERFACE COMPONENTS
    # --------------------------------------------------------------------------

    def _build_header_logo_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=14)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="CaptionStudio ✨", style="Logo.TLabel").pack(anchor=tk.W)
        ttk.Label(card, text="Automated Professional Text Mapping Engine Core Pro V3", style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 0))

    def _build_io_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="1. Core IO Settings & Background Chroma", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))
        
        ttk.Label(card, text="Subtitle SRT:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ui_srt = tk.StringVar()
        ttk.Entry(card, textvariable=self.ui_srt).grid(row=1, column=1, sticky=tk.EW, padx=6)
        ttk.Button(card, text="Browse", command=self._cb_browse_srt).grid(row=1, column=2, sticky=tk.E)

        ttk.Label(card, text="Output Folder:", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ui_out = tk.StringVar()
        ttk.Entry(card, textvariable=self.ui_out).grid(row=2, column=1, sticky=tk.EW, padx=6)
        ttk.Button(card, text="Browse", command=self._cb_browse_out).grid(row=2, column=2, sticky=tk.E)

        ttk.Label(card, text="Chroma Key Color:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_bg_mode = ttk.Combobox(card, values=["Green", "Blue", "Black", "White", "Custom"], state="readonly", width=12)
        self.ui_bg_mode.grid(row=3, column=1, sticky=tk.W, padx=6)
        self.ui_bg_mode.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())
        tk.Button(card, text="Hex Picker", font=("Segoe UI", 8), command=self._cb_pick_bg).grid(row=3, column=2, sticky=tk.E)
        card.columnconfigure(1, weight=1)

    def _build_visual_presets_grid_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(card, text="2. Inbuilt Premium Visual Caption Styles Selector", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 2))
        ttk.Label(card, text="Select an inbuilt professional style card to instantly apply locks.", style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 10))

        self.presets_grid_frame = ttk.Frame(card, style="Card.TFrame")
        self.presets_grid_frame.pack(fill=tk.X, pady=(0, 12))
        
        self._refresh_visual_presets_grid()

        ttk.Label(card, text="Create & Save Custom Presets:", style="Muted.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor=tk.W, pady=(4, 2))
        f_save = ttk.Frame(card, style="Card.TFrame")
        f_save.pack(fill=tk.X)
        self.ui_custom_name = ttk.Entry(f_save)
        self.ui_custom_name.pack(side="left", fill=tk.X, expand=True, padx=(0, 6))
        ttk.Button(f_save, text="Save Current Style", command=self._cb_save_custom_style_profile).pack(side="right")

    def _refresh_visual_presets_grid(self):
        for btn in self.preset_buttons.values(): btn.destroy()
        self.preset_buttons.clear()

        names = StyleManager.get_all_presets_names()
        cols = 2
        for i, name in enumerate(names):
            r = i // cols
            c = i % cols
            
            btn = tk.Button(
                self.presets_grid_frame, 
                text=name, 
                font=("Segoe UI", 9, "bold"),
                bg=self.c_bg, 
                fg=self.c_text, 
                activebackground=self.c_accent_l,
                activeforeground=self.c_accent,
                relief="flat", 
                bd=1, 
                highlightbackground=self.c_border,
                padx=8, 
                pady=10,
                command=lambda n=name: self._cb_trigger_visual_style_select(n)
            )
            btn.grid(row=r, column=c, sticky=tk.EW, padx=4, pady=4)
            self.preset_buttons[name] = btn

        for c in range(cols): self.presets_grid_frame.columnconfigure(c, weight=1)

    def _build_typography_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="3. Fine-Tune Typography Customization", style="Section.TLabel").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 8))

        ttk.Label(card, text="Font Family:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ui_font = ttk.Combobox(card, values=FontManager.scan_system_fonts(), state="readonly")
        self.ui_font.grid(row=1, column=1, columnspan=3, sticky=tk.EW, pady=4, padx=(4, 0))
        self.ui_font.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Size (px):", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ui_size = ttk.Spinbox(card, from_=10, to=400, width=6, command=lambda: self._read_ui_to_profiles())
        self.ui_size.grid(row=2, column=1, sticky=tk.W, pady=4, padx=4)
        self.ui_size.bind("<KeyRelease>", lambda e: self._read_ui_to_profiles())

        self.ui_bold = tk.BooleanVar()
        ttk.Checkbutton(card, text="Bold", variable=self.ui_bold, command=lambda: self._read_ui_to_profiles()).grid(row=2, column=2, sticky=tk.W)
        self.ui_italic = tk.BooleanVar()
        ttk.Checkbutton(card, text="Italic", variable=self.ui_italic, command=lambda: self._read_ui_to_profiles()).grid(row=2, column=3, sticky=tk.W)
        self.ui_under = tk.BooleanVar()
        ttk.Checkbutton(card, text="Underline", variable=self.ui_under, command=lambda: self._read_ui_to_profiles()).grid(row=3, column=2, sticky=tk.W)

        ttk.Label(card, text="Text Case:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_case = ttk.Combobox(card, values=["Normal", "Uppercase", "Lowercase", "Sentence Case"], state="readonly", width=12)
        self.ui_case.grid(row=3, column=1, sticky=tk.W, pady=4, padx=4)
        self.ui_case.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Letter Spc:", style="Card.TLabel").grid(row=4, column=0, sticky=tk.W, pady=4)
        self.ui_let_spc = ttk.Scale(card, from_=-5, to=40, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_let_spc.grid(row=4, column=1, columnspan=3, sticky=tk.EW, pady=4, padx=(4, 0))

        ttk.Label(card, text="Line Spc:", style="Card.TLabel").grid(row=5, column=0, sticky=tk.W, pady=4)
        self.ui_line_spc = ttk.Scale(card, from_=0, to=120, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_line_spc.grid(row=5, column=1, columnspan=3, sticky=tk.EW, pady=4, padx=(4, 0))

        ttk.Label(card, text="Text Face:", style="Card.TLabel").grid(row=6, column=0, sticky=tk.W, pady=4)
        tk.Button(card, text="Pick Text Color", font=("Segoe UI", 9), command=self._cb_pick_text).grid(row=6, column=1, sticky=tk.W, pady=4, padx=4)

        ttk.Label(card, text="Strokes / Outline:", style="Card.TLabel").grid(row=7, column=0, sticky=tk.W, pady=4)
        self.ui_out_on = tk.BooleanVar()
        ttk.Checkbutton(card, text="Enable Outline", variable=self.ui_out_on, command=lambda: self._read_ui_to_profiles()).grid(row=7, column=1, sticky=tk.W)
        tk.Button(card, text="Pick Stroke Color", font=("Segoe UI", 9), command=self._cb_pick_out).grid(row=7, column=2, sticky=tk.W)

        ttk.Label(card, text="Stroke Thickness:", style="Card.TLabel").grid(row=8, column=0, sticky=tk.W, pady=4)
        self.ui_out_w = ttk.Scale(card, from_=0, to=30, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_out_w.grid(row=8, column=1, columnspan=3, sticky=tk.EW, pady=4, padx=(4, 0))
        card.columnconfigure(1, weight=1)

    def _build_layout_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="4. Layout Metrics & Screen Anchors", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))

        ttk.Label(card, text="Screen Anchor:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        anchors = ["Top Left", "Top Center", "Top Right", "Center", "Bottom Left", "Bottom Center", "Bottom Right"]
        self.ui_anchor = ttk.Combobox(card, values=anchors, state="readonly")
        self.ui_anchor.grid(row=1, column=1, columnspan=2, sticky=tk.EW, pady=4, padx=4)
        self.ui_anchor.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        self.ui_cust_pos = tk.BooleanVar()
        ttk.Checkbutton(card, text="Use Custom Matrix Percentage Offsets (X / Y)", variable=self.ui_cust_pos, command=self._cb_toggle_pos_mode).grid(row=2, column=0, columnspan=3, sticky=tk.W, pady=6)

        ttk.Label(card, text="Custom X (%):", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_pos_x = ttk.Scale(card, from_=0, to=100, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_pos_x.grid(row=3, column=1, columnspan=2, sticky=tk.EW, pady=4, padx=4)

        ttk.Label(card, text="Custom Y (%):", style="Card.TLabel").grid(row=4, column=0, sticky=tk.W, pady=4)
        self.ui_pos_y = ttk.Scale(card, from_=0, to=100, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_pos_y.grid(row=4, column=1, columnspan=2, sticky=tk.EW, pady=4, padx=4)

        ttk.Label(card, text="Max Wrap Lines:", style="Card.TLabel").grid(row=5, column=0, sticky=tk.W, pady=4)
        self.ui_max_lines = ttk.Spinbox(card, from_=1, to=4, width=5, command=lambda: self._read_ui_to_profiles())
        self.ui_max_lines.grid(row=5, column=1, sticky=tk.W, pady=4, padx=4)
        self.ui_max_lines.bind("<KeyRelease>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Max Bounds W (%):", style="Card.TLabel").grid(row=6, column=0, sticky=tk.W, pady=4)
        self.ui_max_width = ttk.Scale(card, from_=20, to=95, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_max_width.grid(row=6, column=1, columnspan=2, sticky=tk.EW, pady=4, padx=4)
        card.columnconfigure(1, weight=1)

    def _build_effects_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="5. Creative Effects & Kinetic Animations", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(card, text="Special Effect Mode:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ui_fx = ttk.Combobox(card, values=["Standard", "Gradient Gold", "Gradient Silver", "Neon", "Rainbow", "3D"], state="readonly")
        self.ui_fx.grid(row=1, column=1, sticky=tk.EW, pady=4, padx=4)
        self.ui_fx.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Kinetic Animation:", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ui_anim = ttk.Combobox(card, values=AnimationManager.get_animations(), state="readonly")
        self.ui_anim.grid(row=2, column=1, sticky=tk.EW, pady=4, padx=4)
        self.ui_anim.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Transition Speed (ms):", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_anim_speed = ttk.Spinbox(card, from_=50, to=1500, increment=50, width=8, command=lambda: self._read_ui_to_profiles())
        self.ui_anim_speed.grid(row=3, column=1, sticky=tk.W, pady=4, padx=4)
        self.ui_anim_speed.bind("<KeyRelease>", lambda e: self._read_ui_to_profiles())
        card.columnconfigure(1, weight=1)

    def _build_shadow_glow_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(card, text="6. High Impact Shadows & Radiance Glows", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))
        self.ui_sh_on = tk.BooleanVar()
        ttk.Checkbutton(card, text="Enable Drop Shadows Layer", variable=self.ui_sh_on, command=lambda: self._read_ui_to_profiles()).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Label(card, text="Offsets (X/Y):", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=2)
        f = ttk.Frame(card, style="Card.TFrame")
        f.grid(row=2, column=1, sticky=tk.W)
        self.ui_sh_ox = ttk.Spinbox(f, from_=-40, to=40, width=4, command=lambda: self._read_ui_to_profiles())
        self.ui_sh_ox.pack(side="left", padx=2)
        self.ui_sh_oy = ttk.Spinbox(f, from_=-40, to=40, width=4, command=lambda: self._read_ui_to_profiles())
        self.ui_sh_oy.pack(side="left", padx=2)
        
        ttk.Label(card, text="Blur Radius Softness:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.ui_sh_blur = ttk.Scale(card, from_=0, to=25, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_sh_blur.grid(row=3, column=1, sticky=tk.EW, padx=4)
        tk.Button(card, text="Shadow Color Swatch", font=("Segoe UI", 8), command=self._cb_pick_sh).grid(row=4, column=1, sticky=tk.W, padx=4)

        ttk.Label(card, text="Ambient Radiance Blur Filter:", style="Section.TLabel").grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(10, 6))
        self.ui_gl_on = tk.BooleanVar()
        ttk.Checkbutton(card, text="Enable Glow Outlines", variable=self.ui_gl_on, command=lambda: self._read_ui_to_profiles()).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Label(card, text="Glow Radius Size:", style="Card.TLabel").grid(row=7, column=0, sticky=tk.W, pady=2)
        self.ui_gl_size = ttk.Scale(card, from_=2, to=50, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_gl_size.grid(row=7, column=1, sticky=tk.EW, padx=4)
        tk.Button(card, text="Glow Tint Color Picker", font=("Segoe UI", 8), command=self._cb_pick_gl).grid(row=8, column=1, sticky=tk.W, padx=4)
        card.columnconfigure(1, weight=1)

    # --------------------------------------------------------------------------
    # RIGHT COLUMN WORKSPACE VIEWPORT GENERATIONS BLOCKS
    # --------------------------------------------------------------------------

    def _build_preview_panel(self, parent: ttk.Frame):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        ttk.Label(card, text="Pixel-Accurate Live Style Workspace Viewport", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 4))
        
        f = ttk.Frame(card, style="Card.TFrame")
        f.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(f, text="Custom Text Simulator Layer:", style="Card.TLabel").pack(side="left", padx=(0, 6))
        self.ui_preview_txt = ttk.Entry(f)
        self.ui_preview_txt.pack(side="left", fill=tk.X, expand=True)
        self.ui_preview_txt.insert(0, "CaptionStudio")
        self.ui_preview_txt.bind("<KeyRelease>", lambda e: self.trigger_live_preview())

        self.view_canvas = tk.Canvas(card, bg="#E5E5EA", highlightthickness=1, highlightbackground=self.c_border)
        self.view_canvas.pack(fill=tk.BOTH, expand=True)
        self.view_canvas.bind("<Configure>", lambda e: self.trigger_live_preview())

    def _build_progress_panel(self, parent: ttk.Frame):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        
        fb = ttk.Frame(card, style="Card.TFrame")
        fb.pack(fill=tk.X, pady=(0, 8))
        self.btn_run = ttk.Button(fb, text="Start Video Compilation Engine", style="Action.TButton", command=self._cb_start_compilation)
        self.btn_run.pack(side="left", ipadx=10)
        self.btn_abort = ttk.Button(fb, text="Abort Processing", style="Cancel.TButton", command=self._cb_abort_compilation)
        self.btn_abort.pack(side="left", padx=10, ipadx=10)
        self.btn_abort.configure(state=tk.DISABLED)

        self.ui_progress = ttk.Progressbar(card, orient="horizontal", mode="determinate", style="Horizontal.TProgressbar")
        self.ui_progress.pack(fill=tk.X, pady=(0, 4))

        fm = ttk.Frame(card, style="Card.TFrame")
        fm.pack(fill=tk.X)
        self.lbl_met_pct = ttk.Label(fm, text="Progress: 0.0%", font=("Segoe UI", 9, "bold"))
        self.lbl_met_pct.grid(row=0, column=0, sticky=tk.W, padx=(0, 15))
        self.lbl_met_frames = ttk.Label(fm, text="Frames: 0/0", style="Muted.TLabel")
        self.lbl_met_frames.grid(row=0, column=1, sticky=tk.W, padx=15)
        self.lbl_met_speed = ttk.Label(fm, text="Speed: 0.0 FPS", style="Muted.TLabel")
        self.lbl_met_speed.grid(row=0, column=2, sticky=tk.W, padx=15)
        self.lbl_met_eta = ttk.Label(fm, text="ETA: --:--", style="Muted.TLabel")
        self.lbl_met_eta.grid(row=0, column=3, sticky=tk.W, padx=15)
        self.lbl_met_txt = ttk.Label(card, text="Active Record Subtitle Sequence: [Idle Engine Pipeline Target]", style="Muted.TLabel", font=("Segoe UI", 9, "italic"))
        self.lbl_met_txt.pack(anchor=tk.W, pady=(4, 0))

    def _build_logger_panel(self, parent: ttk.Frame):
        card = ttk.Frame(parent, style="Card.TFrame", padding=10)
        card.pack(fill=tk.X)
        self.log_widget = ScrolledText(card, bg="#FFFFFF", fg=self.c_text, font=("Consolas", 9), height=7, bd=0, highlightthickness=1, highlightbackground=self.c_border)
        self.log_widget.pack(fill=tk.X)
        self.log_widget.configure(state=tk.DISABLED)

    # --------------------------------------------------------------------------
    # ENGINE VALUE SYNCHRONIZATIONS & SELECTION PACK BINDINGS
    # --------------------------------------------------------------------------

    def _sync_profiles_into_ui(self):
        self.block_updates = True
        self.ui_bg_mode.set(self.vp.bg_mode)
        self.ui_font.set(self.ts.font_family)
        
        self.ui_size.set(self.ts.font_size)
        self.ui_bold.set(self.ts.bold)
        self.ui_italic.set(self.ts.italic)
        self.ui_under.set(self.ts.underline)
        self.ui_case.set(self.ts.case_mode)
        self.ui_let_spc.set(self.ts.letter_spacing)
        self.ui_line_spc.set(self.ts.line_spacing_px)
        self.ui_out_on.set(self.out_p.enabled)
        self.ui_out_w.set(self.out_p.width)
        self.ui_anchor.set(self.lp.anchor)
        self.ui_cust_pos.set(self.lp.custom_positioning)
        self.ui_pos_x.set(int(self.lp.custom_x_pct * 100))
        self.ui_pos_y.set(int(self.lp.custom_y_pct * 100))
        self.ui_max_lines.set(self.lp.max_lines)
        self.ui_max_width.set(int(self.lp.max_width_pct * 100))
        self.ui_fx.set(self.ep.mode)
        self.ui_anim.set(self.ap.type_name)
        self.ui_anim_speed.set(self.ap.speed_ms)
        self.ui_sh_on.set(self.sh.enabled)
        self.ui_sh_ox.set(self.sh.offset_x)
        self.ui_sh_oy.set(self.sh.offset_y)
        self.ui_sh_blur.set(self.sh.blur)
        self.ui_gl_on.set(self.gl.enabled)
        self.ui_gl_size.set(self.gl.size)
        self._cb_toggle_pos_mode()
        self.block_updates = False

    def _read_ui_to_profiles(self):
        if self.block_updates: return
        self.vp.bg_mode = self.ui_bg_mode.get()
        self.ts.font_family = self.ui_font.get()
        try: self.ts.font_size = int(self.ui_size.get())
        except Exception: pass
        self.ts.bold = self.ui_bold.get()
        self.ts.italic = self.ui_italic.get()
        self.ts.underline = self.ui_under.get()
        self.ts.case_mode = self.ui_case.get()
        self.ts.letter_spacing = int(float(self.ui_let_spc.get()))
        self.ts.line_spacing_px = int(float(self.ui_line_spc.get()))
        self.out_p.enabled = self.ui_out_on.get()
        self.out_p.width = int(float(self.ui_out_w.get()))
        self.lp.anchor = self.ui_anchor.get()
        self.lp.custom_positioning = self.ui_cust_pos.get()
        self.lp.custom_x_pct = float(self.ui_pos_x.get()) / 100.0
        self.lp.custom_y_pct = float(self.ui_pos_y.get()) / 100.0
        try: self.lp.max_lines = int(self.ui_max_lines.get())
        except Exception: pass
        self.lp.max_width_pct = float(self.ui_max_width.get()) / 100.0
        self.ep.mode = self.ui_fx.get()
        self.ap.type_name = self.ui_anim.get()
        try: self.ap.speed_ms = int(self.ui_anim_speed.get())
        except Exception: pass
        self.sh.enabled = self.ui_sh_on.get()
        try:
            self.sh.offset_x = int(self.ui_sh_ox.get())
            self.sh.offset_y = int(self.ui_sh_oy.get())
        except Exception: pass
        self.sh.blur = int(float(self.ui_sh_blur.get()))
        self.gl.enabled = self.ui_gl_on.get()
        self.gl.size = int(float(self.ui_gl_size.get()))
        
        self.trigger_live_preview()

    def _cb_trigger_visual_style_select(self, name: str):
        StyleManager.apply(name, self.ts, self.out_p, self.sh, self.gl, self.ep, self.lp)
        self.append_log(f"Visual Preset Template Card selected and applied successfully: '{name}'", "SUCCESS")
        
        for b_name, b_obj in self.preset_buttons.items():
            if b_name == name: b_obj.configure(bg=self.c_accent_l, fg=self.c_accent, highlightbackground=self.c_accent)
            else: b_obj.configure(bg=self.c_bg, fg=self.c_text, highlightbackground=self.c_border)
            
        self._sync_profiles_into_ui()
        self.trigger_live_preview()

    def _cb_save_custom_style_profile(self):
        name = self.ui_custom_name.get().strip()
        if not name:
            messagebox.showwarning("Name Required", "Please enter a valid unique name label tag to save your custom caption style.")
            return
        if name in StyleManager.get_all_presets_names():
            messagebox.showwarning("Duplicate Profile", "A custom or built-in profile card configuration using this identical key name exists.")
            return

        self._read_ui_to_profiles()
        StyleManager.save_custom(name, self.ts, self.out_p, self.sh, self.gl, self.ep, self.lp)
        self.append_log(f"Custom Style Blueprint profile stored successfully: '{name}'", "SUCCESS")
        
        self.ui_custom_name.delete(0, tk.END)
        self._refresh_visual_presets_grid()
        self._cb_trigger_visual_style_select(name)

    def _cb_toggle_pos_mode(self):
        st = tk.NORMAL if self.ui_cust_pos.get() else tk.DISABLED
        self.ui_pos_x.configure(state=st)
        self.ui_pos_y.configure(state=st)
        if not self.block_updates: self._read_ui_to_profiles()

    def _cb_browse_srt(self):
        f = filedialog.askopenfilename(filetypes=[("Subtitle Track Script", "*.srt")])
        if f: self.ui_srt.set(f); self.append_log(f"Target timeline data script set to: {f}", "INFO")

    def _cb_browse_out(self):
        d = filedialog.askdirectory()
        if d: self.ui_out.set(d); self.append_log(f"Output storage folder link set to: {d}", "INFO")

    def _cb_pick_bg(self):
        c = colorchooser.askcolor(initialcolor=self.vp.bg_custom_hex)
        if c[1]: self.vp.bg_custom_hex = c[1]; self.ui_bg_mode.set("Custom"); self._read_ui_to_profiles()

    def _cb_pick_text(self):
        c = colorchooser.askcolor(initialcolor=self.ts.text_color)
        if c[1]: self.ts.text_color = c[1]; self._read_ui_to_profiles()

    def _cb_pick_out(self):
        c = colorchooser.askcolor(initialcolor=self.out_p.color)
        if c[1]: self.out_p.color = c[1]; self._read_ui_to_profiles()

    def _cb_pick_sh(self):
        c = colorchooser.askcolor(initialcolor=self.sh.color)
        if c[1]: self.sh.color = c[1]; self._read_ui_to_profiles()

    def _cb_pick_gl(self):
        c = colorchooser.askcolor(initialcolor=self.gl.color)
        if c[1]: self.gl.color = c[1]; self._read_ui_to_profiles()

    # --------------------------------------------------------------------------
    # HIGH-FIDELITY VIEWPORT PREVIEW ENGINE COMPUTATION MODULE
    # --------------------------------------------------------------------------

    def trigger_live_preview(self):
        text = self.ui_preview_txt.get()
        cw = self.view_canvas.winfo_width()
        ch = self.view_canvas.winfo_height()
        if cw < 20 or ch < 20: return

        ratio = cw / 1920.0
        sc_size = max(8, int(self.ts.font_size * ratio))
        sc_out_w = max(0, int(self.out_p.width * ratio))
        sc_line_spc = max(0, int(self.ts.line_spacing_px * ratio))
        sc_let_spc = max(-2, int(self.ts.letter_spacing * ratio))
        sc_sh_ox = int(self.sh.offset_x * ratio)
        sc_sh_oy = int(self.sh.offset_y * ratio)
        sc_sh_bl = int(self.sh.blur * ratio)
        sc_gl_sz = int(self.gl.size * ratio)

        sim_vp = VideoProfile(width=cw, height=ch, bg_mode=self.vp.bg_mode, bg_custom_hex=self.vp.bg_custom_hex)
        sim_ts = TextStyleProfile(font_family=self.ts.font_family, font_size=sc_size, bold=self.ts.bold, italic=self.ts.italic, underline=self.ts.underline, case_mode=self.ts.case_mode, letter_spacing=sc_let_spc, line_spacing_px=sc_line_spc, text_color=self.ts.text_color)
        sim_out = OutlineProfile(enabled=self.out_p.enabled, width=sc_out_w, color=self.out_p.color)
        sim_sh = ShadowProfile(enabled=self.sh.enabled, offset_x=sc_sh_ox, offset_y=sc_sh_oy, blur=sc_sh_bl, color=self.sh.color)
        sim_gl = GlowProfile(enabled=self.gl.enabled, size=sc_gl_sz, color=self.gl.color)
        sim_ap = AnimationProfile(type_name="None")

        p_img = self.preview_renderer.compose_full_frame(text, sim_vp, sim_ts, sim_out, sim_sh, sim_gl, sim_ap, self.lp, self.ep, 500, 500, 1000)
        
        self.tk_photo_reference = ImageTk.PhotoImage(p_img)
        self.view_canvas.delete("all")
        self.view_canvas.create_image(0, 0, anchor="nw", image=self.tk_photo_reference)

    # --------------------------------------------------------------------------
    # PIPELINE EXECUTIONS CONTROL THREAD QUEUE DRIVERS
    # --------------------------------------------------------------------------

    def append_log(self, text: str, mode: str = "INFO"):
        stamp = time.strftime("%H:%M:%S")
        colors = {"INFO": "#1F2328", "SUCCESS": "#1A7F37", "WARNING": "#9A6700", "ERROR": "#D1242F"}
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, f"[{stamp}] [{mode}] {text}\n")
        idx_s = self.log_widget.index("end-2c linestart")
        idx_e = self.log_widget.index("end-1c")
        tname = f"tag_{time.time()}"
        self.log_widget.tag_add(tname, idx_s, idx_e)
        self.log_widget.tag_config(tname, foreground=colors.get(mode, "#1F2328"))
        self.log_widget.configure(state=tk.DISABLED)
        self.log_widget.see(tk.END)

    def _cb_abort_compilation(self):
        if self.worker and self.worker.is_alive():
            self.cancel.set()
            self.btn_abort.configure(state=tk.DISABLED)

    def _cb_start_compilation(self):
        s, o = self.ui_srt.get().strip(), self.ui_out.get().strip()
        if not s or not os.path.exists(s) or not o or not os.path.isdir(o):
            messagebox.showerror("Path Validation Error", "Please verify your active input SRT path file and target output directory folder.")
            return

        self.btn_run.configure(state=tk.DISABLED)
        self.btn_abort.configure(state=tk.NORMAL)
        self.ui_progress["value"] = 0
        self.cancel.clear()

        self.worker = RenderWorker(s, o, self.vp, self.ts, self.out_p, self.sh, self.gl, self.ap, self.lp, self.ep, self.q, self.cancel)
        self.worker.start()
        self.root.after(100, self._poll_queue)

    def _poll_queue(self):
        try:
            while True:
                m, data = self.q.get_nowait()
                if m == "LOG": self.append_log(data[0], data[1])
                elif m == "PROGRESS":
                    self.ui_progress["value"] = data["pct"]
                    self.lbl_met_pct.configure(text=f"Progress: {data['pct']:.1f}%")
                    self.lbl_met_frames.configure(text=f"Frames: {data['f']}/{data['tf']}")
                    self.lbl_met_speed.configure(text=f"Speed: {data['speed']:.1f} FPS")
                    es, et = int(data["el"]), int(data["eta"])
                    self.lbl_met_eta.configure(text=f"Elapsed: {es//60:02d}:{es%60:02d} | ETA: {et//60:02d}:{et%60:02d}")
                    self.lbl_met_txt.configure(text=f"Tracking Frame Subtitle: {textwrap.shorten(data['txt'], 60)}")
                elif m == "COMPLETE":
                    messagebox.showinfo("Success", f"Video asset compilation completed cleanly without error frames!\n\nSaved location:\n{data}")
                    self._reset_dashboard()
                    return
                elif m == "CANCELLED":
                    messagebox.showwarning("Cancelled", "Video render compilation processing abandoned.")
                    self._reset_dashboard()
                    return
                elif m == "ERROR":
                    messagebox.showerror("Critical Core Fault", data)
                    self._reset_dashboard()
                    return
                self.q.task_done()
        except queue.Empty: pass
        if self.worker and self.worker.is_alive(): self.root.after(100, self._poll_queue)
        else: self._reset_dashboard()

    def _reset_dashboard(self):
        self.btn_run.configure(state=tk.NORMAL)
        self.btn_abort.configure(state=tk.DISABLED)
        self.lbl_met_txt.configure(text="Active Record Subtitle Sequence: [Idle Engine Pipeline Target]")

# ==============================================================================
# ENTRY CORE EXECUTIONS DRIVER HOOK POINT
# ==============================================================================

if __name__ == "__main__":
    main_root = tk.Tk()
    app = MainWindow(main_root)
    main_root.mainloop()