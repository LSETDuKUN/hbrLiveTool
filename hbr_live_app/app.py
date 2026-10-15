"""Standalone battle dashboard. All Tk access stays on the main thread."""
import json
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

from .components import RoundedCard, RoundedButton
from .model import BattleModel
from .enemy_cards import EnemyCard
from .turns import context_label
from .history import table_rows, DISPLAY_POSITIONS, POSITION_NAMES
from .battle_table import BattleTable

ROOT = Path(__file__).resolve().parent.parent
BG, CARD, FG, DIM = '#201d32', '#302b46', '#f7f0ff', '#bdb1d4'
PINK, CYAN, GOLD = '#f5aacb', '#83e5ed', '#ffd398'
FONT = ('Microsoft YaHei UI', -14)


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
        self.compact = tk.BooleanVar(value=bool(self.settings.get('compact', False)))
        self.topmost = tk.BooleanVar(value=bool(self.settings.get('topmost', True)))
        self.opacity = tk.DoubleVar(value=max(.7, min(1., float(self.settings.get('opacity', 1)))))
        self.root.title('HBR Live · 星屑战斗手帐')
        self.root.configure(bg=BG)
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

    def _restore_geometry(self):
        default = (520, 740) if not self.history_visible.get() or self.compact.get() else (1280, 790)
        values = self.settings.get('bounds', [*default, 80, 60])
        try:
            w, h, x, y = map(int, values)
        except (TypeError, ValueError):
            w, h, x, y = *default, 80, 60
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        w, h = min(max(390 if self.compact.get() or not self.history_visible.get() else 1050, w), sw-30), min(max(650, h), sh-70)
        x, y = max(0, min(x, sw-w-16)), max(0, min(y, sh-h-60))
        self.root.geometry(f'{w}x{h}+{x}+{y}')

    def style(self):
        style = ttk.Style(self.root)
        if style.theme_use() not in ('clam', 'quest'):
            style.theme_use('clam')
        style.configure('Live.Treeview', background=CARD, fieldbackground=CARD,
                        foreground=FG, rowheight=68, borderwidth=0, font=FONT, indent=14)
        style.configure('Live.Treeview.Heading', background='#493752', foreground=PINK,
                        font=(*FONT, 'bold'), relief='flat')
        style.map('Live.Treeview', background=[('selected', '#605077')], foreground=[('selected', '#ffffff')])
        style.configure('Live.TCombobox', fieldbackground=CARD, foreground=FG, background=CARD)
        style.map('Live.TCombobox', fieldbackground=[('readonly', CARD)], foreground=[('readonly', FG)])

    def label(self, parent, text='', color=FG, size=10, **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget('bg'), fg=color,
                        font=('Microsoft YaHei UI', -round(size * 1.35)), **kwargs)

    def build(self):
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill='x', padx=22, pady=(18, 8))
        self.label(head, '✦  HBR LIVE', PINK, 19).pack(side='left')
        self.subtitle = self.label(head, '星屑战斗手帐', DIM, 10)
        self.subtitle.pack(side='left', padx=12)
        menu_button = tk.Menubutton(head, text='设置 ⋯', bg=CARD, fg=FG, relief='flat', padx=12, font=FONT)
        menu_button.pack(side='right')
        menu = tk.Menu(menu_button, tearoff=False, bg=CARD, fg=FG)
        menu_button.configure(menu=menu)
        menu.add_checkbutton(label='紧凑模式', variable=self.compact, command=self.layout)
        menu.add_checkbutton(label='保持置顶', variable=self.topmost,
                             command=lambda: self.root.attributes('-topmost', self.topmost.get()))
        for value, title in ((1., '不透明'), (.9, '透明度 90%'), (.8, '透明度 80%')):
            menu.add_radiobutton(label=title, variable=self.opacity, value=value,
                                command=lambda: self.root.attributes('-alpha', self.opacity.get()))
        menu.add_separator()
        menu.add_command(label='导出本场摘要…', command=self.export)
        menu.add_command(label='保存行动轴…', command=self.export_axis)
        menu.add_command(label='打开记录文件夹', command=self.open_sessions)
        menu.add_command(label='诊断日志', command=self.show_logs)
        self.hero = RoundedCard(self.root)
        self.hero.pack(fill='x', padx=18, pady=6)
        hero = self.hero.content
        self.label(hero, 'TurnMaxDamage · 指令最大伤害', DIM, 10).pack(anchor='w')
        self.total_label = tk.Label(hero, text='0', bg=CARD, fg=PINK,
                                   font=('Segoe UI', -46, 'bold italic'), anchor='w')
        self.total_label.pack(fill='x')
        self.summary = self.label(hero, '尚未连接  ·  等待第一笔行动', DIM)
        self.summary.pack(anchor='w')
        self.current_damage_card = RoundedCard(self.root)
        self.current_damage_card.pack(fill='x', padx=18, pady=6)
        self.label(self.current_damage_card.content, 'TurnDamage · 当前指令伤害', DIM, 10).pack(anchor='w')
        self.current_damage_label = self.label(self.current_damage_card.content, '0', CYAN, 22, anchor='w')
        self.current_damage_label.pack(fill='x')
        controls = tk.Frame(self.root, bg=BG)
        controls.pack(fill='x', padx=18, pady=(8, 4))
        for col in range(3):
            controls.columnconfigure(col, weight=1, uniform='controls')
        self.start_button = RoundedButton(controls, '连接战斗', self.start_or_stop, PINK, BG, (*FONT, 'bold'))
        self.start_button.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self.pause_button = RoundedButton(controls, '暂停', self.toggle_pause, '#4b4163', FG, FONT)
        self.pause_button.grid(row=0, column=1, sticky='ew', padx=5)
        RoundedButton(controls, '星屑资料室', self.open_library, '#4b4163', FG, FONT).grid(row=0, column=2, sticky='ew', padx=(5, 0))
        self.status = self.label(self.root, '先进入战斗指令选择画面，再连接。窗口可随时拖动。', DIM,
                                 anchor='w', justify='left', wraplength=800)
        self.status.pack(fill='x', padx=24, pady=(3, 8))
        history_bar = tk.Frame(self.root, bg=BG)
        history_bar.pack(fill='x', padx=22, pady=(0, 6))
        tk.Checkbutton(history_bar, text='显示行动轴', variable=self.history_visible, command=self.layout,
                       bg=BG, fg=PINK, selectcolor=CARD, activebackground=BG,
                       activeforeground=FG, font=FONT).pack(side='left')
        tk.Button(history_bar, text='保存行动轴…', command=self.export_axis, bg=CARD, fg=FG,
                  relief='flat', font=FONT).pack(side='right')
        self.body = tk.Frame(self.root, bg=BG)
        self.body.pack(fill='both', expand=True, padx=18)
        self.resources = tk.Frame(self.body, bg=BG)
        self.label(self.resources, '敌方状态', CYAN, 13).pack(anchor='w', padx=8, pady=(2, 10))
        self.enemy_cards = {}
        self.enemy_view = tk.Canvas(self.resources, bg=BG, highlightthickness=0, height=350)
        enemy_scroll = ttk.Scrollbar(self.resources, command=self.enemy_view.yview)
        self.enemy_view.configure(yscrollcommand=enemy_scroll.set)
        enemy_scroll.pack(side='right', fill='y')
        self.enemy_view.pack(fill='both', expand=True)
        self.enemy_stack = tk.Frame(self.enemy_view, bg=BG)
        enemy_slot = self.enemy_view.create_window(0, 0, anchor='nw', window=self.enemy_stack)
        self.enemy_view.bind('<Configure>', lambda e: self.enemy_view.itemconfigure(enemy_slot, width=e.width))
        self.enemy_stack.bind('<Configure>', lambda e: self.enemy_view.configure(scrollregion=self.enemy_view.bbox('all')))
        self.resource_note = self.label(self.resources, '各条独立读取 · 比例参考本场观测最大值', DIM, 9, anchor='w', wraplength=275)
        self.resource_note.pack(fill='x', padx=8, pady=5, before=self.enemy_view)
        self.history = tk.Frame(self.body, bg=BG)
        self.label(self.history, '行动记录', PINK, 13).pack(anchor='w', pady=(2, 10))
        tk.Button(self.history, text='切换头像 / 角色风格', command=lambda: self.tree.toggle_portraits(),
                  bg=CARD, fg=DIM, relief='flat', font=FONT).pack(anchor='e')
        tree_wrap = tk.Frame(self.history, bg=CARD)
        tree_wrap.pack(fill='both', expand=True)
        self.tree = BattleTable(tree_wrap)
        scrollbar = ttk.Scrollbar(tree_wrap, command=self.tree.yview)
        horizontal = ttk.Scrollbar(tree_wrap, orient='horizontal', command=self.tree.xview)
        self.tree.configure(yscrollcommand=scrollbar.set, xscrollcommand=horizontal.set)
        horizontal.pack(side='bottom', fill='x')
        scrollbar.pack(side='right', fill='y')
        self.tree.pack(fill='both', expand=True)
        self.tree.bind('<<TreeviewSelect>>', lambda _: self.render_details())
        self.tree.bind('<<RowDetails>>', lambda _: self.show_details())
        self.detail_caption = self.label(self.history, '一行一次行动 · / 表示未观测到行动 · 双击查看本行全部详情。', DIM, 9, anchor='w', wraplength=420, justify='left')
        self.detail_caption.pack(fill='x', pady=8)
        self.detail_wrap = tk.Frame(self.history, bg=CARD)
        self.detail = tk.Text(self.detail_wrap, height=6, bg=CARD, fg=FG, relief='flat', font=FONT,
                              wrap='word', padx=12, pady=10, state='disabled')
        detail_scroll = ttk.Scrollbar(self.detail_wrap, command=self.detail.yview)
        self.detail.configure(yscrollcommand=detail_scroll.set)
        detail_scroll.pack(side='right', fill='y')
        self.detail.pack(fill='both', expand=True)
        self.detail_button = RoundedButton(self.history, '展开本行详情', self.toggle_details, '#4b4163', FG, FONT)
        self.detail_button.pack(fill='x', pady=(0, 6))
        self.history.bind('<Configure>', lambda e: self.detail_caption.configure(wraplength=max(200,e.width-10)))
        self.footer = self.label(self.root, '本地记录  ·  只读内存  ·  无需截图', DIM, 9, anchor='w')
        self.footer.pack(side='bottom', fill='x', padx=24, pady=(10, 14), before=self.body)
        self.root.bind('<Configure>', self.on_resize, add='+')

    def on_resize(self, event):
        if event.widget is self.root:
            self.status.configure(wraplength=max(300, event.width-50))
            self.total_label.configure(font=('Segoe UI', -36 if event.width < 500 else -46, 'bold italic'))

    def layout(self):
        self.resources.grid_forget()
        self.history.grid_forget()
        if not self.history_visible.get():
            self.root.minsize(390, 650)
            self.body.columnconfigure(0, weight=1, minsize=0)
            self.body.columnconfigure(1, weight=0, minsize=0)
            self.body.rowconfigure(0, weight=1)
            self.body.rowconfigure(1, weight=0)
            self.resources.pack_propagate(True)
            self.resources.grid(row=0, column=0, sticky='nsew')
            self.enemy_view.configure(height=350)
            self.subtitle.pack_forget()
            self.root.geometry('520x740')
        elif self.compact.get():
            self.root.minsize(390, 820)
            self.body.columnconfigure(0, weight=1)
            self.body.columnconfigure(1, weight=0)
            self.body.rowconfigure(0, weight=0)
            self.body.rowconfigure(1, weight=1)
            self.resources.pack_propagate(True)
            self.subtitle.pack_forget()
            self.resources.grid(row=0, column=0, sticky='ew')
            self.history.grid(row=1, column=0, sticky='nsew', pady=(8, 0))
            self.detail_caption.pack_forget()
            self.resource_note.pack_forget()
            self.enemy_view.configure(height=min(270, max(238, len(self.enemy_cards)*238)))
            self.root.geometry(f'420x{min(850, self.root.winfo_screenheight()-90)}')
        else:
            self.root.minsize(1050, 730)
            self.body.columnconfigure(0, weight=0, minsize=295)
            self.body.columnconfigure(1, weight=1)
            self.body.rowconfigure(0, weight=1)
            self.body.rowconfigure(1, weight=0)
            self.resources.configure(width=300)
            self.resources.pack_propagate(False)
            self.subtitle.pack(side='left', padx=12)
            self.resources.grid(row=0, column=0, sticky='nsew', padx=(0, 16))
            self.history.grid(row=0, column=1, sticky='nsew')
            self.detail_caption.pack(fill='x', pady=8)
            self.resource_note.pack(fill='x', padx=8, pady=8)
            self.root.geometry('1280x790')

        self.update_detail_visibility()

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
        self.pause_button.configure(text='暂停')
        self.start_button.configure(text='取消连接')
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
            self.set_status('连接成功后可暂停。', DIM)
            return
        if self.paused.is_set():
            self.paused.clear()
            self.pause_button.configure(text='暂停')
            self.set_status('正在读取 · 可以行动', CYAN)
        else:
            self.paused.set()
            self.pause_button.configure(text='继续')
            self.set_status('已暂停 · 思考期间请勿行动；继续后沿用本场记录。', GOLD)

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
                    self.last_sample = None
                    self.connected = True
                    self.start_button.configure(text='停止')
                    self.set_status('内存已连接 · 可以行动', CYAN)
                elif kind == 'snapshot':
                    self.model.update(data)
                    self.last_packet = data
                    self.render(data.get('events', []))
                elif kind == 'heartbeat':
                    self.last_sample = data
                    self.footer.configure(text=f'最近采样 {time.strftime("%H:%M:%S", time.localtime(data))}  ·  本场记录自动保存')
                elif kind == 'stopped':
                    self.connected = False
                    for card in self.enemy_cards.values():
                        card.set_monitoring(False)
                    self.start_button.configure(text='连接新战斗')
                    self.pause_button.configure(text='暂停')
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
        self.enemy_keys = list(self.model.enemies)
        self.render_enemy()
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
                card.pack(fill='x', pady=(0, 6))
            self.enemy_cards[key].update_state(state)
        if self.compact.get() and self.history_visible.get():
            self.enemy_view.configure(height=min(270, max(238, len(self.enemy_cards)*238)))

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
            text += '未观测到对敌伤害；已记录技能发动，暂不解析特殊效果。\n'
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
        window.geometry('580x500')
        box = tk.Text(window, bg=BG, fg=FG, font=FONT, wrap='word', padx=20, pady=20)
        scroll = ttk.Scrollbar(window, command=box.yview)
        box.configure(yscrollcommand=scroll.set)
        scroll.pack(side='right', fill='y')
        box.pack(fill='both', expand=True)
        box.insert('end', text)
        box.configure(state='disabled')

    def open_library(self):
        from hbr_data.window import LibraryWindow
        if self.library is None or not self.library.window.winfo_exists():
            self.library = LibraryWindow(self.root)
            self.style()
        self.library.window.deiconify()
        self.library.window.lift()

    def set_status(self, text, color=DIM):
        self.status.configure(text=text, fg=color)
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
                bounds=[self.root.winfo_width(), self.root.winfo_height(), self.root.winfo_x(), self.root.winfo_y()])
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
