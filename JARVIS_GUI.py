"""J.A.R.V.I.S. desktop chat application (Tkinter, no console window)."""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from typing import Any

import JARVIS as assistant
import jarvis_workspace as workspace
import jarvis_model_manager as model_manager


# Dark navy interface with a teal accent.
# Custom midnight-blue / turquoise Command Centre theme.
BG = "#071426"
SIDEBAR = "#091B31"
PANEL = "#0D223B"
PANEL_LIGHT = "#143451"
BORDER = "#1D4665"
TEXT = "#EAF7FF"
MUTED = "#8EADC4"
ACCENT = "#38E0D0"
ACCENT_DARK = "#103E4A"
BLUE = "#398BFF"
BLUE_DARK = "#123B68"
USER_BUBBLE = "#10375B"
ERROR = "#FF8797"
SUCCESS = "#55E0A2"
MAX_DISPLAY_MESSAGES = 120
MAX_TRANSCRIPT_MESSAGES = 2000
MAX_EVENTS_PER_TICK = 100


# Built-in palettes share semantic colour roles so the entire desktop app,
# settings dialogs, chat bubbles and Workspace can be recoloured consistently.
THEME_NAMES = {
    "midnight": "Midnight Blue",
    "arctic": "Arctic Light",
    "emerald": "Emerald",
    "violet": "Nebula Violet",
    "crimson": "Crimson",
    "amber": "Solar Amber",
}
THEME_LABEL_TO_KEY = {label: key for key, label in THEME_NAMES.items()}

# The original v1.4.0 palette is the source palette used by widgets built with
# fixed colour literals. This map translates those colours into semantic roles.
_BASE_COLOR_TO_ROLE = {
    "#071426": "BG", "#091B31": "SIDEBAR", "#0D223B": "PANEL",
    "#143451": "PANEL_LIGHT", "#1D4665": "BORDER", "#EAF7FF": "TEXT",
    "#8EADC4": "MUTED", "#38E0D0": "ACCENT", "#103E4A": "ACCENT_DARK",
    "#398BFF": "BLUE", "#123B68": "BLUE_DARK", "#10375B": "USER_BUBBLE",
    "#FF8797": "ERROR", "#55E0A2": "SUCCESS", "#06202C": "INK",
    "#07151B": "INK", "#0A1D32": "CHAT_PANEL", "#0C2947": "HERO",
    "#0C2C42": "STATUS_PILL", "#0D233A": "QUICK_TILE", "#0D2943": "COMPOSER",
    "#0D2945": "CORE", "#0E2B43": "ASSISTANT_BUBBLE", "#10334F": "QUICK_HOVER",
    "#103A58": "SIDEBAR_ACTIVE", "#103C4A": "TILE_TEAL", "#103D49": "STATUS_GOOD_BG",
    "#103D4A": "ACCENT_DARK", "#103E59": "LOGO_INNER", "#10485A": "ASSISTANT_AVATAR",
    "#12314D": "SIDEBAR_BORDER", "#143A57": "SCROLLBAR", "#153A56": "QUICK_HOVER",
    "#153D50": "TILE_CYAN", "#163C67": "TILE_BLUE", "#164968": "SIDEBAR_HOVER",
    "#173A57": "TILE_LAVENDER", "#174A76": "USER_AVATAR", "#17647B": "ASSISTANT_EDGE",
    "#183A54": "CHAT_DIVIDER", "#1A3A55": "DIVIDER", "#1A3F5B": "QUICK_TILE_BORDER",
    "#1A5274": "HERO_BORDER", "#1B3D59": "CHAT_BORDER", "#1B4D68": "CORE_BORDER",
    "#1B5974": "SIDEBAR_ACTIVE_BORDER", "#24617D": "COMPOSER_BORDER",
    "#2679B8": "USER_EDGE", "#412638": "STATUS_BAD_BG", "#58717A": "DISABLED_TEXT",
    "#64E6D9": "TILE_CYAN_FG", "#6589A7": "SECTION_TEXT", "#66E5D7": "ACCENT_HOVER",
    "#69B6FF": "TILE_BLUE_FG", "#6F93AC": "SUBTLE", "#72EFE3": "ACCENT_HOVER",
    "#73F3E7": "ACCENT_HOVER", "#87C7F6": "TILE_LAVENDER_FG", "#8ACBFF": "USER_AVATAR_FG",
    "#8BC8F3": "PROCESSING_FG", "#A9C7DC": "HERO_MUTED", "#B8E1FF": "USER_TEXT",
}


