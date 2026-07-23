import os
import sys
import math
import time
import json
import queue
import base64
import textwrap
import subprocess
import threading
from io import BytesIO
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from tkinter.scrolledtext import ScrolledText

import numpy as np
import pysrt
from PIL import Image, ImageDraw, ImageFont, ImageChops, ImageFilter, ImageTk

# Windows Font Registry import with graceful fallback
if sys.platform.startswith("win"):
    import winreg
else:
    winreg = None


# ==============================================================================
# 1. ACCURATE WORD BOUNDING BOX ENGINE & DATA STRUCTURES
# ==============================================================================

@dataclass
class Word:
    word: str
    start_ms: float
    end_ms: float
    index: int = 0
    
    # Accurate Metrics & Positions
    width: float = 0.0
    height: float = 0.0
    ascent: float = 0.0
    descent: float = 0.0
    bbox_left: float = 0.0
    bbox_top: float = 0.0
    bbox_right: float = 0.0
    bbox_bottom: float = 0.0
    
    pos_x: float = 0.0        # Relative X origin on caption line
    pos_y: float = 0.0        # Relative baseline Y on caption line
    center_x: float = 0.0     # Absolute word center X
    center_y: float = 0.0     # Absolute word center Y
    
    scale: float = 1.0
    rotation: float = 0.0
    opacity: float = 1.0
    animation_state: str = "None"
    effect_state: str = "None"
    highlight_state: bool = False

@dataclass
class CaptionGroup:
    start_ms: float
    end_ms: float
    text: str
    words: List[Word] = field(default_factory=list)
    lines: List[List[Word]] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0

@dataclass
class GroupingProfile:
    preferred_words_per_line: int = 3
    max_lines: int = 2
    screen_safe_margin: int = 80
    enable_safe_area: bool = True

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
    font_family: str = "Impact"
    font_size: int = 80
    bold: bool = True
    italic: bool = False
    underline: bool = False
    case_mode: str = "Uppercase"  # Normal, Uppercase, Lowercase, Sentence Case
    letter_spacing: int = 2
    line_spacing_px: int = 15
    text_color: str = "#FFCC00"
    text_opacity: float = 1.0
    gradient_secondary_color: str = "#FF5500"
    use_gradient_fill: bool = False

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
    double_outline: bool = False
    outer_width: int = 16
    outer_color: str = "#FF0000"

    def get_rgba(self) -> Tuple[int, int, int, int]:
        h = self.color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.opacity))
        except Exception:
            return (0, 0, 0, int(255 * self.opacity))

    def get_outer_rgba(self) -> Tuple[int, int, int, int]:
        h = self.outer_color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.opacity))
        except Exception:
            return (255, 0, 0, int(255 * self.opacity))

@dataclass
class ShadowProfile:
    enabled: bool = True
    offset_x: int = 8
    offset_y: int = 8
    blur: int = 4
    color: str = "#000000"
    opacity: float = 0.8
    style: str = "Soft Shadow"

    def get_rgba(self) -> Tuple[int, int, int, int]:
        h = self.color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.opacity))
        except Exception:
            return (0, 0, 0, int(255 * self.opacity))

@dataclass
class GlowProfile:
    enabled: bool = False
    size: int = 14
    color: str = "#FFFF00"
    opacity: float = 0.8
    inner_glow: bool = False

    def get_rgba(self) -> Tuple[int, int, int, int]:
        h = self.color.lstrip('#')
        try:
            return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * self.opacity))
        except Exception:
            return (255, 255, 0, int(255 * self.opacity))

@dataclass
class AnimationProfile:
    type_name: str = "Pop"
    entry_anim: str = "Pop"
    loop_anim: str = "None"
    exit_anim: str = "Fade"
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
    mode: str = "Standard"
    intensity: float = 1.0

@dataclass
class WordHighlightProfile:
    enabled: bool = True
    mode: str = "Background Box"  # Background Box, Scale & Color, Color Highlight, Rounded Rectangle, Underline, Glow
    params: Dict[str, Any] = field(default_factory=dict)

    def get_param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)

@dataclass
class ActiveWordAnimationProfile:
    anim_type: str = "Bounce"  # Bounce, Pop, Scale, Rotate, Shake, Swing, Jelly, Rubber, Wave, Pulse
    params: Dict[str, Any] = field(default_factory=dict)

    def get_param(self, key: str, default: Any = None) -> Any:
        return self.params.get(key, default)


# ==============================================================================
# GENERIC PROPERTY SYSTEM SPECIFICATIONS & REGISTRY (TIMING SPECS STRIPPED)
# ==============================================================================

@dataclass
class ParamSpec:
    key: str
    label: str
    type: str  # "float", "int", "bool", "color", "combo"
    default: Any
    min_val: float = 0.0
    max_val: float = 100.0
    step: float = 1.0
    options: List[str] = field(default_factory=list)
    category: str = "General"


HIGHLIGHT_MODE_SPECS: Dict[str, List[ParamSpec]] = {
    "Background Box": [
        ParamSpec("bg_enable", "Enable Fill", "bool", True, category="Appearance"),
        ParamSpec("bg_color", "Background Color", "color", "#FF0055", category="Appearance"),
        ParamSpec("bg_opacity", "Opacity", "float", 0.95, 0.0, 1.0, 0.05, category="Appearance"),
        ParamSpec("corner_radius", "Corner Radius", "float", 12.0, 0.0, 50.0, 1.0, category="Appearance"),
        
        ParamSpec("pad_left", "Padding Left", "float", 16.0, 0.0, 60.0, 1.0, category="Padding"),
        ParamSpec("pad_right", "Padding Right", "float", 16.0, 0.0, 60.0, 1.0, category="Padding"),
        ParamSpec("pad_top", "Padding Top", "float", 10.0, 0.0, 60.0, 1.0, category="Padding"),
        ParamSpec("pad_bottom", "Padding Bottom", "float", 10.0, 0.0, 60.0, 1.0, category="Padding"),
        
        ParamSpec("scale_x", "Scale X", "float", 1.0, 0.5, 2.5, 0.05, category="Transform"),
        ParamSpec("scale_y", "Scale Y", "float", 1.0, 0.5, 2.5, 0.05, category="Transform"),
        ParamSpec("offset_x", "Offset X", "float", 0.0, -50.0, 50.0, 1.0, category="Transform"),
        ParamSpec("offset_y", "Offset Y", "float", 0.0, -50.0, 50.0, 1.0, category="Transform"),
        
        ParamSpec("border_width", "Border Width", "float", 0.0, 0.0, 20.0, 1.0, category="Border"),
        ParamSpec("border_color", "Border Color", "color", "#FFFFFF", category="Border"),
        
        ParamSpec("shadow_enable", "Shadow Enable", "bool", True, category="Shadow"),
        ParamSpec("shadow_blur", "Shadow Blur", "float", 6.0, 0.0, 30.0, 1.0, category="Shadow"),
        ParamSpec("shadow_ox", "Shadow Offset X", "float", 4.0, -30.0, 30.0, 1.0, category="Shadow"),
        ParamSpec("shadow_oy", "Shadow Offset Y", "float", 4.0, -30.0, 30.0, 1.0, category="Shadow"),
        
        ParamSpec("glow_enable", "Glow Enable", "bool", False, category="Glow"),
        ParamSpec("glow_radius", "Glow Radius", "float", 15.0, 0.0, 50.0, 1.0, category="Glow"),
        ParamSpec("glow_color", "Glow Color", "color", "#FF007F", category="Glow"),
    ],
    "Scale & Color": [
        ParamSpec("scale", "Scale", "float", 1.22, 0.5, 2.5, 0.05, category="Transform"),
        ParamSpec("min_scale", "Minimum Scale", "float", 1.0, 0.5, 1.5, 0.05, category="Transform"),
        ParamSpec("max_scale", "Maximum Scale", "float", 1.35, 1.0, 3.0, 0.05, category="Transform"),
        
        ParamSpec("active_color", "Color", "color", "#00FFCC", category="Appearance"),
        ParamSpec("interpolation", "Interpolation", "combo", "Linear", options=["Linear", "EaseIn", "EaseOut", "EaseInOut"], category="Appearance"),
    ],
    "Color Highlight": [
        ParamSpec("active_color", "Highlight Color", "color", "#00FFCC", category="Appearance"),
        ParamSpec("opacity", "Opacity", "float", 1.0, 0.0, 1.0, 0.05, category="Appearance"),
        ParamSpec("gradient_enable", "Gradient Enable", "bool", False, category="Appearance"),
        ParamSpec("gradient_color", "Gradient Color", "color", "#FF007F", category="Appearance"),
    ],
    "Rounded Rectangle": [
        ParamSpec("corner_radius", "Corner Radius", "float", 16.0, 0.0, 50.0, 1.0, category="Appearance"),
        ParamSpec("padding", "Padding", "float", 12.0, 0.0, 50.0, 1.0, category="Appearance"),
        ParamSpec("fill_color", "Fill Color", "color", "#00FFCC", category="Appearance"),
        ParamSpec("opacity", "Opacity", "float", 0.9, 0.0, 1.0, 0.05, category="Appearance"),
        
        ParamSpec("border_width", "Border Width", "float", 2.0, 0.0, 20.0, 1.0, category="Border"),
        ParamSpec("border_color", "Border Color", "color", "#FFFFFF", category="Border"),
        
        ParamSpec("scale", "Scale", "float", 1.0, 0.5, 2.0, 0.05, category="Transform"),
        ParamSpec("offset_x", "Offset X", "float", 0.0, -50.0, 50.0, 1.0, category="Transform"),
        ParamSpec("offset_y", "Offset Y", "float", 0.0, -50.0, 50.0, 1.0, category="Transform"),
    ],
    "Underline": [
        ParamSpec("active_color", "Color", "color", "#00FFCC", category="Appearance"),
        ParamSpec("thickness", "Thickness", "float", 6.0, 1.0, 20.0, 1.0, category="Appearance"),
        ParamSpec("dist_from_text", "Distance From Text", "float", 6.0, 0.0, 30.0, 1.0, category="Appearance"),
        ParamSpec("width_scale", "Width Scale", "float", 1.0, 0.5, 2.0, 0.05, category="Transform"),
        ParamSpec("glow_enable", "Glow", "bool", False, category="Glow"),
    ],
    "Glow": [
        ParamSpec("glow_color", "Glow Color", "color", "#00FFCC", category="Glow"),
        ParamSpec("glow_radius", "Glow Radius", "float", 18.0, 1.0, 50.0, 1.0, category="Glow"),
        ParamSpec("glow_opacity", "Glow Opacity", "float", 0.9, 0.0, 1.0, 0.05, category="Glow"),
        ParamSpec("glow_intensity", "Glow Intensity", "float", 1.5, 0.1, 3.0, 0.1, category="Glow"),
        ParamSpec("blur_radius", "Blur Radius", "float", 8.0, 0.0, 30.0, 1.0, category="Glow"),
    ]
}

MOTION_MODE_SPECS: Dict[str, List[ParamSpec]] = {
    "Bounce": [
        ParamSpec("amplitude", "Amplitude", "float", 22.0, 0.0, 100.0, 1.0, category="Motion"),
        ParamSpec("frequency", "Frequency Shape", "float", 1.0, 0.1, 10.0, 0.1, category="Motion"),
        ParamSpec("elasticity", "Elasticity", "float", 0.5, 0.0, 1.0, 0.05, category="Motion"),
        ParamSpec("damping", "Damping", "float", 0.2, 0.0, 1.0, 0.05, category="Motion"),
        ParamSpec("offset_x", "Offset X", "float", 0.0, -50.0, 50.0, 1.0, category="Motion"),
        ParamSpec("offset_y", "Offset Y", "float", 0.0, -50.0, 50.0, 1.0, category="Motion"),
    ],
    "Pop": [
        ParamSpec("start_scale", "Start Scale", "float", 0.7, 0.0, 1.5, 0.05, category="Motion"),
        ParamSpec("end_scale", "End Scale", "float", 1.3, 1.0, 3.0, 0.05, category="Motion"),
        ParamSpec("overshoot", "Overshoot", "float", 0.2, 0.0, 1.0, 0.05, category="Motion"),
    ],
    "Scale": [
        ParamSpec("min_scale", "Minimum Scale", "float", 1.0, 0.5, 1.5, 0.05, category="Motion"),
        ParamSpec("max_scale", "Maximum Scale", "float", 1.25, 1.0, 3.0, 0.05, category="Motion"),
        ParamSpec("interpolation", "Interpolation", "combo", "EaseInOut", options=["Linear", "EaseIn", "EaseOut", "EaseInOut"], category="Motion"),
    ],
    "Rotate": [
        ParamSpec("start_angle", "Start Angle", "float", -15.0, -360.0, 360.0, 1.0, category="Motion"),
        ParamSpec("end_angle", "End Angle", "float", 15.0, -360.0, 360.0, 1.0, category="Motion"),
        ParamSpec("pivot", "Pivot", "combo", "Center", options=["Center", "Bottom-Left", "Top-Left", "Bottom-Center"], category="Motion"),
        ParamSpec("clockwise", "Clockwise", "bool", True, category="Motion"),
    ],
    "Shake": [
        ParamSpec("amplitude_x", "Amplitude X", "float", 10.0, 0.0, 50.0, 1.0, category="Motion"),
        ParamSpec("amplitude_y", "Amplitude Y", "float", 6.0, 0.0, 50.0, 1.0, category="Motion"),
        ParamSpec("frequency", "Frequency", "float", 6.0, 1.0, 20.0, 0.5, category="Motion"),
        ParamSpec("random_seed", "Random Seed", "int", 42, 0, 100, 1, category="Motion"),
    ],
    "Swing": [
        ParamSpec("angle", "Angle", "float", 18.0, 0.0, 90.0, 1.0, category="Motion"),
        ParamSpec("frequency", "Frequency", "float", 2.0, 0.1, 10.0, 0.1, category="Motion"),
        ParamSpec("pivot", "Pivot", "combo", "Center", options=["Center", "Top-Center", "Bottom-Center"], category="Motion"),
        ParamSpec("damping", "Damping", "float", 0.3, 0.0, 1.0, 0.05, category="Motion"),
    ],
    "Jelly": [
        ParamSpec("h_stretch", "Horizontal Stretch", "float", 0.25, 0.0, 1.0, 0.05, category="Motion"),
        ParamSpec("v_stretch", "Vertical Stretch", "float", 0.20, 0.0, 1.0, 0.05, category="Motion"),
        ParamSpec("elasticity", "Elasticity", "float", 0.6, 0.0, 1.0, 0.05, category="Motion"),
    ],
    "Rubber": [
        ParamSpec("stretch_x", "Stretch X", "float", 0.3, 0.0, 1.0, 0.05, category="Motion"),
        ParamSpec("stretch_y", "Stretch Y", "float", 0.2, 0.0, 1.0, 0.05, category="Motion"),
    ],
    "Wave": [
        ParamSpec("amplitude", "Amplitude", "float", 12.0, 0.0, 50.0, 1.0, category="Motion"),
        ParamSpec("frequency", "Frequency", "float", 3.0, 0.1, 10.0, 0.1, category="Motion"),
        ParamSpec("direction", "Direction", "combo", "Vertical", options=["Vertical", "Horizontal"], category="Motion"),
    ],
    "Pulse": [
        ParamSpec("min_scale", "Minimum Scale", "float", 0.95, 0.5, 1.5, 0.05, category="Motion"),
        ParamSpec("max_scale", "Maximum Scale", "float", 1.20, 1.0, 3.0, 0.05, category="Motion"),
        ParamSpec("repeat", "Repeat Cycles", "bool", True, category="Motion"),
    ]
}


