"""Shared visual tokens and palettes. Presentation only: no data access."""
import tkinter as tk
from tkinter import font as tkfont, ttk

# ---- palette ---------------------------------------------------------------
# Two palettes share one token vocabulary. Values are installed into module
# globals by use(), so every widget reads them when it is built.
PALETTES = {
    'midnight': dict(
        bg='#171226', surface='#1e1832', card='#251e3c', card_hi='#2e2549',
        line='#372d55', line_soft='#2c2444',
        fg='#f6f0fd', dim='#a99ec7', muted='#7f749e',
        pink='#f7a9cd', cyan='#8fe3ea', gold='#ffd39b', mint='#9fe6bf',
        rose='#f5a4b0', lavender='#c6b8f2',
        pink_deep='#432a3d', cyan_deep='#1f3a44', gold_deep='#3d3122',
        mint_deep='#203a31', rose_deep='#3e2732', lavender_deep='#2f2a4d',
        neutral_deep='#2b2445',
        pink_fill='#f7a9cd', cyan_fill='#8fe3ea', gold_fill='#ffd39b',
        mint_fill='#9fe6bf', on_fill='#2a2036', shadow='#0c0918',
    ),
    'dawn': dict(
        bg='#faf1e6', surface='#fffaf2', card='#fffdf8', card_hi='#f4e4d3',
        line='#e7d4bf', line_soft='#f2e6d7',
        fg='#4b3a2c', dim='#7d6757', muted='#a58f7c',
        pink='#bf5f38', cyan='#2f8a83', gold='#a8731c', mint='#4f8a4a',
        rose='#b04a3c', lavender='#7c6ab3',
        pink_deep='#fbe7d8', cyan_deep='#e3f2f0', gold_deep='#fbeedb',
        mint_deep='#e9f3e5', rose_deep='#f9e5e1', lavender_deep='#efedfa',
        neutral_deep='#f4ece2',
        pink_fill='#f2b48c', cyan_fill='#a9dcd8', gold_fill='#f3d59a',
        mint_fill='#bfe0b4', on_fill='#4b3a2c', shadow='#e6d3bd',
    ),
    'sakura': dict(
        bg='#f5ecf5', surface='#fbf5fb', card='#ffffff', card_hi='#efe1ee',
        line='#dfcddd', line_soft='#ecdfeb',
        fg='#3f3350', dim='#6f6284', muted='#9a8cab',
        pink='#c8457e', cyan='#1f8794', gold='#9c6a17', mint='#2f855a',
        rose='#bf4459', lavender='#5f51b5',
        pink_deep='#fde8f1', cyan_deep='#e5f6f8', gold_deep='#fdf3e2',
        mint_deep='#e7f7ee', rose_deep='#fde9ec', lavender_deep='#eeebfb',
        neutral_deep='#f4eff8',
        pink_fill='#f9bfd6', cyan_fill='#a7e4ec', gold_fill='#ffdda8',
        mint_fill='#b6ebcd', on_fill='#4a3a55', shadow='#e0cfe4',
    ),
}
NAME = 'midnight'
TITLES = {
    'midnight': '深色 · 星夜',
    'sakura': '浅色 · 樱粉',
    'dawn': '暖色 · 晨露',
}


def use(name):
    """Install one palette into module globals."""
    global NAME
    palette = PALETTES.get(name) or PALETTES['midnight']
    NAME = name if name in PALETTES else 'midnight'
    for key, value in palette.items():
        globals()[key.upper()] = value
    globals()['on_fill'] = palette['on_fill']
    _resolved.clear()
    return NAME


def options():
    order = ('midnight', 'sakura', 'dawn')
    return tuple(name for name in order if name in PALETTES) + tuple(
        name for name in PALETTES if name not in order)


