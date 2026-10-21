"""Manual, inspectable first step toward battle damage prediction."""
import json
import math
import tkinter as tk
from tkinter import ttk

from . import theme
from .components import (RoundedButton, RoundedCard, RoundedEntry, RoundedSelect, Segment,
                         TabBar, ToggleChip)
from .damage_math import DamageInputs, calculate, skill_base, enemy_attribute_reduction
from .damage_probability import distribution
from .destruction import apply_to_result, dp_factor, simulate_pools
from .equipment_editor import EquipmentEditor
from .effect_editor import EffectEditor
from .passive_audit import audit_text
from .damage_autofill import autofill, WEIGHTS, style_elements

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
        self.pending_effects=[]
        self.pending_delta={}
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
        modes = tk.Frame(bar, bg=theme.SURFACE)
        modes.pack(fill='x', pady=(10, 0))
        self.mode_choices = {}
        tk.Label(modes, text='模式', bg=theme.SURFACE, fg=theme.DIM, font=theme.ui(11)).pack(side='left')
        for key, label in [('transcend', '雷超越'), ('high_boost', '高阶增幅')]:
            tk.Label(modes, text=label, bg=theme.SURFACE, fg=theme.MUTED,
                     font=theme.ui(11)).pack(side='left', padx=(12, 4))
            var = tk.StringVar(self, value='自动'); self.mode_choices[key] = var
            RoundedSelect(modes, textvariable=var, values=['自动', '启用', '禁用'],
                          width=theme.px(96), height=theme.px(30)).pack(side='left')
        tk.Label(modes, text='修改后点击自动填充；仅影响试算', bg=theme.SURFACE, fg=theme.MUTED,
                 font=theme.ui(10)).pack(side='left', padx=12)

    def build_pages(self):
        self.tab_names = ['乘区试算', '技能与属性', 'Buff／Debuff', '逐段破坏率', '饰品效果', '当前内存参数', '天赋与被动审查']
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
        self.build_destruction_page(*self.page_widgets['逐段破坏率'])
        self.build_equipment_page(*self.page_widgets['饰品效果'])
        self.build_probability_page(self.page_widgets['乘区试算'][0],self.result_area)
        self.build_raw_page(*self.page_widgets['当前内存参数'])
        self.build_audit_page(*self.page_widgets['天赋与被动审查'])
        self.effect_editor = EffectEditor(self.page_widgets['Buff／Debuff'][1],self.update_pending)
        self.effect_editor.pack(fill='both', expand=True)
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

    def fold(self,parent,title):
        shell=tk.Frame(parent,bg=theme.BG);shell.pack(fill='x',pady=5)
        body=tk.Frame(shell,bg=theme.BG)
        opened=tk.BooleanVar(self,value=False)
        def toggle():
            opened.set(not opened.get())
            button.configure(text=('▾ ' if opened.get() else '▸ ')+title)
            if opened.get():body.pack(fill='x')
            else:body.pack_forget()
        button=tk.Button(shell,text='▸ '+title,command=toggle,bg=theme.SURFACE,fg=theme.DIM,
                         relief='flat',anchor='w',font=theme.ui(11))
        button.pack(fill='x')
        return body

    # ---- pages -------------------------------------------------------------
    def build_form_page(self, frame, form):
        self.result_area=tk.Frame(form,bg=theme.BG)
        self.result_area.pack(fill='x',pady=6)
        self.summary=tk.Label(self.result_area,text='尚无计算结果',bg=theme.BG,fg=theme.FG,
                              font=theme.ui(13,'bold'),justify='left',anchor='w')
        self.summary.pack(fill='x',pady=6)
        self.damage_metric=tk.StringVar(self,value='raw')
        Segment(self.result_area,[('raw','打出伤害（含溢出）'),('applied','实际扣除 DP＋HP')],
                self.damage_metric,command=self.compute,accent=theme.CYAN).pack(anchor='w')
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
        self.use_destruction = tk.BooleanVar(self, value=False)
        ToggleChip(form, '启用逐段破坏率递推（参数完整时自动启用）', self.use_destruction,
                   accent=theme.PINK).pack(anchor='w')
        self.note(form, '各段先结算伤害，再增加破坏率。破盾当段即增加破坏率；该段溢出伤害不转入 HP，后续段使用新破坏率。\n'
                        '敌人系数沿用 DamageRateValue（例如 4），不是属性抗性百分比；有破坏抗性状态时需核对最终有效系数。')
        for key, label in [('skill_dr','技能破坏倍率'),('main_hits','本体 Hit 数'),('enemy_dr','敌人有效破坏系数'),
                           ('max_dr','本技能有效破坏率上限 %'),('destruction_bonus','破坏率获取提升合计 %')]:
            self.params[key] = self.field_row(form, label, 20)
        self.note(form,'主界面选择自动跨 DP/HP 时，按敌人剩余 DP 逐段判断承伤池；破盾段溢出仍丢弃。')
        for key, label in [('enemy_dp','敌人剩余 DP'),('enemy_hp','敌人剩余 HP（可空）')]:
            self.params[key] = self.field_row(form, label, 28)
        RoundedButton(form, '计算逐段伤害', self.compute, theme.mix(theme.CARD_HI, theme.PINK, .3),
                      theme.FG, theme.ui(11), height=32).pack(anchor='w', pady=8)
        self.destruction_report = self.text_panel(form, height=16)

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
        for value in (data['low'],data.get('mean',1),data['high']):
            x=l+(value-xmin)/span*(r-l)
            c.create_line(x,t,x,b,fill=theme.PINK if value==1 else theme.mix(theme.SURFACE,theme.LAVENDER,.7),
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

    def reload_choices(self):
        data=self.snapshot()
        for box,key in [(self.player_box,'players'),(self.enemy_box,'enemies')]:
            old=box.get();labels=[f'{i+1}. {p.get("name") or p.get("actor") or "未命名"}' for i,p in enumerate(data.get(key,[]))]
            box.configure(values=labels)
            default=0
            if key=='players' and old not in labels:
                default=next((i for i,p in enumerate(data.get(key,[]))
                              if p.get('actor_position',0) in (0,1,2) and any(
                                  part.get('skill_type_raw')==10 for part in
                                  p.get('combat_inputs',p.get('inputs',{})).get('selected_skill',{}).get('parts',[]))),0)
            if labels:box.current(labels.index(old) if old in labels else default)
            else:box.set('')
        self.loaded_snapshot=data

    def fill(self):
        # Preserve selected identities even if list ordering changes in a new snapshot.
        old=self.loaded_snapshot
        pi,ei=self.player_box.current(),self.enemy_box.current()
        if pi<0 or ei<0:return
        player=old['players'][pi];enemy=old['enemies'][ei]
        data=self.snapshot()
        if not data.get('connected'):
            self.fill_notes='未连接战斗，未覆盖表单';self.refresh();return
        player=next((p for p in data.get('players',[]) if p.get('actor_id')==player.get('actor_id')),None)
        enemy=next((e for e in data.get('enemies',[]) if e.get('address')==enemy.get('address')),None)
        if player is None or enemy is None:
            self.fill_notes='所选角色/敌人已变化，请刷新列表';self.refresh();return
        inputs=player.get('combat_inputs',player.get('inputs',{}))
        gauge=data.get('element_gauge') or {}
        turn=inputs.get('reinforced_mode_turn')
        automatic=dict(transcend=gauge.get('full') is True and gauge.get('element')==3,
                       high_boost=any(s.get('label')=='SpecialStatus.HighBoost' and s.get('effective') is not False
                                      and not s.get('pending_add') and not s.get('pending_remove')
                                      for s in player.get('statuses',[])),
                       ghost=isinstance(turn,int) and turn>0,
                       gidou='Passive.Condition_AttackUp11' in inputs.get('passive_labels',[]))
        modes={k:(automatic[k] if v.get()=='自动' else v.get()=='启用') for k,v in self.mode_choices.items()}
        # Let autofill apply its complete status/expiry/condition filtering in auto mode.
        if self.mode_choices['high_boost'].get()=='自动':modes.pop('high_boost')
        modes.update(ghost=automatic['ghost'],gidou=automatic['gidou'])
        modes['enemies']=data.get('enemies',[])
        od=data.get('od_state') or {}
        modes.update(od_active=od.get('active') if od.get('available') else None,od_level=od.get('level'))
        modes['lightning_style']='Thunder' in style_elements(player.get('style_label',''))
        if gauge.get('full') and (gauge.get('element')!=3 or modes.get('transcend')):
            modes['super_break_element']={1:'Fire',2:'Ice',3:'Thunder',4:'Light',5:'Dark'}.get(gauge.get('element'))
        filled=autofill(player,enemy,data.get('field_state'),modes=modes,party=data.get('players',[]))
        from .effect_pending import with_pending,PREVIEW_KEYS
        identity=data.get('run_id') or tuple(p.get('actor_id') for p in data.get('players',[]))
        if getattr(self,'pending_battle',identity)!=identity:self.pending_effects=[]
        self.pending_battle=identity
        self.pending_delta={}
        self.damage_orb_enabled.set(False)
        self.pending_context=(player,enemy,data.get('field_state'),modes,data.get('players',[]))
        self.pending_base=filled
        if self.pending_effects:
            p,e=with_pending(player,enemy,self.pending_effects)
            filled=autofill(p,e,data.get('field_state'),modes=modes,party=data.get('players',[]))
            self.pending_delta={k:filled['values'][k]-self.pending_base['values'][k] for k in PREVIEW_KEYS}
        self.effect_editor.pending_list.delete(0,'end')
        self.effect_editor.load_party(data.get('players',[]),player,enemy,modes)
        self.render_pending()
        filled['notes'].append('模式判断：'+str({k:v for k,v in modes.items() if k!='enemies'})+'；自动依据雷量表、风格资料、强化剩余回合及运行时天赋列表，可手动纠正。')
        if not gauge:filled['skipped'].append('元素量表未读取：超越可手动启用，仍需确认是雷属性风格')
        for k,var in self.values.items():
            v=filled['values'][k];var.set('' if v is None else f'{v:g}')
        for k,var in self.flags.items():var.set(filled['values'][k])
        self.pool.set('auto')
        self.shield_state=enemy.get('enemy_progress',{}).get('shield')
        self.auto_pool_blocked=bool(enemy.get('enemy_progress',{}).get('dp_extra')) and not (
            self.shield_state and self.shield_state.get('limit_per_turn')==1)
        from .shield_layers import shield_text
        if self.shield_state:filled['notes'].append(shield_text(self.shield_state)+'；下一层 DP 容量来自本地资料')
        for k,var in self.params.items():
            v=filled['params'].get(k);var.set('' if v is None else f'{v:g}')
        self.hit_weights.set(', '.join(f'{w:.8g}' for w in filled.get('hit_weights',[])))
        self.hit_source.configure(text=filled.get('hit_note','权重未确认'))
        self.use_destruction.set(filled.get('destruction_ready',False))
        self.hp_adjustments=filled.get('hp_adjustments',{})
        self.use_dp_scaling.set(filled.get('dp_scaling',False))
        self.sp_scaling=filled.get('sp_scaling',False)
        self.sp_dr_scaling.set(False)
        if self.sp_scaling:self.sp_panel.pack(fill='x',pady=8,before=self.skill_title)
        else:self.sp_panel.pack_forget()
        if filled.get('dp_scaling'):self.dp_panel.pack(fill='x',pady=8,before=self.skill_title)
        else:self.dp_panel.pack_forget()
        self.equipment_editor.load(filled.get('equipment_details',[]),filled.get('equipment_owned',[]))
        self.equipment_text.configure(state='normal');self.equipment_text.delete('1.0','end')
        self.equipment_text.insert('end','饰品贡献已计入相应乘区，不需要再次相加。\n按运行时已装备被动匹配；实际状态优先于预填。\n\n'+'\n\n'.join(filled.get('equipment_notes') or ['未读到可确认的饰品效果']))
        self.equipment_text.configure(state='disabled')
        self.filled_chain=filled['values']['chain']
        self.pending_chain_weights=filled.get('chain_weights',[])
        self.show_chain(filled)
        self.use_skill.set(True);self.skill_title.configure(text=filled['skill'])
        self.fill_notes='自动填充来源与假设：\n'+'\n'.join(filled['notes'])+'\n\n未自动计入 / 待核对：\n'+'\n'.join(filled['skipped'])
        self.refresh();self.compute()

    def update_pending(self,action,payload):
        from .effect_pending import targeted_row,with_pending,PREVIEW_KEYS
        if not hasattr(self,'pending_context'):raise ValueError('请先自动填充伤害角色和敌人')
        player,enemy,fields,modes,party=self.pending_context
        rows=list(self.pending_effects)
        if action=='add':
            item,amount=payload
            if item.get('passive') and any(r['item'].get('source')==item.get('source') and r['item'].get('caster')==item.get('caster') and r['item']['part'].get('label')==item['part'].get('label') for r in rows):
                raise ValueError('该来源被动已预添加；请删除后再修改，避免重复计入')
            recipient=next((p for p in party if p.get('actor_id')==item.get('recipient_id')),player)
            row=targeted_row(item,amount,party or [player],modes.get('enemies') or [enemy],recipient,enemy)
            if item.get('part',{}).get('_branch_path') and any(r['item'].get('source')==item.get('source') and
                    r['item']['part'].get('_branch_path')!=item['part']['_branch_path'] for r in rows):
                raise ValueError('同一技能已有另一个条件分支，请先删除再切换场景')
            rows.append(row)
        else:rows.pop(payload)
        p,e=with_pending(player,enemy,rows)
        computed=autofill(p,e,fields,modes=modes,party=party)
        keys=PREVIEW_KEYS
        delta={k:computed['values'][k]-self.pending_base['values'][k] for k in keys}
        # Reconcile only the preview contribution; preserve unrelated manual edits.
        updates={k:float(self.values[k].get())-self.pending_delta.get(k,0)+delta[k] for k in keys}
        for k,v in updates.items():self.values[k].set(f'{v:.10g}')
        self.hp_adjustments=computed.get('hp_adjustments',{})
        beads=computed.get('chain_weights',[])
        chain_changed=(delta['chain']!=self.pending_delta.get('chain',0) or
                       beads!=getattr(self,'pending_chain_weights',self.pending_base.get('chain_weights',[])))
        self.pending_chain_weights=beads
        self.pending_effects=rows;self.pending_delta=delta
        if chain_changed:
            count=int(computed.get('params',{}).get('main_hits') or 0)
            raw=self.hit_weights.get().replace('，',',').replace(' ', ',')
            current=[float(w) for w in raw.split(',') if w.strip()]
            new=computed.get('hit_weights',[])
            weights=current[:count]+beads if count and len(current)>=count else new
            self.hit_weights.set(', '.join(f'{w:.8g}' for w in weights))
            self.filled_chain=computed['values']['chain']
            self.show_chain(dict(computed,hit_weights=weights))
        self.render_pending()
        self.effect_editor.result.configure(text='已按施加对象保存，并重新筛选覆盖；切换角色自动填充后仍保留。当前乘区净变化：'+', '.join(f'{k} {v:+.3f}%' for k,v in delta.items() if v))
        self.compute()

    def render_pending(self):
        self.effect_editor.pending_list.delete(0,'end')
        for row in self.pending_effects:
            amount=f'{row["amount"]:g}%'
            if row['state']['label']=='SpecialStatus.Funnel':amount=f'{row["state"]["values"]["numValue"]} 颗 × '+amount
            self.effect_editor.pending_list.insert('end','、'.join(row.get('target_names',[]))+' ← '+row['item']['title']+' '+amount)

    def show_chain(self,filled):
        from .funnels import describe
        count=filled.get('params',{}).get('main_hits') or 0
        self.chain_expression.set(describe(filled.get('chain_weights',filled.get('hit_weights',[])[int(count):])))
        self.chain_dirty=False

    def compute(self):
        try:
            if self.chain_dirty:
                from .funnels import parse
                beads=parse(self.chain_expression.get())
                self.values['chain'].set(f'{sum(beads)*100:g}')
                raw=self.hit_weights.get().replace('，',',').replace(' ', ',')
                weights=[float(w) for w in raw.split(',') if w.strip()]
                count=int(float(self.params['main_hits'].get() or 0))
                if count>0 and len(weights)>=count:
                    self.hit_weights.set(', '.join(str(w) for w in weights[:count]+beads))
                self.chain_dirty=False
            self.destruction_report.configure(state='normal');self.destruction_report.delete('1.0','end')
            self.destruction_report.configure(state='disabled')
            auto=self.pool.get()=='auto'
            cross=auto
            if auto and getattr(self,'auto_pool_blocked',False):raise ValueError('当前为多层盾，自动跨池尚未支持；可选择单池核对')
            if cross and not self.use_destruction.get():
                raise ValueError('跨 DP/HP 计算需要先启用逐段递推并补齐参数')
            self.equipment_editor.apply({**self.values,**self.params})
            if self.use_dp_scaling.get():
                factor=dp_factor(*(float(self.params[k].get()) for k in ('own_dp','own_dp_max','dp_zero_factor','dp_full_factor')))
                self.values['health_factor'].set(f'{factor:.10g}')
            values={k:float(v.get()) for k,v in self.values.items() if k!='base'}
            base=self.values['base'].get().strip()
            if self.use_skill.get():
                skill_params={k:v.get() for k,v in self.params.items()}
                skill_params['sp_scaling']=self.sp_scaling
                if not self.damage_orb_enabled.get():skill_params['orb']='0'
                computed,weighted=skill_base(skill_params,self.flags['critical'].get())
                base=str(computed);self.values['base'].set(f'{computed:.8g}')
            values.update(base=float(base) if base else None,target_pool=('dp' if float(self.params['enemy_dp'].get())>0 else 'hp') if auto else self.pool.get(),
                          **{k:v.get() for k,v in self.flags.items()})
            inputs=DamageInputs(**values)
            if not cross and inputs.target_pool=='hp' and getattr(self,'hp_adjustments',{}):
                from dataclasses import replace
                inputs=replace(inputs,**{k:getattr(inputs,k)+v for k,v in self.hp_adjustments.items()})
            result=calculate(inputs);detail=None
            if self.use_destruction.get():
                raw=self.hit_weights.get().replace('，',',').replace(' ', ',')
                weights=[float(w) for w in raw.split(',') if w.strip()]
                count=float(self.params['main_hits'].get())
                if not math.isfinite(count) or not count.is_integer():raise ValueError('本体 Hit 数必须为整数')
                args=[float(self.params[k].get()) for k in ('skill_dr','enemy_dr','destruction_bonus','max_dr')]
                if self.sp_scaling and self.sp_dr_scaling.get():
                    from .sp_scaling import sp_factor
                    args[0]*=sp_factor(self.params['sp_consumed'].get(),self.params['sp_cap'].get())
                if cross:
                    hp=self.params['enemy_hp'].get().strip()
                    detail=simulate_pools(inputs,weights,int(count),*args,float(self.params['enemy_dp'].get()),float(hp) if hp else None,
                                          hp_adjustments=getattr(self,'hp_adjustments',{}),shield=getattr(self,'shield_state',None))
                    result.update(damage=detail['damage'],minimum=None,maximum=None,multiplier=None,
                                  note='逐段跨池基准情景；破盾溢出丢弃，不计入 HP。支持已确认的阿蒙锁盾；其他多层盾、动态增减益及伤害衰减未模拟。')
                else:
                    result,detail=apply_to_result(result,inputs,weights,int(count),*args)
                lines=[f"破坏率：{inputs.destruction:g}% → {detail['final']:g}%"]
                lines.append(f"理论增量 {detail['theoretical_increment']:.3f} 个百分点（不计上限终值 {detail['theoretical_final']:.3f}%）\n实际增量 {detail['actual_increment']:.3f} 个百分点 · 被上限截去 {detail['clipped']:.3f} 个百分点")
                if detail.get('segmented'):
                    lines.append(f"DP 扣除 {detail['dp_damage']:,.2f} · HP 扣除 {detail['hp_damage']:,.2f} · 丢弃破盾溢出 {detail['overflow']:,.2f}")
                for row in detail['rows']:
                    if detail.get('segmented'):
                        suffix=f" · {row['pool'].upper()} 原伤害 {row['raw_damage']:,.2f} / 扣除 {row['applied_damage']:,.2f} / 丢弃溢出 {row['overflow']:,.2f}"
                    else:
                        share=(result['damage']*row['damage_weight']/detail['weighted']) if result['damage'] is not None else None
                        suffix=f" · 基准伤害 {share:,.2f}" if share is not None else ''
                    lines.append(f"{row['hit']:>2} {row['kind']} · 破坏率 {row['before']:.3f}% → {row['after']:.3f}% · 理论 +{row['theoretical_increment']:.3f} / 实际 +{row['increment']:.3f} 个百分点"+suffix)
                self.destruction_report.configure(state='normal');self.destruction_report.insert('end','\n'.join(lines));self.destruction_report.configure(state='disabled')
            if values['absorbed']:
                self.plot_data=None;self.draw_plot();self.prob_summary.configure(text='吸收情景不输出伤害概率曲线')
            elif detail and detail.get('segmented'):
                from .pool_probability import pool_distribution
                data=pool_distribution(detail)
                applied_data=data
                if self.damage_metric.get()=='raw':
                    from .raw_probability import raw_distribution
                    data=raw_distribution(detail)
                self.plot_data=data;self.plot_damage=1
                branches='；'.join(('未破盾' if b['hit'] is None else '起始已破盾' if b['hit']==0 else f"第 {b['hit']} 段破盾")+f" {b['probability']:.3%}" for b in applied_data['branches'])
                if data.get('raw'):
                    summary=f"打出伤害：{data['samples']:,} 次固定种子抽样，含破盾及锁盾溢出；击杀后停止后续段。\n平均值抽样标准误约 {data['mean_error']:,.2f}；极小尾部概率不能视为精确值。\n实际扣除均值 {applied_data['mean']:,.2f}\n"+branches
                else:
                    summary=f"破盾分支数值卷积 · 实际扣除均值 {data['mean']:,.4g} · 中央 90%：{data['low']:,.4g} – {data['high']:,.4g}\n"+branches
                if applied_data['kill_probability'] is not None:
                    summary+=f"\n当前模型击杀概率 {applied_data['kill_probability']:.3%}（按实际扣除判断）"
                if data['atoms']:summary+='\n集中概率：'+'；'.join(f'{x:,.4g} 伤害 {p:.3%}' for x,p in data['atoms'])
                self.prob_summary.configure(text=summary);self.draw_plot()
            else:
                self.update_probability(result['damage'],detail['weights'] if detail else None)
                if self.damage_metric.get()=='applied':
                    self.prob_summary.configure(text=self.prob_summary.cget('text')+'\n当前为单池参考计算，仅显示打出伤害；实际扣除量需启用自动跨 DP/HP。')
            text='弱点条件：'+('满足' if result['weak'] else '不满足（不计心眼／脆弱）')+'\n'
            if detail and detail.get('segmented'):text+='跨池各段分别采用 DP/HP 特攻，下面单池乘区仅供参考。\n'
            text+='  ×  '.join(f'{NAMES[k]} {v:.4g}' for k,v in result['factors'].items())+'\n\n'
            if self.use_skill.get():text+=f'敌方属性下降采用最高值：{enemy_attribute_reduction({k:v.get() for k,v in self.params.items()},self.flags["critical"].get()):g} 点\n'
            if result['multiplier'] is not None:text+=f"总倍率：{result['multiplier']:.6g}\n"
            od_gain=self.params['od_gain_bonus'].get().strip()
            if od_gain:
                gain=float(od_gain)
                if not math.isfinite(gain) or gain<0:raise ValueError('OD 获取增幅必须为有限非负数')
                text+=f'OD 饰品获取倍率：×{1+gain/100:g}（例如原获取 20% → {20*(1+gain/100):g}%；不影响伤害）\n'
            if result['damage'] is not None:
                if detail and detail.get('segmented'):
                    text+=f"无浮动基准打出伤害（含溢出）：{detail['raw_damage']:,.2f}\n实际扣除 DP＋HP：{result['damage']:,.2f}\n"
                else:
                    text+=f"未衰减试算伤害：{result['damage']:,.2f}\n"
                if result['minimum'] is not None:
                    text+=f"0.9–1.1 浮动边界：{result['minimum']:,.2f} – {result['maximum']:,.2f}\n"
                    text+='这是理论边界，不表示总伤害在区间内均匀分布；多 Hit 独立浮动通常更集中。\n'
                else:text+='此处为无浮动基准；随机伤害均值、区间和各破盾段概率见浮动概率曲线。\n'
            if detail:text+=f"破坏率递推终值：{detail['final']:g}%（逐段明细见专页）\n"
            else:text+='逐段递推未启用：沿用固定破坏率，请核对逐段破坏率页的缺失参数。\n'
            text+=result['note']+'\n充能暂按参考计算器并入加攻。Token 与血量条件需填技能适用的实际增幅。'
        except (ValueError, OverflowError) as exc:
            text='无法计算：'+str(exc)
            self.plot_data=None;self.draw_plot();self.prob_summary.configure(text=text)
        if self.plot_data:
            data=self.plot_data;scale=self.plot_damage if self.plot_damage is not None else 1
            mean=data['mean'] if data.get('absolute') else self.plot_damage
            title='平均打出伤害（抽样估计）' if data.get('raw') else '平均实际扣除' if data.get('absolute') else '平均打出伤害'
            self.summary.configure(text=(f'{title}  {mean:,.2f}' if mean is not None else '平均伤害  待填写基础伤害')+
                f"\n伤害浮动区间（中央 90%）  {data['low']*scale:,.2f} – {data['high']*scale:,.2f}")
        else:self.summary.configure(text='暂无法生成完整结果：'+self.prob_summary.cget('text'))
        self.result.configure(state='normal');self.result.delete('1.0','end')
        self.result.insert('end',text)
        self.result.configure(state='disabled')

    def refresh(self):
        from .damage_inputs import STATS
        data=self.snapshot()
        self.audit.configure(state='normal');self.audit.delete('1.0','end')
        self.audit.insert('end',audit_text(data.get('players',[])));self.audit.configure(state='disabled')
        lines=[self.fill_notes,'\n已连接战斗' if data.get('connected') else '\n未连接：如有数据，属于保留快照']
        for player in data.get('players',[]):
            inputs=player.get('inputs',player.get('combat_inputs',{}));skill=inputs.get('selected_skill',{})
            lines.append('\n'+str(player.get('name') or '角色')+' · '+str(skill.get('name') or '预选未读到'))
            lines.append(' / '.join(f'{STATS[k]} {v}' for k,v in inputs.get('stats',{}).items()))
            lines.append('Token：'+str(inputs.get('token','未读到')))
        for enemy in data.get('enemies',[]):
            inputs=enemy.get('inputs',enemy.get('combat_inputs',{}))
            lines.append('\n'+str(enemy.get('name') or '敌人')+
                         ' · 边界参考 '+str(inputs.get('_borderRefParam','未读到'))+
                         ' / 防御参考 '+str(inputs.get('_defenseRefParam','未读到')))
        lines.append('\n以下为技能威力、偏向权重及条件原始参数（未自动代入）：\n')
        self.raw.configure(state='normal');self.raw.delete('1.0','end')
        self.raw.insert('end','\n'.join(lines)+json.dumps(data,ensure_ascii=False,indent=2));self.raw.configure(state='disabled')
