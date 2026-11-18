"""Manual, inspectable first step toward battle damage prediction."""
import json
import math
import tkinter as tk
from tkinter import ttk

from . import theme
from .components import (Fold, RoundedButton, RoundedCard, RoundedEntry, RoundedSelect, Segment,
                         TabBar, ToggleChip)
from .damage_math import DamageInputs, calculate, skill_base, enemy_attribute_reduction
from .damage_probability import distribution
from .destruction import apply_to_result, dp_factor, simulate_pools
from .equipment_editor import EquipmentEditor
from .effect_editor import EffectEditor
from .passive_audit import audit_text
from .damage_autofill import autofill, WEIGHTS, style_elements
from hbr_live_core import damage_service

GROUPS = (
    ('基础伤害', theme.DIM, (('base','基础伤害（可空）'),)),
    ('连击乘区', theme.CYAN, (('chain','颗数 × 每颗倍率'),)),
    ('加攻乘区', theme.PINK, (('attack','普通加攻 %'),('element_attack','元素加攻 %'),
        ('mind_eye','心眼 %'),('servant_mind_eye','仆人心眼（另加）%'),('field','场地 %'),('charge','充能 %'))),
    ('技能独立修正', theme.MINT, (('token_bonus','Token 增伤 %'),('dp_bonus','对 DP 特攻 %'),('hp_bonus','对 HP 特攻 %'),
        ('health_factor','技能资源比例倍率'),('down_factor','倒地条件倍率'),('other_factor','其他独立倍率'))),
    ('暴击乘区', theme.GOLD, (('critical_bonus','普通爆伤（含基础50）%'),('element_critical_bonus','元素爆伤 %'))),
    ('减防乘区', theme.ROSE, (('defense_down','普通减防 %'),('element_defense_down','元素减防 %'),('fragile','脆弱 %'))),
    ('弱点与抗性', theme.LAVENDER, (('weapon_bonus','武器弱点加成 %'),('element_bonus','元素弱点加成 %'),
        ('weakness_deepen','弱点加深 %'),('resistance','抗性 %'))),
    ('破坏率与 OD', theme.CYAN, (('destruction','当前破坏率 %'),('od','OD 倍率'))))
FIELDS = tuple(pair for _,_,fields in GROUPS for pair in fields)
theme.BG, theme.CARD, theme.FG, theme.DIM = theme.BG, theme.CARD, theme.FG, theme.DIM

NAMES = dict(attack='加攻（含充能／适用心眼）', defense='减防（含适用脆弱）', affinity='相性',
             critical='暴伤', chain='连击', destruction='破坏率', od='OD', token='Token',
             specialization='DP/HP 特攻', health='血量条件', down='倒地条件', other='其他')


def scroll_page(parent):
    frame = tk.Frame(parent, bg=theme.BG)
    canvas = tk.Canvas(frame, bg=theme.BG, highlightthickness=0, bd=0)
    bar = ttk.Scrollbar(frame, command=canvas.yview, style='Panel.Vertical.TScrollbar')
    bar.pack(side='right', fill='y')
    canvas.pack(fill='both', expand=True)
    canvas.configure(yscrollcommand=bar.set)
    body = tk.Frame(canvas, bg=theme.BG)
    item = canvas.create_window(0, 0, anchor='nw', window=body, width=1)
    body.bind('<Configure>', lambda e: canvas.configure(scrollregion=canvas.bbox('all')))
    canvas.bind('<Configure>', lambda e: canvas.itemconfigure(item, width=e.width))
    # Binding on the toplevel covers descendants without a global mouse binding.
    def wheel(event):
        if frame.winfo_ismapped() and str(event.widget).startswith(str(frame)):
            canvas.yview_scroll(-int(event.delta/120), 'units')
    frame.wheel = wheel
    parent.winfo_toplevel().bind('<MouseWheel>', wheel, add='+')
    return frame, body


