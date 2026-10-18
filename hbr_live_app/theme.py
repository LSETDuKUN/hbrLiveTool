"""Shared visual tokens. Presentation only: never reads game or catalog data."""
import tkinter as tk
from tkinter import font as tkfont, ttk

# ---- palette ---------------------------------------------------------------
# Deep plum ground with pastel accents; neighbouring tones stay close in value
# so nothing shouts louder than the damage numbers themselves.
BG = '#171226'
SURFACE = '#1e1832'
CARD = '#251e3c'
CARD_HI = '#2e2549'
LINE = '#372d55'
LINE_SOFT = '#2c2444'
FG = '#f6f0fd'
DIM = '#a99ec7'
MUTED = '#7f749e'

PINK = '#f7a9cd'
CYAN = '#8fe3ea'
GOLD = '#ffd39b'
MINT = '#9fe6bf'
ROSE = '#f5a4b0'
LAVENDER = '#c6b8f2'

PINK_DEEP = '#432a3d'
CYAN_DEEP = '#1f3a44'
GOLD_DEEP = '#3d3122'
MINT_DEEP = '#203a31'
ROSE_DEEP = '#3e2732'
LAVENDER_DEEP = '#2f2a4d'
NEUTRAL_DEEP = '#2b2445'

# ---- geometry --------------------------------------------------------------
PAD = 18
GAP = 12
RADIUS = 22
RADIUS_SM = 14