# ---- type scale ------------------------------------------------------------
# Sizes are design pixels at 96 dpi; they are multiplied by the live display
# scale so text keeps its apparent size on 125% / 150% desktops.
UI_FAMILY = 'Microsoft YaHei UI'
NUM_CANDIDATES = ('Segoe UI Variable Display', 'Segoe UI', 'Arial')
DISPLAY_CANDIDATES = ('Segoe UI Black', 'Segoe UI Semibold', 'Segoe UI Variable Display', 'Arial Black', 'Arial')
MONO_CANDIDATES = ('Cascadia Code', 'Consolas', 'Courier New')
SCALE = 1.0
_families = None
_resolved = {}


def install_scale(root):
    global SCALE
    try:
        SCALE = max(1.0, float(root.winfo_fpixels('1i')) / 96.0)
    except (tk.TclError, AttributeError, ValueError):
        SCALE = 1.0
    return SCALE


def px(size):
    return max(7, int(round(size * SCALE)))


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
    return _resolved.setdefault('num', _first(NUM_CANDIDATES, 'Segoe UI'))


def mono_family():
    return _resolved.setdefault('mono', _first(MONO_CANDIDATES, 'Consolas'))


def ui(size=12, weight='normal'):
    return (UI_FAMILY, -px(size), weight) if weight != 'normal' else (UI_FAMILY, -px(size))


def display_family():
    return _resolved.setdefault('display', _first(DISPLAY_CANDIDATES, 'Segoe UI'))


def display(size=34):
    return (display_family(), -px(size))


def num(size=15, weight='bold', slant='roman'):
    return (num_family(), -px(size), weight, slant)


def mono(size=11, weight='normal'):
    return (mono_family(), -px(size), weight)


# ---- geometry --------------------------------------------------------------
PAD = 18
GAP = 12
RADIUS = 22
RADIUS_SM = 14