def populate_default_params(profile_obj: Any, mode_name: str, specs_dict: Dict[str, List[ParamSpec]]):
    """Helper to ensure all parameters for a mode are pre-populated with defaults."""
    specs = specs_dict.get(mode_name, [])
    for s in specs:
        if s.key not in profile_obj.params:
            profile_obj.params[s.key] = s.default


# ==============================================================================
# PROFESSIONAL CAPTION TEMPLATE SERIALIZATION ENGINE (.cstemplate)
# ==============================================================================

class SafeDataclassEncoder:
    """Safely updates target dataclass instances from raw dictionary data ignoring unknown or missing fields."""
    @staticmethod
    def apply_dict_to_dataclass(target_obj: Any, source_dict: Dict[str, Any]):
        if not isinstance(source_dict, dict):
            return
        for field_name, value in source_dict.items():
            if hasattr(target_obj, field_name):
                setattr(target_obj, field_name, value)


class CaptionTemplateManager:
    """Central registry and file manager for .cstemplate files."""
    SOFTWARE_VERSION = "3.3.0"
    TEMPLATE_FORMAT_VERSION = "1.3.0"
    TEMPLATE_DIR = os.path.join(os.path.expanduser("~"), "CaptionStudio", "Templates")
    FAVORITES_FILE = os.path.join(os.path.expanduser("~"), "CaptionStudio", "favorites.json")
    RECENT_FILE = os.path.join(os.path.expanduser("~"), "CaptionStudio", "recent.json")

    @classmethod
    def ensure_directories(cls):
        os.makedirs(os.path.join(cls.TEMPLATE_DIR, "Built-in"), exist_ok=True)
        os.makedirs(os.path.join(cls.TEMPLATE_DIR, "User"), exist_ok=True)

    @classmethod
    def serialize_workspace(cls, app: Any, name: str, description: str = "", author: str = "User", category: str = "User", tags: List[str] = None) -> Dict[str, Any]:
        thumb_b64 = cls.generate_thumbnail_b64(app)

        template_data = {
            "version": cls.TEMPLATE_FORMAT_VERSION,
            "compatible_software_version": cls.SOFTWARE_VERSION,
            "metadata": {
                "name": name,
                "description": description,
                "author": author,
                "category": category,
                "tags": tags or ["caption", "preset"],
                "created_date": datetime.now().isoformat(),
                "modified_date": datetime.now().isoformat(),
                "thumbnail_b64": thumb_b64
            },
            "profiles": {
                "video": asdict(app.vp),
                "text_style": asdict(app.ts),
                "outline": asdict(app.out_p),
                "shadow": asdict(app.sh),
                "glow": asdict(app.gl),
                "animation": asdict(app.ap),
                "layout": asdict(app.lp),
                "effects": asdict(app.ep),
                "word_highlight": asdict(app.wh),
                "active_word_animation": asdict(app.awa),
                "grouping": asdict(app.gp)
            },
            "future_extensions": {
                "animated_emojis": {},
                "gif_stickers": {},
                "motion_graphics": {},
                "video_effects": {},
                "custom_shaders": {}
            }
        }
        return template_data

    @classmethod
    def deserialize_into_workspace(cls, app: Any, template_data: Dict[str, Any]):
        profiles = template_data.get("profiles", {})

        SafeDataclassEncoder.apply_dict_to_dataclass(app.vp, profiles.get("video", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.ts, profiles.get("text_style", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.out_p, profiles.get("outline", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.sh, profiles.get("shadow", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.gl, profiles.get("glow", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.ap, profiles.get("animation", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.lp, profiles.get("layout", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.ep, profiles.get("effects", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.wh, profiles.get("word_highlight", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.awa, profiles.get("active_word_animation", {}))
        SafeDataclassEncoder.apply_dict_to_dataclass(app.gp, profiles.get("grouping", {}))

        populate_default_params(app.wh, app.wh.mode, HIGHLIGHT_MODE_SPECS)
        populate_default_params(app.awa, app.awa.anim_type, MOTION_MODE_SPECS)

        app._sync_profiles_into_ui()
        RenderCacheManager.clear()

    @classmethod
    def generate_thumbnail_b64(cls, app: Any) -> str:
        try:
            sample_words = [
                Word("CAPTION", 0.0, 400.0, 0),
                Word("STUDIO", 400.0, 800.0, 1),
                Word("PRO", 800.0, 1200.0, 2)
            ]
            groups = SmartCaptionGroupEngine.build_caption_groups(sample_words, app.gp, app.vp, app.ts, app.out_p, app.wh)
            group = groups[0] if groups else None
            
            sim_vp = VideoProfile(width=480, height=270, bg_mode="Black")
            ratio = 480.0 / 1920.0

            sc_ts = TextStyleProfile(
                font_family=app.ts.font_family,
                font_size=max(12, int(app.ts.font_size * ratio)),
                bold=app.ts.bold,
                italic=app.ts.italic,
                case_mode=app.ts.case_mode,
                text_color=app.ts.text_color
            )
            sc_out = OutlineProfile(enabled=app.out_p.enabled, width=max(1, int(app.out_p.width * ratio)), color=app.out_p.color)
            sc_sh = ShadowProfile(enabled=app.sh.enabled, offset_x=int(app.sh.offset_x * ratio), offset_y=int(app.sh.offset_y * ratio), blur=int(app.sh.blur * ratio), color=app.sh.color)
            sc_gl = GlowProfile(enabled=app.gl.enabled, size=int(app.gl.size * ratio), color=app.gl.color)
            sim_lp = LayoutProfile(anchor="Center Center", custom_positioning=False)

            img = app.preview_renderer.compose_full_frame(
                group, sim_vp, sc_ts, sc_out, sc_sh, sc_gl,
                app.ap, sim_lp, app.ep, app.wh, app.awa, 600.0
            )

            buf = BytesIO()
            img.save(buf, format="PNG")
            return base64.b64encode(buf.getvalue()).decode("utf-8")
        except Exception:
            return ""

    @classmethod
    def load_favorites(cls) -> List[str]:
        if os.path.exists(cls.FAVORITES_FILE):
            try:
                with open(cls.FAVORITES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception: pass
        return []

    @classmethod
    def save_favorites(cls, favs: List[str]):
        try:
            with open(cls.FAVORITES_FILE, "w", encoding="utf-8") as f:
                json.dump(favs, f, indent=2)
        except Exception: pass

    @classmethod
    def load_recent(cls) -> List[str]:
        if os.path.exists(cls.RECENT_FILE):
            try:
                with open(cls.RECENT_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception: pass
        return []

    @classmethod
    def add_recent(cls, filepath: str):
        recents = cls.load_recent()
        if filepath in recents: recents.remove(filepath)
        recents.insert(0, filepath)
        recents = recents[:10]
        try:
            with open(cls.RECENT_FILE, "w", encoding="utf-8") as f:
                json.dump(recents, f, indent=2)
        except Exception: pass


# ==============================================================================
# PERFORMANCE CACHE MANAGER
# ==============================================================================

class RenderCacheManager:
    """High-performance multi-level cache for Fonts, Layouts, Glyphs, Shadows, and Glows."""
    _font_cache: Dict[Tuple[str, int, bool, bool], ImageFont.FreeTypeFont] = {}
    _word_surface_cache: Dict[str, Image.Image] = {}

    @classmethod
    def clear(cls):
        cls._font_cache.clear()
        cls._word_surface_cache.clear()


# ==============================================================================
# FONT ENGINE & SYSTEM REGISTRY SCANNER
# ==============================================================================

class FontManager:
    _font_map: Dict[str, str] = {}
    _font_categories: Dict[str, str] = {}
    _recent_fonts: List[str] = []
    _favorite_fonts: List[str] = []

    @classmethod
    def scan_system_fonts(cls) -> List[str]:
        cls._font_map.clear()
        if sys.platform.startswith("win") and winreg:
            font_dir = os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts")
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts")
                for i in range(winreg.QueryInfoKey(key)[1]):
                    try:
                        name, val, _ = winreg.EnumValue(key, i)
                        clean_name = name.split("(")[0].strip()
                        path = val if os.path.isabs(val) else os.path.join(font_dir, val)
                        if os.path.exists(path) and path.lower().endswith((".ttf", ".otf", ".ttc")):
                            cls._font_map[clean_name] = path
                    except Exception:
                        continue
                winreg.CloseKey(key)
            except Exception:
                pass

        search_paths = []
        if sys.platform.startswith("win"):
            search_paths.append(os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"))
            search_paths.append(os.path.expanduser("~\\AppData\\Local\\Microsoft\\Windows\\Fonts"))
        elif sys.platform == "darwin":
            search_paths.extend(["/Library/Fonts", "/System/Library/Fonts", os.path.expanduser("~/Library/Fonts")])
        else:
            search_paths.extend(["/usr/share/fonts", "/usr/local/share/fonts", os.path.expanduser("~/.fonts")])

        for base_path in search_paths:
            if os.path.exists(base_path):
                for root, _, files in os.walk(base_path):
                    for f in files:
                        if f.lower().endswith((".ttf", ".otf", ".ttc")):
                            path = os.path.join(root, f)
                            font_name = os.path.splitext(f)[0].replace("-", " ").replace("_", " ").title()
                            if font_name not in cls._font_map:
                                cls._font_map[font_name] = path

        for name in cls._font_map:
            nl = name.lower()
            if any(k in nl for k in ["script", "hand", "brush", "calligraphy"]):
                cls._font_categories[name] = "Handwriting"
            elif any(k in nl for k in ["serif", "georgia", "times", "garamond", "bodoni"]):
                cls._font_categories[name] = "Serif"
            elif any(k in nl for k in ["impact", "anton", "bebas", "black", "bold", "heavy"]):
                cls._font_categories[name] = "Display"
            else:
                cls._font_categories[name] = "Sans-Serif"

        sorted_names = sorted(list(cls._font_map.keys()))
        return sorted_names if sorted_names else ["Arial", "Impact", "Segoe UI"]

    @classmethod
    def get_font_path(cls, family: str) -> str:
        if not cls._font_map:
            cls.scan_system_fonts()
        if family in cls._font_map:
            return cls._font_map[family]
        family_clean = family.lower().replace(" ", "")
        for name, path in cls._font_map.items():
            if family_clean in name.lower().replace(" ", ""):
                return path
        if sys.platform.startswith("win"):
            return os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts", "impact.ttf")
        return ""

    @classmethod
    def mark_recent(cls, family: str):
        if family in cls._recent_fonts:
            cls._recent_fonts.remove(family)
        cls._recent_fonts.insert(0, family)
        cls._recent_fonts = cls._recent_fonts[:8]

    @classmethod
    def toggle_favorite(cls, family: str):
        if family in cls._favorite_fonts:
            cls._favorite_fonts.remove(family)
        else:
            cls._favorite_fonts.append(family)


# ==============================================================================
# PHOTOSHOP / CAPCUT STYLE FONT PICKER DIALOG
# ==============================================================================

class FontPickerPopup(tk.Toplevel):
    def __init__(self, parent, current_font: str, on_select_callback):
        super().__init__(parent)
        self.title("Select Typography Font")
        self.geometry("540x650")
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#121214")
        self.on_select_callback = on_select_callback
        self.selected_font = current_font
        self._all_fonts = FontManager.scan_system_fonts()
        self.sample_cache: Dict[str, ImageTk.PhotoImage] = {}
        self._build_ui()
        self._populate_list()

    def _build_ui(self):
        search_frame = tk.Frame(self, bg="#1E1E24", padx=10, pady=10)
        search_frame.pack(fill=tk.X)
        tk.Label(search_frame, text="🔍", bg="#1E1E24", fg="#FFFFFF", font=("Segoe UI", 12)).pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._populate_list())
        search_entry = tk.Entry(search_frame, textvariable=self.search_var, bg="#18181C", fg="#FFFFFF",
                                insertbackground="#FFFFFF", relief="flat", font=("Segoe UI", 11),
                                highlightthickness=1, highlightbackground="#2D2D38", highlightcolor="#0969DA")
        search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=8)
        search_entry.focus_set()

        cat_frame = tk.Frame(self, bg="#121214", pady=6)
        cat_frame.pack(fill=tk.X, padx=10)
        self.cat_var = tk.StringVar(value="All")
        categories = ["All", "Favorites ⭐", "Display", "Sans-Serif", "Serif", "Handwriting"]
        for cat in categories:
            btn = tk.Radiobutton(cat_frame, text=cat, variable=self.cat_var, value=cat,
                                 bg="#1E1E24", fg="#CCCCCC", selectcolor="#0969DA",
                                 activebackground="#1E1E24", activeforeground="#FFFFFF",
                                 indicatoron=False, relief="flat", padx=8, pady=3,
                                 command=self._populate_list)
            btn.pack(side=tk.LEFT, padx=2)

        list_container = tk.Frame(self, bg="#121214")
        list_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.canvas = tk.Canvas(list_container, bg="#18181C", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(list_container, orient="vertical", command=self.canvas.yview)
        self.scroll_frame = tk.Frame(self.canvas, bg="#18181C")

        self.scroll_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.scroll_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _render_font_sample(self, family: str) -> ImageTk.PhotoImage:
        if family in self.sample_cache:
            return self.sample_cache[family]
        img = Image.new("RGBA", (450, 40), (24, 24, 28, 255))
        draw = ImageDraw.Draw(img)
        font_path = FontManager.get_font_path(family)
        try:
            pil_font = ImageFont.truetype(font_path if font_path else "arial.ttf", 18)
        except Exception:
            pil_font = ImageFont.load_default()

        draw.text((10, 8), "Aa", font=pil_font, fill=(9, 105, 218, 255))
        draw.text((55, 10), family[:28], font=pil_font, fill=(240, 240, 240, 255))
        tk_img = ImageTk.PhotoImage(img)
        self.sample_cache[family] = tk_img
        return tk_img

    def _populate_list(self):
        for child in self.scroll_frame.winfo_children():
            child.destroy()
        query = self.search_var.get().lower().strip()
        category = self.cat_var.get()

        filtered = []
        for f in self._all_fonts:
            if query and query not in f.lower():
                continue
            if category == "Favorites ⭐" and f not in FontManager._favorite_fonts:
                continue
            if category not in ["All", "Favorites ⭐"] and FontManager._font_categories.get(f) != category:
                continue
            filtered.append(f)

        for font_family in filtered:
            item_frame = tk.Frame(self.scroll_frame, bg="#18181C", pady=2)
            item_frame.pack(fill=tk.X, expand=True)

            fav_text = "⭐" if font_family in FontManager._favorite_fonts else "☆"
            fav_btn = tk.Label(item_frame, text=fav_text, bg="#18181C", fg="#FFCC00", font=("Segoe UI", 12), cursor="hand2")
            fav_btn.pack(side=tk.LEFT, padx=5)
            fav_btn.bind("<Button-1>", lambda e, f=font_family: self._toggle_fav(f))

            sample_img = self._render_font_sample(font_family)
            lbl = tk.Label(item_frame, image=sample_img, bg="#18181C", cursor="hand2")
            lbl.image = sample_img
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)

            handler = lambda e, f=font_family: self._select_font(f)
            item_frame.bind("<Button-1>", handler)
            lbl.bind("<Button-1>", handler)

    def _toggle_fav(self, family: str):
        FontManager.toggle_favorite(family)
        self._populate_list()

    def _select_font(self, family: str):
        FontManager.mark_recent(family)
        self.selected_font = family
        self.on_select_callback(family)
        self.destroy()


# ==============================================================================
# WORD TIMELINE ENGINE & INTELLIGENT SMART LAYOUT ENGINE
# ==============================================================================

class WordTimelineEngine:
    """Parses SRT files into a continuous timeline of individual Word objects."""

    @staticmethod
    def parse_srt_to_words(srt_path: str) -> List[Word]:
        try:
            subs = pysrt.open(srt_path, encoding="utf-8")
        except Exception:
            subs = pysrt.open(srt_path, encoding="latin-1")

        words: List[Word] = []
        global_idx = 0

        for sub in subs:
            block_start = float(sub.start.ordinal)
            block_end = float(sub.end.ordinal)
            sub_text = sub.text.strip().replace("\n", " ")
            raw_words = [w for w in sub_text.split() if w.strip()]

            if not raw_words:
                continue

            if len(raw_words) == 1:
                w_obj = Word(
                    word=raw_words[0],
                    start_ms=block_start,
                    end_ms=block_end,
                    index=global_idx
                )
                words.append(w_obj)
                global_idx += 1
            else:
                total_duration = max(10.0, block_end - block_start)
                word_dur = total_duration / len(raw_words)
                for idx, w_str in enumerate(raw_words):
                    w_start = block_start + (idx * word_dur)
                    w_end = w_start + word_dur
                    w_obj = Word(
                        word=w_str,
                        start_ms=w_start,
                        end_ms=w_end,
                        index=global_idx
                    )
                    words.append(w_obj)
                    global_idx += 1

        return words


def measure_rendered_word_width(word_str: str, font: ImageFont.FreeTypeFont, 
                                ts: TextStyleProfile, out: OutlineProfile, 
                                wh: WordHighlightProfile) -> float:
    """Calculates the absolute maximum pixel rendering width of a word including strokes, padding, scale, and active highlights."""
    w_text = word_str
    if ts.case_mode == "Uppercase": w_text = w_text.upper()
    elif ts.case_mode == "Lowercase": w_text = w_text.lower()

    bbox = font.getbbox(w_text)
    raw_w = (bbox[2] - bbox[0]) + (len(w_text) * ts.letter_spacing)

    scale_mult = 1.0
    pad_x = 0.0

    if wh.enabled:
        if wh.mode == "Background Box":
            pad_x = float(wh.params.get("pad_left", 16.0) + wh.params.get("pad_right", 16.0))
            scale_mult = float(wh.params.get("scale_x", 1.0)) * 1.35
        elif wh.mode == "Scale & Color":
            scale_mult = float(wh.params.get("scale", 1.22)) * 1.35
        elif wh.mode == "Rounded Rectangle":
            pad_x = float(wh.params.get("padding", 12.0)) * 2.0
            scale_mult = float(wh.params.get("scale", 1.0)) * 1.35

    stroke_extra = (out.outer_width if out.double_outline else out.width * 2) if out.enabled else 0
    total_w = (raw_w + pad_x + stroke_extra) * scale_mult
    return total_w


class SmartCaptionGroupEngine:
    """Smart Layout Engine prioritizing: 1. Screen Safety, 2. User Preferences, 3. Visual Balance."""

    @staticmethod
    def build_caption_groups(words: List[Word], gp: GroupingProfile, vp: VideoProfile, 
                             ts: TextStyleProfile, out: OutlineProfile, 
                             wh: WordHighlightProfile) -> List[CaptionGroup]:
        if not words:
            return []

        path = FontManager.get_font_path(ts.font_family)
        try:
            font = ImageFont.truetype(path if path else "arial.ttf", ts.font_size)
        except Exception:
            font = ImageFont.load_default()

        space_w = (font.getbbox(" ")[2] - font.getbbox(" ")[0]) + ts.letter_spacing
        
        # Calculate maximum safe width
        if gp.enable_safe_area:
            max_avail_w = float(vp.width - (gp.screen_safe_margin * 2))
        else:
            max_avail_w = float(vp.width - 40)
        max_avail_w = max(100.0, max_avail_w)

        groups: List[CaptionGroup] = []
        curr_lines: List[List[Word]] = []
        curr_line: List[Word] = []
        curr_line_w = 0.0

        for w_obj in words:
            w_w = measure_rendered_word_width(w_obj.word, font, ts, out, wh)

            needed_w = w_w if not curr_line else (curr_line_w + space_w + w_w)
            exceeds_safe_area = (needed_w > max_avail_w)
            reached_preferred_limit = (len(curr_line) >= gp.preferred_words_per_line)

            if curr_line and (exceeds_safe_area or reached_preferred_limit):
                curr_lines.append(curr_line)
                curr_line = []
                curr_line_w = 0.0

                if len(curr_lines) >= gp.max_lines:
                    groups.append(SmartCaptionGroupEngine._create_group_from_lines(curr_lines))
                    curr_lines = []

            curr_line.append(w_obj)
            curr_line_w += (w_w + space_w) if len(curr_line) > 1 else w_w

        if curr_line:
            curr_lines.append(curr_line)
        if curr_lines:
            groups.append(SmartCaptionGroupEngine._create_group_from_lines(curr_lines))

        return groups

    @staticmethod
    def _create_group_from_lines(lines: List[List[Word]]) -> CaptionGroup:
        all_words = [w for line in lines for w in line]
        start_ms = all_words[0].start_ms
        end_ms = all_words[-1].end_ms
        full_text = " ".join([w.word for w in all_words])
        return CaptionGroup(
            start_ms=start_ms,
            end_ms=end_ms,
            text=full_text,
            words=all_words,
            lines=lines
        )


# ==============================================================================
# 30+ BUILT-IN PREMIUM CAPTION STYLES CATALOG
# ==============================================================================

class StyleManager:
    _custom_presets: Dict[str, Dict[str, Any]] = {}

    _inbuilt_catalog: Dict[str, Dict[str, Any]] = {
        "Alex Hormozi Classic": {
            "ts_font_family": "Impact", "ts_font_size": 85, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FFCC00", "ts_letter_spacing": 3, "out_enabled": True, "out_width": 10,
            "out_color": "#000000", "sh_enabled": True, "sh_offset_x": 8, "sh_offset_y": 8, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 12, "gl_color": "#FFFF00", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Hormozi Yellow": {
            "ts_font_family": "Impact", "ts_font_size": 80, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FFE500", "ts_letter_spacing": 2, "out_enabled": True, "out_width": 8,
            "out_color": "#000000", "sh_enabled": True, "sh_offset_x": 6, "sh_offset_y": 6, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 12, "gl_color": "#FFFF00", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "MrBeast": {
            "ts_font_family": "Montserrat", "ts_font_size": 90, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#00F0FF", "ts_letter_spacing": 4, "out_enabled": True, "out_width": 12,
            "out_color": "#000000", "sh_enabled": True, "sh_offset_x": 10, "sh_offset_y": 10, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": True, "gl_size": 15, "gl_color": "#00F0FF", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Magnates Media": {
            "ts_font_family": "Georgia", "ts_font_size": 75, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#D4AF37", "ts_letter_spacing": 5, "out_enabled": True, "out_width": 4,
            "out_color": "#111111", "sh_enabled": True, "sh_offset_x": 4, "sh_offset_y": 6, "sh_blur": 8,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 10, "gl_color": "#D4AF37", "ep_mode": "Gold Foil", "lp_anchor": "Bottom Center"
        },
        "Netflix": {
            "ts_font_family": "Bebas Neue", "ts_font_size": 85, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#E50914", "ts_letter_spacing": 3, "out_enabled": True, "out_width": 4,
            "out_color": "#000000", "sh_enabled": True, "sh_offset_x": 4, "sh_offset_y": 4, "sh_blur": 5,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 0, "gl_color": "#000000", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Submagic": {
            "ts_font_family": "Montserrat", "ts_font_size": 78, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FF007F", "ts_letter_spacing": 2, "out_enabled": True, "out_width": 6,
            "out_color": "#FFFFFF", "sh_enabled": True, "sh_offset_x": 4, "sh_offset_y": 4, "sh_blur": 4,
            "sh_color": "#000000", "gl_enabled": True, "gl_size": 12, "gl_color": "#FF007F", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Captions AI": {
            "ts_font_family": "Inter", "ts_font_size": 75, "ts_bold": True, "ts_case_mode": "Normal",
            "ts_text_color": "#38BDF8", "ts_letter_spacing": 1, "out_enabled": True, "out_width": 4,
            "out_color": "#0F172A", "sh_enabled": True, "sh_offset_x": 0, "sh_offset_y": 4, "sh_blur": 8,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 0, "gl_color": "#000000", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "Gaming RGB": {
            "ts_font_family": "Impact", "ts_font_size": 85, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#00FFCC", "ts_letter_spacing": 3, "out_enabled": True, "out_width": 8,
            "out_color": "#FF0055", "sh_enabled": True, "sh_offset_x": 6, "sh_offset_y": 6, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": True, "gl_size": 20, "gl_color": "#00FFCC", "ep_mode": "RGB", "lp_anchor": "Bottom Center"
        },
        "Fire": {
            "ts_font_family": "Impact", "ts_font_size": 85, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FF4500", "ts_letter_spacing": 2, "out_enabled": True, "out_width": 8,
            "out_color": "#220000", "sh_enabled": True, "sh_offset_x": 6, "sh_offset_y": 6, "sh_blur": 4,
            "sh_color": "#000000", "gl_enabled": True, "gl_size": 18, "gl_color": "#FF8700", "ep_mode": "Fire", "lp_anchor": "Bottom Center"
        },
        "Cyberpunk": {
            "ts_font_family": "Impact", "ts_font_size": 82, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FFE600", "ts_letter_spacing": 3, "out_enabled": True, "out_width": 8,
            "out_color": "#FF0055", "sh_enabled": True, "sh_offset_x": 8, "sh_offset_y": 8, "sh_blur": 0,
            "sh_color": "#00FFFF", "gl_enabled": True, "gl_size": 15, "gl_color": "#FF0055", "ep_mode": "Cyberpunk", "lp_anchor": "Bottom Center"
        },
        "TikTok Viral": {
            "ts_font_family": "Proxima Nova", "ts_font_size": 82, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#25F4EE", "ts_letter_spacing": 2, "out_enabled": True, "out_width": 8,
            "out_color": "#FE2C55", "sh_enabled": True, "sh_offset_x": 6, "sh_offset_y": 6, "sh_blur": 0,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 0, "gl_color": "#000000", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        },
        "YouTube Shorts": {
            "ts_font_family": "Impact", "ts_font_size": 85, "ts_bold": True, "ts_case_mode": "Uppercase",
            "ts_text_color": "#FF0000", "ts_letter_spacing": 3, "out_enabled": True, "out_width": 10,
            "out_color": "#FFFFFF", "sh_enabled": True, "sh_offset_x": 6, "sh_offset_y": 6, "sh_blur": 2,
            "sh_color": "#000000", "gl_enabled": False, "gl_size": 0, "gl_color": "#000000", "ep_mode": "Standard", "lp_anchor": "Bottom Center"
        }
    }

    @classmethod
    def get_all_presets_names(cls) -> List[str]:
        return list(cls._inbuilt_catalog.keys()) + list(cls._custom_presets.keys())

    @classmethod
    def apply(cls, name: str, ts: TextStyleProfile, out: OutlineProfile, 
              sh: ShadowProfile, gl: GlowProfile, ep: EffectsProfile, lp: LayoutProfile,
              wh: WordHighlightProfile, awa: ActiveWordAnimationProfile):
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
        gl.size = data.get("gl_size", 12)
        gl.color = data.get("gl_color", "#FFFF00")
        
        ep.mode = data["ep_mode"]
        lp.anchor = data["lp_anchor"]

        populate_default_params(wh, wh.mode, HIGHLIGHT_MODE_SPECS)
        populate_default_params(awa, awa.anim_type, MOTION_MODE_SPECS)


# ==============================================================================
# KINETIC ANIMATION ENGINE & TRANSFORM MATH (NORMALIZED TIMING ENGINE)
# ==============================================================================

class AnimationManager:
    @staticmethod
    def get_entry_animations() -> List[str]:
        return ["None", "Pop", "Bounce", "Elastic", "Scale", "Rotate", "Drop", "Stretch", "Flip", "Blur In", "Slide"]

    @staticmethod
    def get_loop_animations() -> List[str]:
        return ["None", "Floating", "Pulse", "Heartbeat", "Wave", "Jelly", "Rubber", "Shake", "Glow Pulse"]

    @staticmethod
    def get_exit_animations() -> List[str]:
        return ["None", "Fade", "Shrink", "Slide", "Rotate", "Drop"]

    @staticmethod
    def evaluate_stage(ap: AnimationProfile, time_from_start_ms: float, time_to_end_ms: float, duration_ms: float) -> Dict[str, Any]:
        res = {"alpha_factor": 1.0, "scale_factor": 1.0, "offset_x": 0.0, "offset_y": 0.0, "rotation_deg": 0.0, "blur_radius": 0.0, "char_visible_pct": 1.0}
        if duration_ms <= 0: return res

        speed = float(ap.speed_ms)
        entry_t = min(1.0, max(0.0, time_from_start_ms / max(1.0, speed)))
        exit_t = min(1.0, max(0.0, time_to_end_ms / max(1.0, speed)))

        # ENTRY ANIMATION
        entry = ap.entry_anim if ap.entry_anim != "None" else ap.type_name
        if entry_t < 1.0 and entry != "None":
            t = entry_t
            if entry == "Pop":
                res["scale_factor"] = 0.2 + 0.8 * math.sin(t * math.pi / 2.0)
            elif entry == "Bounce":
                res["offset_y"] = -180.0 * abs(math.cos(t * math.pi * 1.5)) * (1.0 - t)
            elif entry == "Elastic":
                res["scale_factor"] = 1.0 + 0.4 * math.sin(t * math.pi * 3.5) * (1.0 - t)
            elif entry == "Scale":
                res["scale_factor"] = 0.3 + 0.7 * t
            elif entry == "Rotate":
                res["rotation_deg"] = (1.0 - t) * 180.0
                res["alpha_factor"] = t
            elif entry == "Drop":
                res["offset_y"] = -350.0 * (1.0 - t)**2
            elif entry == "Stretch":
                res["scale_factor"] = 0.5 + 0.5 * t
            elif entry == "Flip":
                res["scale_factor"] = max(0.05, abs(math.cos(t * math.pi)))
            elif entry == "Blur In":
                res["blur_radius"] = (1.0 - t) * 12.0
                res["alpha_factor"] = t

        # EXIT ANIMATION
        if exit_t < 1.0 and ap.exit_anim != "None":
            t = exit_t
            if ap.exit_anim == "Fade": res["alpha_factor"] *= t
            elif ap.exit_anim == "Shrink": res["scale_factor"] *= t
            elif ap.exit_anim == "Drop": res["offset_y"] += 350.0 * (1.0 - t)**2

        # LOOP ANIMATION
        if ap.loop_anim != "None":
            cycle = (time_from_start_ms / 400.0) * math.pi
            if ap.loop_anim == "Pulse": res["scale_factor"] *= (1.0 + 0.08 * math.sin(cycle))
            elif ap.loop_anim == "Floating": res["offset_y"] += math.sin(cycle) * 12.0
            elif ap.loop_anim == "Shake": res["offset_x"] += math.sin(cycle * 3.0) * 8.0
            elif ap.loop_anim == "Heartbeat": res["scale_factor"] *= (1.0 + 0.12 * abs(math.sin(cycle * 2.0)))
            elif ap.loop_anim == "Wave": res["offset_y"] += math.sin(cycle * 2.0) * 10.0

        return res

    @staticmethod
    def evaluate_active_word_transform(awa_type: str, progress: float, params: Dict[str, Any]) -> Tuple[float, float, float, float, float]:
        """Calculates scale_x, scale_y, offset_x, offset_y, rotation driven ENTIRELY by normalized word timing (progress 0.0 -> 1.0)."""
        s_x, s_y, dx, dy, rot = 1.0, 1.0, 0.0, 0.0, 0.0
        p = min(1.0, max(0.0, progress))

        interp = params.get("interpolation", "Linear")
        p_eased = p
        if interp == "EaseIn":
            p_eased = p * p
        elif interp == "EaseOut":
            p_eased = p * (2.0 - p)
        elif interp == "EaseInOut":
            p_eased = p * p * (3.0 - 2.0 * p)

        if awa_type == "Bounce":
            amp = params.get("amplitude", 22.0)
            freq = params.get("frequency", 1.0)
            damp = params.get("damping", 0.2)
            ox = params.get("offset_x", 0.0)
            oy = params.get("offset_y", 0.0)
            decay = math.exp(-damp * p * 5.0)
            dy = oy - amp * math.sin(p * math.pi * freq) * decay
            dx = ox
        elif awa_type == "Pop":
            s_start = params.get("start_scale", 0.7)
            s_end = params.get("end_scale", 1.3)
            over = params.get("overshoot", 0.2)
            curve = math.sin(p * math.pi)
            scale_val = s_start + (s_end - s_start) * p + over * curve
            s_x = s_y = scale_val
        elif awa_type == "Scale":
            s_min = params.get("min_scale", 1.0)
            s_max = params.get("max_scale", 1.25)
            s_val = s_min + (s_max - s_min) * math.sin(p_eased * math.pi)
            s_x = s_y = s_val
        elif awa_type == "Rotate":
            start_a = params.get("start_angle", -15.0)
            end_a = params.get("end_angle", 15.0)
            cw = params.get("clockwise", True)
            mult = 1.0 if cw else -1.0
            rot = mult * (start_a + (end_a - start_a) * math.sin(p * math.pi))
        elif awa_type == "Shake":
            amp_x = params.get("amplitude_x", 10.0)
            amp_y = params.get("amplitude_y", 6.0)
            freq = params.get("frequency", 6.0)
            dx = amp_x * math.sin(p * math.pi * freq)
            dy = amp_y * math.cos(p * math.pi * freq)
        elif awa_type == "Swing":
            ang = params.get("angle", 18.0)
            freq = params.get("frequency", 2.0)
            damp = params.get("damping", 0.3)
            decay = math.exp(-damp * p * 4.0)
            rot = ang * math.sin(p * math.pi * freq) * decay
        elif awa_type == "Jelly":
            h_st = params.get("h_stretch", 0.25)
            v_st = params.get("v_stretch", 0.20)
            elas = params.get("elasticity", 0.6)
            decay = math.exp(-elas * p * 3.0)
            s_x = 1.0 + h_st * math.sin(p * math.pi * 2.0) * decay
            s_y = 1.0 - v_st * math.sin(p * math.pi * 2.0) * decay
        elif awa_type == "Rubber":
            st_x = params.get("stretch_x", 0.3)
            st_y = params.get("stretch_y", 0.2)
            s_x = 1.0 + st_x * math.cos(p * math.pi * 2.0) * (1.0 - p)
            s_y = 1.0 - st_y * math.cos(p * math.pi * 2.0) * (1.0 - p)
        elif awa_type == "Wave":
            amp = params.get("amplitude", 12.0)
            freq = params.get("frequency", 3.0)
            direct = params.get("direction", "Vertical")
            val = amp * math.sin(p * math.pi * freq)
            if direct == "Vertical": dy = val
            else: dx = val
        elif awa_type == "Pulse":
            s_min = params.get("min_scale", 0.95)
            s_max = params.get("max_scale", 1.20)
            rep = params.get("repeat", True)
            cycles = 2.0 if rep else 1.0
            s_val = s_min + (s_max - s_min) * abs(math.sin(p * math.pi * cycles))
            s_x = s_y = s_val

        return s_x, s_y, dx, dy, rot


# ==============================================================================
# VISUALLY DISTINCT EFFECTS ENGINE
# ==============================================================================

class EffectManager:
    @staticmethod
    def apply_word_effect(base_img: Image.Image, mode: str, frame_time_ms: float = 0.0) -> Image.Image:
        if mode == "Standard": return base_img
        w, h = base_img.size
        if w < 2 or h < 2: return base_img

        if mode in ["Gold Foil", "Silver Foil", "Metal"]:
            grad = Image.new("RGBA", (w, h))
            draw = ImageDraw.Draw(grad)
            for y in range(h):
                p = y / max(1, h)
                if mode == "Gold Foil":
                    r, g, b = int(255 - 40*p), int(215 - 80*p), int(15 + 30*p)
                elif mode == "Silver Foil":
                    v = int(245 - 80*p)
                    r, g, b = v, v, v
                elif mode == "Metal":
                    r, g, b = int(180 - 90*p), int(190 - 80*p), int(205 - 70*p)
                draw.line([(0, y), (w, y)], fill=(r, g, b, 255))
            return Image.composite(grad, base_img, base_img)

        elif mode == "Cyberpunk":
            a = base_img.split()[3]
            glow = a.filter(ImageFilter.GaussianBlur(5))
            mask = Image.new("RGBA", (w, h), (255, 0, 85, 255))
            gl_img = Image.composite(mask, Image.new("RGBA", (w, h)), glow)
            return Image.alpha_composite(gl_img, base_img)

        elif mode == "RGB":
            off = 6
            l_lay = base_img.transform((w, h), Image.Transform.AFFINE, (1, 0, off, 0, 1, 0))
            r_lay = base_img.transform((w, h), Image.Transform.AFFINE, (1, 0, -off, 0, 1, 0))
            cyan = Image.merge("RGBA", [Image.new("L", (w, h), 0), l_lay.split()[1], l_lay.split()[2], l_lay.split()[3]])
            red = Image.merge("RGBA", [r_lay.split()[0], Image.new("L", (w, h), 0), Image.new("L", (w, h), 0), r_lay.split()[3]])
            return Image.alpha_composite(Image.alpha_composite(cyan, red), base_img)

        elif mode in ["Fire", "Ice"]:
            a = base_img.split()[3]
            glow = a.filter(ImageFilter.GaussianBlur(8))
            tint = (255, 69, 0, 255) if mode == "Fire" else (0, 229, 255, 255)
            gl_img = Image.composite(Image.new("RGBA", (w, h), tint), Image.new("RGBA", (w, h)), glow)
            return Image.alpha_composite(gl_img, base_img)

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
# UNIFIED RENDER ENGINE & STABLE CENTER ANCHOR LAYOUT
# ==============================================================================

def hex_to_rgba(hex_str: str, opacity: float = 1.0) -> Tuple[int, int, int, int]:
    h = hex_str.lstrip('#')
    try:
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16), int(255 * opacity))
    except Exception:
        return (255, 255, 255, int(255 * opacity))


class SubtitleRenderer:
    """Unified Rendering Engine ensuring absolute center anchor stability and accurate background wrapping."""

    def get_font(self, family: str, size: int, bold: bool, italic: bool) -> ImageFont.FreeTypeFont:
        key = (family, size, bold, italic)
        if key in RenderCacheManager._font_cache:
            return RenderCacheManager._font_cache[key]
        path = FontManager.get_font_path(family)
        try:
            f = ImageFont.truetype(path if path else "arial.ttf", size)
            RenderCacheManager._font_cache[key] = f
            return f
        except Exception:
            return ImageFont.load_default()

    def layout_caption_group(self, group: CaptionGroup, font: ImageFont.FreeTypeFont, 
                              ts: TextStyleProfile, out: OutlineProfile) -> Tuple[int, int]:
        ascent, descent = font.getmetrics()
        space_w = (font.getbbox(" ")[2] - font.getbbox(" ")[0]) + ts.letter_spacing
        line_height = (ascent + descent) + (out.width * 2)

        line_widths = []
        for line in group.lines:
            lw = 0.0
            for w_obj in line:
                raw_txt = w_obj.word
                if ts.case_mode == "Uppercase": raw_txt = raw_txt.upper()
                elif ts.case_mode == "Lowercase": raw_txt = raw_txt.lower()

                bbox = font.getbbox(raw_txt)
                w_obj.ascent = float(ascent)
                w_obj.descent = float(descent)
                w_obj.bbox_left = float(bbox[0])
                w_obj.bbox_top = float(bbox[1])
                w_obj.bbox_right = float(bbox[2])
                w_obj.bbox_bottom = float(bbox[3])
                
                w_obj.width = (bbox[2] - bbox[0]) + (len(raw_txt) * ts.letter_spacing)
                w_obj.height = float(ascent + descent)
                lw += w_obj.width + space_w
            line_widths.append(max(0.0, lw - space_w))

        group.width = max(line_widths) if line_widths else 100.0
        group.height = (len(group.lines) * line_height) + ((len(group.lines) - 1) * ts.line_spacing_px)

        curr_y = 0.0
        for l_idx, line in enumerate(group.lines):
            lw = line_widths[l_idx]
            curr_x = (group.width - lw) / 2.0  # STABLE CENTER ANCHOR
            baseline_y = curr_y + ascent + out.width
            
            for w_obj in line:
                w_obj.pos_x = curr_x
                w_obj.pos_y = baseline_y
                w_obj.center_x = curr_x + (w_obj.width / 2.0)
                w_obj.center_y = baseline_y - (ascent / 2.0) + (descent / 2.0)
                curr_x += w_obj.width + space_w
            curr_y += line_height + ts.line_spacing_px

        return int(group.width), int(group.height)

    def render_caption_group_overlay(self, group: CaptionGroup, frame_time_ms: float,
                                     ts: TextStyleProfile, out: OutlineProfile,
                                     ep: EffectsProfile, wh: WordHighlightProfile,
                                     awa: ActiveWordAnimationProfile,
                                     anim: Dict[str, Any]) -> Tuple[Image.Image, int, int]:
        font = self.get_font(ts.font_family, ts.font_size, ts.bold, ts.italic)
        group_w, group_h = self.layout_caption_group(group, font, ts, out)

        pad = 160 + (out.outer_width if out.double_outline else out.width * 2)
        cw, ch = int(group_w + pad), int(group_h + pad)
        overlay = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)

        origin_x = pad / 2.0
        origin_y = pad / 2.0

        f_rgba = (ts.get_text_rgba()[0], ts.get_text_rgba()[1], ts.get_text_rgba()[2], int(ts.get_text_rgba()[3] * anim["alpha_factor"]))
        o_rgba = (out.get_rgba()[0], out.get_rgba()[1], out.get_rgba()[2], int(out.get_rgba()[3] * anim["alpha_factor"]))

        active_word: Optional[Word] = None
        for w_obj in group.words:
            if w_obj.start_ms <= frame_time_ms < w_obj.end_ms:
                active_word = w_obj
                break
        if not active_word and group.words and frame_time_ms >= group.words[-1].end_ms:
            if frame_time_ms <= group.end_ms:
                active_word = group.words[-1]

        # 1. RENDER ACTIVE HIGHLIGHT BACKGROUND (NORMALIZED WORD PROGRESS TIMING)
        if wh.enabled and active_word:
            hp = wh.params
            act_dur = max(1.0, active_word.end_ms - active_word.start_ms)
            normalized_progress = min(1.0, max(0.0, (frame_time_ms - active_word.start_ms) / act_dur))
            s_x, s_y, dx, dy, _ = AnimationManager.evaluate_active_word_transform(awa.anim_type, normalized_progress, awa.params)

            box_cx = origin_x + active_word.center_x + dx
            box_cy = origin_y + active_word.center_y + dy

            if wh.mode == "Background Box":
                p_l = hp.get("pad_left", 16.0)
                p_r = hp.get("pad_right", 16.0)
                p_t = hp.get("pad_top", 10.0)
                p_b = hp.get("pad_bottom", 10.0)
                
                sc_x = hp.get("scale_x", 1.0) * s_x
                sc_y = hp.get("scale_y", 1.0) * s_y
                off_x = hp.get("offset_x", 0.0)
                off_y = hp.get("offset_y", 0.0)

                base_w = active_word.width + p_l + p_r
                base_h = active_word.ascent + active_word.descent + p_t + p_b

                scaled_w = base_w * sc_x
                scaled_h = base_h * sc_y

                bx0 = box_cx + off_x - (scaled_w / 2.0)
                by0 = box_cy + off_y - (scaled_h / 2.0)
                bx1 = bx0 + scaled_w
                by1 = by0 + scaled_h

                bg_col = hex_to_rgba(hp.get("bg_color", "#FF0055"), hp.get("bg_opacity", 0.95))
                c_rad = hp.get("corner_radius", 12.0)

                if hp.get("shadow_enable", False):
                    so_x = hp.get("shadow_ox", 4.0)
                    so_y = hp.get("shadow_oy", 4.0)
                    draw.rounded_rectangle([bx0 + so_x, by0 + so_y, bx1 + so_x, by1 + so_y], radius=c_rad, fill=(0, 0, 0, 140))

                if hp.get("bg_enable", True):
                    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=c_rad, fill=bg_col)

                b_w = hp.get("border_width", 0.0)
                if b_w > 0:
                    b_col = hex_to_rgba(hp.get("border_color", "#FFFFFF"), 1.0)
                    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=c_rad, outline=b_col, width=int(b_w))

            elif wh.mode == "Rounded Rectangle":
                pad_val = hp.get("padding", 12.0)
                sc = hp.get("scale", 1.0) * s_x
                off_x = hp.get("offset_x", 0.0)
                off_y = hp.get("offset_y", 0.0)

                base_w = (active_word.width + pad_val * 2.0) * sc
                base_h = (active_word.ascent + active_word.descent + pad_val * 2.0) * sc

                bx0 = box_cx + off_x - (base_w / 2.0)
                by0 = box_cy + off_y - (base_h / 2.0)
                bx1 = bx0 + base_w
                by1 = by0 + base_h

                fill_c = hex_to_rgba(hp.get("fill_color", "#00FFCC"), hp.get("opacity", 0.9))
                c_rad = hp.get("corner_radius", 16.0)
                draw.rounded_rectangle([bx0, by0, bx1, by1], radius=c_rad, fill=fill_c)

                b_w = hp.get("border_width", 2.0)
                if b_w > 0:
                    b_col = hex_to_rgba(hp.get("border_color", "#FFFFFF"), 1.0)
                    draw.rounded_rectangle([bx0, by0, bx1, by1], radius=c_rad, outline=b_col, width=int(b_w))

            elif wh.mode == "Underline":
                u_col = hex_to_rgba(hp.get("active_color", "#00FFCC"), 1.0)
                th = hp.get("thickness", 6.0)
                dist = hp.get("dist_from_text", 6.0)
                w_scale = hp.get("width_scale", 1.0)

                uw = active_word.width * w_scale
                ux0 = box_cx - (uw / 2.0)
                uy0 = origin_y + active_word.pos_y + dist
                ux1 = ux0 + uw

                draw.line([(ux0, uy0), (ux1, uy0)], fill=u_col, width=int(th))

        # 2. RENDER INACTIVE WORDS
        for w_obj in group.words:
            if w_obj == active_word:
                continue

            word_txt = w_obj.word
            if ts.case_mode == "Uppercase": word_txt = word_txt.upper()
            elif ts.case_mode == "Lowercase": word_txt = word_txt.lower()

            wx = origin_x + w_obj.pos_x
            wy = origin_y + w_obj.pos_y - w_obj.ascent

            if out.enabled and out.double_outline:
                outer_rgba = (out.get_outer_rgba()[0], out.get_outer_rgba()[1], out.get_outer_rgba()[2], int(out.get_outer_rgba()[3] * anim["alpha_factor"]))
                draw.text((wx, wy), word_txt, font=font, fill=f_rgba, stroke_width=out.outer_width, stroke_fill=outer_rgba)

            draw.text((wx, wy), word_txt, font=font, fill=f_rgba, stroke_width=out.width if out.enabled else 0, stroke_fill=o_rgba)

        # 3. RENDER ACTIVE WORD (NORMALIZED WORD PROGRESS TIMING)
        if active_word:
            word_txt = active_word.word
            if ts.case_mode == "Uppercase": word_txt = word_txt.upper()
            elif ts.case_mode == "Lowercase": word_txt = word_txt.lower()

            act_dur = max(1.0, active_word.end_ms - active_word.start_ms)
            normalized_progress = min(1.0, max(0.0, (frame_time_ms - active_word.start_ms) / act_dur))
            s_x, s_y, dx, dy, rot = AnimationManager.evaluate_active_word_transform(awa.anim_type, normalized_progress, awa.params)

            active_color_hex = wh.params.get("active_color", "#00FFCC")
            active_fill = hex_to_rgba(active_color_hex, anim["alpha_factor"])

            w_surf, sw, sh_size = self._render_single_word_surface(word_txt, font, active_fill, out, anim["alpha_factor"], ep, ts, frame_time_ms)

            mode_scale = 1.0
            if wh.mode == "Scale & Color":
                mode_scale = wh.params.get("scale", 1.22)

            final_scale_x = mode_scale * s_x
            final_scale_y = mode_scale * s_y
            
            if final_scale_x != 1.0 or final_scale_y != 1.0:
                nw = max(1, int(sw * final_scale_x))
                nh = max(1, int(sh_size * final_scale_y))
                w_surf = w_surf.resize((nw, nh), Image.Resampling.LANCZOS)

            if rot != 0.0:
                w_surf = w_surf.rotate(rot, resample=Image.Resampling.BICUBIC, expand=True)

            px = int(origin_x + active_word.center_x + dx - w_surf.width / 2.0)
            py = int(origin_y + active_word.center_y + dy - w_surf.height / 2.0)
            overlay.paste(w_surf, (px, py), w_surf)

        return overlay, cw, ch

    def _render_single_word_surface(self, word_txt: str, font: ImageFont.FreeTypeFont, 
                                     fill_rgba: Tuple[int, int, int, int], out: OutlineProfile, 
                                     alpha_factor: float, ep: EffectsProfile, 
                                     ts: TextStyleProfile, frame_time_ms: float) -> Tuple[Image.Image, int, int]:
        bbox = font.getbbox(word_txt)
        ascent, descent = font.getmetrics()
        w_raw = (bbox[2] - bbox[0]) + (len(word_txt) * ts.letter_spacing)
        h_raw = ascent + descent

        pad = 60 + (out.outer_width if out.double_outline else out.width * 2)
        sw = max(1, int(w_raw + pad))
        sh = max(1, int(h_raw + pad))

        surf = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        draw = ImageDraw.Draw(surf)

        lx = (sw - w_raw) / 2.0
        ly = (sh - h_raw) / 2.0

        o_rgba = (out.get_rgba()[0], out.get_rgba()[1], out.get_rgba()[2], int(out.get_rgba()[3] * alpha_factor))

        if out.enabled and out.double_outline:
            outer_rgba = (out.get_outer_rgba()[0], out.get_outer_rgba()[1], out.get_outer_rgba()[2], int(out.get_outer_rgba()[3] * alpha_factor))
            draw.text((lx, ly), word_txt, font=font, fill=fill_rgba, stroke_width=out.outer_width, stroke_fill=outer_rgba)

        draw.text((lx, ly), word_txt, font=font, fill=fill_rgba, stroke_width=out.width if out.enabled else 0, stroke_fill=o_rgba)
        
        surf = EffectManager.apply_word_effect(surf, ep.mode, frame_time_ms)
        return surf, sw, sh

    def compose_full_frame(self, group: Optional[CaptionGroup], vp: VideoProfile, 
                           ts: TextStyleProfile, out: OutlineProfile, 
                           sh: ShadowProfile, gl: GlowProfile, 
                           ap: AnimationProfile, lp: LayoutProfile, 
                           ep: EffectsProfile, wh: WordHighlightProfile, 
                           awa: ActiveWordAnimationProfile,
                           frame_time_ms: float) -> Image.Image:
        frame = Image.new("RGBA", (vp.width, vp.height), vp.get_rgba())
        if not group or not group.words:
            return frame

        dur_ms = max(1.0, group.end_ms - group.start_ms)
        anim = AnimationManager.evaluate_stage(ap, frame_time_ms - group.start_ms, group.end_ms - frame_time_ms, dur_ms)

        overlay, ow, oh = self.render_caption_group_overlay(group, frame_time_ms, ts, out, ep, wh, awa, anim)

        sf = anim["scale_factor"]
        if sf != 1.0 and ow > 0 and oh > 0:
            nw, nh = max(1, int(ow * sf)), max(1, int(oh * sf))
            overlay = overlay.resize((nw, nh), Image.Resampling.LANCZOS)
            ow, oh = nw, nh

        fx, fy = PositionManager.calculate(lp.anchor, ow, oh, vp.width, vp.height, 
                                           lp.custom_positioning, lp.custom_x_pct, lp.custom_y_pct, 
                                           anim["offset_x"], anim["offset_y"])

        comp = Image.new("RGBA", (vp.width, vp.height), (0, 0, 0, 0))

        # Glow Layer
        if gl.enabled and anim["alpha_factor"] > 0:
            g_rgba = (gl.get_rgba()[0], gl.get_rgba()[1], gl.get_rgba()[2], int(gl.get_rgba()[3] * anim["alpha_factor"]))
            glow_mask = overlay.split()[3].filter(ImageFilter.GaussianBlur(gl.size))
            glow_sol = Image.new("RGBA", (ow, oh), g_rgba)
            glow_b = Image.composite(glow_sol, Image.new("RGBA", (ow, oh)), glow_mask)
            comp.paste(glow_b, (fx, fy), glow_b)

        # Shadow Layer
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
# DYNAMIC COLLAPSIBLE PROPERTY UI GENERATOR
# ==============================================================================

class CollapsibleFrame(ttk.Frame):
    def __init__(self, parent, title: str = "", collapsed: bool = False):
        super().__init__(parent)
        self.collapsed = collapsed
        self.title = title

        self.btn = tk.Button(
            self,
            text=f"{'▶' if self.collapsed else '▼'}  {title}",
            anchor="w",
            bg="#2B2B36",
            fg="#FFFFFF",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=8,
            pady=4,
            activebackground="#0969DA",
            activeforeground="#FFFFFF",
            command=self.toggle
        )
        self.btn.pack(fill=tk.X, expand=True, pady=(2, 2))

        self.sub_frame = ttk.Frame(self, style="Card.TFrame", padding=6)
        if not self.collapsed:
            self.sub_frame.pack(fill=tk.BOTH, expand=True)

    def toggle(self):
        self.collapsed = not self.collapsed
        self.btn.configure(text=f"{'▶' if self.collapsed else '▼'}  {self.title}")
        if self.collapsed:
            self.sub_frame.pack_forget()
        else:
            self.sub_frame.pack(fill=tk.BOTH, expand=True)


class DynamicPropertyEditor(ttk.Frame):
    """Generic Property System UI Generator that builds accordion property panels."""

    def __init__(self, parent, specs: List[ParamSpec], data_dict: Dict[str, Any], on_change_callback):
        super().__init__(parent, style="Card.TFrame")
        self.specs = specs
        self.data_dict = data_dict
        self.on_change_callback = on_change_callback

        categories: Dict[str, List[ParamSpec]] = {}
        for s in specs:
            categories.setdefault(s.category, []).append(s)

        for cat_title, cat_specs in categories.items():
            col_frame = CollapsibleFrame(self, title=cat_title, collapsed=False)
            col_frame.pack(fill=tk.X, expand=True, pady=2)

            for idx, spec in enumerate(cat_specs):
                if spec.key not in self.data_dict:
                    self.data_dict[spec.key] = spec.default

                row_f = ttk.Frame(col_frame.sub_frame, style="Card.TFrame")
                row_f.pack(fill=tk.X, pady=3)

                lbl = ttk.Label(row_f, text=f"{spec.label}:", style="Card.TLabel", width=16)
                lbl.pack(side=tk.LEFT, anchor=tk.W)

                if spec.type == "bool":
                    var = tk.BooleanVar(value=bool(self.data_dict[spec.key]))
                    chk = ttk.Checkbutton(row_f, variable=var, command=lambda s=spec.key, v=var: self._on_bool_change(s, v))
                    chk.pack(side=tk.LEFT, anchor=tk.W)

                elif spec.type == "color":
                    btn_f = ttk.Frame(row_f, style="Card.TFrame")
                    btn_f.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    
                    swatch = tk.Label(btn_f, width=4, bg=str(self.data_dict[spec.key]), relief="solid", bd=1)
                    swatch.pack(side=tk.LEFT, padx=(0, 6))

                    btn = tk.Button(btn_f, text="Pick...", font=("Segoe UI", 8), bg="#2B2B36", fg="#FFFFFF", relief="flat",
                                    command=lambda s=spec.key, sw=swatch: self._on_color_pick(s, sw))
                    btn.pack(side=tk.LEFT)

                elif spec.type == "combo":
                    c_var = tk.StringVar(value=str(self.data_dict[spec.key]))
                    cb = ttk.Combobox(row_f, textvariable=c_var, values=spec.options, state="readonly", width=14)
                    cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
                    cb.bind("<<ComboboxSelected>>", lambda e, s=spec.key, v=c_var: self._on_combo_change(s, v))

                elif spec.type in ["float", "int"]:
                    curr_val = self.data_dict[spec.key]
                    val_lbl = ttk.Label(row_f, text=f"{curr_val:.2f}" if spec.type == "float" else f"{int(curr_val)}", width=6, style="Muted.TLabel")
                    val_lbl.pack(side=tk.RIGHT)

                    sc = ttk.Scale(row_f, from_=spec.min_val, to=spec.max_val, orient=tk.HORIZONTAL)
                    sc.set(float(curr_val))
                    sc.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
                    sc.configure(command=lambda val, s=spec.key, t=spec.type, vl=val_lbl: self._on_scale_change(s, val, t, vl))

    def _on_bool_change(self, key: str, var: tk.BooleanVar):
        self.data_dict[key] = var.get()
        self.on_change_callback()

    def _on_color_pick(self, key: str, swatch: tk.Label):
        c = colorchooser.askcolor(initialcolor=str(self.data_dict[key]))
        if c[1]:
            self.data_dict[key] = c[1]
            swatch.configure(bg=c[1])
            self.on_change_callback()

    def _on_combo_change(self, key: str, var: tk.StringVar):
        self.data_dict[key] = var.get()
        self.on_change_callback()

    def _on_scale_change(self, key: str, raw_val: str, val_type: str, val_lbl: ttk.Label):
        v = float(raw_val)
        if val_type == "int":
            v = int(round(v))
            val_lbl.configure(text=f"{v}")
        else:
            val_lbl.configure(text=f"{v:.2f}")
        self.data_dict[key] = v
        self.on_change_callback()


# ==============================================================================
# TEMPLATE LIBRARY BROWSER DIALOG WIDGET
# ==============================================================================

class TemplateBrowserDialog(tk.Toplevel):
    """Visual Template Browser Dialog supporting Categories, Search, Favorites & Instant Loading."""

    def __init__(self, parent: Any, app_ref: Any):
        super().__init__(parent)
        self.title("Caption Studio Pro Template Library Browser")
        self.geometry("960x650")
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#121214")

        self.app_ref = app_ref
        self.selected_template_path: Optional[str] = None
        self.thumb_image_cache: Dict[str, ImageTk.PhotoImage] = {}
        self.template_list: List[Dict[str, Any]] = []

        CaptionTemplateManager.ensure_directories()
        self.favorites = CaptionTemplateManager.load_favorites()
        self.recents = CaptionTemplateManager.load_recent()

        self._build_ui()
        self._rescan_templates()

    def _build_ui(self):
        top_bar = tk.Frame(self, bg="#1E1E24", padx=12, pady=10)
        top_bar.pack(fill=tk.X)

        tk.Label(top_bar, text="🎨 Template Library", bg="#1E1E24", fg="#38BDF8", font=("Segoe UI", 14, "bold")).pack(side=tk.LEFT)

        tk.Label(top_bar, text="🔍", bg="#1E1E24", fg="#FFFFFF", font=("Segoe UI", 11)).pack(side=tk.LEFT, padx=(20, 4))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *args: self._filter_and_render_grid())
        search_entry = tk.Entry(top_bar, textvariable=self.search_var, bg="#18181C", fg="#FFFFFF", insertbackground="#FFFFFF", width=22, relief="flat", highlightthickness=1, highlightbackground="#2D2D38")
        search_entry.pack(side=tk.LEFT, padx=4)

        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, bg="#2D2D38", bd=0, sashwidth=4)
        paned.pack(fill=tk.BOTH, expand=True)

        sidebar = tk.Frame(paned, bg="#18181C", width=180, padx=8, pady=10)
        paned.add(sidebar, minsize=160)

        self.cat_var = tk.StringVar(value="All")
        categories = ["All", "Built-in", "User", "Favorites ⭐", "Recently Used 🕒"]
        for cat in categories:
            btn = tk.Radiobutton(
                sidebar, text=cat, variable=self.cat_var, value=cat,
                bg="#18181C", fg="#CCCCCC", selectcolor="#0969DA",
                activebackground="#18181C", activeforeground="#FFFFFF",
                indicatoron=False, relief="flat", anchor="w", padx=10, pady=6,
                font=("Segoe UI", 10, "bold"),
                command=self._filter_and_render_grid
            )
            btn.pack(fill=tk.X, pady=2)

        grid_container = tk.Frame(paned, bg="#121214")
        paned.add(grid_container, minsize=500)

        self.canvas = tk.Canvas(grid_container, bg="#121214", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(grid_container, orient="vertical", command=self.canvas.yview)
        self.grid_frame = tk.Frame(self.canvas, bg="#121214")

        self.grid_frame.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.grid_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.bind_all("<MouseWheel>", lambda e: self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units"))

    def _rescan_templates(self):
        self.template_list.clear()
        base_dir = CaptionTemplateManager.TEMPLATE_DIR

        for root_dir, _, files in os.walk(base_dir):
            for file in files:
                if file.endswith(".cstemplate"):
                    f_path = os.path.join(root_dir, file)
                    try:
                        with open(f_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            data["_filepath"] = f_path
                            self.template_list.append(data)
                    except Exception:
                        continue

        self._filter_and_render_grid()

    def _filter_and_render_grid(self):
        for child in self.grid_frame.winfo_children():
            child.destroy()

        query = self.search_var.get().lower().strip()
        category = self.cat_var.get()

        filtered = []
        for t in self.template_list:
            meta = t.get("metadata", {})
            t_name = meta.get("name", "Untitled")
            f_path = t.get("_filepath", "")

            if query and query not in t_name.lower():
                continue

            if category == "Built-in" and "Built-in" not in f_path:
                continue
            elif category == "User" and "User" not in f_path:
                continue
            elif category == "Favorites ⭐" and f_path not in self.favorites:
                continue
            elif category == "Recently Used 🕒" and f_path not in self.recents:
                continue

            filtered.append(t)

        cols = 3
        for idx, t in enumerate(filtered):
            r = idx // cols
            c = idx % cols

            meta = t.get("metadata", {})
            f_path = t.get("_filepath", "")
            t_name = meta.get("name", "Untitled")
            author = meta.get("author", "Unknown")

            card = tk.Frame(self.grid_frame, bg="#1E1E24", padx=6, pady=6, highlightthickness=1, highlightbackground="#2D2D38")
            card.grid(row=r, column=c, padx=8, pady=8, sticky="nsew")

            thumb_img = self._get_thumbnail(meta.get("thumbnail_b64", ""))
            lbl_img = tk.Label(card, image=thumb_img, bg="#121214")
            lbl_img.image = thumb_img
            lbl_img.pack(fill=tk.X)

            lbl_title = tk.Label(card, text=t_name, bg="#1E1E24", fg="#FFFFFF", font=("Segoe UI", 10, "bold"), anchor="w")
            lbl_title.pack(fill=tk.X, pady=(4, 0))

            lbl_sub = tk.Label(card, text=f"By: {author}", bg="#1E1E24", fg="#9DA4B0", font=("Segoe UI", 8), anchor="w")
            lbl_sub.pack(fill=tk.X)

            is_fav = f_path in self.favorites
            fav_btn = tk.Label(card, text="⭐" if is_fav else "☆", bg="#1E1E24", fg="#FFCC00", font=("Segoe UI", 11), cursor="hand2")
            fav_btn.pack(anchor="e")
            fav_btn.bind("<Button-1>", lambda e, p=f_path: self._toggle_favorite(p))

            card.bind("<Double-Button-1>", lambda e, data=t: self._apply_template(data))
            lbl_img.bind("<Double-Button-1>", lambda e, data=t: self._apply_template(data))
            lbl_title.bind("<Double-Button-1>", lambda e, data=t: self._apply_template(data))

    def _get_thumbnail(self, b64_str: str) -> ImageTk.PhotoImage:
        if not b64_str:
            img = Image.new("RGBA", (140, 80), (30, 30, 36, 255))
            return ImageTk.PhotoImage(img)

        try:
            raw_bytes = base64.b64decode(b64_str)
            img = Image.open(BytesIO(raw_bytes))
            img.thumbnail((160, 90), Image.Resampling.LANCZOS)
            return ImageTk.PhotoImage(img)
        except Exception:
            img = Image.new("RGBA", (140, 80), (30, 30, 36, 255))
            return ImageTk.PhotoImage(img)

    def _toggle_favorite(self, path: str):
        if path in self.favorites:
            self.favorites.remove(path)
        else:
            self.favorites.append(path)
        CaptionTemplateManager.save_favorites(self.favorites)
        self._filter_and_render_grid()

    def _apply_template(self, t_data: Dict[str, Any]):
        f_path = t_data.get("_filepath", "")
        CaptionTemplateManager.add_recent(f_path)
        CaptionTemplateManager.deserialize_into_workspace(self.app_ref, t_data)
        self.app_ref.append_log(f"Caption Template loaded successfully: '{t_data.get('metadata', {}).get('name')}'", "SUCCESS")
        self.destroy()


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
                 wh: WordHighlightProfile, awa: ActiveWordAnimationProfile, gp: GroupingProfile,
                 q: queue.Queue, cancel: threading.Event):
        super().__init__()
        self.srt, self.out, self.vp, self.ts, self.out_p, self.sh, self.gl, self.ap, self.lp, self.ep, self.wh, self.awa, self.gp = srt, out, vp, ts, out_p, sh, gl, ap, lp, ep, wh, awa, gp
        self.q, self.cancel = q, cancel
        self.renderer = SubtitleRenderer()

    def run(self):
        writer = None
        base = os.path.splitext(os.path.basename(self.srt))[0]
        target = os.path.join(self.out, f"{base}_captionstudio_output.mp4")
        try:
            self.q.put(("LOG", ("Parsing Word Timeline Engine timestamps...", "INFO")))
            words = WordTimelineEngine.parse_srt_to_words(self.srt)
            
            if not words:
                self.q.put(("ERROR", "The selected SRT script file holds no active word entries."))
                return

            self.q.put(("LOG", (f"Smart Caption Group Engine grouping {len(words)} words...", "INFO")))
            groups = SmartCaptionGroupEngine.build_caption_groups(words, self.gp, self.vp, self.ts, self.out_p, self.wh)

            writer = FFmpegStreamWriter(target, self.vp)
            writer.start()

            total_sec = (groups[-1].end_ms / 1000.0) + 1.0
            total_frames = math.ceil(total_sec * self.vp.fps)
            cursor = 0
            start_t = time.time()
            last_ui = 0.0

            for f in range(total_frames):
                if self.cancel.is_set(): break
                cm = (f / float(self.vp.fps)) * 1000.0
                while cursor < len(groups) and cm > groups[cursor].end_ms: cursor += 1
                
                active_group = None
                if cursor < len(groups) and groups[cursor].start_ms <= cm <= groups[cursor].end_ms:
                    active_group = groups[cursor]

                f_img = self.renderer.compose_full_frame(active_group, self.vp, self.ts, self.out_p, self.sh, self.gl, 
                                                         self.ap, self.lp, self.ep, self.wh, self.awa, cm)
                writer.write(f_img)

                now = time.time()
                if now - last_ui > 0.12 or f == total_frames - 1:
                    last_ui = now
                    el = now - start_t
                    fps = (f + 1) / el if el > 0 else 0.0
                    eta = (total_frames - (f + 1)) / fps if fps > 0 else 0.0
                    display_txt = active_group.text if active_group else ""
                    self.q.put(("PROGRESS", {"pct": ((f+1)/total_frames)*100, "f": f+1, "tf": total_frames, "speed": fps, "el": el, "eta": eta, "txt": display_txt}))

            errs = writer.close()
            RenderCacheManager.clear()
            if self.cancel.is_set():
                if os.path.exists(target): os.remove(target)
                self.q.put(("CANCELLED", "Operational queue aborted safely."))
            elif errs: self.q.put(("ERROR", f"FFmpeg execution log:\n{errs}"))
            else: self.q.put(("COMPLETE", target))
        except Exception as e:
            if writer: writer.close()
            self.q.put(("ERROR", f"Critical processing engine fault:\n{str(e)}"))


# ==============================================================================
# COMMERCIAL DESKTOP SUITE MAIN WINDOW INTERFACE
# ==============================================================================

class MainWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CaptionStudio Pro Desktop Edition V3")
        self.root.geometry("1420x920")
        self.root.minsize(1200, 820)

        # Profiles State Binding Matrix
        self.vp = VideoProfile()
        self.ts = TextStyleProfile()
        self.out_p = OutlineProfile()
        self.sh = ShadowProfile()
        self.gl = GlowProfile()
        self.ap = AnimationProfile()
        self.lp = LayoutProfile()
        self.ep = EffectsProfile()
        self.wh = WordHighlightProfile()
        self.awa = ActiveWordAnimationProfile()
        self.gp = GroupingProfile()

        populate_default_params(self.wh, self.wh.mode, HIGHLIGHT_MODE_SPECS)
        populate_default_params(self.awa, self.awa.anim_type, MOTION_MODE_SPECS)

        # Dummy Preview Loop State
        self.preview_time_ms = 0.0
        self.preview_timer_id = None

        self.q, self.cancel, self.worker = queue.Queue(), threading.Event(), None
        self.preview_renderer = SubtitleRenderer()
        self.block_updates = False
        self.preset_buttons: Dict[str, tk.Button] = {}

        self.highlight_prop_container: Optional[ttk.Frame] = None
        self.motion_prop_container: Optional[ttk.Frame] = None

        self._apply_dark_theme_tokens()
        self._build_top_menu_bar()
        self._assemble_layout_grid()
        self._sync_profiles_into_ui()
        self._start_continuous_live_preview_loop()

    def _apply_dark_theme_tokens(self):
        """Applies a consistent, professional Dark Palette across all Tkinter / TTK widgets."""
        self.c_bg = "#121214"
        self.c_card = "#1E1E24"
        self.c_input = "#18181C"
        self.c_text = "#FFFFFF"
        self.c_muted = "#9DA4B0"
        self.c_accent = "#0969DA"
        self.c_accent_l = "#1C3D6E"
        self.c_border = "#2D2D38"

        self.root.configure(bg=self.c_bg)
        s = ttk.Style()
        s.theme_use("clam")
        
        # General TTK Elements
        s.configure(".", background=self.c_bg, foreground=self.c_text, font=("Segoe UI", 10), bordercolor=self.c_border)
        s.configure("Card.TFrame", background=self.c_card, relief="flat")
        s.configure("TLabel", background=self.c_bg, foreground=self.c_text)
        s.configure("Card.TLabel", background=self.c_card, foreground=self.c_text)
        s.configure("Logo.TLabel", background=self.c_card, foreground="#38BDF8", font=("Segoe UI", 18, "bold"))
        s.configure("Section.TLabel", background=self.c_card, foreground="#38BDF8", font=("Segoe UI", 11, "bold"))
        s.configure("Muted.TLabel", background=self.c_card, foreground=self.c_muted, font=("Segoe UI", 9))
        
        # Inputs & Selectors
        s.configure("TCheckbutton", background=self.c_card, foreground=self.c_text)
        s.map("TCheckbutton", background=[("active", self.c_card)])

        s.configure("TEntry", fieldbackground=self.c_input, foreground=self.c_text, bordercolor=self.c_border, lightcolor=self.c_border, darkcolor=self.c_border)
        
        s.configure("TCombobox", fieldbackground=self.c_input, background="#2B2B36", foreground=self.c_text, arrowcolor="#FFFFFF", bordercolor=self.c_border, lightcolor=self.c_border, darkcolor=self.c_border)
        s.map("TCombobox", fieldbackground=[("readonly", self.c_input)], selectbackground=[("readonly", self.c_accent)], selectforeground=[("readonly", "#FFFFFF")])
        
        s.configure("TSpinbox", fieldbackground=self.c_input, background="#2B2B36", foreground=self.c_text, arrowcolor="#FFFFFF", bordercolor=self.c_border, lightcolor=self.c_border, darkcolor=self.c_border)
        s.map("TSpinbox", fieldbackground=[("readonly", self.c_input)])

        # Progressbar & Buttons
        s.configure("Horizontal.TProgressbar", background=self.c_accent, troughcolor=self.c_bg, bordercolor=self.c_border, thickness=8)
        s.configure("TButton", background="#2B2B36", foreground=self.c_text, font=("Segoe UI", 9, "bold"), padding=5, borderwidth=0)
        s.map("TButton", background=[("active", self.c_accent_l)], foreground=[("active", "#FFFFFF")])
        s.configure("Action.TButton", background=self.c_accent, foreground="#FFFFFF", font=("Segoe UI", 10, "bold"), padding=8)
        s.map("Action.TButton", background=[("active", "#0550AE")])
        s.configure("Cancel.TButton", background="#CF222E", foreground="#FFFFFF", font=("Segoe UI", 10, "bold"), padding=8)
        s.map("Cancel.TButton", background=[("active", "#A40E1B")])

        # Scrollbars & Treeviews
        s.configure("Vertical.TScrollbar", background="#2B2B36", troughcolor=self.c_bg, bordercolor=self.c_bg, arrowcolor="#FFFFFF")
        s.configure("Horizontal.TScrollbar", background="#2B2B36", troughcolor=self.c_bg, bordercolor=self.c_bg, arrowcolor="#FFFFFF")
        
        s.configure("Treeview", background=self.c_input, foreground=self.c_text, fieldbackground=self.c_input, bordercolor=self.c_border)
        s.configure("Treeview.Heading", background="#2B2B36", foreground=self.c_text, relief="flat")

    def _build_top_menu_bar(self):
        menubar = tk.Menu(self.root, bg="#1E1E24", fg="#FFFFFF", activebackground="#0969DA", activeforeground="#FFFFFF", bd=0)

        # File Menu
        file_menu = tk.Menu(menubar, tearoff=0, bg="#1E1E24", fg="#FFFFFF", activebackground="#0969DA", activeforeground="#FFFFFF")
        file_menu.add_command(label="Open SRT Subtitle...", command=self._cb_browse_srt)
        file_menu.add_separator()
        file_menu.add_command(label="Export Caption Template... (.cstemplate)", command=self._menu_export_caption_template)
        file_menu.add_command(label="Import Caption Template... (.cstemplate)", command=self._menu_import_caption_template)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Template Menu
        template_menu = tk.Menu(menubar, tearoff=0, bg="#1E1E24", fg="#FFFFFF", activebackground="#0969DA", activeforeground="#FFFFFF")
        template_menu.add_command(label="Open Template Library Browser", command=self._menu_open_template_browser)
        template_menu.add_command(label="Save Current Template", command=self._menu_save_template)
        menubar.add_cascade(label="Template", menu=template_menu)

        self.root.config(menu=menubar)

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

        paned.add(left_box, minsize=600, stretch="always")
        paned.add(right_box, minsize=580, stretch="always")

        self._build_header_logo_card()
        self._build_io_card()
        self._build_smart_grouping_card()
        self._build_visual_presets_grid_card()  
        self._build_typography_card()
        self._build_effects_card()
        self._build_animation_card()
        self._build_dynamic_active_word_editor_card()
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
        ttk.Label(card, text="CaptionStudio Pro ✨", style="Logo.TLabel").pack(anchor=tk.W)
        ttk.Label(card, text="Commercial Video Caption Engine & Intelligent Layout Studio", style="Muted.TLabel").pack(anchor=tk.W, pady=(2, 0))

    def _build_io_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="1. Core IO Settings & Chroma Key", style="Section.TLabel").grid(row=0, column=0, columnspan=3, sticky=tk.W, pady=(0, 8))
        
        ttk.Label(card, text="Subtitle SRT:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ui_srt = tk.StringVar()
        ttk.Entry(card, textvariable=self.ui_srt).grid(row=1, column=1, sticky=tk.EW, padx=6)
        ttk.Button(card, text="Browse", command=self._cb_browse_srt).grid(row=1, column=2, sticky=tk.E)

        ttk.Label(card, text="Output Folder:", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ui_out = tk.StringVar()
        ttk.Entry(card, textvariable=self.ui_out).grid(row=2, column=1, sticky=tk.EW, padx=6)
        ttk.Button(card, text="Browse", command=self._cb_browse_out).grid(row=2, column=2, sticky=tk.E)

        ttk.Label(card, text="Chroma Background:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_bg_mode = ttk.Combobox(card, values=["Green", "Blue", "Black", "White", "Custom"], state="readonly", width=12)
        self.ui_bg_mode.grid(row=3, column=1, sticky=tk.W, padx=6)
        self.ui_bg_mode.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())
        tk.Button(card, text="Hex Picker", font=("Segoe UI", 8), command=self._cb_pick_bg).grid(row=3, column=2, sticky=tk.E)
        card.columnconfigure(1, weight=1)

    def _build_smart_grouping_card(self):
        """Updated Smart Layout Engine Settings Card."""
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="2. Smart Layout & Safe Area Engine", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(card, text="Preferred Words Per Line:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ui_pref_w_line = ttk.Spinbox(card, from_=1, to=8, width=6, command=lambda: self._read_ui_to_profiles())
        self.ui_pref_w_line.grid(row=1, column=1, sticky=tk.W, padx=6)

        ttk.Label(card, text="Maximum Lines:", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ui_max_lines = ttk.Spinbox(card, from_=1, to=4, width=6, command=lambda: self._read_ui_to_profiles())
        self.ui_max_lines.grid(row=2, column=1, sticky=tk.W, padx=6)

        ttk.Label(card, text="Screen Safe Margin (px):", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_safe_margin = ttk.Spinbox(card, from_=0, to=300, increment=10, width=6, command=lambda: self._read_ui_to_profiles())
        self.ui_safe_margin.grid(row=3, column=1, sticky=tk.W, padx=6)

        self.ui_enable_safe = tk.BooleanVar(value=True)
        ttk.Checkbutton(card, text="Enable Screen Safe Area Enforcement", variable=self.ui_enable_safe, command=lambda: self._read_ui_to_profiles()).grid(row=4, column=0, columnspan=2, sticky=tk.W, pady=4)

    def _build_visual_presets_grid_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(card, text="3. Built-in Premium Caption Styles", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 2))
        ttk.Label(card, text="Select a commercial preset to instantly configure workspace styles.", style="Muted.TLabel").pack(anchor=tk.W, pady=(0, 10))

        self.presets_grid_frame = ttk.Frame(card, style="Card.TFrame")
        self.presets_grid_frame.pack(fill=tk.X, pady=(0, 12))
        
        self._refresh_visual_presets_grid()

        f_save = ttk.Frame(card, style="Card.TFrame")
        f_save.pack(fill=tk.X)
        ttk.Button(f_save, text="📁 Open Template Browser", command=self._menu_open_template_browser).pack(side="left", padx=2)
        ttk.Button(f_save, text="💾 Save Template...", command=self._menu_save_template).pack(side="left", padx=2)

    def _refresh_visual_presets_grid(self):
        for btn in self.preset_buttons.values(): btn.destroy()
        self.preset_buttons.clear()

        names = StyleManager.get_all_presets_names()
        cols = 3
        for i, name in enumerate(names):
            r = i // cols
            c = i % cols
            
            btn = tk.Button(
                self.presets_grid_frame, 
                text=name, 
                font=("Segoe UI", 8, "bold"),
                bg="#2B2B36", 
                fg=self.c_text, 
                activebackground=self.c_accent_l,
                activeforeground="#FFFFFF",
                relief="flat", 
                bd=1, 
                padx=4, 
                pady=6,
                command=lambda n=name: self._cb_trigger_visual_style_select(n)
            )
            btn.grid(row=r, column=c, sticky=tk.EW, padx=2, pady=2)
            self.preset_buttons[name] = btn

        for c in range(cols): self.presets_grid_frame.columnconfigure(c, weight=1)

    def _build_typography_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="4. Typography & Font Selector", style="Section.TLabel").grid(row=0, column=0, columnspan=4, sticky=tk.W, pady=(0, 8))

        ttk.Label(card, text="Font Family:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        
        font_picker_frame = ttk.Frame(card, style="Card.TFrame")
        font_picker_frame.grid(row=1, column=1, columnspan=3, sticky=tk.EW, pady=4, padx=(4, 0))
        
        self.lbl_selected_font = tk.Label(font_picker_frame, text=self.ts.font_family, bg="#121214", fg="#FFFFFF", font=("Segoe UI", 10, "bold"), anchor="w", padx=8)
        self.lbl_selected_font.pack(side=tk.LEFT, fill=tk.X, expand=True)
        tk.Button(font_picker_frame, text="Aa Pick Font...", font=("Segoe UI", 9, "bold"), bg="#0969DA", fg="#FFFFFF", relief="flat", command=self._cb_open_font_picker).pack(side=tk.RIGHT)

        ttk.Label(card, text="Size (px):", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ui_size = ttk.Spinbox(card, from_=10, to=400, width=6, command=lambda: self._read_ui_to_profiles())
        self.ui_size.grid(row=2, column=1, sticky=tk.W, pady=4, padx=4)

        self.ui_bold = tk.BooleanVar()
        ttk.Checkbutton(card, text="Bold", variable=self.ui_bold, command=lambda: self._read_ui_to_profiles()).grid(row=2, column=2, sticky=tk.W)
        self.ui_italic = tk.BooleanVar()
        ttk.Checkbutton(card, text="Italic", variable=self.ui_italic, command=lambda: self._read_ui_to_profiles()).grid(row=2, column=3, sticky=tk.W)

        ttk.Label(card, text="Text Case:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_case = ttk.Combobox(card, values=["Normal", "Uppercase", "Lowercase", "Sentence Case"], state="readonly", width=12)
        self.ui_case.grid(row=3, column=1, sticky=tk.W, pady=4, padx=4)
        self.ui_case.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Letter Spacing:", style="Card.TLabel").grid(row=4, column=0, sticky=tk.W, pady=4)
        self.ui_let_spc = ttk.Scale(card, from_=-5, to=40, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_let_spc.grid(row=4, column=1, columnspan=3, sticky=tk.EW, pady=4, padx=(4, 0))

        ttk.Label(card, text="Text Face Color:", style="Card.TLabel").grid(row=5, column=0, sticky=tk.W, pady=4)
        tk.Button(card, text="Pick Text Color", font=("Segoe UI", 9), command=self._cb_pick_text).grid(row=5, column=1, sticky=tk.W, pady=4, padx=4)

        ttk.Label(card, text="Primary Stroke:", style="Card.TLabel").grid(row=6, column=0, sticky=tk.W, pady=4)
        self.ui_out_on = tk.BooleanVar()
        ttk.Checkbutton(card, text="Enable Stroke", variable=self.ui_out_on, command=lambda: self._read_ui_to_profiles()).grid(row=6, column=1, sticky=tk.W)
        tk.Button(card, text="Stroke Color", font=("Segoe UI", 9), command=self._cb_pick_out).grid(row=6, column=2, sticky=tk.W)

        ttk.Label(card, text="Stroke Width:", style="Card.TLabel").grid(row=7, column=0, sticky=tk.W, pady=4)
        self.ui_out_w = ttk.Scale(card, from_=0, to=30, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_out_w.grid(row=7, column=1, columnspan=3, sticky=tk.EW, pady=4, padx=(4, 0))
        card.columnconfigure(1, weight=1)

    def _build_effects_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="5. Multi-Layer Text Effects", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(card, text="Text Effect Style:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        effects_list = ["Standard", "Glass", "Chrome", "Metal", "Gold Foil", "Silver Foil", "Fire", "Ice", "Emboss", "Engrave", "RGB", "Cyberpunk"]
        self.ui_fx = ttk.Combobox(card, values=effects_list, state="readonly")
        self.ui_fx.grid(row=1, column=1, sticky=tk.EW, pady=4, padx=4)
        self.ui_fx.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        self.ui_dbl_out = tk.BooleanVar()
        ttk.Checkbutton(card, text="Enable Double Outline Outer Layer", variable=self.ui_dbl_out, command=lambda: self._read_ui_to_profiles()).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=4)
        card.columnconfigure(1, weight=1)

    def _build_animation_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="6. Kinetic Caption Animations", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 8))

        ttk.Label(card, text="Entry Animation:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ui_anim_entry = ttk.Combobox(card, values=AnimationManager.get_entry_animations(), state="readonly")
        self.ui_anim_entry.grid(row=1, column=1, sticky=tk.EW, pady=4, padx=4)
        self.ui_anim_entry.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Loop Animation:", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=4)
        self.ui_anim_loop = ttk.Combobox(card, values=AnimationManager.get_loop_animations(), state="readonly")
        self.ui_anim_loop.grid(row=2, column=1, sticky=tk.EW, pady=4, padx=4)
        self.ui_anim_loop.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Exit Animation:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=4)
        self.ui_anim_exit = ttk.Combobox(card, values=AnimationManager.get_exit_animations(), state="readonly")
        self.ui_anim_exit.grid(row=3, column=1, sticky=tk.EW, pady=4, padx=4)
        self.ui_anim_exit.bind("<<ComboboxSelected>>", lambda e: self._read_ui_to_profiles())

        ttk.Label(card, text="Speed (ms):", style="Card.TLabel").grid(row=4, column=0, sticky=tk.W, pady=4)
        self.ui_anim_speed = ttk.Spinbox(card, from_=50, to=1500, increment=50, width=8, command=lambda: self._read_ui_to_profiles())
        self.ui_anim_speed.grid(row=4, column=1, sticky=tk.W, pady=4, padx=4)
        card.columnconfigure(1, weight=1)

    def _build_dynamic_active_word_editor_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="7. Active Spoken Word Engine (Dynamic Essential Graphics)", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 6))

        self.ui_wh_on = tk.BooleanVar(value=True)
        ttk.Checkbutton(card, text="Enable Active Spoken Word Highlighting", variable=self.ui_wh_on, command=lambda: self._read_ui_to_profiles()).pack(anchor=tk.W, pady=2)

        sel_frame = ttk.Frame(card, style="Card.TFrame")
        sel_frame.pack(fill=tk.X, pady=6)

        ttk.Label(sel_frame, text="Highlight Mode:", style="Card.TLabel").grid(row=0, column=0, sticky=tk.W, pady=4)
        self.ui_wh_mode = ttk.Combobox(sel_frame, values=list(HIGHLIGHT_MODE_SPECS.keys()), state="readonly", width=18)
        self.ui_wh_mode.grid(row=0, column=1, sticky=tk.W, pady=4, padx=6)
        self.ui_wh_mode.bind("<<ComboboxSelected>>", lambda e: self._on_highlight_mode_changed())

        ttk.Label(sel_frame, text="Word Motion:", style="Card.TLabel").grid(row=1, column=0, sticky=tk.W, pady=4)
        self.ui_awa_type = ttk.Combobox(sel_frame, values=list(MOTION_MODE_SPECS.keys()), state="readonly", width=18)
        self.ui_awa_type.grid(row=1, column=1, sticky=tk.W, pady=4, padx=6)
        self.ui_awa_type.bind("<<ComboboxSelected>>", lambda e: self._on_motion_mode_changed())

        self.highlight_prop_container = ttk.Frame(card, style="Card.TFrame")
        self.highlight_prop_container.pack(fill=tk.X, pady=(6, 2))

        self.motion_prop_container = ttk.Frame(card, style="Card.TFrame")
        self.motion_prop_container.pack(fill=tk.X, pady=(6, 2))

    def _on_highlight_mode_changed(self):
        self.wh.mode = self.ui_wh_mode.get()
        populate_default_params(self.wh, self.wh.mode, HIGHLIGHT_MODE_SPECS)
        self._rebuild_highlight_property_editor()

    def _on_motion_mode_changed(self):
        self.awa.anim_type = self.ui_awa_type.get()
        populate_default_params(self.awa, self.awa.anim_type, MOTION_MODE_SPECS)
        self._rebuild_motion_property_editor()

    def _rebuild_highlight_property_editor(self):
        if not self.highlight_prop_container: return
        for child in self.highlight_prop_container.winfo_children():
            child.destroy()

        specs = HIGHLIGHT_MODE_SPECS.get(self.wh.mode, [])
        if specs:
            editor = DynamicPropertyEditor(self.highlight_prop_container, specs, self.wh.params, self._read_ui_to_profiles)
            editor.pack(fill=tk.X, expand=True)

    def _rebuild_motion_property_editor(self):
        if not self.motion_prop_container: return
        for child in self.motion_prop_container.winfo_children():
            child.destroy()

        specs = MOTION_MODE_SPECS.get(self.awa.anim_type, [])
        if specs:
            editor = DynamicPropertyEditor(self.motion_prop_container, specs, self.awa.params, self._read_ui_to_profiles)
            editor.pack(fill=tk.X, expand=True)

    def _build_shadow_glow_card(self):
        card = ttk.Frame(self.scroll_f, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(card, text="8. Global Shadows & Radiance Glow Layers", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky=tk.W, pady=(0, 6))
        self.ui_sh_on = tk.BooleanVar()
        ttk.Checkbutton(card, text="Enable Drop Shadows Layer", variable=self.ui_sh_on, command=lambda: self._read_ui_to_profiles()).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Label(card, text="Offsets (X/Y):", style="Card.TLabel").grid(row=2, column=0, sticky=tk.W, pady=2)
        f = ttk.Frame(card, style="Card.TFrame")
        f.grid(row=2, column=1, sticky=tk.W)
        self.ui_sh_ox = ttk.Spinbox(f, from_=-40, to=40, width=4, command=lambda: self._read_ui_to_profiles())
        self.ui_sh_ox.pack(side="left", padx=2)
        self.ui_sh_oy = ttk.Spinbox(f, from_=-40, to=40, width=4, command=lambda: self._read_ui_to_profiles())
        self.ui_sh_oy.pack(side="left", padx=2)
        
        ttk.Label(card, text="Blur Softness:", style="Card.TLabel").grid(row=3, column=0, sticky=tk.W, pady=2)
        self.ui_sh_blur = ttk.Scale(card, from_=0, to=25, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_sh_blur.grid(row=3, column=1, sticky=tk.EW, padx=4)
        tk.Button(card, text="Shadow Color", font=("Segoe UI", 8), command=self._cb_pick_sh).grid(row=4, column=1, sticky=tk.W, padx=4)

        ttk.Label(card, text="Radiance Glow Filter:", style="Section.TLabel").grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(10, 6))
        self.ui_gl_on = tk.BooleanVar()
        ttk.Checkbutton(card, text="Enable Glow Outlines", variable=self.ui_gl_on, command=lambda: self._read_ui_to_profiles()).grid(row=6, column=0, columnspan=2, sticky=tk.W, pady=2)
        
        ttk.Label(card, text="Glow Radius Size:", style="Card.TLabel").grid(row=7, column=0, sticky=tk.W, pady=2)
        self.ui_gl_size = ttk.Scale(card, from_=2, to=50, orient=tk.HORIZONTAL, command=lambda v: self._read_ui_to_profiles())
        self.ui_gl_size.grid(row=7, column=1, sticky=tk.EW, padx=4)
        tk.Button(card, text="Glow Tint Color", font=("Segoe UI", 8), command=self._cb_pick_gl).grid(row=8, column=1, sticky=tk.W, padx=4)
        card.columnconfigure(1, weight=1)

    # --------------------------------------------------------------------------
    # LIVE PREVIEW PANEL WITH CONTINUOUS SYNCHRONIZED PIPELINE
    # --------------------------------------------------------------------------

    def _build_preview_panel(self, parent: ttk.Frame):
        card = ttk.Frame(parent, style="Card.TFrame", padding=12)
        card.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(card, text="Live Active Word Preview Panel", style="Section.TLabel").pack(anchor=tk.W, pady=(0, 4))
        
        f = ttk.Frame(card, style="Card.TFrame")
        f.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(f, text="Dummy Preview Sentence:", style="Card.TLabel").pack(side="left", padx=(0, 6))
        self.ui_preview_txt = ttk.Entry(f)
        self.ui_preview_txt.pack(side="left", fill=tk.X, expand=True)
        self.ui_preview_txt.insert(0, "Imagine how powerful your captions can become")
        self.ui_preview_txt.bind("<KeyRelease>", lambda e: self._read_ui_to_profiles())

        self.view_canvas = tk.Canvas(card, bg="#121214", height=280, highlightthickness=1, highlightbackground=self.c_border)
        self.view_canvas.pack(fill=tk.X, expand=False)

    def _start_continuous_live_preview_loop(self):
        """Continuously renders a real-time animated preview passing through the unified Smart Caption Group Engine pipeline."""
        def step_preview():
            self.preview_time_ms += 40.0
            if self.preview_time_ms > 2400.0:
                self.preview_time_ms = 0.0

            text_str = self.ui_preview_txt.get().strip()
            if text_str:
                raw_words = text_str.split()
                w_objects = []
                dur_per_word = 2000.0 / max(1, len(raw_words))
                for i, w in enumerate(raw_words):
                    w_objects.append(Word(word=w, start_ms=i*dur_per_word, end_ms=(i+1)*dur_per_word, index=i))

                # 1. RUN THROUGH SMART CAPTION GROUP ENGINE AT FULL VIDEO RESOLUTION (EXACT EXPORT PIPELINE)
                groups = SmartCaptionGroupEngine.build_caption_groups(
                    w_objects, self.gp, self.vp, self.ts, self.out_p, self.wh
                )

                # 2. SELECT ACTIVE GROUP FOR PREVIEW TIME
                active_group = None
                for g in groups:
                    if g.start_ms <= self.preview_time_ms <= g.end_ms:
                        active_group = g
                        break
                if not active_group and groups:
                    active_group = groups[0] if self.preview_time_ms < groups[0].start_ms else groups[-1]

                cw = self.view_canvas.winfo_width()
                ch = self.view_canvas.winfo_height()
                if cw > 20 and ch > 20 and active_group:
                    ratio = cw / 1920.0
                    sc_size = max(8, int(self.ts.font_size * ratio))
                    sc_out_w = max(0, int(self.out_p.width * ratio))
                    sc_let_spc = max(-2, int(self.ts.letter_spacing * ratio))

                    sim_vp = VideoProfile(width=cw, height=ch, bg_mode=self.vp.bg_mode, bg_custom_hex=self.vp.bg_custom_hex)
                    sim_ts = TextStyleProfile(
                        font_family=self.ts.font_family, font_size=sc_size, bold=self.ts.bold,
                        italic=self.ts.italic, case_mode=self.ts.case_mode, letter_spacing=sc_let_spc,
                        text_color=self.ts.text_color
                    )
                    sim_out = OutlineProfile(enabled=self.out_p.enabled, width=sc_out_w, color=self.out_p.color, double_outline=self.out_p.double_outline)
                    sim_sh = ShadowProfile(enabled=self.sh.enabled, offset_x=int(self.sh.offset_x*ratio), offset_y=int(self.sh.offset_y*ratio), blur=int(self.sh.blur*ratio), color=self.sh.color)
                    sim_gl = GlowProfile(enabled=self.gl.enabled, size=int(self.gl.size*ratio), color=self.gl.color)
                    sim_ap = AnimationProfile(entry_anim="None", loop_anim="None", exit_anim="None")
                    
                    # Layout Profile Fixed to Center Horizontally and Vertically for Preview Panel
                    sim_lp = LayoutProfile(anchor="Center Center", custom_positioning=False)

                    # Scale WordHighlight Profile pixel parameters for preview canvas size
                    scaled_wh = WordHighlightProfile(
                        enabled=self.wh.enabled,
                        mode=self.wh.mode,
                        params=dict(self.wh.params)
                    )
                    for px_param in ["pad_left", "pad_right", "pad_top", "pad_bottom", "corner_radius", "border_width", "padding", "thickness", "dist_from_text", "shadow_blur", "shadow_ox", "shadow_oy", "glow_radius"]:
                        if px_param in scaled_wh.params:
                            scaled_wh.params[px_param] = float(scaled_wh.params[px_param]) * ratio

                    p_img = self.preview_renderer.compose_full_frame(
                        active_group, sim_vp, sim_ts, sim_out, sim_sh, sim_gl, 
                        sim_ap, sim_lp, self.ep, scaled_wh, self.awa, 
                        self.preview_time_ms
                    )
                    
                    self.tk_photo_reference = ImageTk.PhotoImage(p_img)
                    self.view_canvas.delete("all")
                    self.view_canvas.create_image(0, 0, anchor="nw", image=self.tk_photo_reference)

            self.preview_timer_id = self.root.after(40, step_preview)

        step_preview()

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
        card.pack(fill=tk.BOTH, expand=True)
        self.log_widget = ScrolledText(card, bg="#121214", fg=self.c_text, font=("Consolas", 9), height=5, bd=0, highlightthickness=1, highlightbackground=self.c_border, insertbackground="#FFFFFF")
        self.log_widget.pack(fill=tk.BOTH, expand=True)
        self.log_widget.configure(state=tk.DISABLED)

    # --------------------------------------------------------------------------
    # MENU & TEMPLATE CALLBACK HANDLERS
    # --------------------------------------------------------------------------

    def _menu_export_caption_template(self):
        f = filedialog.asksaveasfilename(defaultextension=".cstemplate", filetypes=[("Caption Studio Template", "*.cstemplate")])
        if not f: return

        name = os.path.splitext(os.path.basename(f))[0]
        data = CaptionTemplateManager.serialize_workspace(self, name=name, author="User")
        
        try:
            with open(f, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            self.append_log(f"Caption Template exported: '{f}'", "SUCCESS")
        except Exception as e:
            messagebox.showerror("Export Error", f"Failed to save template:\n{str(e)}")

    def _menu_import_caption_template(self):
        f = filedialog.askopenfilename(filetypes=[("Caption Studio Template", "*.cstemplate")])
        if not f: return

        try:
            with open(f, "r", encoding="utf-8") as file:
                data = json.load(file)
            CaptionTemplateManager.deserialize_into_workspace(self, data)
            self.append_log(f"Caption Template imported: '{f}'", "SUCCESS")
        except Exception as e:
            messagebox.showerror("Import Error", f"Failed to load template file:\n{str(e)}")

    def _menu_save_template(self):
        CaptionTemplateManager.ensure_directories()
        user_dir = os.path.join(CaptionTemplateManager.TEMPLATE_DIR, "User")

        name = filedialog.asksaveasfilename(initialdir=user_dir, defaultextension=".cstemplate", filetypes=[("Caption Studio Template", "*.cstemplate")])
        if not name: return

        if os.path.exists(name):
            if not messagebox.askyesno("Overwrite Template", "A template with this name already exists. Overwrite?"):
                return

        t_name = os.path.splitext(os.path.basename(name))[0]
        data = CaptionTemplateManager.serialize_workspace(self, name=t_name, author="User")

        try:
            with open(name, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=2)
            self.append_log(f"Template saved to library: '{t_name}'", "SUCCESS")
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save template:\n{str(e)}")

    def _menu_open_template_browser(self):
        TemplateBrowserDialog(self.root, self)

    # --------------------------------------------------------------------------
    # ENGINE VALUE SYNCHRONIZATIONS & BINDINGS
    # --------------------------------------------------------------------------

    def _sync_profiles_into_ui(self):
        self.block_updates = True
        self.ui_bg_mode.set(self.vp.bg_mode)
        self.lbl_selected_font.configure(text=self.ts.font_family)
        
        self.ui_pref_w_line.set(self.gp.preferred_words_per_line)
        self.ui_max_lines.set(self.gp.max_lines)
        self.ui_safe_margin.set(self.gp.screen_safe_margin)
        self.ui_enable_safe.set(self.gp.enable_safe_area)

        self.ui_size.set(self.ts.font_size)
        self.ui_bold.set(self.ts.bold)
        self.ui_italic.set(self.ts.italic)
        self.ui_case.set(self.ts.case_mode)
        self.ui_let_spc.set(self.ts.letter_spacing)
        self.ui_out_on.set(self.out_p.enabled)
        self.ui_out_w.set(self.out_p.width)
        self.ui_dbl_out.set(self.out_p.double_outline)
        self.ui_fx.set(self.ep.mode)
        self.ui_anim_entry.set(self.ap.entry_anim)
        self.ui_anim_loop.set(self.ap.loop_anim)
        self.ui_anim_exit.set(self.ap.exit_anim)
        self.ui_anim_speed.set(self.ap.speed_ms)
        
        self.ui_wh_on.set(self.wh.enabled)
        self.ui_wh_mode.set(self.wh.mode)
        self.ui_awa_type.set(self.awa.anim_type)

        self._rebuild_highlight_property_editor()
        self._rebuild_motion_property_editor()

        self.ui_sh_on.set(self.sh.enabled)
        self.ui_sh_ox.set(self.sh.offset_x)
        self.ui_sh_oy.set(self.sh.offset_y)
        self.ui_sh_blur.set(self.sh.blur)
        self.ui_gl_on.set(self.gl.enabled)
        self.ui_gl_size.set(self.gl.size)
        self.block_updates = False

    def _read_ui_to_profiles(self):
        if self.block_updates: return
        self.vp.bg_mode = self.ui_bg_mode.get()
        try:
            self.gp.preferred_words_per_line = int(self.ui_pref_w_line.get())
            self.gp.max_lines = int(self.ui_max_lines.get())
            self.gp.screen_safe_margin = int(self.ui_safe_margin.get())
            self.gp.enable_safe_area = self.ui_enable_safe.get()
            self.ts.font_size = int(self.ui_size.get())
        except Exception: pass

        self.ts.bold = self.ui_bold.get()
        self.ts.italic = self.ui_italic.get()
        self.ts.case_mode = self.ui_case.get()
        self.ts.letter_spacing = int(float(self.ui_let_spc.get()))
        self.out_p.enabled = self.ui_out_on.get()
        self.out_p.width = int(float(self.ui_out_w.get()))
        self.out_p.double_outline = self.ui_dbl_out.get()
        self.ep.mode = self.ui_fx.get()
        self.ap.entry_anim = self.ui_anim_entry.get()
        self.ap.loop_anim = self.ui_anim_loop.get()
        self.ap.exit_anim = self.ui_anim_exit.get()
        try: self.ap.speed_ms = int(self.ui_anim_speed.get())
        except Exception: pass

        self.wh.enabled = self.ui_wh_on.get()
        self.wh.mode = self.ui_wh_mode.get()
        self.awa.anim_type = self.ui_awa_type.get()

        self.sh.enabled = self.ui_sh_on.get()
        try:
            self.sh.offset_x = int(self.ui_sh_ox.get())
            self.sh.offset_y = int(self.ui_sh_oy.get())
        except Exception: pass
        self.sh.blur = int(float(self.ui_sh_blur.get()))
        self.gl.enabled = self.ui_gl_on.get()
        self.gl.size = int(float(self.ui_gl_size.get()))

    def _cb_open_font_picker(self):
        FontPickerPopup(self.root, self.ts.font_family, self._on_font_selected)

    def _on_font_selected(self, font_family: str):
        self.ts.font_family = font_family
        self.lbl_selected_font.configure(text=font_family)
        RenderCacheManager.clear()

    def _cb_trigger_visual_style_select(self, name: str):
        StyleManager.apply(name, self.ts, self.out_p, self.sh, self.gl, self.ep, self.lp, self.wh, self.awa)
        self.append_log(f"Visual Preset selected: '{name}'", "SUCCESS")
        
        for b_name, b_obj in self.preset_buttons.items():
            if b_name == name: b_obj.configure(bg=self.c_accent_l, fg="#FFFFFF")
            else: b_obj.configure(bg="#2B2B36", fg=self.c_text)
            
        self._sync_profiles_into_ui()

    def _cb_browse_srt(self):
        f = filedialog.askopenfilename(filetypes=[("Subtitle Track Script", "*.srt")])
        if f: self.ui_srt.set(f); self.append_log(f"Subtitle path set: {f}", "INFO")

    def _cb_browse_out(self):
        d = filedialog.askdirectory()
        if d: self.ui_out.set(d); self.append_log(f"Output directory set: {d}", "INFO")

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
    # WORKER THREAD & EXPORT CONTROL DRIVERS
    # --------------------------------------------------------------------------

    def append_log(self, text: str, mode: str = "INFO"):
        stamp = time.strftime("%H:%M:%S")
        colors = {"INFO": "#FFFFFF", "SUCCESS": "#2EA043", "WARNING": "#D29922", "ERROR": "#F85149"}
        self.log_widget.configure(state=tk.NORMAL)
        self.log_widget.insert(tk.END, f"[{stamp}] [{mode}] {text}\n")
        idx_s = self.log_widget.index("end-2c linestart")
        idx_e = self.log_widget.index("end-1c")
        tname = f"tag_{time.time()}"
        self.log_widget.tag_add(tname, idx_s, idx_e)
        self.log_widget.tag_config(tname, foreground=colors.get(mode, "#FFFFFF"))
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

        self.worker = RenderWorker(s, o, self.vp, self.ts, self.out_p, self.sh, self.gl, self.ap, self.lp, self.ep, self.wh, self.awa, self.gp, self.q, self.cancel)
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
                    self.lbl_met_txt.configure(text=f"Tracking Subtitle: {textwrap.shorten(data['txt'], 60)}")
                elif m == "COMPLETE":
                    messagebox.showinfo("Success", f"Video compilation completed cleanly!\n\nSaved location:\n{data}")
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
# ENTRY POINT
# ==============================================================================

if __name__ == "__main__":
    main_root = tk.Tk()
    app = MainWindow(main_root)
    main_root.mainloop()