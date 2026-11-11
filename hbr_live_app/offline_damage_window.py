"""Damage calculator fed by a saved team and a user-entered enemy (no battle)."""
import tkinter as tk

from . import theme
from .components import RoundedButton, RoundedCard, RoundedEntry, RoundedSelect, Segment, ToggleChip
from .damage_window import DamageWindow, scroll_page
from . import offline_battle as ob

SETUP = '配队与敌人'
OD_LEVELS = [('0', '无 OD'), ('1', 'OD1'), ('2', 'OD2'), ('3', 'OD3')]


class OfflineDamageWindow(DamageWindow):
    """Reuses every live calculator page; only the snapshot source differs."""

    def __init__(self, parent, store, team_key=None, draft=False):
        self.store = store
        self.initial_team = (draft, team_key) if team_key is not None else None
        super().__init__(parent, self.offline_snapshot)
        self.title('离线伤害试算 · 配队档案')
        self.show_page(SETUP)

    # ---- state -------------------------------------------------------------
    def load_teams(self):
        self.teams = [(False, key, name, payload) for key, name, payload in self.store.rows()]
        self.teams += [(True, key, payload['captured_at'].replace('T', ' '), payload)
                       for key, _, payload in self.store.rows(True)]

    def team_labels(self):
        return [('待确认 · ' if draft else '') + f'{name}' + (f' · #{key}' if not draft else '')
                for draft, key, name, _ in self.teams]

    def current_team(self):
        index = self.team_box.current() if hasattr(self, 'team_box') else -1
        return self.teams[index] if 0 <= index < len(self.teams) else None

    def offline_snapshot(self):
        team = self.current_team()
        if team is None or self.offline_enemy is None:
            return dict(connected=bool(team), offline=True, players=[], enemies=[])
        draft, key, _, payload = team
        statuses = {}
        enemy_statuses = []
        count = len(payload.get('members', []))
        for target, status in self.manual_statuses:
            if target == ob.ENEMY:
                enemy_statuses.append(status)
            else:
                for index in (range(count) if target == ob.ALL_MEMBERS else [target]):
                    statuses.setdefault(index, []).append(status)
        enemy = dict(self.offline_enemy, statuses=enemy_statuses)
        return ob.snapshot(('d' if draft else 's') + str(key), payload, enemy, self.skill_choices, statuses,
                           self.offline_field, int(self.od_level.get() or 0))

    # ---- chrome ------------------------------------------------------------
    def build_header(self):
        super().build_header()
        head = self.winfo_children()[-1]
        for child in head.winfo_children():
            if isinstance(child, tk.Label) and child.cget('text') == '✦ 伤害试算':
                child.configure(text='✦ 离线伤害试算')
            elif isinstance(child, tk.Label):
                child.configure(text='配队档案 + 手填敌人 · 不连接战斗')

    def build_selector(self):
        # Initialise offline state before the base window first asks for a snapshot.
        self.manual_statuses = []
        self.status_serial = 0
        self.skill_choices = {}
        self.offline_enemy = None
        self.offline_field = {'statuses': []}
        self.od_level = tk.StringVar(self, value='0')
        self.load_teams()
        super().build_selector()

    def build_pages(self):
        super().build_pages()
        frame, body = scroll_page(self.pages)
        self.page_widgets = {SETUP: (frame, body), **self.page_widgets}
        self.tabs.names = [SETUP] + list(self.tabs.names)
        self.tab_names = list(self.tabs.names)
        self.build_setup(body)
        self.tabs.draw()

    def section(self, parent, title, color, hint=''):
        shell = RoundedCard(parent, background=theme.CARD, outline=theme.LINE, accent=color, pad=(16, 12))
        shell.pack(fill='x', pady=6, padx=4)
        head = tk.Frame(shell.content, bg=theme.CARD)
        head.pack(fill='x', pady=(0, 8))
        tk.Label(head, text=title, bg=theme.CARD, fg=color, font=theme.ui(12, 'bold')).pack(side='left')
        if hint:
            tk.Label(head, text=hint, bg=theme.CARD, fg=theme.MUTED, font=theme.ui(10)).pack(side='left', padx=10)
        return shell.content

    def entry(self, parent, row, column, label, value='', width=110, justify='right'):
        tk.Label(parent, text=label, bg=theme.CARD, fg=theme.DIM, font=theme.ui(11), anchor='w').grid(
            row=row, column=column * 2, sticky='w', padx=(0, 6), pady=3)
        var = tk.StringVar(self, value=value)
        RoundedEntry(parent, textvariable=var, width=theme.px(width), justify=justify).grid(
            row=row, column=column * 2 + 1, sticky='w', padx=(0, 18), pady=3)
        return var

    def build_setup(self, body):
        # Team
        team = self.section(body, '① 选择配队', theme.PINK, '来自配队档案；六维为首次采样实测值')
        row = tk.Frame(team, bg=theme.CARD)
        row.pack(fill='x')
        self.team_box = RoundedSelect(row, values=self.team_labels(), width=theme.px(360),
                                      placeholder='暂无配队档案')
        self.team_box.pack(side='left')
        self.team_box.bind('<<ComboboxSelected>>', lambda e: self.change_team())
        RoundedButton(row, '重新读取档案', self.reload_teams, theme.CARD_HI, theme.DIM,
                      theme.ui(11), height=30).pack(side='left', padx=8)
        self.members_frame = tk.Frame(team, bg=theme.CARD)
        self.members_frame.pack(fill='x', pady=(10, 0))

        # Enemy
        enemy = self.section(body, '② 敌人参数', theme.CYAN, '全部手填；DP 填 0 表示直接打 HP')
        grid = tk.Frame(enemy, bg=theme.CARD)
        grid.pack(fill='x')
        self.enemy_vars = dict(
            name=self.entry(grid, 0, 0, '名称', '自定义敌人', 150, 'left'),
            dp=self.entry(grid, 0, 1, 'DP', '0'),
            hp=self.entry(grid, 0, 2, 'HP', '1000000'),
            defense=self.entry(grid, 1, 0, '防御参考（属性值）', '', 150),
            damage_rate=self.entry(grid, 1, 1, '当前破坏率 %', '100'),
            coefficient=self.entry(grid, 1, 2, '有效破坏系数', ''),
            maximum=self.entry(grid, 2, 0, '破坏率上限 %', '', 150))
        self.enemy_down = tk.BooleanVar(self, value=False)
        ToggleChip(grid, '倒地中', self.enemy_down, accent=theme.GOLD).grid(row=2, column=2, columnspan=2, sticky='w')
        tk.Label(enemy, text='相性：填写游戏中的伤害倍率 %（弱点 150 / 普通 100 / 抗性 50 / 吸收为负）',
                 bg=theme.CARD, fg=theme.MUTED, font=theme.ui(10), anchor='w').pack(fill='x', pady=(10, 4))
        rates = tk.Frame(enemy, bg=theme.CARD)
        rates.pack(fill='x')
        self.rate_vars = {}
        for i, key in enumerate(ob.RESIST_KEYS):
            self.rate_vars[key] = self.entry(rates, i // 5, i % 5, ob.ELEMENT_NAMES[key], '100', 64)

        # Field / OD
        extra = self.section(body, '③ 场地与 OD', theme.MINT)
        row = tk.Frame(extra, bg=theme.CARD)
        row.pack(fill='x')
        tk.Label(row, text='场地属性', bg=theme.CARD, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        self.field_element = tk.StringVar(self, value='无场地')
        RoundedSelect(row, textvariable=self.field_element, values=['无场地'] + [n for k, n in ob.ELEMENTS if k],
                      width=theme.px(96), height=theme.px(30)).pack(side='left', padx=(6, 12))
        tk.Label(row, text='场地加成 %', bg=theme.CARD, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        self.field_bonus = tk.StringVar(self, value='')
        RoundedEntry(row, textvariable=self.field_bonus, width=theme.px(80), height=theme.px(30)).pack(
            side='left', padx=(6, 18))
        tk.Label(row, text='OD', bg=theme.CARD, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        Segment(row, OD_LEVELS, self.od_level, command=self.apply_setup, accent=theme.MINT).pack(side='left', padx=6)

        # Manual statuses
        manual = self.section(body, '④ 手动 Buff / Debuff', theme.GOLD,
                              '同类有限期效果按游戏规则取高两层；勾选常驻则直接相加')
        row = tk.Frame(manual, bg=theme.CARD)
        row.pack(fill='x')
        self.status_target = RoundedSelect(row, values=(), width=theme.px(150), height=theme.px(30))
        self.status_target.pack(side='left')
        self.status_kind = RoundedSelect(row, values=list(ob.KIND_TITLES.values()), width=theme.px(220),
                                         height=theme.px(30))
        self.status_kind.pack(side='left', padx=6)
        self.status_kind.current(0)
        self.status_kind.bind('<<ComboboxSelected>>', lambda e: self.sync_status_target())
        self.status_element = tk.StringVar(self, value='无属性')
        RoundedSelect(row, textvariable=self.status_element, values=[n for _, n in ob.ELEMENTS],
                      width=theme.px(88), height=theme.px(30)).pack(side='left')
        row2 = tk.Frame(manual, bg=theme.CARD)
        row2.pack(fill='x', pady=(8, 0))
        tk.Label(row2, text='数值', bg=theme.CARD, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        self.status_value = tk.StringVar(self, value='')
        RoundedEntry(row2, textvariable=self.status_value, width=theme.px(80), height=theme.px(30)).pack(
            side='left', padx=(6, 12))
        tk.Label(row2, text='颗数（连击）', bg=theme.CARD, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        self.status_count = tk.StringVar(self, value='')
        RoundedEntry(row2, textvariable=self.status_count, width=theme.px(60), height=theme.px(30)).pack(
            side='left', padx=(6, 12))
        self.status_permanent = tk.BooleanVar(self, value=False)
        ToggleChip(row2, '常驻', self.status_permanent, accent=theme.GOLD, height=30).pack(side='left')
        RoundedButton(row2, '添加', self.add_status, theme.PINK_FILL, theme.on_fill, theme.ui(11),
                      height=30).pack(side='left', padx=8)
        RoundedButton(row2, '删除所选', self.remove_status, theme.CARD_HI, theme.FG, theme.ui(11),
                      height=30).pack(side='left')
        RoundedButton(row2, '清空', self.clear_statuses, theme.CARD_HI, theme.DIM, theme.ui(11),
                      height=30).pack(side='left', padx=8)
        self.status_list = tk.Listbox(manual, height=6, bg=theme.SURFACE, fg=theme.FG, bd=0,
                                      highlightthickness=0, selectbackground=theme.CARD_HI,
                                      selectforeground=theme.FG, font=theme.ui(11), activestyle='none')
        self.status_list.pack(fill='x', pady=(8, 0))
        tk.Label(manual, text='也可在「Buff／Debuff」页按队员技能预发动效果；两处添加的效果会一起参与覆盖筛选。',
                 bg=theme.CARD, fg=theme.MUTED, font=theme.ui(10), anchor='w').pack(fill='x', pady=(6, 0))

        bar = tk.Frame(body, bg=theme.BG)
        bar.pack(fill='x', pady=10, padx=4)
        RoundedButton(bar, '应用并计算 ›', self.apply_setup, theme.PINK_FILL, theme.on_fill,
                      theme.ui(13, 'bold'), height=38).pack(side='left')
        self.setup_message = tk.Label(bar, text='', bg=theme.BG, fg=theme.MUTED, font=theme.ui(11),
                                      anchor='w', justify='left')
        self.setup_message.pack(side='left', padx=14, fill='x', expand=True)

        index = 0
        if self.initial_team:
            index = next((i for i, (d, k, _, _) in enumerate(self.teams) if (d, k) == self.initial_team), 0)
        if self.teams:
            self.team_box.current(index)
        self.read_enemy(quiet=True)
        self.render_members()

    # ---- setup actions -----------------------------------------------------
    def reload_teams(self):
        current = self.current_team()
        self.load_teams()
        self.team_box.configure(values=self.team_labels())
        keys = [(d, k) for d, k, _, _ in self.teams]
        if current and (current[0], current[1]) in keys:
            self.team_box.current(keys.index((current[0], current[1])))
        elif self.teams:
            self.team_box.current(0)
        else:
            self.team_box.set('')
        self.change_team()

    def change_team(self):
        self.skill_choices = {}
        self.manual_statuses = [(t, s) for t, s in self.manual_statuses if t in (ob.ENEMY, ob.ALL_MEMBERS)]
        self.render_members()
        self.render_statuses()
        self.apply_setup()

    def members(self):
        team = self.current_team()
        return team[3].get('members', []) if team else []

    def render_members(self):
        for widget in self.members_frame.winfo_children():
            widget.destroy()
        members = self.members()
        if not members:
            tk.Label(self.members_frame, text='尚无配队档案：先在战斗中采样并在「配队档案」保存。',
                     bg=theme.CARD, fg=theme.MUTED, font=theme.ui(11)).pack(anchor='w')
        self.members_frame.columnconfigure(1, weight=1)
        self.members_frame.columnconfigure(3, weight=1)
        for index, member in enumerate(members):
            row, column = index % 3, (index // 3) * 2
            front = '前排' if member.get('position') in (0, 1, 2) else '后排'
            title = f"{member.get('actor') or '?'} · {member.get('style_name') or member.get('style_label')}"
            tk.Label(self.members_frame, text=f'{front}  {title}', bg=theme.CARD, fg=theme.FG,
                     font=theme.ui(11), anchor='w').grid(row=row * 2, column=column, sticky='w', pady=(4, 0))
            skills = [s for s in member.get('skills', []) if s.get('label')]
            labels = [f"{s.get('name') or s['label']}  Lv.{s.get('level') if s.get('level') is not None else '?'}"
                      for s in skills]
            box = RoundedSelect(self.members_frame, values=labels, width=theme.px(300), height=theme.px(30),
                                placeholder='无已读取技能')
            box.grid(row=row * 2 + 1, column=column, sticky='w', padx=(0, 18), pady=(2, 4))
            if labels:
                box.current(self.skill_choices.get(index, 0))
            box.bind('<<ComboboxSelected>>', lambda e, i=index, b=box: self.choose_skill(i, b.current()))
        self.sync_status_target()

    def choose_skill(self, index, choice):
        self.skill_choices[index] = max(0, choice)
        self.apply_setup()

    def target_options(self):
        options = [(ob.ALL_MEMBERS, '我方全体')]
        options += [(i, '我方 · ' + str(m.get('actor') or m.get('style_label'))) for i, m in enumerate(self.members())]
        return options

    def sync_status_target(self):
        kind = list(ob.KIND_TITLES)[max(0, self.status_kind.current())]
        enemy_side = ob.STATUS_KINDS[kind][1] == 'enemy'
        self.target_choices = [(ob.ENEMY, '敌人')] if enemy_side else self.target_options()
        old = self.status_target.get()
        labels = [label for _, label in self.target_choices]
        self.status_target.configure(values=labels)
        self.status_target.current(labels.index(old) if old in labels else 0)

    def add_status(self):
        try:
            kind = list(ob.KIND_TITLES)[self.status_kind.current()]
            element = next(k for k, n in ob.ELEMENTS if n == self.status_element.get())
            index = self.status_target.current()
            if not 0 <= index < len(self.target_choices):
                raise ValueError('请选择施加对象')
            self.status_serial += 1
            status = ob.manual_status(kind, self.status_value.get(), element, self.status_count.get() or None,
                                      self.status_serial, self.status_permanent.get())
        except (ValueError, StopIteration, IndexError) as exc:
            self.setup_message.configure(text=str(exc) or '参数不完整', fg=theme.ROSE)
            return
        self.manual_statuses.append((self.target_choices[index][0], status))
        self.render_statuses()
        self.apply_setup()

    def remove_status(self):
        selected = self.status_list.curselection()
        if selected:
            self.manual_statuses.pop(selected[0])
            self.render_statuses()
            self.apply_setup()

    def clear_statuses(self):
        self.manual_statuses = []
        self.render_statuses()
        self.apply_setup()

    def render_statuses(self):
        names = dict(self.target_options() + [(ob.ENEMY, '敌人')])
        self.status_list.delete(0, 'end')
        for target, status in self.manual_statuses:
            self.status_list.insert('end', f'{names.get(target, "?")}  ←  {ob.describe_status(status)}')

    def number(self, var, label, optional=False, integer=False):
        text = var.get().strip().replace(',', '')
        if not text:
            if optional:
                return None
            raise ValueError(f'请填写{label}')
        try:
            value = float(text)
        except ValueError:
            raise ValueError(f'{label}不是数字') from None
        return int(value) if integer and value == int(value) else value

    def read_enemy(self, quiet=False):
        try:
            v = self.enemy_vars
            rates = {key: self.number(var, ob.ELEMENT_NAMES[key] + '相性', optional=True)
                     for key, var in self.rate_vars.items()}
            self.offline_enemy = ob.manual_enemy(
                name=v['name'].get().strip(), dp=self.number(v['dp'], 'DP', integer=True),
                hp=self.number(v['hp'], 'HP', integer=True),
                defense=self.number(v['defense'], '防御参考', optional=True),
                damage_rate=self.number(v['damage_rate'], '当前破坏率'),
                destruction_coefficient=self.number(v['coefficient'], '破坏系数', optional=True),
                destruction_max=self.number(v['maximum'], '破坏率上限', optional=True),
                rates=rates, down=1 if self.enemy_down.get() else 0)
            element = next((k for k, n in ob.ELEMENTS if n == self.field_element.get()), '')
            bonus = self.number(self.field_bonus, '场地加成', optional=True)
            self.offline_field = ob.zone_state(element, bonus)
            return True
        except ValueError as exc:
            if not quiet:
                self.setup_message.configure(text=str(exc), fg=theme.ROSE)
            return False

    def apply_setup(self):
        if not self.read_enemy():
            return
        progress = self.offline_enemy.get('enemy_progress', {})
        if self.offline_enemy.get('combat_inputs', {}).get('_defenseRefParam') is None:
            message = '未填防御参考：属性差将无法计算，基础伤害需手填。'
        elif progress.get('destruction_coefficient') is None or progress.get('destruction_max') is None:
            message = '未填有效破坏系数 / 破坏率上限：破坏率递推与跨 DP/HP 结果无法生成（不自动猜测）。'
        else:
            message = '已应用；切换到「乘区试算」查看结果，填充后仍可手动修改乘区。'
        self.reload_choices()
        if self.player_box.current() >= 0 and self.enemy_box.current() >= 0:
            self.fill()
        else:
            self.refresh(); self.compute()
        self.setup_message.configure(text=message, fg=theme.MINT if '已应用' in message else theme.GOLD)