def mix(first, second, ratio):
    """Blend two #rrggbb colours; ratio 0 keeps first, 1 keeps second."""
    ratio = max(0.0, min(1.0, ratio))
    a = tuple(int(first[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(second[i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x + (y - x) * ratio):02x}' for x, y in zip(a, b))


def lift(color, amount=.06):
    return mix(color, '#ffffff', amount)


def sink(color, amount=.12):
    return mix(color, '#000000', amount)


# ---- typography ------------------------------------------------------------
UI_FAMILY = 'Microsoft YaHei UI'
NUM_CANDIDATES = ('Segoe UI Variable Display', 'Segoe UI', 'Arial')
MONO_CANDIDATES = ('Cascadia Code', 'Consolas', 'Courier New')
_families = None
_resolved = {}


def _known():
    global _families
    if _families is None:
        try:
            _families = frozenset(tkfont.families())
        except tk.TclError:
            _families = frozenset()
    return _families


def _first(candidates, fallback):
    known = _known()
    for name in candidates:
        if name in known:
            return name
    return fallback


def num_family():
    if 'num' not in _resolved:
        _resolved['num'] = _first(NUM_CANDIDATES, 'Segoe UI')
    return _resolved['num']


def mono_family():
    if 'mono' not in _resolved:
        _resolved['mono'] = _first(MONO_CANDIDATES, 'Consolas')
    return _resolved['mono']


def ui(size=13, weight='normal'):
    """Pixel-sized UI font; negative sizes keep DPI scaling predictable."""
    return (UI_FAMILY, -int(size), weight) if weight != 'normal' else (UI_FAMILY, -int(size))


def num(size=16, weight='bold', slant='roman'):
    return (num_family(), -int(size), weight, slant)


def mono(size=12, weight='normal'):
    return (mono_family(), -int(size), weight)


# ---- ttk -------------------------------------------------------------------
def install(root):
    """Apply the shared ttk look once for the widget-level dashboard."""
    style = ttk.Style(root)
    # Only replace the native Windows theme; a window that installed its own
    # derived theme (hbr_data uses 'quest') must keep it.
    if style.theme_use() in ('vista', 'winnative', 'xpnative', 'aqua', 'default'):
        for theme in ('clam', 'alt'):
            if theme in style.theme_names():
                try:
                    style.theme_use(theme)
                    break
                except tk.TclError:
                    continue
    configure(style)
    return style


def configure(style):
    field = mix(SURFACE, '#000000', .35)
    edge = mix(LINE, FG, .12)
    style.configure('TEntry', fieldbackground=field, foreground=FG, insertcolor=FG,
                    bordercolor=edge, lightcolor=field, darkcolor=field, padding=6)
    style.map('TEntry', bordercolor=[('focus', PINK)], lightcolor=[('focus', PINK)],
              darkcolor=[('focus', field)])
    style.configure('TCombobox', fieldbackground=field, background=CARD, foreground=FG,
                    arrowcolor=DIM, bordercolor=edge, lightcolor=edge, darkcolor=edge, padding=5)
    style.map('TCombobox', fieldbackground=[('readonly', field)], foreground=[('readonly', FG)])
    style.configure('TButton', background=CARD_HI, foreground=FG, padding=(12, 6), relief='flat',
                    borderwidth=0, font=ui(12))
    style.map('TButton', background=[('active', mix(CARD_HI, PINK, .16))])
    style.configure('TScrollbar', background=CARD_HI, troughcolor=SURFACE, bordercolor=SURFACE,
                    arrowcolor=DIM, relief='flat', gripcount=0, arrowsize=11)
    style.map('TScrollbar', background=[('active', mix(CARD_HI, PINK, .25))])
    style.configure('Live.Treeview', background=CARD, fieldbackground=CARD, foreground=FG,
                    rowheight=68, borderwidth=0, font=ui(13), indent=14)
    style.configure('Live.Treeview.Heading', background=CARD_HI, foreground=PINK,
                    font=ui(13, 'bold'), relief='flat')
    style.map('Live.Treeview', background=[('selected', CARD_HI)],
              foreground=[('selected', FG)])
    style.configure('Live.TCombobox', fieldbackground=CARD, foreground=FG, background=CARD,
                    arrowcolor=DIM, bordercolor=LINE, lightcolor=CARD, darkcolor=CARD)
    style.map('Live.TCombobox', fieldbackground=[('readonly', CARD)],
              foreground=[('readonly', FG)])


def dialog_style(style, prefix='Panel'):
    """Scoped styles for the standalone windows (damage / library)."""
    for name in ('Frame', 'Label', 'Checkbutton', 'Radiobutton', 'Notebook'):
        style.configure(f'{prefix}.T{name}', background=BG, foreground=FG, font=ui(13))
    style.configure(f'{prefix}.TLabel', background=BG, foreground=DIM, font=ui(12))
    style.configure(f'{prefix}.TCheckbutton', background=BG, foreground=FG, font=ui(12),
                    indicatorcolor=CARD_HI)
    style.map(f'{prefix}.TCheckbutton', indicatorcolor=[('selected', PINK_DEEP)],
              background=[('active', BG)])
    style.configure(f'{prefix}.TRadiobutton', background=BG, foreground=FG, font=ui(12))
    field = mix(SURFACE, '#000000', .35)
    edge = mix(LINE, FG, .12)
    style.configure(f'{prefix}.TEntry', fieldbackground=field, foreground=FG, insertcolor=FG,
                    bordercolor=edge, lightcolor=field, darkcolor=field, padding=6)
    style.map(f'{prefix}.TEntry', fieldbackground=[('readonly', mix(SURFACE, '#000000', .2))],
              bordercolor=[('focus', PINK)], lightcolor=[('focus', PINK)], darkcolor=[('focus', field)])
    style.configure(f'{prefix}.TButton', background=CARD_HI, foreground=FG, padding=(14, 7),
                    relief='flat', borderwidth=0, font=ui(12))
    style.map(f'{prefix}.TButton', background=[('active', mix(CARD_HI, PINK, .18))])
    style.configure(f'{prefix}.TCombobox', fieldbackground=CARD, background=CARD, foreground=FG,
                    bordercolor=LINE, arrowcolor=DIM, padding=5)
    style.map(f'{prefix}.TCombobox', fieldbackground=[('readonly', CARD)],
              foreground=[('readonly', FG)])
    style.configure(f'{prefix}.TNotebook', background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure(f'{prefix}.TNotebook.Tab', background=CARD, foreground=DIM,
                    padding=(16, 9), borderwidth=0, font=ui(12))
    style.map(f'{prefix}.TNotebook.Tab', background=[('selected', CARD_HI)],
              foreground=[('selected', PINK)])
    style.configure(f'{prefix}.TLabelframe', background=CARD, borderwidth=0)
    style.configure(f'{prefix}.TLabelframe.Label', background=CARD, foreground=PINK, font=ui(12))
    style.configure(f'{prefix}.TSeparator', background=LINE)
    style.configure(f'{prefix}.TScrollbar', background=CARD_HI, troughcolor=SURFACE,
                    bordercolor=SURFACE, arrowcolor=DIM, relief='flat', gripcount=0)


def text_widget_options(bg=CARD):
    return dict(bg=bg, fg=FG, insertbackground=FG, relief='flat', borderwidth=0,
                padx=14, pady=12, font=ui(13), selectbackground=mix(CARD, PINK, .35),
                selectforeground=FG, highlightthickness=0)