class DamageWindow(tk.Toplevel):
    def __init__(self, parent, snapshot):
        super().__init__(parent)
        self.title('伤害试算 · 星屑战斗手帐')
        self.geometry('1180x900')
        self.configure(bg=theme.BG)
        self.minsize(980, 700)
        self.option_add('*Font', theme.ui(12))
        style = ttk.Style(self)
        theme.dialog_style(style, 'Panel')
        self.plot_data = None
        self.plot_damage = None
        self.snapshot = snapshot
        self.loaded_snapshot = {}
        self.pending_effects=[];self.dismissed_effects=set()
        self.pending_delta={}
        from .damage_sequence import DamageSequence
        self.sequence=DamageSequence()
        self.sequence_candidate=None
        self.fill_notes = '尚未自动填充'
        self.build_header()
        self.build_selector()
        self.build_pages()
        self.reload_choices(); self.refresh()
        if self.loaded_snapshot.get('connected') and self.player_box.current() >= 0 and self.enemy_box.current() >= 0:
            self.fill()
        else:
            self.compute()

    # ---- chrome ------------------------------------------------------------
    def build_header(self):
        head = tk.Frame(self, bg=theme.BG)
        head.pack(fill='x', padx=20, pady=(16, 10))
        tk.Label(head, text='✦ 伤害试算', bg=theme.BG, fg=theme.PINK,
                 font=theme.ui(16, 'bold')).pack(side='left')
        tk.Label(head, text='手填乘区 · 不影响战斗记录', bg=theme.BG, fg=theme.MUTED,
                 font=theme.ui(11)).pack(side='left', padx=12, pady=(4, 0))
        self.compute_button = RoundedButton(head, text='计算', command=self.compute,
                                            bg=theme.PINK_FILL, fg=theme.on_fill,
                                            font=theme.ui(13, 'bold'), height=36)
        self.compute_button.pack(side='right')

    def build_selector(self):
        bar = tk.Frame(self, bg=theme.SURFACE, padx=16, pady=12)
        bar.pack(fill='x', padx=18, pady=(0, 10))
        row = tk.Frame(bar, bg=theme.SURFACE)
        row.pack(fill='x')
        tk.Label(row, text='角色', bg=theme.SURFACE, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        self.player_box = RoundedSelect(row, values=(), width=theme.px(240))
        self.player_box.pack(side='left', padx=(6, 14))
        tk.Label(row, text='敌人', bg=theme.SURFACE, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        self.enemy_box = RoundedSelect(row, values=(), width=theme.px(240))
        self.enemy_box.pack(side='left', padx=(6, 14))
        RoundedButton(row, '刷新列表', self.reload_choices, theme.CARD_HI, theme.DIM,
                      theme.ui(11), height=30).pack(side='left')
        RoundedButton(row, '自动填充', self.fill, theme.mix(theme.CARD_HI, theme.CYAN, .26), theme.FG,
                      theme.ui(11), height=30).pack(side='left', padx=8)
        RoundedButton(row,'下一位',self.next_actor,theme.CARD_HI,theme.FG,height=30).pack(side='left',padx=6)
        modes = tk.Frame(bar, bg=theme.SURFACE)
        modes.pack(fill='x', pady=(10, 0))
        self.mode_choices = {}
        tk.Label(modes, text='模式', bg=theme.SURFACE, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        for key, label in [('transcend', '元素超越'), ('high_boost', '高阶增幅')]:
            tk.Label(modes, text=label, bg=theme.SURFACE, fg=theme.MUTED,
                     font=theme.ui(11)).pack(side='left', padx=(12, 4))
            var = tk.StringVar(self, value='自动'); self.mode_choices[key] = var
            RoundedSelect(modes, textvariable=var, values=['自动', '启用', '禁用'],
                          width=theme.px(96), height=theme.px(30)).pack(side='left')
        self.transcend_element=tk.StringVar(self,value='自动属性')
        RoundedSelect(modes,textvariable=self.transcend_element,values=['自动属性','火','冰','雷','光','暗'],
                      width=theme.px(100),height=theme.px(30)).pack(side='left',padx=6)
        tk.Label(modes, text='修改后点击自动填充；仅影响试算', bg=theme.SURFACE, fg=theme.MUTED,
                 font=theme.ui(10)).pack(side='left', padx=12)
        shared = tk.Frame(bar, bg=theme.SURFACE)
        shared.pack(fill='x', pady=(10, 0))
        tk.Label(shared, text='技能形态', bg=theme.SURFACE, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        self.form_choice = tk.StringVar(self, value='无切换形态')
        self.form_box = RoundedSelect(shared, textvariable=self.form_choice, values=['无切换形态'],
                                      width=theme.px(220), height=theme.px(30))
        self.form_box.pack(side='left', padx=(6, 18))
        self.form_box.bind('<<ComboboxSelected>>', lambda e: self.fill())
        self.form_key = None
        # One boss stat for every calculation: damage difference and debuff
        # difference both read this value, so it lives here instead of per page.
        self.enemy_stat_title = tk.Label(shared, text='敌方属性 · 读取', bg=theme.SURFACE, fg=theme.DIM,
                                         font=theme.ui(11))
        self.enemy_stat_title.pack(side='left')
        self.enemy_stat = tk.StringVar(self, value='')
        self.enemy_stat_override = None
        stat_entry = RoundedEntry(shared, textvariable=self.enemy_stat, width=theme.px(96), height=theme.px(30))
        stat_entry.pack(side='left', padx=6)
        stat_entry.entry.bind('<Return>', self.apply_enemy_stat)
        stat_entry.entry.bind('<FocusOut>', self.apply_enemy_stat, add='+')
        RoundedButton(shared, '恢复读取值', self.reset_enemy_stat, theme.CARD_HI, theme.DIM,
                      theme.ui(10), height=28).pack(side='left', padx=4)
        tk.Label(shared, text='伤害属性差与减益效果量共用此值；回车生效', bg=theme.SURFACE, fg=theme.MUTED,
                 font=theme.ui(10)).pack(side='left', padx=12)

    # ---- shared boss stat / skill forms -------------------------------------
    def apply_enemy_stat(self, event=None):
        try:
            value = damage_service.parse_enemy_stat(self.enemy_stat.get())
        except ValueError:
            self.enemy_stat_title.configure(text='敌方属性 · 无效', fg=theme.ROSE)
            return
        if value == self.enemy_stat_override:
            return
        self.enemy_stat_override = value
        self.push_enemy_stat()
        if hasattr(self, 'pending_context') and self.loaded_snapshot.get('connected'):
            self.fill()
        else:
            self.compute()

    def reset_enemy_stat(self):
        self.enemy_stat_override = None
        self.enemy_stat.set('')
        self.push_enemy_stat()
        if self.loaded_snapshot.get('connected'):
            self.fill()

    def push_enemy_stat(self):
        manual = self.enemy_stat_override is not None
        self.enemy_stat_title.configure(text='敌方属性 · ' + ('手动' if manual else '读取'),
                                        fg=theme.GOLD if manual else theme.DIM)
        if manual:
            text = f'{self.enemy_stat_override:g}'
            if hasattr(self, 'params') and 'enemy' in self.params:
                self.params['enemy'].set(text)
            if hasattr(self, 'effect_editor'):
                self.effect_editor.values['enemy'].set(text)

    def shared_enemy(self, enemy):
        """Apply the shared boss stat to one enemy snapshot (or mirror the read value)."""
        resolved, live = damage_service.apply_shared_enemy(enemy, self.enemy_stat_override)
        if self.enemy_stat_override is None:
            self.enemy_stat.set('' if live is None else f'{live:g}')
        return resolved

    def resolve_forms(self, data, actor_id):
        """Concrete form for switch skills: manual for the selected actor, auto otherwise."""
        info = damage_service.resolve_skill_forms(data, actor_id, self.form_choice.get(), self.form_key)
        self.form_choice.set(info['selected_label'])
        self.form_key = info['form_key']
        self.form_box.configure(values=info['labels'])
        return info['data'], info['notes']


    def build_pages(self):
        self.tab_names = ['乘区试算', '技能与属性', 'Buff／Debuff', '饰品效果', '当前内存参数', '天赋与被动审查']
        self.tabs = TabBar(self, self.tab_names, self.show_page, bg=theme.BG)
        self.tabs.pack(fill='x', padx=14, pady=(0, 6))
        self.pages = tk.Frame(self, bg=theme.BG)
        self.pages.pack(fill='both', expand=True, padx=12, pady=(0, 12))
        self.page_widgets = {}
        for name in self.tab_names:
            frame, body = scroll_page(self.pages)
            self.page_widgets[name] = (frame, body)
        self.build_form_page(*self.page_widgets['乘区试算'])
        self.build_skill_page(*self.page_widgets['技能与属性'])
        self.build_destruction_page(self.page_widgets['乘区试算'][0], self.battle_parameters)
        self.build_equipment_page(*self.page_widgets['饰品效果'])
        self.build_probability_page(self.page_widgets['乘区试算'][0],self.result_area)
        self.sequence_panel.pack_forget()
        self.sequence_panel.pack(fill='x',pady=8)
        self.build_raw_page(*self.page_widgets['当前内存参数'])
        self.build_audit_page(*self.page_widgets['天赋与被动审查'])
        self.effect_editor = EffectEditor(self.page_widgets['Buff／Debuff'][1],self.update_pending)
        self.effect_editor.pack(fill='both', expand=True)
        self.effect_editor.shared_enemy=lambda:self.enemy_stat_override
        RoundedButton(self.effect_editor.actions,'预发动所选技能效果',self.pre_cast_support,theme.CARD_HI,theme.FG,height=32).pack(side='left',padx=8)
        self.show_page(self.tab_names[0])

    def show_page(self, name):
        for page, (frame, _) in self.page_widgets.items():
            if page == name:
                frame.pack(fill='both', expand=True)
            else:
                frame.pack_forget()
        self.tabs.current = name
        self.tabs.draw()

    def note(self, parent, text, size=11, color=None):
        label = tk.Label(parent, text=text, bg=theme.BG, fg=color or theme.MUTED, justify='left',
                         anchor='w', font=theme.ui(size))
        label.pack(fill='x', pady=(0, 6))
        label.bind('<Configure>', lambda e: label.configure(wraplength=max(240, e.width - 8)))
        return label

    def fold(self, parent, title, prominent=False):
        shell = Fold(parent, title, prominent=prominent, opened=False, bg=theme.BG)
        shell.pack(fill='x', pady=5)
        return shell.body

    # ---- pages -------------------------------------------------------------
    def build_form_page(self, frame, form):
        self.battle_parameters=self.fold(form,'敌人 DP / HP 与破坏率参数',prominent=True)
        self.result_area=tk.Frame(form,bg=theme.BG)
        self.result_area.pack(fill='x',pady=6)
        self.summary=tk.Label(self.result_area,text='尚无计算结果',bg=theme.BG,fg=theme.FG,
                              font=theme.ui(13,'bold'),justify='left',anchor='w')
        self.summary.pack(fill='x',pady=6)
        self.hit_details=self.fold(self.result_area,'逐 Hit 明细 · 每段伤害与破坏率',prominent=True)
        self.damage_metric=tk.StringVar(self,value='raw')
        Segment(self.result_area,[('raw','打出伤害（含溢出）'),('applied','实际扣除 DP＋HP')],
                self.damage_metric,command=self.compute,accent=theme.CYAN).pack(anchor='w')
        from .sequence_panel import SequencePanel
        self.sequence_panel=SequencePanel(self.result_area,self.sequence_action)
        self.sequence_panel.pack(fill='x',pady=8)
        self.sequence_panel.update_sequence(self.sequence)
        self.summary.bind('<Configure>',lambda e:self.summary.configure(wraplength=max(300,e.width-12)))
        self.result_details=self.fold(form,'计算明细与备注')
        self.note(self.result_details, '自动填充当前状态与已确认的攻击前效果；填充后可修改，实时采样不会覆盖你的修改。\n'
                        '跨池按每段实际目标计算；支持已识别的阿蒙锁盾；尚不模拟其他多层盾、行动中新增状态和伤害衰减。', 11)
        grid = tk.Frame(form, bg=theme.BG)
        grid.pack(fill='x')
        self.values = {}
        defaults = DamageInputs()
        self.factor_labels = {}
        grid.columnconfigure(0, weight=1, uniform='group')
        grid.columnconfigure(1, weight=1, uniform='group')
        for idx, (title, color, fields) in enumerate(GROUPS):
            shell = RoundedCard(grid, background=theme.CARD, outline=theme.LINE, accent=color,
                                pad=(16, 12), stretch=True)
            shell.grid(row=idx//2, column=idx%2, sticky='nsew', padx=6, pady=6)
            card = shell.content
            head = tk.Frame(card, bg=theme.CARD)
            head.pack(fill='x', pady=(0, 6))
            tk.Label(head, text=title, bg=theme.CARD, fg=color,
                     font=theme.ui(12, 'bold')).pack(side='left')
            tk.Label(head, text=f'{len(fields)} 项', bg=theme.CARD, fg=theme.MUTED,
                     font=theme.ui(10)).pack(side='right')
            rows = tk.Frame(card, bg=theme.CARD)
            rows.pack(fill='x')
            rows.columnconfigure(1, weight=1)
            for row, (key, label) in enumerate(fields):
                tk.Label(rows, text=label, bg=theme.CARD, fg=theme.DIM,
                         font=theme.ui(11), anchor='w').grid(row=row, column=0, sticky='w', pady=3)
                value = getattr(defaults, key)
                var = tk.StringVar(self, value='' if value is None else str(value))
                self.values[key] = var
                if key=='chain':
                    self.chain_expression=tk.StringVar(self,value='0 × 25%')
                    self.chain_dirty=False
                    self.chain_expression.trace_add('write',lambda *_:setattr(self,'chain_dirty',True))
                    var=self.chain_expression
                RoundedEntry(rows, textvariable=var, width=theme.px(132)).grid(
                    row=row, column=1, sticky='e', padx=(10, 0), pady=3)
        options = tk.Frame(form, bg=theme.SURFACE, padx=14, pady=10)
        options.pack(fill='x', pady=10,before=self.result_area)
        self.pool = tk.StringVar(self, value='hp')
        tk.Label(options, text='目标判定', bg=theme.SURFACE, fg=theme.DIM,
                 font=theme.ui(11)).pack(side='left')
        Segment(options, [('auto', '自动跨 DP/HP'), ('dp', '仅 DP'), ('hp', '仅 HP')], self.pool, accent=theme.CYAN).pack(
            side='left', padx=(8, 18))
        self.flags = {}
        for key, title in [('critical', '暴击'), ('penetration_critical', '贯通暴击'), ('absorbed', '吸收')]:
            var = tk.BooleanVar(self, value=getattr(defaults, key))
            self.flags[key] = var
            ToggleChip(options, title, var, accent=theme.GOLD).pack(side='left', padx=(0, 8))
        self.result = self.text_panel(self.result_details, height=12)

    def text_panel(self, parent, height=10):
        box = tk.Frame(parent, bg=theme.SURFACE, padx=2, pady=2)
        box.pack(fill='both', expand=True, pady=(0, 8))
        widget = tk.Text(box, height=height, **theme.text_widget_options(theme.SURFACE), wrap='word')
        bar = ttk.Scrollbar(box, command=widget.yview)
        widget.configure(yscrollcommand=bar.set)
        bar.pack(side='right', fill='y')
        widget.pack(fill='both', expand=True)
        return widget

    def field_row(self, parent, label, width=20):
        row = tk.Frame(parent, bg=theme.BG)
        row.pack(fill='x', pady=4)
        tk.Label(row, text=label, bg=theme.BG, fg=theme.DIM, font=theme.ui(11), width=width,
                 anchor='w').pack(side='left')
        var = tk.StringVar(self, value='')
        RoundedEntry(row, textvariable=var, width=theme.px(150)).pack(side='left')
        return var

    def build_skill_page(self, frame, form):
        self.params = {}
        self.use_skill = tk.BooleanVar(self, value=False)
        self.damage_orb_enabled=tk.BooleanVar(self,value=False)
        use_row = tk.Frame(form, bg=theme.BG)
        use_row.pack(fill='x', pady=(0, 4))
        ToggleChip(use_row, '用技能参数生成基础伤害', self.use_skill, accent=theme.PINK).pack(side='left')
        tk.Label(use_row, text='取消则使用手填基础伤害', bg=theme.BG, fg=theme.MUTED,
                 font=theme.ui(10)).pack(side='left', padx=10, pady=(4, 0))
        self.skill_title = tk.Label(form, text='尚未自动填充', bg=theme.BG, fg=theme.PINK,
                                    font=theme.ui(12, 'bold'), anchor='w')
        self.skill_title.pack(fill='x', pady=8)
        self.sp_scaling=False
        self.sp_panel=tk.Frame(form,bg=theme.SURFACE,padx=14,pady=10)
        self.note(self.sp_panel,'全 SP 技能：威力为封顶端点。预计消耗默认当前 SP，可按行动前回复/消耗手动修改。超过封顶只限制效果，不代表实际少消耗 SP。')
        for key,label in [('sp_consumed','预计消耗 SP'),('sp_cap','效果封顶 SP')]:
            tk.Label(self.sp_panel,text=label,bg=theme.SURFACE,fg=theme.DIM).pack(anchor='w')
            self.params[key]=tk.StringVar(self,value='')
            RoundedEntry(self.sp_panel,textvariable=self.params[key],width=theme.px(150)).pack(anchor='w')
        self.sp_dr_scaling=tk.BooleanVar(self,value=False)
        ToggleChip(self.sp_panel,'破坏倍率也随消耗 SP 线性缩放（核实后启用）',self.sp_dr_scaling,accent=theme.CYAN).pack(anchor='w')
        self.dp_panel = tk.Frame(form, bg=theme.SURFACE, padx=14, pady=10)
        self.use_dp_scaling = tk.BooleanVar(self, value=False)
        ToggleChip(self.dp_panel, '按技能端点及自身 DP 自动计算独立倍率', self.use_dp_scaling,
                   accent=theme.CYAN).pack(anchor='w')
        grid = tk.Frame(self.dp_panel, bg=theme.SURFACE)
        grid.pack(fill='x', pady=(6, 0))
        grid.columnconfigure(0, weight=1); grid.columnconfigure(1, weight=1)
        for index, (key, label) in enumerate([('own_dp','自身当前 DP'),('own_dp_max','自身 DP 上限'),
                                              ('dp_zero_factor','0 DP 时倍率'),('dp_full_factor','满 DP 时倍率')]):
            cell = tk.Frame(grid, bg=theme.SURFACE)
            cell.grid(row=index//2, column=index % 2, sticky='w', pady=3)
            tk.Label(cell, text=label, bg=theme.SURFACE, fg=theme.DIM, font=theme.ui(11),
                     width=16, anchor='w').pack(side='left')
            var = tk.StringVar(self, value=''); self.params[key] = var
            RoundedEntry(cell, textvariable=var, width=theme.px(140)).pack(side='left', padx=(4, 0))
        from .damage_inputs import STATS
        blocks = [
            ('威力与等级', theme.PINK, [
                ('min_power', '最小威力'), ('max_power', '最大威力'), ('difference', '属性差阈值'),
                ('level', '技能等级'), ('enemy', '敌方防御参考值'), ('orb', '宝珠（核实后启用）'),
                ('growth_min', '最小威力等级成长'), ('growth_max', '最大威力等级成长')]),
            ('属性', theme.CYAN, [(key, STATS[key]) for key in WEIGHTS]),
            ('属性权重', theme.MINT, [('weight_' + key, STATS[key] + '权重') for key in WEIGHTS]),
            ('其他修正', theme.GOLD, [
                ('calamity', '灾厄属性下降（通常 20）'), ('fear_of_devil', '大灾厄属性下降（通常 100）'),
                ('critical_rate_bonus', '普通暴击率加成 %（供核对）'),
                ('element_critical_rate_bonus', '元素暴击率加成 %（供核对）'),
                ('morale_level', '士气等级（每层六维 +5）'), ('od_gain_bonus', 'OD 饰品获取量增幅 %')]),
        ]
        for title, color, fields in blocks:
            block = tk.Frame(form, bg=theme.SURFACE, padx=16, pady=12)
            block.pack(fill='x', pady=6)
            head = tk.Frame(block, bg=theme.SURFACE)
            head.pack(fill='x', pady=(0, 8))
            tk.Label(head, text=title, bg=theme.SURFACE, fg=color,
                     font=theme.ui(12, 'bold')).pack(side='left')
            grid = tk.Frame(block, bg=theme.SURFACE)
            grid.pack(fill='x')
            for column in range(3):
                grid.columnconfigure(column, weight=1, uniform='param')
            for index, (key, label) in enumerate(fields):
                cell = tk.Frame(grid, bg=theme.SURFACE)
                cell.grid(row=index // 3, column=index % 3, sticky='ew', padx=6, pady=5)
                tk.Label(cell, text=label, bg=theme.SURFACE, fg=theme.DIM, font=theme.ui(11),
                         anchor='w', justify='left').pack(fill='x')
                var = tk.StringVar(self, value=''); self.params[key] = var
                if key=='orb':
                    var.set('5')
                    ToggleChip(cell,'启用宝珠',self.damage_orb_enabled,accent=theme.CYAN).pack(side='left')
                    RoundedSelect(cell,textvariable=var,values=['1','2','3','4','5'],
                                  width=theme.px(70),height=theme.px(28)).pack(side='left')
                else:RoundedEntry(cell, textvariable=var, width=theme.px(148)).pack(anchor='w', pady=(3, 0))
        self.note(form, '权重为 0 的属性不参与计算。特殊技能条件、偏向和其他独立修正仍需核对。')

    def build_destruction_page(self, frame, form):
        # Automatic DP/HP mode always uses per-hit destruction; the optional toggle
        # is only for comparing fixed-pool results against constant destruction.
        self.use_destruction = tk.BooleanVar(self, value=False)
        self.note(form, '逐段试算 · 自动判断 DP / HP，结算伤害后增加破坏率', 12, theme.CYAN)
        fields=[('enemy_dp','剩余 DP'),('enemy_hp','剩余 HP（可空）'),
                ('skill_dr','技能破坏倍率'),('main_hits','本体 Hit 数'),
                ('enemy_dr','敌人有效破坏系数'),('max_dr','本技能破坏率上限 %'),
                ('destruction_bonus','破坏率获取提升 %')]
        current=tk.Frame(form,bg=theme.BG);current.pack(fill='x',pady=4)
        tk.Label(current,text='当前破坏率 %',bg=theme.BG,fg=theme.DIM,font=theme.ui(11)).pack(side='left',padx=6)
        RoundedEntry(current,textvariable=self.values['destruction'],width=theme.px(160)).pack(side='left')
        grid=tk.Frame(form,bg=theme.BG);grid.pack(fill='x')
        for column in range(2):grid.columnconfigure(column,weight=1)
        for index,(key,label) in enumerate(fields):
            cell=tk.Frame(grid,bg=theme.BG)
            cell.grid(row=index//2,column=index%2,sticky='ew',padx=6)
            self.params[key]=self.field_row(cell,label,16)
        self.calculation_status=self.note(form,'自动填充后直接计算；连续预演沿用上一人的破坏率和剩余 DP / HP。')
        RoundedButton(form,'重新计算',self.compute,theme.mix(theme.CARD_HI,theme.CYAN,.28),
                      theme.FG,theme.ui(11),height=32).pack(anchor='w',pady=4)
        details=self.hit_details
        ToggleChip(details,'单池比较时也计算逐段破坏率',self.use_destruction,
                   accent=theme.PINK).pack(anchor='w')
        self.note(details,'自动跨 DP/HP 始终按逐段计算。破盾当段增加破坏率，但溢出伤害不转入 HP。'
                          '达到本技能上限后停止增长；已有破坏率不会因换用其他属性技能而降低。')
        self.destruction_report=self.text_panel(details,height=16)

    def build_equipment_page(self, frame, form):
        self.equipment_editor = EquipmentEditor(form)
        self.equipment_editor.pack(fill='x')
        RoundedButton(form, '应用修改并计算', self.compute, theme.mix(theme.CARD_HI, theme.PINK, .3),
                      theme.FG, theme.ui(11), height=32).pack(anchor='w', pady=8)
        self.equipment_text = self.text_panel(form, height=12)

    def build_probability_page(self, frame, probability):
        controls=self.fold(self.result_details,'概率模型、Hit 权重与破盾分支')
        self.note(controls, '每 Hit 独立均匀浮动 0.9–1.1；按各段伤害权重合计，采用参考网站的概率模型。')
        self.note(controls, '跨 DP/HP 时按破盾段概率混合各分支；竖线标记集中概率。固定增益、独立逐 Hit 浮动；支持已确认的阿蒙锁盾，其他多层盾和衰减待补充。')
        self.hit_weights = tk.StringVar(self, value='')
        tk.Label(controls, text='各 Hit 相对伤害权重（含追击，逗号分隔；可修改）', bg=theme.BG, fg=theme.DIM,
                 font=theme.ui(11), anchor='w').pack(fill='x', pady=(6, 4))
        weights_row = tk.Frame(controls, bg=theme.BG)
        weights_row.pack(fill='x')
        RoundedEntry(weights_row, textvariable=self.hit_weights, width=theme.px(520),
                     justify='left').pack(side='left', fill='x', expand=True, padx=(0, 8))
        RoundedButton(weights_row, '重新计算', self.compute, theme.mix(theme.CARD_HI, theme.CYAN, .28),
                      theme.FG, theme.ui(11), height=32).pack(side='left', padx=8)
        self.hit_source = tk.Label(controls, text='尚无权重，不假定为单 Hit', bg=theme.BG, fg=theme.MUTED,
                                   font=theme.ui(11), anchor='w')
        self.hit_source.pack(fill='x', pady=6)
        self.prob_summary = tk.Label(controls, text='', bg=theme.BG, fg=theme.FG, font=theme.ui(11),
                                     anchor='w', justify='left')
        self.prob_summary.pack(fill='x', pady=(0, 8))
        self.prob_summary.bind('<Configure>', lambda e: self.prob_summary.configure(
            wraplength=max(300, e.width - 8)))
        self.plot = tk.Canvas(probability, bg=theme.SURFACE, highlightthickness=0, bd=0, height=380)
        self.plot.pack(fill='both', expand=True, pady=6)
        self.plot.bind('<Configure>', lambda e: self.draw_plot())
        self.plot.bind('<Motion>', self.hover_plot)
        self.plot_hint = tk.Label(controls, text='横轴：伤害倍率；纵轴：概率密度（面积为概率）',
                                  bg=theme.BG, fg=theme.MUTED, font=theme.ui(10), anchor='w')
        self.plot_hint.pack(fill='x')

    def build_raw_page(self, frame, data):
        self.note(data, '刷新获取当前已连接战斗的快照；原始参数并非预计算伤害。')
        RoundedButton(data, '刷新参数快照', self.refresh, theme.CARD_HI, theme.FG,
                      theme.ui(11), height=32).pack(anchor='w', pady=6)
        self.raw = self.text_panel(data, height=30)

    def build_audit_page(self, frame, audit_page):
        self.note(audit_page, '只列出运行时确实持有的天赋与被动；不根据风格资料推测解锁状态。')
        RoundedButton(audit_page, '刷新已加载天赋与被动', self.refresh, theme.CARD_HI, theme.FG,
                      theme.ui(11), height=32).pack(anchor='w', pady=6)
        self.audit = self.text_panel(audit_page, height=30)

    # ---- behaviour ---------------------------------------------------------
    def theme_widgets(self, widget):
        # Scoped style names only; the dashboard keeps its own look.
        name = widget.winfo_class()
        if name in ('TFrame','TLabel','TCheckbutton','TRadiobutton','TNotebook','TEntry','TButton','TCombobox'):
            widget.configure(style='Panel.'+name)
        for child in widget.winfo_children():
            self.theme_widgets(child)

    def update_probability(self, damage, effective_weights=None):
        self.plot_data=None;self.plot_damage=damage
        try:
            raw=self.hit_weights.get().replace('，',',').replace(' ', ',')
            weights=[float(w) for w in raw.split(',') if w.strip()]
            data=distribution(effective_weights if effective_weights is not None else weights);self.plot_data=data
            scale=damage if damage is not None else 1
            unit='伤害' if damage is not None else '倍率'
            text=f"{data['hits']} Hit · 中央 90% {unit}区间：{data['low']*scale:,.4g} – {data['high']*scale:,.4g} · 浮动标准差 {data['sigma']:.2%}"
            if hasattr(self,'filled_chain') and float(self.values['chain'].get())!=self.filled_chain:
                text+='\n连击合计已修改：请同步修改上方追击权重，曲线仍按当前权重列表计算。'
            self.prob_summary.configure(text=text)
        except ValueError as exc:self.prob_summary.configure(text='曲线未生成：'+str(exc))
        self.draw_plot()

    def draw_plot(self):
        if not hasattr(self,'plot'):return
        c=self.plot;c.delete('all');data=self.plot_data
        w=max(300,c.winfo_width());h=max(220,c.winfo_height());l,r,t,b=64,w-28,38,h-52
        c.create_rectangle(0,0,w,h,fill=theme.SURFACE,outline='')
        if not data:
            c.create_text(l,44,anchor='w',text='填入已确认的各 Hit 权重后显示概率曲线',fill=theme.MUTED,
                          font=theme.ui(11));return
        peak=max(data['density']) or 1;scale=self.plot_damage if self.plot_damage is not None else 1
        xmin,xmax=data.get('domain',(.9,1.1));span=xmax-xmin
        c.create_text(l,18,anchor='w',fill=theme.MUTED,text='概率密度（每单位伤害）' if data.get('absolute') else '概率密度（每单位伤害倍率）',font=theme.ui(10))
        for i in range(5):
            y=b-(b-t)*i/4
            c.create_line(l,y,r,y,fill=theme.LINE_SOFT)
            c.create_text(l-10,y,anchor='e',text=f'{peak*i/4:.3g}',fill=theme.MUTED,font=theme.num(10))
        for i in range(5):
            x=l+(r-l)*i/4;factor=xmin+span*i/4
            c.create_text(x,b+18,text=f'{factor*scale:,.4g}',fill=theme.MUTED,font=theme.num(10))
        points=[]
        for x,y in zip(data['x'][::1 if data.get('absolute') else 4],data['density'][::1 if data.get('absolute') else 4]):
            if xmin<=x<=xmax:points.extend((l+(x-xmin)/span*(r-l),b-y/peak*(b-t)))
        if points:
            polygon=c.create_polygon([l,b]+points+[r,b],fill=theme.CYAN_DEEP,outline='')
            c.itemconfigure(polygon,fill=theme.mix(theme.SURFACE,theme.CYAN,.18))
            c.create_line(points,fill=theme.CYAN,width=2,smooth=False)
        # Highlight the mean line itself; comparing the value with 1 only worked
        # for the old relative plot and never matched absolute damage.
        for value,is_mean in ((data['low'],False),(data.get('mean',1),True),(data['high'],False)):
            x=l+(value-xmin)/span*(r-l)
            c.create_line(x,t,x,b,fill=theme.PINK if is_mean else theme.mix(theme.SURFACE,theme.LAVENDER,.7),
                          dash=(3,5))

        for value,prob in data.get('atoms',[]):
            x=l+(value-xmin)/span*(r-l)
            c.create_line(x,t,x,b,fill=theme.GOLD,width=2)
            c.create_text(x,t+12,anchor='n',text=f'{prob:.2%}',fill=theme.GOLD,font=theme.num(10))

    def hover_plot(self,event):
        if not self.plot_data:return
        width=max(300,self.plot.winfo_width())
        xmin,xmax=self.plot_data.get('domain',(.9,1.1))
        factor=xmin+(event.x-64)/(width-92)*(xmax-xmin)
        if not xmin<=factor<=xmax:return
        d=self.plot_data;idx=max(0,min(len(d['x'])-1,round((factor-d['x'][0])/d['step'])))
        scale=self.plot_damage if self.plot_damage is not None else 1
        self.plot_hint.configure(text=f'{"伤害" if d.get("absolute") else "伤害倍率"} {factor:.4f} · 对应伤害 {factor*scale:,.4g} · 密度 {d["density"][idx]:.3f}（密度不是单点概率）')

    def next_actor(self):
        from .preview_order import ordered_frontline
        data=self.snapshot();players=data.get('players',[])
        order=ordered_frontline(players)
        current=self.player_box.current()
        if not order:return
        if current in order and order.index(current)==len(order)-1:
            self.sequence_panel.message.configure(text='本轮已核查到最后一位；未自动预添加或重复发动技能。')
            return
        index=order[order.index(current)+1] if current in order else order[0]
        self.player_box.current(index);self.fill()

    def reload_choices(self):
        data=self.snapshot()
        for box,key in [(self.player_box,'players'),(self.enemy_box,'enemies')]:
            old=box.get();labels=[f'{i+1}. {p.get("name") or p.get("actor") or "未命名"}' for i,p in enumerate(data.get(key,[]))]
            box.configure(values=labels)
            default=0
            if key=='players' and old not in labels:
                from .preview_order import ordered_frontline
                ordered=ordered_frontline(data.get(key,[]))
                default=ordered[0] if ordered else 0
            if labels:box.current(labels.index(old) if old in labels else default)
            else:box.set('')
        self.loaded_snapshot=data

    def sync_preview_epoch(self,data):
        epoch=(data.get('run_id'),data.get('execution_revision'))
        old=getattr(self,'preview_epoch',epoch)
        self.preview_epoch=epoch
        if old==epoch:return False
        self.sequence.clear();self.pending_effects=[];self.dismissed_effects=set();self.pending_delta={}
        self.sequence_candidate=None;self.preview_needs_fill=True
        if hasattr(self,'pending_context'):del self.pending_context
        self.sequence_panel.update_sequence(self.sequence);self.render_pending()
        self.sequence_panel.message.configure(text='实战行动已推进，旧伤害预演和预添加效果已清空；以新快照重新填充。')
        self.plot_data=None;self.draw_plot()
        self.summary.configure(text='等待新一轮指令选择后重新填充')
        return True

    def observe_live(self):
        data=self.snapshot()
        self.sync_preview_epoch(data)
        if getattr(self,'preview_needs_fill',False) and (data.get('turn_context') or {}).get('selecting'):
            self.fill()

    def _current_prepared(self):
        return dict(
            pending_context=getattr(self, 'pending_context', None),
            pending_base=getattr(self, 'pending_base', {}),
            pending_effects=list(getattr(self, 'pending_effects', [])),
            dismissed_effects=set(getattr(self, 'dismissed_effects', set())),
            pending_delta=dict(getattr(self, 'pending_delta', {})),
            pending_chain_weights=list(getattr(self, 'pending_chain_weights',
                                               getattr(self, 'pending_base', {}).get('chain_weights', []))),
            values={k: v.get() for k, v in self.values.items()},
            hit_weights_str=self.hit_weights.get(),
            filled_chain=getattr(self, 'filled_chain', None),
            chain_expression=self.chain_expression.get(),
            skill_title=self.skill_title.cget('text'),
        )

    def fill(self):
        # Preserve selected identities even if list ordering changes in a new snapshot.
        old = self.loaded_snapshot
        pi, ei = self.player_box.current(), self.enemy_box.current()
        if pi < 0 or ei < 0:
            return
        player, enemy = old['players'][pi], old['enemies'][ei]
        data = self.snapshot()
        if not data.get('connected'):
            self.fill_notes = '未连接战斗，未覆盖表单'
            self.refresh()
            return
        self.sync_preview_epoch(data)
        options = dict(
            transcend=self.mode_choices['transcend'].get(),
            high_boost=self.mode_choices['high_boost'].get(),
            transcend_element=self.transcend_element.get(),
            form_choice=self.form_choice.get(),
            enemy_stat=self.enemy_stat_override,
            damage_metric=self.damage_metric.get(),
        )
        prepared = damage_service.prepare(
            data,
            player.get('actor_id'),
            enemy.get('address'),
            options=options,
            sequence=self.sequence,
            sequence_battle=getattr(self, 'sequence_battle', None),
            pending_effects=self.pending_effects,
            dismissed_effects=self.dismissed_effects,
            pending_battle=getattr(self, 'pending_battle', None),
            form_key=self.form_key,
            autofill_fn=autofill,
        )
        form_info = prepared.get('form_info')
        if form_info:
            self.form_choice.set(form_info['selected_label'])
            self.form_key = form_info['form_key']
            self.form_box.configure(values=form_info['labels'])
        if not prepared.get('ok'):
            reason = prepared.get('reason')
            if reason in ('disconnected', 'missing_target'):
                self.fill_notes = prepared.get('fill_notes', '')
                self.refresh()
            elif reason == 'sequence_conflict':
                if prepared.get('sequence_reset'):
                    self.sequence_panel.update_sequence(self.sequence)
                self.sequence_battle = prepared.get('sequence_battle')
                self.sequence_panel.message.configure(text=prepared.get('sequence_error', ''))
            return
        if self.enemy_stat_override is None:
            live = prepared.get('live_enemy_stat')
            self.enemy_stat.set('' if live is None else f'{live:g}')
        if prepared.get('sequence_reset'):
            self.sequence_panel.update_sequence(self.sequence)
        self.sequence_battle = prepared['sequence_battle']
        self.pending_battle = prepared['pending_battle']
        self.pending_effects = prepared['pending_effects']
        self.dismissed_effects = prepared['dismissed_effects']
        self.pending_delta = prepared['pending_delta']
        self.pending_context = prepared['pending_context']
        self.pending_base = prepared['pending_base']
        self.damage_orb_enabled.set(prepared['damage_orb_enabled'])
        self.effect_editor.pending_list.delete(0, 'end')
        self.effect_editor.load_party(prepared['party'], prepared['player'], prepared['enemy'], prepared['modes'])
        self.render_pending()
        for k, var in self.values.items():
            var.set(prepared['values'][k])
        for k, var in self.flags.items():
            var.set(prepared['flags'][k])
        self.pool.set(prepared['pool'])
        self.shield_state = prepared['shield_state']
        self.auto_pool_blocked = prepared['auto_pool_blocked']
        for k, var in self.params.items():
            var.set(prepared['params'].get(k, ''))
        self.hit_weights.set(prepared['hit_weights_str'])
        self.hit_source.configure(text=prepared['hit_note'])
        self.use_destruction.set(prepared['use_destruction'])
        self.hp_adjustments = prepared['hp_adjustments']
        self.use_dp_scaling.set(prepared['use_dp_scaling'])
        self.sp_scaling = prepared['sp_scaling']
        self.sp_dr_scaling.set(prepared['sp_dr_scaling'])
        if self.sp_scaling:
            self.sp_panel.pack(fill='x', pady=8, before=self.skill_title)
        else:
            self.sp_panel.pack_forget()
        if prepared['use_dp_scaling']:
            self.dp_panel.pack(fill='x', pady=8, before=self.skill_title)
        else:
            self.dp_panel.pack_forget()
        self.equipment_editor.load(prepared['equipment_details'], prepared['equipment_owned'])
        self.equipment_text.configure(state='normal')
        self.equipment_text.delete('1.0', 'end')
        self.equipment_text.insert('end', prepared['equipment_text'])
        self.equipment_text.configure(state='disabled')
        self.filled_chain = prepared['filled_chain']
        self.pending_chain_weights = prepared['pending_chain_weights']
        self.show_chain(prepared['filled'])
        self.use_skill.set(prepared['use_skill'])
        self.skill_title.configure(text=prepared['skill_title'])
        self.fill_notes = prepared['fill_notes']
        self.preview_needs_fill = False
        self.refresh()
        self.compute()

    def pre_cast_support(self):
        if not hasattr(self, 'pending_context'):
            return
        updated, _, _, message = damage_service.pre_cast_support(
            self._current_prepared(),
            caster_index=self.effect_editor.caster_box.current(),
        )
        self.pending_effects = updated['pending_effects']
        self.fill()
        self.effect_editor.result.configure(text=message)

    def update_pending(self, action, payload):
        self.sync_preview_epoch(self.snapshot())
        if not hasattr(self, 'pending_context'):
            raise ValueError('请先自动填充伤害角色和敌人')
        updated = damage_service.apply_pending(
            self._current_prepared(),
            action,
            payload,
            current_values={k: v.get() for k, v in self.values.items()},
            current_hit_weights=self.hit_weights.get(),
            autofill_fn=autofill,
        )
        for k, v in updated['updates'].items():
            self.values[k].set(f'{v:.10g}')
        self.hp_adjustments = updated['hp_adjustments']
        self.pending_chain_weights = updated['pending_chain_weights']
        self.pending_effects = updated['pending_effects']
        self.dismissed_effects = updated['dismissed_effects']
        self.pending_delta = updated['pending_delta']
        if updated['chain_changed']:
            self.hit_weights.set(updated['hit_weights_str'])
            self.filled_chain = updated['filled_chain']
            self.chain_expression.set(updated['chain_expression'])
            self.chain_dirty = False
        self.render_pending()
        self.effect_editor.result.configure(text=updated['pending_status_text'])
        self.compute()

    def render_pending(self):
        self.effect_editor.pending_list.delete(0, 'end')
        for line in damage_service.format_pending_rows(self.pending_effects):
            self.effect_editor.pending_list.insert('end', line)

    def sequence_action(self, action):
        try:
            self.sync_preview_epoch(self.snapshot())
            if action == 'add':
                if not hasattr(self, 'pending_context'):
                    raise ValueError('请先自动填充角色与敌人，并使用自动跨 DP/HP')
                player, enemy, *_ = self.pending_context
                for box, key, identity in [
                    (self.player_box, 'players', player.get('actor_id')),
                    (self.enemy_box, 'enemies', enemy.get('address')),
                ]:
                    selected = self.loaded_snapshot.get(key, [])
                    index = box.current()
                    field = 'actor_id' if key == 'players' else 'address'
                    if index < 0 or index >= len(selected) or selected[index].get(field) != identity:
                        raise ValueError('切换角色或敌人后请先自动填充')
                self.compute()
                out = damage_service.sequence_add(
                    self.sequence,
                    self._current_prepared(),
                    dict(sequence_candidate=self.sequence_candidate),
                    skill_title=self.skill_title.cget('text'),
                )
                message = out['message']
            else:
                if action == 'undo':
                    out = damage_service.sequence_undo(self.sequence)
                else:
                    out = damage_service.sequence_clear(self.sequence)
                    self.pending_effects = []
                    self.dismissed_effects = set()
                    self.pending_delta = {}
                self.fill()
                message = out['message']
            self.sequence_panel.update_sequence(self.sequence)
            self.sequence_panel.message.configure(text=message)
        except (ValueError, TypeError, OverflowError) as exc:
            self.sequence_panel.message.configure(text=str(exc))

    def show_chain(self, filled):
        self.chain_expression.set(damage_service.format_chain_expression(filled))
        self.chain_dirty = False

    def compute(self):
        self.sequence_candidate = None
        if getattr(self, 'preview_needs_fill', False):
            return

        def apply_equipment(values_str, params_str, updated_values, updated_params):
            self.equipment_editor.apply({**self.values, **self.params})
            for k, v in self.values.items():
                values_str[k] = v.get()
            for k, v in self.params.items():
                params_str[k] = v.get()

        overrides = dict(
            values={k: v.get() for k, v in self.values.items()},
            params={k: v.get() for k, v in self.params.items()},
            flags={k: v.get() for k, v in self.flags.items()},
            pool=self.pool.get(),
            damage_metric=self.damage_metric.get(),
            use_skill=self.use_skill.get(),
            damage_orb_enabled=self.damage_orb_enabled.get(),
            use_destruction=self.use_destruction.get(),
            use_dp_scaling=self.use_dp_scaling.get(),
            sp_scaling=self.sp_scaling,
            sp_dr_scaling=self.sp_dr_scaling.get(),
            hit_weights=self.hit_weights.get(),
            chain_expression=self.chain_expression.get(),
            chain_dirty=self.chain_dirty,
            filled_chain=getattr(self, 'filled_chain', None),
            hp_adjustments=getattr(self, 'hp_adjustments', {}),
            shield_state=getattr(self, 'shield_state', None),
            auto_pool_blocked=getattr(self, 'auto_pool_blocked', False),
            equipment_apply=apply_equipment,
        )
        res = damage_service.compute(None, overrides)
        for k, v in res['updated_values'].items():
            if k == 'hit_weights':
                self.hit_weights.set(v)
            elif k in self.values:
                self.values[k].set(v)
        self.chain_dirty = res['chain_dirty']
        self.destruction_report.configure(state='normal')
        self.destruction_report.delete('1.0', 'end')
        if res['destruction_report']:
            self.destruction_report.insert('end', res['destruction_report'])
        self.destruction_report.configure(state='disabled')
        if res['calculation_status'] is not None:
            self.calculation_status.configure(text=res['calculation_status'])
        self.plot_data = res['plot_data']
        self.plot_damage = res['plot_damage']
        self.prob_summary.configure(text=res['prob_summary'])
        self.draw_plot()
        self.summary.configure(text=res['summary_text'])
        self.result.configure(state='normal')
        self.result.delete('1.0', 'end')
        self.result.insert('end', res['detail_text'])
        self.result.configure(state='disabled')
        self.sequence_candidate = res['sequence_candidate']

    def refresh(self):
        data = self.snapshot()
        audit, raw_header = damage_service.format_raw_inspection(data, self.fill_notes)
        self.audit.configure(state='normal')
        self.audit.delete('1.0', 'end')
        self.audit.insert('end', audit)
        self.audit.configure(state='disabled')
        self.raw.configure(state='normal')
        self.raw.delete('1.0', 'end')
        self.raw.insert('end', raw_header + json.dumps(data, ensure_ascii=False, indent=2))
        self.raw.configure(state='disabled')
