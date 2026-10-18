"""Standalone battle dashboard. All Tk access stays on the main thread."""
import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from . import theme
from .components import RoundedCard, RoundedButton, Pill, ToggleChip, rounded
from .model import BattleModel
from .enemy_cards import EnemyCard
from .turns import context_label
from .history import table_rows, DISPLAY_POSITIONS, POSITION_NAMES
from .battle_table import BattleTable

ROOT = Path(__file__).resolve().parent.parent
FONT = theme.ui(13)


class App:
    def __init__(self, root=None):
        self.root = root or tk.Tk()
        self.model = BattleModel()
        self.queue = queue.Queue()
        self.stop_event = threading.Event()
        self.paused = threading.Event()
        self.thread = None
        self.connected = False
        self.closing = False
        self.library = None
        self.enemy_keys = []
        self.history_rows = {}
        self.details_open = False
        self.history_visible = tk.BooleanVar(master=self.root, value=False)
        self.prompted_runs = set()
        self.damage_timer = None
        self.damage_display = (None, 0)
        self.log_lines = []
        self.last_packet = None
        self.last_sample = None
        self.session_path = None
        self.settings = self._load_settings()
        theme.use(self.settings.get('theme', theme.NAME))
        self.compact = tk.BooleanVar(value=bool(self.settings.get('compact', False)))
        self.players_visible = tk.BooleanVar(value=not self.compact.get())
        self.topmost = tk.BooleanVar(value=bool(self.settings.get('topmost', True)))
        self.opacity = tk.DoubleVar(value=max(.7, min(1., float(self.settings.get('opacity', 1)))))
        self.root.title('HBR Live · 星屑战斗手帐')
        self.root.configure(bg=theme.BG)
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.attributes('-topmost', self.topmost.get())
        self.root.attributes('-alpha', self.opacity.get())
        self.style()
        self.build()
        self.layout()
        self._restore_geometry()
        self.root.after(60, self.pump)

    def _load_settings(self):
        try:
            data = json.loads((ROOT / 'settings.json').read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def open_damage_calculator(self):
        from .damage_window import DamageWindow
        window = getattr(self, 'damage_window', None)
        if window is not None and window.winfo_exists():
            window.deiconify();window.lift();return
        def snapshot():
            return dict(connected=self.connected,
                players=[dict(p,name=p.get('actor'), inputs=p.get('combat_inputs', {})) for p in self.model.players],
                enemies=[dict(e,inputs=e.get('combat_inputs', {}))
                         for e in self.model.enemies.values() if e.get('active')],field_state=self.model.field_state,
                         element_gauge=self.model.element_gauge,od_state=self.model.od_state)
        self.damage_window = DamageWindow(self.root, snapshot)

    def _restore_geometry(self):
        default = (500, 860) if self.compact.get() else (1180, 900)
        values = self.settings.get('bounds', [*default, 80, 60])
        try:
            w, h, x, y = map(int, values)
        except (TypeError, ValueError):
            w, h, x, y = *default, 80, 60
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(max(440 if self.compact.get() else 900, w), sw-30), min(max(660, h), sh-70)
        x, y = max(0, min(x, sw-w-16)), max(0, min(y, sh-h-60))
        self.root.geometry(f'{w}x{h}+{x}+{y}')

    def style(self):
        theme.install(self.root)

    def label(self, parent, text='', color=theme.FG, size=12, bold=False, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=theme.ui(size, 'bold' if bold else 'normal'), **kwargs)

    # ---- construction ------------------------------------------------------
    def build(self):
        self.build_header()
        self.build_hero()
        self.build_controls()
        self.build_status()
        self.build_toolbar()
        self.build_field()
        self.build_body()
        self.build_history()
        self.footer = self.label(self.root, '本地记录  ·  只读内存  ·  无需截图', theme.MUTED, 10, anchor='w')
        self.footer.pack(side='bottom', fill='x', padx=26, pady=(4, 12), before=self.body)
        self.root.bind('<Configure>', self.on_resize, add='+')
        self.root.bind_all('<MouseWheel>', self.scroll_battle, add='+')

    def build_header(self):
        head = tk.Frame(self.root, bg=theme.BG)
        head.pack(fill='x', padx=22, pady=(14, 8))
        brand = tk.Frame(head, bg=theme.BG)
        brand.pack(side='left')
        tk.Label(brand, text='✦', bg=theme.BG, fg=theme.PINK, font=theme.ui(19)).pack(side='left')
        tk.Label(brand, text='HBR LIVE', bg=theme.BG, fg=theme.FG,
                 font=(theme.num_family(), -19, 'bold')).pack(side='left', padx=(9, 0))
        self.subtitle = self.label(brand, '星屑战斗手帐', theme.DIM, 12)
        self.subtitle.pack(side='left', padx=(12, 0), pady=(3, 0))
        self.menu = tk.Menu(self.root, tearoff=False, bg=theme.CARD, fg=theme.FG, activebackground=theme.CARD_HI,
                            activeforeground=theme.FG, bd=0, relief='flat')
        self.menu.add_checkbutton(label='紧凑模式', variable=self.compact, command=self.change_compact)
        self.menu.add_checkbutton(label='保持置顶', variable=self.topmost,
                                  command=lambda: self.root.attributes('-topmost', self.topmost.get()))
        for value, title in ((1., '不透明'), (.9, '透明度 90%'), (.8, '透明度 80%')):
            self.menu.add_radiobutton(label=title, variable=self.opacity, value=value,
                                      command=lambda: self.root.attributes('-alpha', self.opacity.get()))
        self.menu.add_separator()
        self.theme_var = tk.StringVar(master=self.root, value=theme.NAME)
        for value, title in (('midnight', '深色 · 星夜'), ('sakura', '浅色 · 樱粉')):
            self.menu.add_radiobutton(label='外观：' + title, variable=self.theme_var, value=value,
                                      command=lambda v=value: self.set_theme(v))
        self.menu.add_separator()
        self.menu.add_command(label='导出本场摘要…', command=self.export)
        self.menu.add_command(label='保存行动轴…', command=self.export_axis)
        self.menu.add_command(label='打开记录文件夹', command=self.open_sessions)
        self.menu.add_command(label='诊断日志', command=self.show_logs)
        self.settings_button = RoundedButton(head, '设置 ⋯', self.drop_menu, theme.CARD_HI, theme.FG,
                                             theme.ui(12), height=34)
        self.settings_button.configure(width=96)
        self.settings_button.pack(side='right')

    def drop_menu(self):
        button = self.settings_button
        self.menu.tk_popup(button.winfo_rootx(), button.winfo_rooty() + button.winfo_height() + 4)

    def build_hero(self):
        summary = self.hero_row = tk.Frame(self.root, bg=theme.BG)
        summary.pack(fill='x', padx=18, pady=(0, 10))
        self.hero_stacked = False
        summary.columnconfigure(0, weight=3, uniform='damage')
        summary.columnconfigure(1, weight=2, uniform='damage')
        self.hero = RoundedCard(summary, background=theme.mix(theme.CARD, theme.PINK, .07),
                                accent=theme.PINK, pad=(18, 14), stretch=True, height=150)
        self.hero.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        hero = self.hero.content
        top = tk.Frame(hero, bg=self.hero.background)
        top.pack(fill='x')
        self.label(top, '指令最大伤害', theme.PINK, 12, bold=True).pack(side='left')
        self.label(top, 'TURN MAX DAMAGE', theme.MUTED, 9).pack(side='left', padx=(8, 0), pady=(2, 0))
        self.total_label = tk.Label(hero, text='0', bg=self.hero.background, fg=theme.PINK,
                                    font=theme.num(34), anchor='w')
        self.total_label.pack(fill='x', pady=(2, 0))
        meta = tk.Frame(hero, bg=self.hero.background)
        meta.pack(fill='x')
        self.summary = self.label(meta, '尚未连接  ·  等待第一笔行动', theme.DIM, 11, anchor='w')
        self.summary.pack(side='left', fill='x', expand=True)
        self.od_label = self.label(meta, 'OD · 等待采样', theme.CYAN, 11, bold=True)
        self.od_label.pack(side='right')
        hero.bind('<Configure>', lambda e: self.summary.configure(
            wraplength=max(90, e.width - self.od_label.winfo_reqwidth() - 12)))

        self.current_damage_card = RoundedCard(summary, background=theme.mix(theme.CARD, theme.CYAN, .07),
                                               accent=theme.CYAN, pad=(18, 14), stretch=True, height=150)
        self.current_damage_card.grid(row=0, column=1, sticky='nsew', padx=(6, 0))
        current = self.current_damage_card.content
        top = tk.Frame(current, bg=self.current_damage_card.background)
        top.pack(fill='x')
        self.label(top, '当前指令伤害', theme.CYAN, 12, bold=True).pack(side='left')
        self.label(top, 'TURN DAMAGE', theme.MUTED, 9).pack(side='left', padx=(8, 0), pady=(2, 0))
        self.current_damage_label = tk.Label(current, text='0', bg=self.current_damage_card.background,
                                             fg=theme.CYAN, font=theme.num(23), anchor='w')
        self.current_damage_label.pack(fill='x', pady=(4, 0))
        self.label(current, '含追击与连击珠', theme.MUTED, 10).pack(anchor='w', pady=(2, 0))

    def build_controls(self):
        controls = tk.Frame(self.root, bg=theme.BG)
        controls.pack(fill='x', padx=18, pady=(0, 8))
        for col in range(3):
            controls.columnconfigure(col, weight=1, uniform='controls')
        self.start_button = RoundedButton(controls, '连接战斗', self.start_or_stop, theme.PINK_FILL, theme.on_fill,
                                          theme.ui(13, 'bold'), height=46)
        self.start_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.pause_button = RoundedButton(controls, '暂停', self.toggle_pause, theme.CARD_HI, theme.FG,
                                          theme.ui(13), height=46)
        self.pause_button.grid(row=0, column=1, sticky='ew', padx=5)
        self.library_button = RoundedButton(controls, '星屑资料室', self.open_library, theme.CARD_HI, theme.FG,
                                            theme.ui(13), height=46)
        self.library_button.grid(row=0, column=2, sticky='ew', padx=(5, 0))

    def build_status(self):
        bar = RoundedCard(self.root, background=theme.SURFACE, outline=theme.LINE, pad=(14, 7),
                          radius=theme.RADIUS_SM)
        bar.pack(fill='x', padx=18, pady=(0, 10))
        row = bar.content
        self.status_dot = tk.Canvas(row, width=10, height=10, bg=theme.SURFACE, highlightthickness=0, bd=0)
        self.status_dot.pack(side='left', padx=(0, 9))
        self._draw_status_dot(theme.DIM)
        self.status = self.label(row, '先进入战斗指令选择画面，再连接。窗口可随时拖动。', theme.DIM, 11,
                                 anchor='w', justify='left', wraplength=900)
        self.status.pack(side='left', fill='x', expand=True)

    def _draw_status_dot(self, color):
        self.status_dot.delete('all')
        self.status_dot.create_oval(1, 1, 9, 9, fill=color, outline='')

    def build_toolbar(self):
        bar = tk.Frame(self.root, bg=theme.BG)
        bar.pack(fill='x', padx=22, pady=(0, 8))
        self.players_toggle = ToggleChip(bar, '角色状态', self.players_visible, self.layout, theme.PINK)
        self.players_toggle.pack(side='left')
        self.history_toggle = ToggleChip(bar, '行动轴窗口', self.history_visible, self.toggle_history, theme.CYAN)
        self.history_toggle.pack(side='left', padx=8)
        self.export_button = RoundedButton(bar, '保存行动轴…', self.export_axis, theme.CARD_HI, theme.DIM,
                                           theme.ui(12), height=34)
        self.export_button.pack(side='right')
        self.damage_button = RoundedButton(bar, '伤害试算', self.open_damage_calculator,
                                           theme.mix(theme.CARD_HI, theme.PINK, .22), theme.FG,
                                           theme.ui(12), height=34)
        self.damage_button.pack(side='right', padx=8)

    def build_field(self):
        card = RoundedCard(self.root, background=theme.mix(theme.SURFACE, theme.MINT, .10), outline=theme.mix(theme.LINE, theme.MINT, .3),
                           pad=(14, 8), radius=theme.RADIUS_SM)
        card.pack(fill='x', padx=18, pady=(0, 10))
        row = card.content
        self.label(row, '◈', theme.MINT, 12, bold=True).pack(side='left', padx=(2, 10))
        self.field_label = self.label(row, '场地 · 待连接', theme.MINT, 11, anchor='w', justify='left',
                                      cursor='hand2')
        self.field_label.pack(side='left', fill='x', expand=True)
        self.field_label.bind('<Button-1>', lambda e: self.show_field_details())
        self.field_label.bind('<Configure>', lambda e: self.field_label.configure(wraplength=max(160, e.width - 20)))

    def build_body(self):
        self.body = tk.Frame(self.root, bg=theme.BG)
        self.body.pack(fill='both', expand=True, padx=18)
        # team
        self.allies = tk.Frame(self.body, bg=theme.BG)
        allies_card = RoundedCard(self.allies, background=theme.SURFACE, outline=theme.LINE, pad=(14, 12),
                                  stretch=True)
        allies_card.pack(fill='both', expand=True)
        head = tk.Frame(allies_card.content, bg=theme.SURFACE)
        head.pack(fill='x', pady=(0, 8))
        self.label(head, '队伍 · 六人状态', theme.PINK, 13, bold=True).pack(side='left')
        self.label(head, '点击头像查看状态', theme.MUTED, 10).pack(side='right', pady=(2, 0))
        self.player_view = tk.Canvas(allies_card.content, bg=theme.SURFACE, highlightthickness=0, bd=0)
        player_scroll = ttk.Scrollbar(allies_card.content, command=self.player_view.yview)
        self.player_view.configure(yscrollcommand=player_scroll.set)
        player_scroll.pack(side='right', fill='y')
        self.player_view.pack(fill='both', expand=True)
        from .player_panel import PlayerPanel
        self.player_panel = PlayerPanel(self.player_view, self.text_window)
        self.player_slot = self.player_view.create_window(0, 0, anchor='nw', window=self.player_panel)
        self.player_view.bind('<Configure>', self.fit_player_view)
        self.player_panel.bind('<Configure>', lambda e: self.player_view.configure(scrollregion=self.player_view.bbox('all')))
        # enemies
        self.resources = tk.Frame(self.body, bg=theme.BG)
        res_card = RoundedCard(self.resources, background=theme.SURFACE, outline=theme.LINE, pad=(14, 12),
                               stretch=True)
        res_card.pack(fill='both', expand=True)
        inner = res_card.content
        head = tk.Frame(inner, bg=theme.SURFACE)
        head.pack(fill='x', pady=(0, 2))
        self.label(head, 'Boss 状态与行动', theme.CYAN, 13, bold=True).pack(side='left')
        self.enemy_cards = {}
        self.enemy_view = tk.Canvas(inner, bg=theme.SURFACE, highlightthickness=0, bd=0)
        enemy_scroll = ttk.Scrollbar(inner, command=self.enemy_view.yview)
        self.enemy_view.configure(yscrollcommand=enemy_scroll.set)
        enemy_scroll.pack(side='right', fill='y')
        self.enemy_view.pack(fill='both', expand=True)
        self.enemy_stack = tk.Frame(self.enemy_view, bg=theme.SURFACE)
        self.enemy_status_panels = {}
        enemy_slot = self.enemy_view.create_window(0, 0, anchor='nw', window=self.enemy_stack)
        self.enemy_view.bind('<Configure>', lambda e: self.enemy_view.itemconfigure(enemy_slot, width=e.width))
        self.enemy_stack.bind('<Configure>', lambda e: self.enemy_view.configure(scrollregion=self.enemy_view.bbox('all')))
        self.resource_note = self.label(inner, '各条独立读取 · 比例参考本场观测最大值', theme.MUTED, 10,
                                        anchor='w', wraplength=275)
        self.resource_note.pack(fill='x', pady=(0, 6), before=self.enemy_view)

    def build_history(self):
        self.history_window = tk.Toplevel(self.root)
        self.history_window.title('HBR Live · 行动记录')
        self.history_window.configure(bg=theme.BG)
        self.history_window.geometry('1120x680')
        self.history_window.withdraw()
        self.history_window.protocol('WM_DELETE_WINDOW', self.hide_history)
        self.history = tk.Frame(self.history_window, bg=theme.BG, padx=16, pady=12)
        self.history.pack(fill='both', expand=True)
        self.label(self.history, '行动记录', theme.PINK, 14, bold=True).pack(anchor='w', pady=(2, 10))
        RoundedButton(self.history, '切换头像 / 角色风格', lambda: self.tree.toggle_portraits(),
                      theme.CARD_HI, theme.DIM, theme.ui(12), height=32).pack(anchor='e')
        tree_wrap = tk.Frame(self.history, bg=theme.CARD)
        tree_wrap.pack(fill='both', expand=True, pady=(8, 0))
        self.tree = BattleTable(tree_wrap)
        scrollbar = ttk.Scrollbar(tree_wrap, command=self.tree.yview)
        horizontal = ttk.Scrollbar(tree_wrap, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        scrollbar.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.render_details())
        self.tree.bind('<<RowDetails>>', lambda _: self.show_details())
        self.detail_caption = self.label(self.history, '一行一次行动 · / 表示未观测到行动 · 双击查看本行全部详情。',
                                         theme.MUTED, 10, anchor='w', wraplength=420, justify='left')
        self.detail_caption.pack(fill='x', pady=8)
        self.detail_wrap = tk.Frame(self.history, bg=theme.CARD)
        self.detail = tk.Text(self.detail_wrap, height=6, **theme.text_widget_options(theme.CARD),
                              wrap='word', state='disabled')
        detail_scroll = ttk.Scrollbar(self.detail_wrap, command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side='right', fill='y')
        self.detail.pack(fill='both', expand=True)
        self.detail_button = RoundedButton(self.history, '展开本行详情', self.toggle_details, theme.CARD_HI, theme.FG,
                                           theme.ui(12), height=38)
        self.detail_button.pack(fill='x', pady=(8, 6))
        self.history.bind('<Configure>', lambda e: self.detail_caption.configure(wraplength=max(200, e.width-10)))

    # ---- interaction -------------------------------------------------------
    def fit_player_view(self, event):
        needed = self.player_panel.winfo_reqheight()
        self.player_view.itemconfigure(self.player_slot, width=event.width,
                                       height=max(event.height, needed))

    def scroll_battle(self, event):
        widget = event.widget
        while widget is not None:
            if widget in (self.player_view, self.enemy_view):
                widget.yview_scroll(-int(event.delta / 120), 'units')
                return 'break'
            widget = getattr(widget, 'master', None)

    def on_resize(self, event):
        if event.widget is self.root:
            self.status.configure(wraplength=max(240, event.width - 110))
            size = 24 if event.width < 620 else (28 if event.width < 820 else 34)
            self.total_label.configure(font=theme.num(size))
            self.layout_hero(event.width < 900)
            narrow = event.width < 760
            self.export_button.configure(text='保存' if narrow else '保存行动轴…')
            self.damage_button.configure(text='试算' if narrow else '伤害试算')

    def layout_hero(self, stacked):
        if stacked == self.hero_stacked:
            return
        self.hero_stacked = stacked
        row = self.hero_row
        if stacked:
            row.columnconfigure(0, weight=1, uniform='')
            row.columnconfigure(1, weight=0, uniform='')
            self.current_damage_card.grid_configure(row=1, column=0, padx=0, pady=(8, 0))
            self.hero.grid_configure(row=0, column=0, padx=0)
            self.current_damage_card.fixed_height = 132
        else:
            row.columnconfigure(0, weight=3, uniform='damage')
            row.columnconfigure(1, weight=2, uniform='damage')
            self.hero.grid_configure(row=0, column=0, padx=(0, 6))
            self.current_damage_card.grid_configure(row=0, column=1, padx=(6, 0), pady=0)
            self.current_damage_card.fixed_height = 150
        self.current_damage_card.configure(height=self.current_damage_card.fixed_height)
        self.current_damage_card.draw()

    def layout(self):
        visible = self.players_visible.get()
        self.root.minsize(980 if visible else 440, 760)
        self.body.columnconfigure(0, weight=5 if visible else 0,
                                  uniform='battle' if visible else '', minsize=380 if visible else 0)
        self.body.columnconfigure(1, weight=4 if visible else 1,
                                  uniform='battle' if visible else '', minsize=340)
        self.body.rowconfigure(0, weight=1)
        if visible:
            self.allies.grid(row=0, column=0, sticky='nsew', padx=(0, 6))
        else:
            self.allies.grid_remove()
        self.resources.grid(row=0, column=1, sticky='nsew', padx=(6 if visible else 0, 0))
        self.players_toggle.draw()
        self.update_detail_visibility()

    def change_compact(self):
        self.players_visible.set(not self.compact.get())
        self.layout()
        self.players_toggle.draw()
        self.root.geometry('500x860' if self.compact.get() else '1180x900')

    def toggle_history(self):
        if self.history_visible.get():
            self.history_window.deiconify()
            self.history_window.lift()
        else:
            self.history_window.withdraw()

    def hide_history(self):
        self.history_visible.set(False)
        self.history_window.withdraw()

    def update_detail_visibility(self):
        if self.details_open:
            self.detail_wrap.pack(fill='x', after=self.detail_button)
        else:
            self.detail_wrap.pack_forget()
        self.detail_button.configure(text='收起本行详情' if self.details_open else '展开本行详情')

    def toggle_details(self):
        self.details_open = not self.details_open
        self.update_detail_visibility()
        self.render_details()

    def start_or_stop(self):
        if self.thread and self.thread.is_alive():
            self.stop_event.set()
            self.set_status('正在停止并保存记录…')
            return
        self.stop_event.clear()
        self.paused.clear()
        self.connected = False
        self.pause_button.configure(text='暂停', bg=theme.CARD_HI)
        self.start_button.configure(text='取消连接', bg=theme.mix(theme.CARD_HI, theme.ROSE, .45))
        self.set_status('正在连接，请暂不行动…')
        from .source import run
        self.thread = threading.Thread(target=run,
            args=(self.stop_event, self.paused, self.queue.put, ROOT / 'sessions'), daemon=True)
        self.thread.start()

    def start(self):
        if not self.thread or not self.thread.is_alive():
            self.start_or_stop()

    def toggle_pause(self):
        if not self.connected:
            self.set_status('连接成功后可暂停。', theme.DIM)
            return
        if self.paused.is_set():
            self.paused.clear()
            self.pause_button.configure(text='暂停', bg=theme.CARD_HI)
            self.set_status('正在读取 · 可以行动', theme.CYAN)
        else:
            self.paused.set()
            self.pause_button.configure(text='继续', bg=theme.mix(theme.CARD_HI, theme.GOLD, .45))
            self.set_status('已暂停 · 思考期间请勿行动；继续后沿用本场记录。', theme.GOLD)

    def pump(self):
        try:
            # Bound each pass so long bursts cannot starve Tk input.
            for _ in range(200):
                kind, data = self.queue.get_nowait()
                if kind == 'connected':
                    self.model = BattleModel()
                    self.model.run_id = data['run_id']
                    self.update_damage()
                    self.session_path = data['path']
                    self.tree.delete(*self.tree.get_children())
                    self.history_rows = {}
                    self.enemy_keys = []
                    for card in self.enemy_cards.values():
                        card.destroy()
                    self.enemy_cards.clear()
                    for panel in self.enemy_status_panels.values():
                        panel.destroy()
                    self.enemy_status_panels.clear()
                    self.player_panel.reset()
                    self.field_label.configure(text='场地 · 等待采样')
                    self.last_sample = None
                    self.connected = True
                    self.start_button.configure(text='停止', bg=theme.mix(theme.CARD_HI, theme.ROSE, .6))
                    self.set_status('内存已连接 · 可以行动', theme.CYAN)
                elif kind == 'snapshot':
                    self.model.update(data)
                    self.last_packet = data
                    self.last_events = data.get('events', [])
                    self.render(data.get('events', []))
                elif kind == 'heartbeat':
                    self.last_sample = data
                    self.footer.configure(text=f'最近采样 {time.strftime("%H:%M:%S", time.localtime(data))}  ·  本场记录自动保存')
                elif kind == 'stopped':
                    self.connected = False
                    for card in self.enemy_cards.values():
                        card.set_monitoring(False)
                    self.start_button.configure(text='连接新战斗', bg=theme.mix(theme.CARD_HI, theme.MINT, .4))
                    self.pause_button.configure(text='暂停', bg=theme.CARD_HI)
                elif kind == 'battle_end':
                    run_id = data['run_id']
                    if run_id not in self.prompted_runs:
                        self.prompted_runs.add(run_id)
                        saved = self.model.export()
                        self.root.after_idle(lambda saved=saved: self.offer_axis(saved))
                elif kind == 'error':
                    self.set_status(data, '#ffadb7')
                elif kind == 'status':
                    self.set_status(data)
        except queue.Empty:
            pass
        fresh = self.connected and not self.paused.is_set() and self.last_sample is not None and time.time()-self.last_sample < 3
        for card in self.enemy_cards.values():
            card.set_monitoring(fresh)
        if not self.closing:
            self.root.after(60, self.pump)

    def render(self, events=()):
        self.update_damage()
        batches = {e['command']['id'] for e in self.model.actions.values() if e.get('command') and e['command'].get('kind') != 'instant'}
        current = self.model.turn_context
        prefix = f'Turn {current["turn"]}  ·  ' if current else ''
        self.summary.configure(text=f'{prefix}{len(batches)} 组指令 · 本场累计 {self.model.total:,}')
        from .overdrive import od_label
        self.od_label.configure(text=od_label(self.model.od_state))
        self.enemy_keys = list(self.model.enemies)
        self.render_enemy()
        self.player_panel.update_state(self.model.players, self.model.element_gauge)
        field = self.model.field_state or {}
        active = [s for s in field.get('statuses',[]) if not s.get('pending_add') and not s.get('pending_remove')]
        from .statuses import status_line
        self.field_label.configure(text='场地 · '+('  /  '.join(status_line(s)+' · '+s.get('duration','持续待确认') for s in active)
            if active else '未观测到场地' if field.get('available') else '暂不可读'))
        if events:
            self.history_rows = table_rows(self.model.actions.values())
            self.tree.set_rows(self.history_rows)
        self.render_details()

    def update_damage(self):
        stats = self.model.command_damage
        self.total_label.configure(text=f'{stats["maximum"]:,}')
        identity, value = stats['current_id'], stats['current']
        old_id, old_value = self.damage_display
        if (identity, value) == self.damage_display:
            return
        if self.damage_timer is not None:
            self.root.after_cancel(self.damage_timer)
            self.damage_timer = None
        base = old_value if identity == old_id else 0
        self.damage_display = (identity, value)
        if value > base:
            self.current_damage_label.configure(text=f'{base:,} + {value-base:,}')
            self.damage_timer = self.root.after(600, self.settle_damage)
        else:
            self.current_damage_label.configure(text=f'{value:,}')

    def settle_damage(self):
        self.damage_timer = None
        self.current_damage_label.configure(text=f'{self.damage_display[1]:,}')

    def render_enemy(self):
        for number, (key, state) in enumerate(self.model.enemies.items(), 1):
            if key not in self.enemy_cards:
                card = self.enemy_cards[key] = EnemyCard(self.enemy_stack, number, self.show_enemy_details)
                card.pack(fill='x', padx=(0, 10), pady=(0, 8))
                from .status_groups import StatusGroups
                panel = StatusGroups(self.enemy_stack, self.show_status_details, enemy=True)
                panel.pack(fill='x', padx=(2, 14), pady=(0,12))
                self.enemy_status_panels[key] = panel
            self.enemy_cards[key].update_state(state)
            self.enemy_status_panels[key].update_state(state)

    def show_status_details(self, status):
        from .statuses import status_details
        self.text_window(status['name'], status_details(dict(statuses_available=True,statuses=[status])))

    def show_field_details(self):
        from .statuses import status_details
        field = self.model.field_state or {}
        self.text_window('场地详情', status_details(dict(statuses_available=field.get('available'),statuses=field.get('statuses',[])))
            +'\n\n场地独立于角色状态。特殊场地的原始参数不直接当作通用加攻倍率。')

    def target_label(self, address, fallback='目标未确认'):
        if address in self.enemy_keys:
            return f'敌{self.enemy_keys.index(address)+1}'
        return fallback

    def show_enemy_details(self, number, state):
        aliases = state.get('names') or [dict(kind='internal', name=state['name'])]
        text = '\n'.join(f"{ {'cn': '中文', 'en': '国际服', 'internal': '内部名称'}.get(n['kind'], n['kind'])}：{n['name']}" for n in aliases)
        if state.get('enemy_label'):
            text += f'\n资料标识：{state["enemy_label"]}'
        preview = state.get('forecast', {})
        from .enemy_prediction import prediction_details
        text += '\n\n' + prediction_details(preview)
        text += '\n\n' + (state.get('action_rules') or '本地资料尚未收录此敌人的行动规则。')
        from .statuses import status_details
        text += '\n\n当前状态：\n' + status_details(state)
        self.text_window(f'敌{number} · 名称与行动规则', text)

    def target_summary(self, event):
        targets = event.get('targets') or [dict(address=h['target']) for h in event['hits']]
        return '、'.join(dict.fromkeys(self.target_label(t['address'], t.get('name', '目标未确认')) for t in targets)) or '待确认'

    def detail_text(self):
        selected = self.tree.selection()
        if not selected or selected[0] not in self.history_rows:
            return '选择一行，展开查看所有角色的伤害、作用目标和逐 Hit 明细。'
        row = self.history_rows[selected[0]]
        events = row['events']
        text = context_label(row['group']) + f' · 合计 {sum(e["value"] for e in events):,}\n'
        if row['position_unknown']:
            text += '部分事件位置未确认，未填入前排行动位。\n'
        frontline = (row['group'] or {}).get('frontline')
        if frontline:
            text += '本批前排（左→右）：' + ' / '.join(
                f"{POSITION_NAMES[p['position']]} {p['actor']}"
                for pos in DISPLAY_POSITIONS for p in frontline if p['position'] == pos) + '\n'
        else:
            text += '完整前排名单未确认；仅使用事件中实际读到的位置。\n'
        text += '角色行动顺序：' + ' → '.join(e['actor'] for e in events) + '\n\n'
        return text + '\n'.join(self.event_detail_text(event) for event in events)

    def event_detail_text(self, event):
        text = f'{event["actor"]} · {event["skill"]}\n显示伤害 {event["value"]:,}  ·  {"已结算" if event["settled"] else "命中进行中"}\n\n'
        if event.get('style_label') or event.get('style_name'):
            text += f'风格：{event.get("style_name") or "名称未收录"}\n风格标识：{event.get("style_label") or "未确认"}\n\n'
        totals = {}
        for hit in event['hits']:
            totals[hit['target']] = totals.get(hit['target'], 0) + hit['damage']
        if totals:
            text += '目标伤害：' + ' / '.join(f'{self.target_label(k)} {v:,}' for k,v in totals.items()) + '\n\n'
        else:
            text += '未观测到对敌伤害；已记录技能发动，暂不解析特殊效果。\n\n'
        text += '作用目标：' + self.target_summary(event) + '\n\n'
        for n, hit in enumerate(event['hits'], 1):
            enemy = self.model.enemies.get(hit['target'], {})
            target_index = self.enemy_keys.index(hit['target'])+1 if hit['target'] in self.enemy_keys else '?'
            kind = '连击珠' if hit['funnel'] else '本体'
            crit = ' · 暴击' if hit['critical'] else ''
            text += f'{n:02d}  {kind}{crit}    {hit["damage"]:,}\n      → 敌人 {target_index} · {enemy.get("name", "未知目标")}\n'
        return text

    def render_details(self):
        self.detail.configure(state='normal')
        self.detail.delete('1.0', 'end')
        self.detail.insert('end', self.detail_text())
        self.detail.configure(state='disabled')

    def show_details(self):
        self.text_window('命中明细', self.detail_text())

    def text_window(self, title, text):
        window = tk.Toplevel(self.root)
        window.title('HBR Live · ' + title)
        window.configure(bg=theme.BG)
        window.geometry('620x540')
        head = tk.Frame(window, bg=theme.BG)
        head.pack(fill='x', padx=20, pady=(16, 8))
        self.label(head, title, theme.PINK, 14, bold=True).pack(side='left')
        box = RoundedCard(window, background=theme.CARD, pad=(0, 0), stretch=True)
        box.pack(fill='both', expand=True, padx=16, pady=(0, 16))
        body = tk.Frame(box.content, bg=theme.CARD)
        body.pack(fill='both', expand=True, padx=6, pady=6)
        text_widget = tk.Text(body, **theme.text_widget_options(theme.CARD), wrap='word')
        scroll = ttk.Scrollbar(body, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        text_widget.pack(fill='both', expand=True)
        text_widget.insert('end', text)
        text_widget.configure(state='disabled')
        for pass_event in ('<MouseWheel>',):
            text_widget.bind(pass_event, lambda e: text_widget.yview_scroll(-int(e.delta / 120), 'units'))

    def open_library(self):
        from hbr_data.window import LibraryWindow
        if self.library is None or not self.library.window.winfo_exists():
            self.library = LibraryWindow(self.root)
            self.style()
        self.library.window.deiconify()
        self.library.window.lift()

    def set_theme(self, name):
        name = theme.use(name)
        self.settings['theme'] = name
        self.rebuild()

    def rebuild(self):
        """Rebuild every widget so a palette change applies immediately."""
        window = getattr(self, 'damage_window', None)
        if window is not None:
            try:
                window.destroy()
            except tk.TclError:
                pass
            self.damage_window = None
        if self.library is not None:
            try:
                self.library.window.destroy()
            except tk.TclError:
                pass
            self.library = None
        for child in list(self.root.winfo_children()):
            child.destroy()
        self.enemy_cards = {}
        self.enemy_status_panels = {}
        self.history_rows = {}
        self.root.configure(bg=theme.BG)
        self.style()
        self.build()
        self.layout()
        self.render(getattr(self, 'last_events', []))
        if self.history_visible.get():
            self.history_window.deiconify()

    def set_status(self, text, color=theme.DIM):
        self.status.configure(text=text, fg=color)
        self._draw_status_dot(color)
        self.log_lines.append(time.strftime('%H:%M:%S') + '  ' + text)
        self.log_lines = self.log_lines[-300:]

    def show_logs(self):
        self.text_window('诊断日志', '\n'.join(self.log_lines) or '暂无日志')

    def open_sessions(self):
        path = ROOT / 'sessions'
        path.mkdir(exist_ok=True)
        os.startfile(str(path))

    def export(self):
        path = filedialog.asksaveasfilename(parent=self.root, title='导出本场摘要',
            initialfile=(self.model.run_id or 'battle') + '.json', defaultextension='.json',
            filetypes=[('战斗摘要', '*.json')])
        if path:
            try:
                Path(path).write_text(json.dumps(self.model.export(), ensure_ascii=False, indent=2), encoding='utf-8')
                self.set_status('摘要已导出')
            except OSError as exc:
                messagebox.showerror('导出失败', str(exc), parent=self.root)

    def offer_axis(self, data):
        if self.closing or not data['actions']:
            return
        if messagebox.askyesno('战斗结束', '是否保存本场行动轴？\n可保存为图片或表格。', parent=self.root):
            self.export_axis(data)

    def export_axis(self, data=None):
        data = data or self.model.export()
        if not data['actions']:
            self.set_status('尚无角色行动可保存。')
            return
        path = filedialog.asksaveasfilename(parent=self.root, title='保存行动轴',
            initialfile=(data['run_id'] or 'battle')+'-行动轴.png', defaultextension='.png',
            filetypes=[('行动轴图片', '*.png'), ('行动轴表格', '*.html')])
        if path:
            try:
                from .axis_export import save_axis
                files = save_axis(data, Path(path), portraits=self.tree.show_portraits)
                self.set_status(f'行动轴已保存 · {len(files)} 个文件')
            except (OSError, ValueError, ImportError) as exc:
                messagebox.showerror('保存失败', str(exc), parent=self.root)

    def close(self):
        if not self.closing:
            self.closing = True
            self.stop_event.set()
            settings = dict(compact=self.compact.get(), topmost=self.topmost.get(), opacity=self.opacity.get(),
                theme=theme.NAME, bounds=[self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()])
            try:
                temp = ROOT / 'settings.json.tmp'
                temp.write_text(json.dumps(settings), encoding='utf-8')
                temp.replace(ROOT / 'settings.json')
            except OSError:
                pass
        if self.thread and self.thread.is_alive():
            self.status.configure(text='正在保存并关闭…')
            self.root.after(100, self.close)
        else:
            self.root.destroy()