def _mix_color(first: str, second: str, amount: float) -> str:
    """Blend two #RRGGBB colours; amount is the share of the second colour."""
    a = tuple(int(first[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(second[i:i + 2], 16) for i in (1, 3, 5))
    values = tuple(round(x * (1 - amount) + y * amount) for x, y in zip(a, b))
    return "#" + "".join(f"{value:02X}" for value in values)


def _make_theme(*, bg: str, sidebar: str, panel: str, panel_light: str,
                border: str, text: str, muted: str, accent: str, blue: str,
                error: str, success: str, user_bubble: str, assistant_bubble: str,
                hero: str | None = None, ink: str = "#06131D") -> dict[str, str]:
    """Build a complete coherent palette from a small set of design anchors."""
    blue_dark = _mix_color(blue, bg, 0.67)
    hero = hero or _mix_color(panel, blue, 0.20)
    accent_dark = _mix_color(panel, accent, 0.16)
    result = {
        "BG": bg, "SIDEBAR": sidebar, "PANEL": panel, "PANEL_LIGHT": panel_light,
        "BORDER": border, "TEXT": text, "MUTED": muted, "ACCENT": accent,
        "ACCENT_DARK": accent_dark, "BLUE": blue, "BLUE_DARK": blue_dark,
        "USER_BUBBLE": user_bubble, "ERROR": error, "SUCCESS": success, "INK": ink,
        "HERO": hero, "HERO_BORDER": _mix_color(hero, blue, .38),
        "CORE": _mix_color(sidebar, blue, .15), "CORE_BORDER": _mix_color(border, blue, .4),
        "DIVIDER": _mix_color(bg, border, .58), "CHAT_PANEL": _mix_color(bg, panel, .58),
        "CHAT_DIVIDER": _mix_color(panel, border, .55), "STATUS_PILL": _mix_color(panel, accent, .15),
        "QUICK_TILE": _mix_color(sidebar, panel, .55), "QUICK_TILE_BORDER": _mix_color(border, sidebar, .25),
        "QUICK_HOVER": _mix_color(sidebar, accent, .22), "TILE_BLUE": _mix_color(panel, blue, .34),
        "TILE_BLUE_FG": _mix_color(text, blue, .4), "TILE_TEAL": _mix_color(panel, accent, .2),
        "TILE_LAVENDER": _mix_color(panel, blue, .18), "TILE_CYAN": _mix_color(panel, accent, .14),
        "TILE_CYAN_FG": _mix_color(text, accent, .42), "COMPOSER": _mix_color(bg, panel, .72),
        "COMPOSER_BORDER": _mix_color(border, accent, .42), "SECTION_TEXT": _mix_color(muted, accent, .25),
        "SUBTLE": _mix_color(muted, bg, .16), "ASSISTANT_BUBBLE": assistant_bubble,
        "ASSISTANT_EDGE": _mix_color(border, accent, .38),
        "ASSISTANT_AVATAR": _mix_color(sidebar, accent, .34),
        "USER_AVATAR": _mix_color(blue, blue_dark, .25),
        "USER_EDGE": _mix_color(blue, border, .4), "USER_AVATAR_FG": _mix_color(text, blue, .3),
        "USER_TEXT": _mix_color(text, blue, .2), "DISABLED_TEXT": _mix_color(muted, bg, .35),
        "STATUS_GOOD_BG": _mix_color(panel, success, .16), "STATUS_BAD_BG": _mix_color(panel, error, .18),
        "ACCENT_HOVER": _mix_color(accent, text, .22), "PROCESSING_FG": _mix_color(muted, blue, .48),
        "HERO_MUTED": _mix_color(text, muted, .42), "SIDEBAR_BORDER": _mix_color(sidebar, border, .55),
        "SIDEBAR_ACTIVE": _mix_color(sidebar, accent, .18),
        "SIDEBAR_HOVER": _mix_color(sidebar, accent, .27), "SIDEBAR_ACTIVE_BORDER": _mix_color(border, accent, .52),
        "LOGO_INNER": _mix_color(sidebar, blue, .30), "SCROLLBAR": _mix_color(panel_light, bg, .35),
    }
    return result


THEMES: dict[str, dict[str, str]] = {
    "midnight": {
        "BG": "#071426", "SIDEBAR": "#091B31", "PANEL": "#0D223B",
        "PANEL_LIGHT": "#143451", "BORDER": "#1D4665", "TEXT": "#EAF7FF",
        "MUTED": "#8EADC4", "ACCENT": "#38E0D0", "ACCENT_DARK": "#103E4A",
        "BLUE": "#398BFF", "BLUE_DARK": "#123B68", "USER_BUBBLE": "#10375B",
        "ERROR": "#FF8797", "SUCCESS": "#55E0A2", "INK": "#06202C",
        "HERO": "#0C2947", "HERO_BORDER": "#1A5274", "CORE": "#0D2945",
        "CORE_BORDER": "#1B4D68", "DIVIDER": "#1A3A55", "CHAT_PANEL": "#0A1D32",
        "CHAT_DIVIDER": "#183A54", "STATUS_PILL": "#0C2C42", "QUICK_TILE": "#0D233A",
        "QUICK_TILE_BORDER": "#1A3F5B", "QUICK_HOVER": "#10334F", "TILE_BLUE": "#163C67",
        "TILE_BLUE_FG": "#69B6FF", "TILE_TEAL": "#103C4A", "TILE_LAVENDER": "#173A57",
        "TILE_CYAN": "#153D50", "TILE_CYAN_FG": "#64E6D9", "COMPOSER": "#0D2943",
        "COMPOSER_BORDER": "#24617D", "SECTION_TEXT": "#6589A7", "SUBTLE": "#6F93AC",
        "ASSISTANT_BUBBLE": "#0E2B43", "ASSISTANT_EDGE": "#17647B", "ASSISTANT_AVATAR": "#10485A",
        "USER_AVATAR": "#174A76", "USER_EDGE": "#2679B8", "USER_AVATAR_FG": "#8ACBFF",
        "USER_TEXT": "#B8E1FF", "DISABLED_TEXT": "#58717A", "STATUS_GOOD_BG": "#103D49",
        "STATUS_BAD_BG": "#412638", "ACCENT_HOVER": "#73F3E7", "PROCESSING_FG": "#8BC8F3",
        "HERO_MUTED": "#A9C7DC", "SIDEBAR_BORDER": "#12314D", "SIDEBAR_ACTIVE": "#103A58",
        "SIDEBAR_HOVER": "#164968", "SIDEBAR_ACTIVE_BORDER": "#1B5974", "LOGO_INNER": "#103E59",
        "SCROLLBAR": "#143A57",
    },
    "arctic": _make_theme(bg="#F1F6FB", sidebar="#E1EBF4", panel="#FFFFFF", panel_light="#E5EEF6",
        border="#C4D4E2", text="#172D42", muted="#587187", accent="#008F91", blue="#2878C7",
        error="#C3425C", success="#16845C", user_bubble="#DDEBFA", assistant_bubble="#EAF2F8",
        hero="#DDEDF8", ink="#10263A"),
    "emerald": _make_theme(bg="#071A18", sidebar="#0A2420", panel="#10312C", panel_light="#19443C",
        border="#286458", text="#E7FFF8", muted="#91B9AA", accent="#4BE0A8", blue="#37B8AA",
        error="#FF8295", success="#58E3A5", user_bubble="#123E39", assistant_bubble="#102A28",
        ink="#052019"),
    "violet": _make_theme(bg="#100D20", sidebar="#19132D", panel="#241C3D", panel_light="#33284F",
        border="#4C3B70", text="#F4EDFF", muted="#B3A4CC", accent="#C49AFF", blue="#7C8CFF",
        error="#FF8EAB", success="#66DDB5", user_bubble="#30234F", assistant_bubble="#211A37",
        ink="#1A1030"),
    "crimson": _make_theme(bg="#1B0D16", sidebar="#28121F", panel="#361B2A", panel_light="#492337",
        border="#6A344A", text="#FFF0F4", muted="#C7A0AE", accent="#FF789E", blue="#E47CBA",
        error="#FF9BAA", success="#72D7A9", user_bubble="#4A2035", assistant_bubble="#2D1725",
        ink="#300D20"),
    "amber": _make_theme(bg="#171309", sidebar="#241D0C", panel="#33280F", panel_light="#493817",
        border="#6B5120", text="#FFF7E5", muted="#C5B38A", accent="#FFC857", blue="#E5A63A",
        error="#FF8B83", success="#80D6A1", user_bubble="#493516", assistant_bubble="#2B220F",
        ink="#2B1B00"),
}

_GLOBAL_THEME_BINDINGS = {
    "BG": "BG", "SIDEBAR": "SIDEBAR", "PANEL": "PANEL", "PANEL_LIGHT": "PANEL_LIGHT",
    "BORDER": "BORDER", "TEXT": "TEXT", "MUTED": "MUTED", "ACCENT": "ACCENT",
    "ACCENT_DARK": "ACCENT_DARK", "BLUE": "BLUE", "BLUE_DARK": "BLUE_DARK",
    "USER_BUBBLE": "USER_BUBBLE", "ERROR": "ERROR", "SUCCESS": "SUCCESS",
}
_THEME_COLOR_OPTIONS = (
    "background", "foreground", "activebackground", "activeforeground", "highlightbackground",
    "highlightcolor", "selectbackground", "selectforeground", "insertbackground",
    "disabledforeground", "troughcolor",
)

SYSTEM_PROMPT = (
    "You are J.A.R.V.I.S., a capable, concise and polite local desktop assistant. "
    "Answer general questions clearly, accurately and in plain language. "
    "You can open supported apps and websites, search the web, check the date and time, "
    "take and read notes, paste text, open common folders, manage timers, and control Spotify playback, search and Spotify-only app volume. Spotify volume must never change Windows master volume or other apps. "
    "For typing requests, preserve the user's exact wording and pass the complete text in the text argument. "
    "For web searches, pass only the user's complete search phrase in the query argument; never pass tool metadata. "
    "Arithmetic and common time/timer commands are handled locally before you are called; do not call unrelated tools for them. "
    "When a tool is needed, choose the single most relevant tool and provide all required arguments. "
    "Do not invent tool results, claim actions succeeded unless the tool confirms it, or repeat a tool call that already failed. "
    "Ask one brief clarifying question if an action is ambiguous. "
    "Keep answers concise unless the user asks for more detail."
)


class JarvisApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.events: queue.Queue[tuple[str, Any]] = queue.Queue()
        self.busy = False
        self.closing = False
        self.history: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.transcript: list[tuple[str, str]] = []
        self.message_body_labels: list[tk.Label] = []
        self.workspace_window: tk.Toplevel | None = None
        self._notified_reminder_ids: set[str] = set()
        settings = assistant.load_settings()

        self.root.title(f"{assistant.APP_NAME} — Desktop Assistant")
        self.root.geometry(settings.get("window_geometry", "1360x860"))
        self.root.minsize(1080, 700)
        self.root.configure(bg=BG)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.report_callback_exception = self._report_tk_exception

        self.voice_var = tk.BooleanVar(value=bool(settings.get("voice_enabled", True)))
        self.theme_name = settings.get("theme", "midnight")
        if self.theme_name not in THEMES:
            self.theme_name = "midnight"
        self._build_styles()
        self._build_layout()
        self.apply_theme(self.theme_name)
        assistant.set_voice_enabled(self.voice_var.get(), persist=False)
        assistant.ui_message_callback = self.queue_assistant_message

        self.add_message(
            "assistant",
            "I'm online and ready. Ask me anything, or use one of the quick actions to get started.\n\n"
            "I can reason with Gemma, calculate using BIDMAS, search the web, open apps, "
            "manage your notes and reminders, and launch 25 built-in Workspace tools.",
        )
        self.root.after(100, self._drain_events)
        self.root.after(250, self._start_connection_check)
        self.root.after(4000, self._poll_reminders)
        self.input.focus_set()

    def _walk_widgets(self, parent: tk.Misc):
        """Yield a widget and all descendants, including child Toplevels."""
        yield parent
        try:
            children = parent.winfo_children()
        except tk.TclError:
            return
        for child in children:
            yield from self._walk_widgets(child)

    def _apply_theme_tree(self, parent: tk.Misc, palette: dict[str, str]) -> None:
        """Recolour existing Tk widgets while remembering each option's semantic role."""
        inverse_current = {value.lower(): role for role, value in palette.items()}
        for widget in self._walk_widgets(parent):
            try:
                role_cache = getattr(widget, "_jarvis_theme_roles", None)
                if role_cache is None:
                    role_cache = {}
                    setattr(widget, "_jarvis_theme_roles", role_cache)
                changes: dict[str, str] = {}
                supported = set(widget.keys())
                for option in _THEME_COLOR_OPTIONS:
                    if option not in supported:
                        continue
                    try:
                        current = str(widget.cget(option)).lower()
                    except tk.TclError:
                        continue
                    role = role_cache.get(option)
                    if role is None:
                        role = _BASE_COLOR_TO_ROLE.get(current)
                        if role is None:
                            role = inverse_current.get(current)
                        if role:
                            role_cache[option] = role
                    if role and role in palette:
                        changes[option] = palette[role]
                if changes:
                    widget.configure(**changes)
            except (tk.TclError, AttributeError):
                continue

    def apply_theme(self, theme_name: str, *, persist: bool = False) -> None:
        """Apply a palette immediately to all open windows; optionally persist it."""
        if theme_name not in THEMES:
            raise ValueError(f"Unknown theme: {theme_name}")
        self.theme_name = theme_name
        palette = THEMES[theme_name]
        if persist:
            assistant.save_settings(theme=theme_name)
        # Keep the legacy module constants in step so widgets created later use
        # the selected core colours rather than reverting to Midnight Blue.
        for constant, role in _GLOBAL_THEME_BINDINGS.items():
            globals()[constant] = palette[role]
        self._apply_theme_tree(self.root, palette)
        try:
            self.root.configure(bg=palette["BG"])
            style = ttk.Style(self.root)
            style.configure(
                "Jarvis.TCombobox", fieldbackground=palette["PANEL_LIGHT"],
                background=palette["PANEL_LIGHT"], foreground=palette["TEXT"],
                arrowcolor=palette["ACCENT"], bordercolor=palette["BORDER"],
                lightcolor=palette["BORDER"], darkcolor=palette["BORDER"], padding=7,
            )
            style.map(
                "Jarvis.TCombobox",
                fieldbackground=[("readonly", palette["PANEL_LIGHT"])],
                foreground=[("readonly", palette["TEXT"])],
                selectbackground=[("readonly", palette["BLUE_DARK"])],
                selectforeground=[("readonly", palette["TEXT"])],
            )
            style.configure(
                "Jarvis.Vertical.TScrollbar", background=palette["PANEL_LIGHT"],
                troughcolor=palette["BG"], bordercolor=palette["BG"],
                arrowcolor=palette["MUTED"], relief="flat",
            )
        except tk.TclError:
            pass

    # ----------------------------- UI construction -----------------------------

    def _build_styles(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Jarvis.Vertical.TScrollbar",
            background=PANEL_LIGHT,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED,
            relief="flat",
        )
        style.configure(
            "Jarvis.TCombobox",
            fieldbackground=PANEL_LIGHT,
            background=PANEL_LIGHT,
            foreground=TEXT,
            arrowcolor=ACCENT,
            bordercolor=BORDER,
            lightcolor=BORDER,
            darkcolor=BORDER,
            padding=7,
        )
        style.map(
            "Jarvis.TCombobox",
            fieldbackground=[("readonly", PANEL_LIGHT)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", BLUE_DARK)],
            selectforeground=[("readonly", TEXT)],
        )

    def _build_layout(self) -> None:
        """Build the custom blue/turquoise Command Centre interface."""
        self.root.grid_rowconfigure(0, weight=1)
        self.root.grid_columnconfigure(1, weight=1)

        # Left navigation rail.
        sidebar = tk.Frame(self.root, bg=SIDEBAR, width=244, highlightbackground="#12314D", highlightthickness=1)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)

        brand = tk.Frame(sidebar, bg=SIDEBAR)
        brand.pack(fill="x", padx=20, pady=(24, 18))
        brand_icon = tk.Canvas(brand, width=48, height=48, bg=SIDEBAR, highlightthickness=0)
        brand_icon.pack(side="left", padx=(0, 11))
        brand_icon.create_oval(3, 3, 45, 45, fill="#103E59", outline=ACCENT, width=2)
        brand_icon.create_oval(10, 10, 38, 38, outline=BLUE, width=1)
        brand_icon.create_text(24, 24, text="J", fill=TEXT, font=("Segoe UI", 18, "bold"))
        brand_text = tk.Frame(brand, bg=SIDEBAR)
        brand_text.pack(side="left", fill="y", expand=True)
        tk.Label(brand_text, text="J.A.R.V.I.S.", bg=SIDEBAR, fg=TEXT,
                 font=("Segoe UI", 17, "bold")).pack(anchor="w", pady=(3, 0))
        tk.Label(brand_text, text="DESKTOP INTELLIGENCE", bg=SIDEBAR, fg=ACCENT,
                 font=("Segoe UI", 7, "bold")).pack(anchor="w", pady=(1, 0))

        self._section_label(sidebar, "YOUR SPACE", top=3)
        self._sidebar_button(sidebar, "▣   Command Centre", lambda: self.input.focus_set(), primary=True)
        self._sidebar_button(sidebar, "✦   Explore Workspace", self.open_workspace)
        self._sidebar_button(sidebar, "＋   New conversation", self.clear_chat)
        self._sidebar_button(sidebar, "⇧   Export conversation", self.export_chat)

        self._section_label(sidebar, "QUICK LAUNCH", top=24)
        quick_actions = [
            ("◷", "Check the time", "What time is it?"),
            ("∑", "BIDMAS calculator", "Calculate 12 + 2 × 3"),
            ("⌕", "Search the web", "Search the web for Python tutorials"),
            ("▤", "Open my notes", "Open my notes"),
            ("◉", "Set a timer", "Set a timer for 1 minute"),
            ("♫", "Spotify controls", "__spotify_controls__"),
        ]
        for symbol, label, command in quick_actions:
            callback = self.open_spotify_controls if command == "__spotify_controls__" else (lambda value=command: self.use_quick_action(value))
            self._quick_action_button(sidebar, symbol, label, callback)

        # Pinned model / local status card at the bottom of the rail.
        bottom = tk.Frame(sidebar, bg=SIDEBAR)
        bottom.pack(side="bottom", fill="x", padx=15, pady=16)
        tk.Frame(bottom, bg="#1A3A55", height=1).pack(fill="x", pady=(0, 13))
        core_card = tk.Frame(bottom, bg="#0D2945", highlightbackground="#1B4D68", highlightthickness=1)
        core_card.pack(fill="x", pady=(0, 10))
        core_top = tk.Frame(core_card, bg="#0D2945")
        core_top.pack(fill="x", padx=11, pady=(10, 4))
        tk.Label(core_top, text="●", bg="#0D2945", fg=SUCCESS, font=("Segoe UI", 9)).pack(side="left")
        tk.Label(core_top, text="LOCAL AI CORE", bg="#0D2945", fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(side="left", padx=6)
        tk.Label(core_card, text=assistant.get_model_name(), bg="#0D2945", fg=TEXT,
                 font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=11)
        self.model_label = tk.Label(
            core_card, text=f"{assistant.get_num_ctx():,} token context · On-device",
            bg="#0D2945", fg=MUTED, font=("Segoe UI", 8), wraplength=190, justify="left",
        )
        self.model_label.pack(anchor="w", padx=11, pady=(3, 10))
        self._sidebar_button(bottom, "▦   AI model manager", self.open_model_manager, compact=True)
        self._sidebar_button(bottom, "⚙   Assistant settings", self.open_settings, compact=True)

        # Main application surface.
        main = tk.Frame(self.root, bg=BG)
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_rowconfigure(2, weight=1)
        main.grid_columnconfigure(0, weight=1)

        header = tk.Frame(main, bg=BG)
        header.grid(row=0, column=0, sticky="ew", padx=26, pady=(20, 13))
        header.grid_columnconfigure(0, weight=1)
        title_stack = tk.Frame(header, bg=BG)
        title_stack.grid(row=0, column=0, sticky="w")
        tk.Label(title_stack, text="PERSONAL AI  /  HOME", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(title_stack, text="Command Centre", bg=BG, fg=TEXT,
                 font=("Segoe UI", 22, "bold")).pack(anchor="w", pady=(1, 0))
        tk.Label(title_stack, text="Your local assistant, tools and ideas — all in one place.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(1, 0))

        header_actions = tk.Frame(header, bg=BG)
        header_actions.grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.connection_label = tk.Label(
            header_actions, text="●  CHECKING OLLAMA", bg="#0C2C42", fg=MUTED,
            font=("Segoe UI", 8, "bold"), padx=12, pady=9,
            wraplength=185, justify="center",
        )
        self.connection_label.pack(side="left", padx=(0, 9))
        self.voice_toggle = tk.Checkbutton(
            header_actions, text="Voice", variable=self.voice_var,
            command=self.toggle_voice, bg=BG, fg=TEXT,
            activebackground=BG, activeforeground=ACCENT,
            selectcolor=PANEL, font=("Segoe UI", 9, "bold"), bd=0,
            highlightthickness=0, cursor="hand2",
        )
        self.voice_toggle.pack(side="left", padx=(0, 7))
        self._pill_button(header_actions, "✦  Workspace", self.open_workspace, fill=ACCENT_DARK, ink=ACCENT)

        # Wide hero strip, like a modern AI command dashboard.
        hero = tk.Frame(main, bg="#0C2947", highlightbackground="#1A5274", highlightthickness=1)
        hero.grid(row=1, column=0, sticky="ew", padx=26, pady=(0, 14))
        hero.grid_columnconfigure(0, weight=1)
        hero_copy = tk.Frame(hero, bg="#0C2947")
        hero_copy.grid(row=0, column=0, sticky="w", padx=20, pady=15)
        tk.Label(hero_copy, text="YOUR PERSONAL AI IS READY", bg="#0C2947", fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(hero_copy, text="Think. Create. Get things done.", bg="#0C2947", fg=TEXT,
                 font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(3, 2))
        tk.Label(hero_copy, text="Powered locally by Ollama · Private by design · 25 built-in tools",
                 bg="#0C2947", fg="#A9C7DC", font=("Segoe UI", 9)).pack(anchor="w")
        hero_action = tk.Frame(hero, bg="#0C2947")
        hero_action.grid(row=0, column=1, sticky="e", padx=20)
        self._pill_button(hero_action, "Explore tools  →", self.open_workspace, fill=ACCENT, ink="#06202C")

        # Conversation card and right-hand quick panel.
        body = tk.Frame(main, bg=BG)
        body.grid(row=2, column=0, sticky="nsew", padx=26, pady=(0, 12))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=218)

        chat_card = tk.Frame(body, bg="#0A1D32", highlightbackground="#1B3D59", highlightthickness=1)
        chat_card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        chat_card.grid_rowconfigure(2, weight=1)
        chat_card.grid_columnconfigure(0, weight=1)
        chat_top = tk.Frame(chat_card, bg="#0A1D32")
        chat_top.grid(row=0, column=0, sticky="ew", padx=17, pady=(12, 9))
        tk.Label(chat_top, text="Conversation", bg="#0A1D32", fg=TEXT,
                 font=("Segoe UI", 11, "bold")).pack(side="left")
        tk.Label(chat_top, text="LIVE SESSION", bg="#103D4A", fg=ACCENT,
                 font=("Segoe UI", 7, "bold"), padx=8, pady=4).pack(side="right")
        tk.Frame(chat_card, bg="#183A54", height=1).grid(row=1, column=0, sticky="ew", padx=16)

        chat_shell = tk.Frame(chat_card, bg=BG)
        chat_shell.grid(row=2, column=0, sticky="nsew", padx=7, pady=(5, 8))
        chat_shell.grid_rowconfigure(0, weight=1)
        chat_shell.grid_columnconfigure(0, weight=1)
        self.chat_canvas = tk.Canvas(chat_shell, bg=BG, highlightthickness=0, borderwidth=0)
        scrollbar = tk.Scrollbar(
            chat_shell, orient="vertical", command=self.chat_canvas.yview,
            bg="#143A57", troughcolor=BG, activebackground=ACCENT,
            highlightthickness=0, relief="flat", bd=0, width=9,
        )
        self.chat_canvas.configure(yscrollcommand=scrollbar.set)
        self.chat_canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.message_frame = tk.Frame(self.chat_canvas, bg=BG)
        self.message_window = self.chat_canvas.create_window((0, 0), window=self.message_frame, anchor="nw")
        self.message_frame.bind("<Configure>", self._update_scroll_region)
        self.chat_canvas.bind("<Configure>", self._resize_message_frame)
        self.chat_canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        # Right-side command cards and a concise local-system summary.
        rail = tk.Frame(body, bg=BG, width=218)
        rail.grid(row=0, column=1, sticky="nsew")
        rail.grid_propagate(False)
        tk.Label(rail, text="QUICK LAUNCH", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(3, 9))
        quick_tiles = [
            ("∑", "Calculator", "Calculate 12 + 2 × 3", "#163C67", "#69B6FF"),
            ("⌕", "Web search", "Search the web for AI news", "#103C4A", ACCENT),
            ("▤", "My notes", "Open my notes", "#173A57", "#87C7F6"),
            ("◷", "One-minute timer", "Set a timer for 1 minute", "#153D50", "#64E6D9"),
        ]
        for icon, label, command, tile_bg, icon_fg in quick_tiles:
            tile = tk.Frame(rail, bg="#0D233A", highlightbackground="#1A3F5B", highlightthickness=1)
            tile.pack(fill="x", pady=3)
            row = tk.Frame(tile, bg="#0D233A")
            row.pack(fill="x", padx=9, pady=6)
            icon_badge = tk.Label(row, text=icon, bg=tile_bg, fg=icon_fg,
                                  font=("Segoe UI", 12, "bold"), width=2, pady=3)
            icon_badge.pack(side="left", padx=(0, 8))
            tk.Button(row, text=label, command=lambda value=command: self.use_quick_action(value),
                      bg="#0D233A", fg=TEXT, activebackground="#153A56", activeforeground=ACCENT,
                      relief="flat", bd=0, highlightthickness=0,
                      font=("Segoe UI", 9, "bold"), anchor="w", cursor="hand2").pack(side="left", fill="x", expand=True)

        tk.Label(rail, text="SYSTEM SNAPSHOT", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(13, 6))
        snapshot = tk.Frame(rail, bg="#0D233A", highlightbackground="#1A3F5B", highlightthickness=1)
        snapshot.pack(fill="x")
        self._snapshot_line(snapshot, "AI MODEL", assistant.get_model_name(), ACCENT)
        self._snapshot_line(snapshot, "CONTEXT", f"{assistant.get_num_ctx():,} tokens", TEXT)
        self._snapshot_line(snapshot, "PROCESSING", "On this device", "#8BC8F3")
        tk.Label(rail, text="Tip: press Ctrl + K to open the Workspace.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8), wraplength=205, justify="left").pack(anchor="w", pady=(8, 0))

        # Floating-style composer dock.
        composer_outer = tk.Frame(main, bg=BG)
        composer_outer.grid(row=3, column=0, sticky="ew", padx=26, pady=(0, 17))
        composer_outer.grid_columnconfigure(0, weight=1)
        composer = tk.Frame(composer_outer, bg="#0D2943", highlightbackground="#24617D", highlightthickness=1)
        composer.grid(row=0, column=0, sticky="ew")
        composer.grid_columnconfigure(0, weight=1)
        self.input = tk.Text(
            composer, height=2, wrap="word", bg="#0D2943", fg=TEXT,
            insertbackground=ACCENT, selectbackground=BLUE_DARK, relief="flat", borderwidth=0,
            highlightthickness=0, font=("Segoe UI", 10), padx=15, pady=12, undo=True,
        )
        self.input.grid(row=0, column=0, sticky="nsew", padx=(5, 0), pady=3)
        self.input.insert("1.0", "Ask J.A.R.V.I.S. anything…")
        self.input.configure(fg=MUTED)
        self.input.bind("<FocusIn>", self._remove_placeholder)
        self.input.bind("<Return>", self._on_enter)
        self.input.bind("<KeyRelease>", self._resize_input)
        self.send_button = tk.Button(
            composer, text="Send  ➤", command=self.send_message,
            bg=ACCENT, fg="#06202C", activebackground="#73F3E7", activeforeground="#06202C",
            disabledforeground="#58717A", font=("Segoe UI", 10, "bold"), relief="flat", bd=0,
            padx=19, pady=10, cursor="hand2", highlightthickness=0,
        )
        self.send_button.grid(row=0, column=1, padx=11, pady=10, sticky="se")
        self.status_label = tk.Label(
            composer_outer, text="ENTER TO SEND   ·   SHIFT + ENTER FOR A NEW LINE",
            bg=BG, fg=MUTED, font=("Segoe UI", 7, "bold"),
        )
        self.status_label.grid(row=1, column=0, sticky="w", pady=(7, 0))

        self.root.bind("<Control-l>", lambda _event: self.clear_chat())
        self.root.bind("<Control-n>", lambda _event: self.clear_chat())
        self.root.bind("<Control-s>", lambda _event: self.export_chat())
        self.root.bind("<Control-k>", lambda _event: self.open_workspace(focus_search=True))

    def open_spotify_controls(self) -> None:
        """Open a compact Spotify remote using the app's current theme."""
        window = tk.Toplevel(self.root)
        window.title("J.A.R.V.I.S. — Spotify Controls")
        window.geometry("520x570")
        window.minsize(460, 500)
        window.configure(bg=BG)
        window.transient(self.root)

        outer = tk.Frame(window, bg=BG, padx=24, pady=22)
        outer.pack(fill="both", expand=True)
        tk.Label(outer, text="SPOTIFY  /  MEDIA", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w")
        tk.Label(outer, text="Music controls", bg=BG, fg=TEXT,
                 font=("Segoe UI", 21, "bold")).pack(anchor="w", pady=(2, 3))
        tk.Label(outer, text="Control Spotify without leaving J.A.R.V.I.S.", bg=BG, fg=MUTED,
                 font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 18))

        status = tk.Label(outer, text="Ready. Open Spotify or control its current playback.",
                          bg=PANEL, fg=MUTED, font=("Segoe UI", 9), wraplength=410,
                          justify="left", padx=12, pady=11)
        status.pack(fill="x", pady=(0, 16))

        controls = tk.Frame(outer, bg=BG)
        controls.pack(fill="x")
        actions = (("Open Spotify", "open"), ("Previous", "previous"),
                   ("Play / Pause", "play_pause"), ("Next track", "next"))
        for index, (label, action) in enumerate(actions):
            button = tk.Button(
                controls, text=label,
                command=lambda chosen=action: self._spotify_panel_action(chosen, "", status),
                bg=ACCENT_DARK if action == "play_pause" else PANEL_LIGHT,
                fg=ACCENT if action == "play_pause" else TEXT,
                activebackground=BLUE_DARK, activeforeground=TEXT,
                font=("Segoe UI", 9, "bold"), relief="flat", bd=0,
                padx=10, pady=11, cursor="hand2",
            )
            button.grid(row=index // 2, column=index % 2, sticky="ew", padx=4, pady=4)
        controls.grid_columnconfigure(0, weight=1)
        controls.grid_columnconfigure(1, weight=1)

        # Spotify-only volume uses the Windows audio session for Spotify.exe.
        # It does not touch the Windows master volume or other applications.
        tk.Label(outer, text="SPOTIFY APP VOLUME", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(18, 7))
        volume_header = tk.Frame(outer, bg=BG)
        volume_header.pack(fill="x")
        volume_value = tk.IntVar(value=50)
        volume_readout = tk.Label(volume_header, text="Checking Spotify…", bg=BG, fg=TEXT,
                                  font=("Segoe UI", 10, "bold"))
        volume_readout.pack(side="left")
        volume_hint = tk.Label(volume_header, text="Only changes Spotify", bg=BG, fg=MUTED,
                               font=("Segoe UI", 8))
        volume_hint.pack(side="right")
        volume_scale = tk.Scale(
            outer, from_=0, to=100, orient="horizontal", variable=volume_value,
            showvalue=False, resolution=1, length=420, bg=BG, fg=TEXT,
            troughcolor=PANEL_LIGHT, activebackground=ACCENT,
            highlightthickness=0, bd=0, sliderrelief="flat",
            command=lambda raw: volume_readout.configure(text=f"Spotify volume · {int(float(raw))}%"),
        )
        volume_scale.pack(fill="x", pady=(0, 5))

        volume_buttons = tk.Frame(outer, bg=BG)
        volume_buttons.pack(fill="x")
        tk.Button(
            volume_buttons, text="− 5%", command=lambda: self._spotify_volume_adjust("volume_down", status, volume_value, volume_readout),
            bg=PANEL_LIGHT, fg=TEXT, activebackground=BLUE_DARK, activeforeground=TEXT,
            font=("Segoe UI", 8, "bold"), relief="flat", bd=0, padx=12, pady=7, cursor="hand2",
        ).pack(side="left", padx=(0, 6))
        tk.Button(
            volume_buttons, text="+ 5%", command=lambda: self._spotify_volume_adjust("volume_up", status, volume_value, volume_readout),
            bg=PANEL_LIGHT, fg=TEXT, activebackground=BLUE_DARK, activeforeground=TEXT,
            font=("Segoe UI", 8, "bold"), relief="flat", bd=0, padx=12, pady=7, cursor="hand2",
        ).pack(side="left", padx=6)
        mute_button = tk.Button(
            volume_buttons, text="Mute Spotify", bg=ACCENT_DARK, fg=ACCENT,
            activebackground=BLUE_DARK, activeforeground=TEXT,
            font=("Segoe UI", 8, "bold"), relief="flat", bd=0, padx=12, pady=7, cursor="hand2",
        )
        mute_button.pack(side="right")

        audio_state = {"muted": False}

        def refresh_volume() -> None:
            try:
                state = assistant.spotify.get_spotify_audio_state()
                if state is None:
                    volume_readout.configure(text="Play something in Spotify to control its volume")
                    mute_button.configure(text="Mute Spotify", state="disabled")
                    return
                audio_state["muted"] = bool(state["muted"])
                volume_value.set(int(state["volume"]))
                volume_readout.configure(text=f"Spotify volume · {int(state['volume'])}%")
                mute_button.configure(
                    text="Unmute Spotify" if audio_state["muted"] else "Mute Spotify",
                    state="normal",
                )
                mute_button.configure(command=lambda: self._spotify_volume_mute(
                    "unmute" if audio_state["muted"] else "mute", status, window.after, refresh_volume
                ))
            except Exception as error:
                volume_readout.configure(text="Spotify volume unavailable")
                mute_button.configure(state="disabled")
                status.configure(text=f"Spotify volume check failed: {error}", fg=ERROR)

        def apply_volume(_event=None) -> None:
            result = assistant.spotify_control(action="set_volume", level=volume_value.get())
            status.configure(text=result, fg=SUCCESS if "Set Spotify's own volume" in result else ERROR)
            self.status_label.configure(text=result, fg=ACCENT)
            refresh_volume()

        def poll_volume() -> None:
            try:
                if not window.winfo_exists():
                    return
                refresh_volume()
                window.after(2500, poll_volume)
            except tk.TclError:
                return

        volume_scale.bind("<ButtonRelease-1>", apply_volume)
        volume_scale.bind("<KeyRelease>", apply_volume)
        mute_button.configure(command=lambda: self._spotify_volume_mute("mute", status, window.after, refresh_volume))
        window.after(250, poll_volume)

        tk.Label(outer, text="SEARCH SPOTIFY", bg=BG, fg=ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(18, 7))
        search_row = tk.Frame(outer, bg=BG)
        search_row.pack(fill="x")
        query = tk.StringVar()
        entry = tk.Entry(search_row, textvariable=query, bg=PANEL, fg=TEXT,
                         insertbackground=ACCENT, relief="flat", font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        search_button = tk.Button(
            search_row, text="Search", command=lambda: self._spotify_panel_action("search", query.get(), status),
            bg=ACCENT, fg="#06202C", activebackground="#72EFE3", activeforeground="#06202C",
            font=("Segoe UI", 9, "bold"), relief="flat", bd=0, padx=14, pady=8, cursor="hand2",
        )
        search_button.pack(side="right")
        entry.bind("<Return>", lambda _event: self._spotify_panel_action("search", query.get(), status))
        tk.Label(
            outer,
            text="The volume slider changes Spotify only, not Windows master volume. Playback buttons use global Windows media keys and may reach another active media app.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=420, justify="left",
        ).pack(anchor="w", pady=(12, 0))
        entry.focus_set()

    def _spotify_panel_action(self, action: str, query: str, status: tk.Label) -> None:
        """Run one Spotify action and show the tool's actual result."""
        result = assistant.spotify_control(action=action, query=query)
        try:
            status.configure(text=result, fg=SUCCESS if not result.lower().startswith(("i couldn't", "spotify action not")) else ERROR)
            self.status_label.configure(text=result, fg=ACCENT)
        except tk.TclError:
            pass

    def _spotify_volume_adjust(self, action: str, status: tk.Label, volume_value, volume_readout) -> None:
        """Adjust Spotify's own Windows audio-session volume by five percent."""
        result = assistant.spotify_control(action=action)
        try:
            status.configure(text=result, fg=SUCCESS if "Spotify's own volume" in result else ERROR)
            self.status_label.configure(text=result, fg=ACCENT)
            state = assistant.spotify.get_spotify_audio_state()
            if state is not None:
                volume_value.set(int(state["volume"]))
                volume_readout.configure(text=f"Spotify volume · {int(state['volume'])}%")
        except Exception as error:
            try:
                status.configure(text=f"Spotify volume update failed: {error}", fg=ERROR)
            except tk.TclError:
                pass

    def _spotify_volume_mute(self, action: str, status: tk.Label, after, refresh) -> None:
        """Mute/unmute Spotify only, then refresh the panel state."""
        result = assistant.spotify_control(action=action)
        try:
            status.configure(text=result, fg=SUCCESS if result.startswith(("Muted Spotify", "Unmuted Spotify")) else ERROR)
            self.status_label.configure(text=result, fg=ACCENT)
            after(150, refresh)
        except tk.TclError:
            pass

    def _section_label(self, parent: tk.Widget, text: str, top: int = 0) -> None:
        tk.Label(parent, text=text, bg=SIDEBAR, fg="#6589A7", font=("Segoe UI", 7, "bold")).pack(
            anchor="w", padx=22, pady=(top, 7)
        )

    def _quick_action_button(self, parent: tk.Widget, icon: str, label: str, command) -> None:
        row = tk.Frame(parent, bg=SIDEBAR)
        row.pack(fill="x", padx=14, pady=1)
        tk.Label(row, text=icon, bg=SIDEBAR, fg=ACCENT, width=3,
                 font=("Segoe UI", 10, "bold")).pack(side="left")
        button = tk.Button(row, text=label, command=command, anchor="w", bg=SIDEBAR, fg=MUTED,
                           activebackground="#10334F", activeforeground=TEXT,
                           font=("Segoe UI", 9), relief="flat", bd=0, highlightthickness=0,
                           padx=3, pady=7, cursor="hand2")
        button.pack(side="left", fill="x", expand=True)

    def _pill_button(self, parent: tk.Widget, text: str, command, fill: str = ACCENT, ink: str = "#06202C") -> None:
        tk.Button(parent, text=text, command=command, bg=fill, fg=ink,
                  activebackground="#72EFE3", activeforeground="#06202C",
                  font=("Segoe UI", 9, "bold"), relief="flat", bd=0, highlightthickness=0,
                  padx=13, pady=8, cursor="hand2").pack(side="left")

    @staticmethod
    def _snapshot_line(parent: tk.Widget, label: str, value: str, value_color: str) -> None:
        row = tk.Frame(parent, bg="#0D233A")
        row.pack(fill="x", padx=11, pady=6)
        tk.Label(row, text=label, bg="#0D233A", fg="#6F93AC", font=("Segoe UI", 7, "bold")).pack(anchor="w")
        tk.Label(row, text=value, bg="#0D233A", fg=value_color,
                 font=("Segoe UI", 9, "bold"), wraplength=185, justify="left").pack(anchor="w", pady=(2, 0))

    def _sidebar_button(self, parent: tk.Widget, text: str, command, primary: bool = False, compact: bool = False) -> None:
        button = tk.Button(
            parent, text=text, command=command, anchor="w",
            bg="#103A58" if primary else SIDEBAR,
            fg=ACCENT if primary else MUTED,
            activebackground="#164968", activeforeground=TEXT,
            font=("Segoe UI", 9, "bold" if primary else "normal"),
            relief="flat", bd=0, padx=12, pady=8 if compact else 10,
            cursor="hand2", highlightthickness=1 if primary else 0,
            highlightbackground="#1B5974" if primary else SIDEBAR,
        )
        button.pack(fill="x", padx=12 if compact else 14, pady=3 if compact else 2)

    # ----------------------------- Events / messages -----------------------------

    def _report_tk_exception(self, exc_type, exc_value, exc_traceback) -> None:
        error = exc_value if isinstance(exc_value, BaseException) else RuntimeError(str(exc_value))
        assistant.log_error("Unhandled Tkinter callback exception.", error)
        try:
            self.status_label.configure(text="A display error occurred. Details saved to the J.A.R.V.I.S. log.", fg=ERROR)
        except tk.TclError:
            pass

    def _remove_placeholder(self, _event=None) -> None:
        if self.input.get("1.0", "end-1c") == "Ask J.A.R.V.I.S. anything…":
            self.input.delete("1.0", "end")
            self.input.configure(fg=TEXT)

    def _resize_input(self, _event=None) -> None:
        try:
            lines = int(self.input.index("end-1c").split(".")[0])
            self.input.configure(height=max(2, min(6, lines)))
        except (tk.TclError, ValueError):
            pass

    def _on_enter(self, event: tk.Event):
        if event.state & 0x0001:  # Shift+Enter inserts a newline.
            return None
        self.send_message()
        return "break"

    def _on_mousewheel(self, event: tk.Event) -> None:
        try:
            units = int(-event.delta / 120)
            if units == 0 and event.delta:
                units = -1 if event.delta > 0 else 1
            if units:
                self.chat_canvas.yview_scroll(units, "units")
        except (AttributeError, tk.TclError, TypeError, ValueError):
            pass

    def _scroll_to_bottom(self) -> None:
        """Scroll safely even if a queued callback runs during window shutdown."""
        if self.closing:
            return
        try:
            self.chat_canvas.yview_moveto(1.0)
        except tk.TclError:
            self.closing = True

    def _update_scroll_region(self, _event=None) -> None:
        try:
            self.chat_canvas.configure(scrollregion=self.chat_canvas.bbox("all"))
            if not self.closing:
                self.root.after_idle(self._scroll_to_bottom)
        except tk.TclError:
            self.closing = True

    def _resize_message_frame(self, event: tk.Event) -> None:
        try:
            self.chat_canvas.itemconfigure(self.message_window, width=max(1, event.width))
        except tk.TclError:
            self.closing = True
            return
        wrap = max(300, min(760, event.width - 170))
        for label in self.message_body_labels:
            try:
                label.configure(wraplength=wrap)
            except tk.TclError:
                pass

    def _copy_message(self, message: str) -> None:
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(message)
            self.status_label.configure(text="Message copied to clipboard.", fg=ACCENT)
        except tk.TclError as error:
            assistant.log_error("Could not copy message to clipboard.", error)

    def add_message(self, role: str, message: str) -> None:
        self.transcript.append((role, str(message)))
        if len(self.transcript) > MAX_TRANSCRIPT_MESSAGES:
            del self.transcript[: len(self.transcript) - MAX_TRANSCRIPT_MESSAGES]
        is_user = role == "user"
        row = tk.Frame(self.message_frame, bg=BG)
        row.pack(fill="x", padx=13, pady=7)

        if is_user:
            bubble_bg, edge, accent = USER_BUBBLE, "#2679B8", "#8ACBFF"
            outer = tk.Frame(row, bg=BG)
            outer.pack(anchor="e", padx=(55, 3))
            bubble = tk.Frame(outer, bg=bubble_bg, highlightbackground=edge, highlightthickness=1)
            bubble.pack(side="left", anchor="e")
            avatar = tk.Label(outer, text="YOU", bg="#174A76", fg="#B8E1FF",
                              font=("Segoe UI", 7, "bold"), padx=7, pady=8)
            avatar.pack(side="left", padx=(8, 0), anchor="ne")
            heading_text = "YOU  ·  MESSAGE"
        else:
            bubble_bg, edge, accent = "#0E2B43", "#17647B", ACCENT
            outer = tk.Frame(row, bg=BG)
            outer.pack(anchor="w", padx=(3, 55))
            avatar = tk.Canvas(outer, width=34, height=34, bg=BG, highlightthickness=0)
            avatar.pack(side="left", padx=(0, 9), anchor="ne")
            avatar.create_oval(2, 2, 32, 32, fill="#10485A", outline=ACCENT, width=1)
            avatar.create_text(17, 17, text="J", fill=TEXT, font=("Segoe UI", 12, "bold"))
            bubble = tk.Frame(outer, bg=bubble_bg, highlightbackground=edge, highlightthickness=1)
            bubble.pack(side="left", anchor="w")
            heading_text = "J.A.R.V.I.S.  ·  LOCAL INTELLIGENCE"

        heading = tk.Label(
            bubble, text=heading_text, bg=bubble_bg, fg=accent,
            font=("Segoe UI", 7, "bold"),
        )
        heading.pack(anchor="w", padx=14, pady=(9, 3))
        body = tk.Label(
            bubble, text=str(message), bg=bubble_bg, fg=TEXT,
            justify="left", anchor="w",
            wraplength=max(270, min(650, self.chat_canvas.winfo_width() - 230)),
            font=("Segoe UI", 9), padx=14, pady=0,
        )
        body.pack(anchor="w", fill="x", pady=(0, 11))
        self.message_body_labels.append(body)
        while len(self.message_body_labels) > MAX_DISPLAY_MESSAGES:
            oldest = self.message_body_labels.pop(0)
            try:
                oldest.master.master.destroy()
            except tk.TclError:
                pass

        menu = tk.Menu(self.root, tearoff=False, bg=PANEL, fg=TEXT,
                       activebackground=BLUE_DARK, activeforeground=TEXT)
        menu.add_command(label="Copy message", command=lambda value=str(message): self._copy_message(value))
        for widget in (bubble, heading, body):
            widget.bind("<Button-3>", lambda event, popup=menu: popup.tk_popup(event.x_root, event.y_root))
        self._apply_theme_tree(row, THEMES[self.theme_name])
        if not self.closing:
            try:
                self.root.after_idle(self._scroll_to_bottom)
            except tk.TclError:
                self.closing = True

    def queue_assistant_message(self, message: str) -> None:
        if not self.closing:
            self.events.put(("message", str(message)))

    def _drain_events(self) -> None:
        processed = 0
        while processed < MAX_EVENTS_PER_TICK and not self.closing:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            processed += 1
            try:
                if kind == "message":
                    self.add_message("assistant", str(payload))
                elif kind == "done":
                    self.busy = False
                    self.send_button.configure(state="normal", text="Send  ➤")
                    self.status_label.configure(text="Enter to send  •  Shift + Enter for a new line", fg=MUTED)
                elif kind == "status":
                    ok, status_text = payload
                    palette = THEMES[self.theme_name]
                    self.connection_label.configure(
                        text=status_text,
                        fg=palette["SUCCESS"] if ok else palette["ERROR"],
                        bg=palette["STATUS_GOOD_BG"] if ok else palette["STATUS_BAD_BG"],
                    )
                elif kind == "model_list":
                    combo, hint, models, error_text = payload
                    try:
                        if combo.winfo_exists():
                            suggestions = list(assistant.MODEL_SUGGESTIONS)
                            combo.configure(values=sorted(set(suggestions + models), key=str.casefold))
                        if hint.winfo_exists():
                            if models:
                                hint.configure(text="Installed: " + ", ".join(models))
                            else:
                                hint.configure(text=error_text or "No models found. Check that Ollama is running.")
                    except tk.TclError:
                        pass
                elif kind == "model_manager_list":
                    listbox, status_label, models, error_text = payload
                    try:
                        if listbox.winfo_exists():
                            listbox.delete(0, "end")
                            for item in models:
                                details = " · ".join(part for part in (
                                    item.get("parameter_size", ""),
                                    model_manager.format_bytes(item.get("size", 0)),
                                    item.get("quantization", ""),
                                ) if part)
                                listbox.insert("end", f"{item['name']}  —  {details}" if details else item["name"])
                            listbox.model_names = [item["name"] for item in models]
                        if status_label.winfo_exists():
                            status_label.configure(text=f"{len(models)} installed model(s) found." if models else (error_text or "No models installed yet."))
                    except tk.TclError:
                        pass
                elif kind == "model_manager_progress":
                    dialog, progressbar, status_label, percent, message = payload
                    try:
                        if dialog.winfo_exists():
                            progressbar.stop()
                            progressbar.configure(mode="determinate", maximum=100, value=max(0, min(100, percent)))
                            status_label.configure(text=message)
                    except tk.TclError:
                        pass
                elif kind == "model_manager_done":
                    dialog, progressbar, progress_status, listbox, list_status, download_button, model_tag, error_text = payload
                    try:
                        if dialog.winfo_exists():
                            progressbar.stop()
                            progressbar.configure(mode="determinate", maximum=100, value=100 if not error_text else 0)
                            download_button.configure(state="normal")
                            progress_status.configure(text=(f"Installed {model_tag}. Select it and choose Use model." if not error_text else f"Download failed: {error_text}"))
                            self._refresh_model_manager(listbox, list_status)
                    except tk.TclError:
                        pass
                elif kind == "model_manager_delete_done":
                    listbox, status_label, model_tag, error_text = payload
                    try:
                        if listbox.winfo_exists():
                            status_label.configure(text=(f"Deleted {model_tag}." if not error_text else f"Delete failed: {error_text}"))
                            self._refresh_model_manager(listbox, status_label)
                    except tk.TclError:
                        pass
                else:
                    assistant.log_error(f"Ignored unknown GUI event: {kind!r}")
            except Exception as error:
                assistant.log_error(f"Could not process GUI event {kind!r}.", error)
        if not self.closing:
            try:
                self.root.after(100, self._drain_events)
            except tk.TclError:
                self.closing = True

    # ----------------------------- Assistant actions -----------------------------

    def send_message(self) -> None:
        if self.busy or self.closing:
            return
        user_text = self.input.get("1.0", "end-1c").strip()
        if user_text == "Ask J.A.R.V.I.S. anything…" or not user_text:
            return
        if len(user_text) > assistant.MAX_INPUT_LENGTH:
            messagebox.showwarning("Message too long", f"Please keep messages under {assistant.MAX_INPUT_LENGTH} characters.")
            return

        self.input.delete("1.0", "end")
        self.input.configure(fg=TEXT, height=3)
        self.add_message("user", user_text)
        if user_text.lower() in {"exit", "quit", "shutdown", "goodbye"}:
            self.add_message("assistant", "Shutting down. Goodbye.")
            self.root.after(500, self.close)
            return

        self.busy = True
        self.send_button.configure(state="disabled", text="Thinking…")
        self.status_label.configure(text="J.A.R.V.I.S. is thinking…", fg=ACCENT)
        worker = threading.Thread(
            target=self._run_request, args=(user_text,),
            name="JARVIS-Request", daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            assistant.log_error("Could not start the assistant request thread.", error)
            self.busy = False
            self.send_button.configure(state="normal", text="Send  ➤")
            self.status_label.configure(text="J.A.R.V.I.S. could not start the request. Please try again.", fg=ERROR)

    def _run_request(self, user_text: str) -> None:
        try:
            assistant.process_user_request(user_text, self.history)
        except Exception as error:
            assistant.log_error("Unexpected assistant request error.", error)
            self.queue_assistant_message(f"Something went wrong. Details were saved to {assistant.user_data_dir() / 'jarvis.log'}.")
        finally:
            self.events.put(("done", None))

    def use_quick_action(self, command: str) -> None:
        if self.busy:
            return
        self.input.delete("1.0", "end")
        self.input.configure(fg=TEXT)
        self.input.insert("1.0", command)
        self.send_message()

    def toggle_voice(self) -> None:
        assistant.set_voice_enabled(self.voice_var.get())
        state = "on" if self.voice_var.get() else "off"
        self.status_label.configure(text=f"Voice responses turned {state}.", fg=ACCENT)

    def clear_chat(self) -> None:
        if self.busy:
            self.status_label.configure(text="Wait for the current response before starting a new conversation.", fg=MUTED)
            return
        for child in self.message_frame.winfo_children():
            child.destroy()
        self.message_body_labels.clear()
        self.transcript.clear()
        self.history = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.add_message("assistant", "New conversation started. How can I help?")

    def export_chat(self) -> None:
        if not self.history:
            return
        destination = filedialog.asksaveasfilename(
            title="Export J.A.R.V.I.S. conversation",
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("Markdown files", "*.md")],
            initialfile="jarvis_conversation.txt",
        )
        if not destination:
            return
        lines = ["J.A.R.V.I.S. Conversation", "=" * 28, ""]
        for role, raw_content in list(self.transcript):
            if role not in {"user", "assistant"}:
                continue
            content = str(raw_content).strip()
            if content:
                lines.extend(["You" if role == "user" else "J.A.R.V.I.S.", content, ""])
        try:
            Path(destination).write_text("\n".join(lines), encoding="utf-8")
            self.status_label.configure(text=f"Conversation exported to {destination}", fg=ACCENT)
        except OSError as error:
            assistant.log_error("Conversation export failed.", error)
            messagebox.showerror("Export failed", str(error))

    def _refresh_model_manager(self, listbox: tk.Listbox, status_label: tk.Label) -> None:
        """Refresh the model-manager list without blocking the Tk event loop."""
        def worker() -> None:
            try:
                models = model_manager.list_models()
                error_text = ""
            except Exception as error:
                models = []
                error_text = str(error)
            self.events.put(("model_manager_list", (listbox, status_label, models, error_text)))

        threading.Thread(target=worker, name="JARVIS-Model-Refresh", daemon=True).start()

    def open_model_manager(self, parent: tk.Misc | None = None, on_model_selected=None) -> None:
        """Open the built-in Ollama model manager for downloading and managing models."""
        if self.closing:
            return
        existing = getattr(self, "model_manager_window", None)
        try:
            if existing is not None and existing.winfo_exists():
                existing.lift()
                existing.focus_force()
                return
        except tk.TclError:
            pass

        owner = parent or self.root
        palette = THEMES[self.theme_name]
        window = tk.Toplevel(owner)
        self.model_manager_window = window
        window.title("J.A.R.V.I.S. · AI Model Manager")
        window.geometry("760x610")
        window.minsize(660, 540)
        window.configure(bg=BG)
        window.transient(owner)
        try:
            window.grab_set()
        except tk.TclError:
            pass

        header = tk.Frame(window, bg=SIDEBAR, highlightbackground=BORDER, highlightthickness=1)
        header.pack(fill="x", padx=18, pady=(18, 12))
        tk.Label(header, text="AI MODEL MANAGER", bg=SIDEBAR, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=16, pady=(13, 3))
        tk.Label(header, text="Choose, download and manage your local Ollama models.",
                 bg=SIDEBAR, fg=TEXT, font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=16, pady=(0, 12))

        body = tk.Frame(window, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        left = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1)
        left.pack(side="left", fill="both", expand=True, padx=(0, 10))
        right = tk.Frame(body, bg=PANEL, highlightbackground=BORDER, highlightthickness=1, width=270)
        right.pack(side="right", fill="y")
        right.pack_propagate(False)

        tk.Label(left, text="INSTALLED MODELS", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(14, 7))
        list_frame = tk.Frame(left, bg=PANEL)
        list_frame.pack(fill="both", expand=True, padx=12, pady=(0, 8))
        model_list = tk.Listbox(
            list_frame, bg=PANEL_LIGHT, fg=TEXT, selectbackground=BLUE_DARK,
            selectforeground=TEXT, highlightthickness=1, highlightbackground=BORDER,
            relief="flat", activestyle="none", font=("Segoe UI", 9),
            exportselection=False,
        )
        model_list.pack(side="left", fill="both", expand=True)
        model_scroll = ttk.Scrollbar(list_frame, orient="vertical", command=model_list.yview)
        model_scroll.pack(side="right", fill="y")
        model_list.configure(yscrollcommand=model_scroll.set)
        model_list.model_names = []
        model_status = tk.Label(left, text="Connecting to Ollama…", bg=PANEL, fg=MUTED,
                                 font=("Segoe UI", 8), wraplength=410, justify="left")
        model_status.pack(anchor="w", padx=14, pady=(0, 12))
        tk.Button(left, text="Refresh installed models", command=lambda: self._refresh_model_manager(model_list, model_status),
                  bg=PANEL_LIGHT, fg=TEXT, activebackground=BORDER, relief="flat",
                  padx=12, pady=8, cursor="hand2").pack(anchor="w", padx=14, pady=(0, 14))

        tk.Label(right, text="ADD A MODEL", bg=PANEL, fg=ACCENT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14, pady=(14, 8))
        tk.Label(right, text="Popular choices", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14)
        catalogue_labels = [f"{item['label']}  ·  {item['name']}" for item in model_manager.MODEL_CATALOGUE]
        catalogue_var = tk.StringVar(value=catalogue_labels[0])
        catalogue_combo = ttk.Combobox(
            right, textvariable=catalogue_var, values=catalogue_labels,
            state="readonly", style="Jarvis.TCombobox", width=29,
        )
        catalogue_combo.pack(fill="x", padx=14, pady=(5, 10))
        tk.Label(right, text="Or enter any Ollama model tag", bg=PANEL, fg=TEXT,
                 font=("Segoe UI", 9, "bold")).pack(anchor="w", padx=14)
        custom_var = tk.StringVar()
        custom_entry = tk.Entry(right, textvariable=custom_var, bg=PANEL_LIGHT, fg=TEXT,
                                insertbackground=ACCENT, relief="flat", font=("Segoe UI", 9))
        custom_entry.pack(fill="x", padx=14, pady=(5, 10), ipady=7)
        tk.Label(right, text="Model downloads can be several GB. They are stored by Ollama and are kept when J.A.R.V.I.S. updates.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 8), wraplength=230,
                 justify="left").pack(anchor="w", padx=14, pady=(0, 10))
        progress = ttk.Progressbar(right, mode="determinate", maximum=100, value=0,
                                   style="Jarvis.Horizontal.TProgressbar")
        progress.pack(fill="x", padx=14, pady=(3, 5))
        progress_status = tk.Label(right, text="Ready", bg=PANEL, fg=MUTED,
                                   font=("Segoe UI", 8), wraplength=230, justify="left")
        progress_status.pack(anchor="w", padx=14, pady=(0, 8))

        def selected_tag() -> str | None:
            selection = model_list.curselection()
            if not selection:
                return None
            index = int(selection[0])
            names = getattr(model_list, "model_names", [])
            return names[index] if 0 <= index < len(names) else None

        def start_pull() -> None:
            typed = custom_var.get().strip()
            if typed:
                tag = typed
            else:
                label = catalogue_var.get()
                tag = next((item["name"] for item, display in zip(model_manager.MODEL_CATALOGUE, catalogue_labels) if display == label), "")
            try:
                tag = model_manager.validate_model_tag(tag)
            except ValueError as error:
                messagebox.showwarning("Invalid model tag", str(error), parent=window)
                return
            download_button.configure(state="disabled")
            progress.configure(mode="indeterminate")
            progress.start(12)
            progress_status.configure(text=f"Preparing download: {tag}")

            def worker() -> None:
                error_text = ""
                try:
                    model_manager.pull_model(
                        tag,
                        progress_callback=lambda info: self.events.put((
                            "model_manager_progress", (
                                window, progress, progress_status,
                                info.get("percent", 0),
                                f"{info.get('status', 'Downloading')} · {model_manager.format_bytes(info.get('completed', 0))} / {model_manager.format_bytes(info.get('total', 0))}",
                            )
                        )),
                    )
                except Exception as error:
                    error_text = str(error)
                self.events.put(("model_manager_done", (window, progress, progress_status, model_list, model_status, download_button, tag, error_text)))

            try:
                threading.Thread(target=worker, name="JARVIS-Model-Download", daemon=True).start()
            except RuntimeError as error:
                progress.stop()
                download_button.configure(state="normal")
                progress_status.configure(text=f"Could not start download: {error}")

        def use_selected() -> None:
            tag = selected_tag()
            if not tag:
                messagebox.showinfo("Select a model", "Select an installed model first.", parent=window)
                return
            try:
                if callable(on_model_selected):
                    # When opened from Settings, defer persistence until the
                    # parent Settings dialog's Save button is pressed.
                    on_model_selected(tag)
                    progress_status.configure(text=f"{tag} selected. Press Save in Assistant Settings to apply it.")
                else:
                    assistant.set_model_name(tag)
                    self.model_label.configure(text=f"{tag} · {assistant.get_num_ctx():,} token context · On-device")
                    progress_status.configure(text=f"{tag} is now the active assistant model.")
            except Exception as error:
                messagebox.showerror("Could not select model", str(error), parent=window)

        def remove_selected() -> None:
            tag = selected_tag()
            if not tag:
                messagebox.showinfo("Select a model", "Select an installed model first.", parent=window)
                return
            if tag.casefold() == assistant.get_model_name().casefold():
                messagebox.showwarning("Model is in use", "Choose a different active model before deleting this one.", parent=window)
                return
            if not messagebox.askyesno("Delete model", f"Delete {tag} from Ollama? This removes its local model files.", parent=window):
                return
            progress_status.configure(text=f"Deleting {tag}…")

            def worker() -> None:
                error_text = ""
                try:
                    model_manager.delete_model(tag)
                except Exception as error:
                    error_text = str(error)
                self.events.put(("model_manager_delete_done", (model_list, progress_status, tag, error_text)))
            threading.Thread(target=worker, name="JARVIS-Model-Delete", daemon=True).start()

        actions = tk.Frame(right, bg=PANEL)
        actions.pack(fill="x", padx=14, pady=(4, 14))
        download_button = tk.Button(actions, text="Download model", command=start_pull,
                                    bg=ACCENT, fg="#07151B", activebackground=ACCENT,
                                    relief="flat", padx=12, pady=9, cursor="hand2")
        download_button.pack(fill="x", pady=(0, 7))
        tk.Button(actions, text="Use selected model", command=use_selected,
                  bg=BLUE_DARK, fg=TEXT, activebackground=BLUE,
                  relief="flat", padx=12, pady=8, cursor="hand2").pack(fill="x", pady=(0, 7))
        tk.Button(actions, text="Delete selected model", command=remove_selected,
                  bg=PANEL_LIGHT, fg=TEXT, activebackground=BORDER,
                  relief="flat", padx=12, pady=8, cursor="hand2").pack(fill="x")

        def close_manager() -> None:
            try:
                window.grab_release()
                window.destroy()
            except tk.TclError:
                pass
            self.model_manager_window = None
            if parent is not None:
                try:
                    parent.grab_set()
                except tk.TclError:
                    pass

        window.protocol("WM_DELETE_WINDOW", close_manager)
        window.bind("<Escape>", lambda _event: close_manager())
        self._apply_theme_tree(window, THEMES[self.theme_name])
        self._refresh_model_manager(model_list, model_status)

    def open_settings(self) -> None:
        if self.busy:
            messagebox.showinfo("Assistant busy", "Wait until the current response has finished before changing settings.")
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("J.A.R.V.I.S. settings")
        dialog.configure(bg=BG)
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()
        original_theme = self.theme_name
        theme_var = tk.StringVar(value=THEME_NAMES.get(self.theme_name, THEME_NAMES["midnight"]))
        tk.Label(dialog, text="Appearance theme", bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(18, 5))
        theme_combo = ttk.Combobox(
            dialog, textvariable=theme_var, values=tuple(THEME_NAMES.values()),
            state="readonly", width=36, style="Jarvis.TCombobox",
        )
        theme_combo.pack(fill="x", padx=18, pady=(0, 4), ipady=4)
        theme_hint = tk.Label(
            dialog, text="Preview themes instantly. Save to keep your choice next time.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=360, justify="left",
        )
        theme_hint.pack(anchor="w", padx=18, pady=(0, 13))

        def preview_theme(_event=None) -> None:
            selected = THEME_LABEL_TO_KEY.get(theme_var.get(), original_theme)
            self.apply_theme(selected)

        theme_combo.bind("<<ComboboxSelected>>", preview_theme)
        tk.Label(dialog, text="Ollama model", bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(0, 5))
        model_var = tk.StringVar(value=assistant.get_model_name())
        model_combo = ttk.Combobox(
            dialog,
            textvariable=model_var,
            values=assistant.MODEL_SUGGESTIONS,
            width=36,
            style="Jarvis.TCombobox",
        )
        model_combo.pack(fill="x", padx=18, pady=(0, 6), ipady=4)
        tk.Label(
            dialog,
            text="Recommended for this PC: gemma4:e2b. Choose a model already installed in Ollama; you can also type another exact model tag.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=360, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 7))

        model_hint = tk.Label(dialog, text="Installed model list has not been refreshed yet.", bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=360, justify="left")
        model_hint.pack(anchor="w", padx=18, pady=(0, 8))

        def refresh_models() -> None:
            model_hint.configure(text="Checking installed Ollama models…")

            def worker() -> None:
                try:
                    models = assistant.ensure_ollama_available(timeout=12.0)
                    error_text = ""
                except Exception as error:
                    models = []
                    error_text = f"Could not read Ollama models: {error}"
                self.events.put(("model_list", (model_combo, model_hint, models, error_text)))

            model_worker = threading.Thread(target=worker, name="JARVIS-Model-List", daemon=True)
            try:
                model_worker.start()
            except RuntimeError as error:
                assistant.log_error("Could not start installed-model discovery.", error)
                model_hint.configure(text="Could not start model discovery. Check jarvis.log for details.")

        model_actions = tk.Frame(dialog, bg=BG)
        model_actions.pack(fill="x", padx=18, pady=(0, 14))
        tk.Button(
            model_actions, text="Refresh installed models", command=refresh_models,
            bg=PANEL_LIGHT, fg=TEXT, relief="flat", padx=10, pady=5,
        ).pack(side="left")
        tk.Button(
            model_actions, text="Manage / download models…",
            command=lambda: self.open_model_manager(parent=dialog, on_model_selected=model_var.set),
            bg=BLUE_DARK, fg=TEXT, activebackground=BLUE,
            relief="flat", padx=10, pady=5, cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        tk.Label(dialog, text="Context window", bg=BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=18, pady=(0, 5))
        context_var = tk.StringVar(value=str(assistant.get_num_ctx()))
        context_combo = ttk.Combobox(
            dialog, textvariable=context_var,
            values=tuple(str(value) for value in assistant.SUPPORTED_CONTEXT_SIZES),
            state="readonly", width=14, style="Jarvis.TCombobox",
        )
        context_combo.pack(anchor="w", padx=18, pady=(0, 6))
        tk.Label(
            dialog,
            text="8,192 is the recommended balance for 16 GB RAM. Lower values can reduce memory use; higher values allow longer conversations but need more memory.",
            bg=BG, fg=MUTED, font=("Segoe UI", 8), wraplength=360, justify="left",
        ).pack(anchor="w", padx=18, pady=(0, 14))

        timer_sound_var = tk.BooleanVar(value=bool(assistant.load_settings().get("timer_sound_enabled", True)))
        timer_sound_row = tk.Frame(dialog, bg=BG)
        timer_sound_row.pack(fill="x", padx=18, pady=(0, 14))
        tk.Checkbutton(
            timer_sound_row, text="Play a custom 10-second alarm when a timer finishes",
            variable=timer_sound_var, bg=BG, fg=TEXT, activebackground=BG,
            activeforeground=TEXT, selectcolor=PANEL, font=("Segoe UI", 9),
            relief="flat", highlightthickness=0,
        ).pack(side="left", anchor="w")
        timer_sound_actions = tk.Frame(dialog, bg=BG)
        timer_sound_actions.pack(fill="x", padx=18, pady=(0, 14))
        tk.Button(
            timer_sound_actions, text="Test 10-second alarm",
            command=lambda: assistant.play_timer_sound(force=True),
            bg=PANEL_LIGHT, fg=TEXT, activebackground=BORDER, relief="flat",
            padx=10, pady=5, cursor="hand2",
        ).pack(side="left")
        tk.Button(
            timer_sound_actions, text="Stop sound", command=assistant.stop_timer_sound,
            bg=PANEL_LIGHT, fg=TEXT, activebackground=BORDER, relief="flat",
            padx=10, pady=5, cursor="hand2",
        ).pack(side="left", padx=(8, 0))

        def save_and_close() -> None:
            try:
                chosen, context_size = assistant.set_runtime_preferences(model_var.get(), int(context_var.get()))
            except (ValueError, OSError) as error:
                messagebox.showerror("Could not save settings", str(error), parent=dialog)
                return
            try:
                assistant.save_settings(
                    theme=self.theme_name,
                    timer_sound_enabled=timer_sound_var.get(),
                )
                assistant.set_timer_sound_enabled(timer_sound_var.get(), persist=False)
            except (ValueError, OSError) as error:
                messagebox.showerror("Could not save settings", str(error), parent=dialog)
                return
            self.model_label.configure(text=f"{chosen} · {context_size:,} token context · On-device")
            dialog.destroy()
            self._start_connection_check()

        def cancel_and_restore() -> None:
            self.apply_theme(original_theme)
            try:
                dialog.destroy()
            except tk.TclError:
                pass

        buttons = tk.Frame(dialog, bg=BG)
        buttons.pack(fill="x", padx=18, pady=(0, 18))
        tk.Button(buttons, text="Cancel", command=cancel_and_restore, bg=PANEL_LIGHT, fg=TEXT, relief="flat", padx=14, pady=7).pack(side="right", padx=(6, 0))
        tk.Button(buttons, text="Save", command=save_and_close, bg=ACCENT, fg="#07151B", relief="flat", padx=16, pady=7).pack(side="right")
        dialog.protocol("WM_DELETE_WINDOW", cancel_and_restore)
        self._apply_theme_tree(dialog, THEMES[self.theme_name])
        model_combo.focus_set()
        refresh_models()
        dialog.bind("<Return>", lambda _event: save_and_close())

    def _start_connection_check(self) -> None:
        if self.closing:
            return
        self.connection_label.configure(text="Checking Ollama…", fg=MUTED)
        worker = threading.Thread(
            target=self._connection_check_worker,
            name="JARVIS-Ollama-Check",
            daemon=True,
        )
        try:
            worker.start()
        except RuntimeError as error:
            assistant.log_error("Could not start the Ollama status check.", error)
            self.events.put(("status", (False, "Ollama status unavailable")))

    def _connection_check_worker(self) -> None:
        try:
            status = assistant.check_ollama_status()
        except Exception as error:
            assistant.log_error("Ollama status check failed unexpectedly.", error)
            status = (False, "Ollama status unavailable · see jarvis.log")
        self.events.put(("status", status))

    def open_workspace(self, focus_search: bool = False) -> None:
        """Open the searchable 25-tool workspace / command centre."""
        if self.workspace_window is not None:
            try:
                if self.workspace_window.winfo_exists():
                    self.workspace_window.deiconify()
                    self.workspace_window.lift()
                    if focus_search:
                        self.workspace_search.focus_set()
                    return
            except tk.TclError:
                self.workspace_window = None

        window = tk.Toplevel(self.root)
        self.workspace_window = window
        window.title("J.A.R.V.I.S. — Workspace")
        window.configure(bg=BG)
        window.geometry("1040x760")
        window.minsize(760, 560)
        window.transient(self.root)
        window.protocol("WM_DELETE_WINDOW", lambda: self._close_workspace_window())

        header = tk.Frame(window, bg=BG)
        header.pack(fill="x", padx=28, pady=(24, 16))
        top = tk.Frame(header, bg=BG)
        top.pack(fill="x")
        tk.Label(top, text="Command Centre", bg=BG, fg=TEXT,
                 font=("Segoe UI", 23, "bold")).pack(side="left")
        tk.Label(top, text="25 LOCAL TOOLS", bg=ACCENT_DARK, fg=ACCENT,
                 font=("Segoe UI", 8, "bold"), padx=10, pady=6).pack(side="right")
        tk.Label(header, text="Find a tool, filter by category, then launch an example directly in chat.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=(5, 14))

        controls = tk.Frame(header, bg=BG)
        controls.pack(fill="x")
        self.workspace_search = tk.StringVar()
        search = tk.Entry(controls, textvariable=self.workspace_search, bg=PANEL,
                          fg=TEXT, insertbackground=ACCENT, relief="flat",
                          font=("Segoe UI", 11), highlightthickness=1,
                          highlightbackground=BORDER, highlightcolor=ACCENT)
        search.pack(side="left", fill="x", expand=True, ipady=10, padx=(0, 10))
        search.insert(0, "Search tools, categories or keywords…")
        search.configure(fg=MUTED)
        search.bind("<FocusIn>", lambda _e: self._workspace_search_placeholder(search, True))
        search.bind("<FocusOut>", lambda _e: self._workspace_search_placeholder(search, False))
        category_var = tk.StringVar(value="All categories")
        categories = ["All categories"] + sorted({item["category"] for item in workspace.FEATURE_CATALOG})
        category = ttk.Combobox(controls, textvariable=category_var, values=categories,
                                state="readonly", width=22, style="Jarvis.TCombobox")
        category.pack(side="right", ipady=5)

        content = tk.Frame(window, bg=BG)
        content.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(0, weight=1)
        count_label = tk.Label(content, text="25 tools available", bg=BG, fg=MUTED,
                               font=("Segoe UI", 9, "bold"))
        count_label.grid(row=0, column=0, sticky="w", pady=(0, 10))
        grid_shell = tk.Frame(content, bg=BG)
        grid_shell.grid(row=1, column=0, sticky="nsew")
        grid_shell.grid_rowconfigure(0, weight=1)
        grid_shell.grid_columnconfigure(0, weight=1)
        canvas = tk.Canvas(grid_shell, bg=BG, highlightthickness=0, borderwidth=0)
        bar = tk.Scrollbar(
            grid_shell, orient="vertical", command=canvas.yview,
            bg="#143A57", troughcolor=BG, activebackground=ACCENT,
            highlightthickness=0, relief="flat", bd=0, width=9,
        )
        canvas.configure(yscrollcommand=bar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        bar.grid(row=0, column=1, sticky="ns")
        cards_frame = tk.Frame(canvas, bg=BG)
        card_window = canvas.create_window((0, 0), window=cards_frame, anchor="nw")
        cards_frame.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(card_window, width=event.width))
        canvas.bind_all("<MouseWheel>", self._on_mousewheel)

        def draw_cards(*_args) -> None:
            query = self.workspace_search.get().strip().casefold()
            if query == "search tools, categories or keywords…":
                query = ""
            selected_category = category_var.get()
            matches = [item for item in workspace.FEATURE_CATALOG
                       if (selected_category == "All categories" or item["category"] == selected_category)
                       and (not query or query in " ".join((item["title"], item["description"], item["category"], item["keywords"])).casefold())]
            for child in cards_frame.winfo_children():
                child.destroy()
            count_label.configure(text=f"{len(matches)} of 25 tools shown")
            if not matches:
                tk.Label(cards_frame, text="No tools match that search. Try another phrase.",
                         bg=BG, fg=MUTED, font=("Segoe UI", 11)).pack(pady=40)
                self._apply_theme_tree(cards_frame, THEMES[self.theme_name])
                return
            for index, item in enumerate(matches):
                row, col = divmod(index, 2)
                card = tk.Frame(cards_frame, bg=PANEL, highlightbackground=BORDER,
                                highlightthickness=1, padx=16, pady=14)
                card.grid(row=row, column=col, sticky="nsew", padx=7, pady=7)
                cards_frame.grid_columnconfigure(col, weight=1, uniform="workspace")
                title_row = tk.Frame(card, bg=PANEL)
                title_row.pack(fill="x")
                tk.Label(title_row, text=item["title"], bg=PANEL, fg=TEXT,
                         font=("Segoe UI", 11, "bold")).pack(side="left")
                tk.Label(title_row, text=item["category"].upper(), bg=ACCENT_DARK,
                         fg=ACCENT, font=("Segoe UI", 7, "bold"), padx=6, pady=3).pack(side="right")
                tk.Label(card, text=item["description"], bg=PANEL, fg=MUTED,
                         font=("Segoe UI", 9), justify="left", anchor="w",
                         wraplength=390, height=2).pack(fill="x", pady=(9, 12))
                action_row = tk.Frame(card, bg=PANEL)
                action_row.pack(fill="x")
                tk.Button(action_row, text="Use example  →",
                          command=lambda data=item: self._launch_workspace_feature(data),
                          bg=ACCENT, fg="#07151B", activebackground="#66E5D7",
                          relief="flat", bd=0, font=("Segoe UI", 9, "bold"),
                          padx=12, pady=7, cursor="hand2").pack(side="left")
                tk.Button(action_row, text="Copy command",
                          command=lambda value=item["command"]: self._copy_message(value),
                          bg=PANEL_LIGHT, fg=TEXT, activebackground=BORDER,
                          relief="flat", bd=0, font=("Segoe UI", 9),
                          padx=10, pady=7, cursor="hand2").pack(side="left", padx=(8, 0))
            self._apply_theme_tree(cards_frame, THEMES[self.theme_name])

        self.workspace_search.trace_add("write", draw_cards)
        category_var.trace_add("write", draw_cards)
        draw_cards()
        search.bind("<Return>", lambda _e: "break")
        if focus_search:
            search.focus_set()
        window.bind("<Escape>", lambda _e: self._close_workspace_window())
        window.bind("<Control-k>", lambda _e: search.focus_set())
        self._apply_theme_tree(window, THEMES[self.theme_name])

    @staticmethod
    def _workspace_search_placeholder(entry: tk.Entry, focused: bool) -> None:
        placeholder = "Search tools, categories or keywords…"
        try:
            if focused and entry.get() == placeholder:
                entry.delete(0, "end")
                entry.configure(fg=TEXT)
            elif not focused and not entry.get().strip():
                entry.insert(0, placeholder)
                entry.configure(fg=MUTED)
        except tk.TclError:
            pass

    def _close_workspace_window(self) -> None:
        window = self.workspace_window
        self.workspace_window = None
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _launch_workspace_feature(self, feature: dict[str, str]) -> None:
        if feature["id"] == "stopwatch":
            self.open_stopwatch()
            return
        command = feature["command"]
        self.use_quick_action(command)
        self.status_label.configure(text=f"Workspace · {feature['title']}", fg=ACCENT)

    def open_stopwatch(self) -> None:
        dialog = tk.Toplevel(self.root)
        dialog.title("J.A.R.V.I.S. — Stopwatch")
        dialog.configure(bg=BG)
        dialog.geometry("390x300")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        watch = workspace.Stopwatch()
        running = {"value": False}
        destroyed = {"value": False}
        display = tk.Label(dialog, text="00:00.00", bg=BG, fg=ACCENT,
                           font=("Segoe UI", 34, "bold"))
        display.pack(pady=(35, 18))
        lap_label = tk.Label(dialog, text="No laps yet", bg=BG, fg=MUTED,
                             font=("Segoe UI", 9))
        lap_label.pack(pady=(0, 12))
        buttons = tk.Frame(dialog, bg=BG)
        buttons.pack(pady=12)

        def render() -> None:
            if destroyed["value"]:
                return
            elapsed = watch.elapsed()
            minutes, rest = divmod(elapsed, 60)
            seconds = int(rest)
            hundredths = int((rest - seconds) * 100)
            display.configure(text=f"{int(minutes):02d}:{seconds:02d}.{hundredths:02d}")
            if running["value"]:
                dialog.after(50, render)

        def toggle() -> None:
            if running["value"]:
                watch.stop(); running["value"] = False
                start_button.configure(text="Start")
            else:
                watch.start(); running["value"] = True
                start_button.configure(text="Pause")
                render()

        def lap() -> None:
            value = watch.lap()
            lap_label.configure(text=f"Lap {len(watch.laps())}: {value:.2f}s")

        def reset() -> None:
            watch.reset(); running["value"] = False
            start_button.configure(text="Start")
            display.configure(text="00:00.00")
            lap_label.configure(text="No laps yet")

        start_button = tk.Button(buttons, text="Start", command=toggle, bg=ACCENT,
                                 fg="#07151B", relief="flat", padx=18, pady=8)
        start_button.pack(side="left", padx=5)
        tk.Button(buttons, text="Lap", command=lap, bg=PANEL_LIGHT, fg=TEXT,
                  relief="flat", padx=18, pady=8).pack(side="left", padx=5)
        tk.Button(buttons, text="Reset", command=reset, bg=PANEL_LIGHT, fg=TEXT,
                  relief="flat", padx=18, pady=8).pack(side="left", padx=5)

        def close_watch() -> None:
            destroyed["value"] = True
            try:
                dialog.destroy()
            except tk.TclError:
                pass
        dialog.protocol("WM_DELETE_WINDOW", close_watch)
        self._apply_theme_tree(dialog, THEMES[self.theme_name])

    def _poll_reminders(self) -> None:
        if self.closing:
            return
        try:
            reminders = workspace.ReminderManager().due()
            for reminder in reminders:
                identifier = str(reminder.get("id", ""))
                if identifier and identifier not in self._notified_reminder_ids:
                    self._notified_reminder_ids.add(identifier)
                    assistant.speak(f"Reminder: {reminder.get('title', 'You have a reminder')}. Say dismiss reminder {identifier[:8]} when finished.")
        except Exception as error:
            assistant.log_error("Could not check saved reminders.", error)
        try:
            self.root.after(30_000, self._poll_reminders)
        except tk.TclError:
            self.closing = True

    def close(self) -> None:
        if self.closing:
            return
        try:
            assistant.save_settings(window_geometry=self.root.geometry())
        except Exception as error:
            # A settings or Tk geometry failure must never prevent the window
            # from closing. Preserve the detail in the diagnostic log.
            assistant.log_error("Could not save the desktop window size.", error)
        self.closing = True
        assistant.ui_message_callback = None
        try:
            self.root.unbind_all("<MouseWheel>")
            self.root.destroy()
        except tk.TclError:
            pass


def main() -> None:
    try:
        root = tk.Tk()
        JarvisApp(root)
        root.mainloop()
    except Exception as error:
        assistant.log_error("J.A.R.V.I.S. desktop application failed to start.", error)
        try:
            messagebox.showerror(
                "J.A.R.V.I.S. could not start",
                "The desktop app encountered a startup error.\n\n"
                f"Details were saved to:\n{assistant.user_data_dir() / 'jarvis.log'}\n\n{error}",
            )
        except Exception:
            pass


if __name__ == "__main__":
    main()