# ---- helpers ---------------------------------------------------------------
def hex_to_rgb(value):
    value = value.lstrip('#')
    if len(value) == 3:
        value = ''.join(char * 2 for char in value)
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def mix(first, second, ratio):
    ratio = max(0.0, min(1.0, ratio))
    a = tuple(int(first[i:i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(second[i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x + (y - x) * ratio):02x}' for x, y in zip(a, b))


def field():
    """Editable field background for the active palette."""
    return _field()


def bar_tint(color):
    """Meter fills: full accent on dark, softened on light."""
    return mix(color, CARD, .12) if NAME == 'midnight' else mix(color, CARD, .5)


def lift(color, amount=.06):
    return mix(color, '#ffffff', amount)


def sink(color, amount=.12):
    return mix(color, '#000000', amount)


# ---- ttk -------------------------------------------------------------------
def install(root):
    """Apply the shared ttk look; keeps a window's own derived theme."""
    install_scale(root)
    style = ttk.Style(root)
    if style.theme_use() in ('vista', 'winnative', 'xpnative', 'aqua', 'default'):
        for theme_name in ('clam', 'alt'):
            if theme_name in style.theme_names():
                try:
                    style.theme_use(theme_name)
                    break
                except tk.TclError:
                    continue
    configure(style)
    return style


def _field():
    return mix(CARD, '#000000', .32) if NAME == 'midnight' else mix(SURFACE, BG, .95)


def _edge():
    return mix(LINE, FG, .12) if NAME == 'midnight' else LINE


def configure(style):
    field, edge = _field(), _edge()
    style.configure('TEntry', fieldbackground=field, foreground=FG, insertcolor=FG,
                    bordercolor=edge, lightcolor=edge, darkcolor=edge, padding=6,
                    font=ui(12))
    style.map('TEntry', bordercolor=[('focus', PINK)], lightcolor=[('focus', PINK)],
              darkcolor=[('focus', edge)])
    style.configure('TCombobox', fieldbackground=field, background=CARD, foreground=FG,
                    arrowcolor=DIM, bordercolor=edge, lightcolor=edge, darkcolor=edge,
                    padding=5, font=ui(12))
    style.map('TCombobox', fieldbackground=[('readonly', field)], foreground=[('readonly', FG)])
    style.configure('TButton', background=CARD_HI, foreground=FG, padding=(12, 6), relief='flat',
                    borderwidth=0, font=ui(12))
    style.map('TButton', background=[('active', mix(CARD_HI, PINK, .16))])
    style.configure('TScrollbar', background=mix(CARD_HI, PINK, .4), troughcolor=LINE_SOFT,
                    bordercolor=BG, arrowcolor=mix(PINK, CARD, .3), width=12,
                    relief='flat', gripcount=0, arrowsize=11)
    style.configure('Live.Treeview', background=CARD, fieldbackground=CARD, foreground=FG,
                    rowheight=px(52), borderwidth=0, font=ui(13), indent=14)
    style.configure('Live.Treeview.Heading', background=CARD_HI, foreground=PINK,
                    font=ui(13, 'bold'), relief='flat')
    style.map('Live.Treeview', background=[('selected', CARD_HI)], foreground=[('selected', FG)])
    style.configure('Live.TCombobox', fieldbackground=CARD, foreground=FG, background=CARD,
                    arrowcolor=DIM, bordercolor=edge, lightcolor=CARD, darkcolor=CARD)
    style.map('Live.TCombobox', fieldbackground=[('readonly', CARD)], foreground=[('readonly', FG)])


def dialog_style(style, prefix='Panel'):
    field, edge = _field(), _edge()
    for name in ('Frame', 'Label', 'Checkbutton', 'Radiobutton', 'Notebook'):
        style.configure(f'{prefix}.T{name}', background=BG, foreground=FG, font=ui(13))
    style.configure(f'{prefix}.TLabel', background=BG, foreground=DIM, font=ui(12))
    style.configure(f'{prefix}.TCheckbutton', background=BG, foreground=FG, font=ui(12),
                    indicatorcolor=CARD_HI)
    style.map(f'{prefix}.TCheckbutton', indicatorcolor=[('selected', PINK_DEEP)],
              background=[('active', BG)])
    style.configure(f'{prefix}.TRadiobutton', background=BG, foreground=FG, font=ui(12))
    style.configure(f'{prefix}.TEntry', fieldbackground=field, foreground=FG, insertcolor=FG,
                    bordercolor=edge, lightcolor=edge, darkcolor=edge, padding=6, font=ui(12))
    style.map(f'{prefix}.TEntry', fieldbackground=[('readonly', field)],
              bordercolor=[('focus', PINK)], lightcolor=[('focus', PINK)], darkcolor=[('focus', edge)])
    style.configure(f'{prefix}.TButton', background=CARD_HI, foreground=FG, padding=(14, 7),
                    relief='flat', borderwidth=0, font=ui(12))
    style.map(f'{prefix}.TButton', background=[('active', mix(CARD_HI, PINK, .18))])
    style.configure(f'{prefix}.TCombobox', fieldbackground=field, background=CARD, foreground=FG,
                    bordercolor=edge, arrowcolor=DIM, padding=5, font=ui(12))
    style.map(f'{prefix}.TCombobox', fieldbackground=[('readonly', field)],
              foreground=[('readonly', FG)])
    style.configure(f'{prefix}.TNotebook', background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure(f'{prefix}.TNotebook.Tab', background=CARD, foreground=DIM,
                    padding=(16, 9), borderwidth=0, font=ui(12))
    style.map(f'{prefix}.TNotebook.Tab', background=[('selected', CARD_HI)],
              foreground=[('selected', PINK)])
    style.configure(f'{prefix}.TLabelframe', background=CARD, borderwidth=0)
    style.configure(f'{prefix}.TLabelframe.Label', background=CARD, foreground=PINK, font=ui(12))
    style.configure(f'{prefix}.TSeparator', background=LINE)
    style.configure(f'{prefix}.TScrollbar', background=mix(CARD_HI, LINE, .35), troughcolor=SURFACE,
                    bordercolor=SURFACE, arrowcolor=DIM, relief='flat', gripcount=0)


def text_widget_options(bg_override=None):
    background = bg_override or CARD
    return dict(bg=background, fg=FG, insertbackground=FG, relief='flat', borderwidth=0,
                padx=14, pady=12, font=ui(13), selectbackground=mix(background, PINK, .35),
                selectforeground=FG, highlightthickness=0)


use(NAME)
