"""Presentation groups only: never add incompatible effect values together."""
import tkinter as tk
from copy import deepcopy

from . import theme
from .components import RoundedCard
from .statuses import status_line
from .status_rules import active

def group_list():
    """Resolved per draw so a palette switch is picked up immediately."""
    return (
        ('boost', '加攻 · 心眼', theme.PINK),
        ('funnel', '连击珠', theme.CYAN),
        ('charge', '充能 / 蓄力', theme.MINT),
        ('critical', '暴击 · 爆伤', theme.GOLD),
        ('debuff', '减防 · 脆弱', theme.ROSE),
        ('resist', '抗性 · 弱点', theme.LAVENDER),
        ('negative', '其他已识别减益', theme.ROSE))


def group_backgrounds():
    return dict(boost=theme.PINK_DEEP, funnel=theme.CYAN_DEEP, charge=theme.MINT_DEEP,
                critical=theme.GOLD_DEEP, debuff=theme.ROSE_DEEP, resist=theme.LAVENDER_DEEP,
                negative=theme.NEUTRAL_DEEP)
KINDS = {
    'boost': {'AttackUp','AttackUpIncludeNormal','AttackUpOnlyNormal','MindEye','BIYamawakiServant'},
    'funnel': {'Funnel'},
    'charge': {'BuffCharge'},
    'critical': {'CriticalRateUp','CriticalDamageUp','CriticalRateDown','CriticalDamageDown'},
    'debuff': {'DefenseDown','Fragile'},
    'resist': {'ResistUp','ResistDown','ResistDownOverwrite'},
    'negative': {'AttackDown','ConfusionRandom','StunRandom','SuperStun','Misfortune',
                 'ImprisonRandom','BindRandom','VirusRandom','IllusionRandom','Fatigue','Restraint','RestraintRandom','FearOfDevil'}}

# Explicit text plus contrasting outline stays readable in both palettes.
ELEMENT_BADGES = {
    'Fire': ('火', '#a82e38', '#ffe2df'),
    'Thunder': ('雷', '#755300', '#fff0ad'),
    'Ice': ('冰', '#215ca0', '#dceeff'),
    'Dark': ('暗', '#ece5fa', '#302a3e'),
    'Light': ('光', '#5d5239', '#fffdf2'),
}


def element_badge(status):
    key=status.get('element_key') or {1:'Fire',2:'Ice',3:'Thunder',4:'Light',5:'Dark'}.get(status.get('element_type'))
    return ELEMENT_BADGES.get(key)


def group_statuses(state):
    groups = {key: [] for key,_,_ in group_list()}
    other = []
    for status in state.get('statuses', []):
        kind = status.get('label','').removeprefix('SpecialStatus.')
        key = next((key for key, kinds in KINDS.items() if kind in kinds), None)
        if key and active(status) and not status.get('hidden'):
            groups[key].append(status)
        else:
            other.append(status)
    return groups, other


def effect_line(status):
    text = status_line(status)
    if status.get('buff_limit_type')==4 or status.get('source_effect',{}).get('effect',{}).get('limitType')=='Only':
        text+='【单独发动】'
    if status.get('label')=='SpecialStatus.ResistDown' and status.get('values',{}).get('rateValueInt',0)<0:
        text=text.replace('抗性降低','弱点加深 / 抗性降低')
    if not status.get('value'):
        text += ' · 数值未确认'
    element = status.get('element_type')
    if status.get('element_name'):
        text = status['element_name']+'属性 · '+text
    elif element is not None:
        text = ({0:'普通',1:'火属性',2:'冰属性',3:'雷属性',4:'光属性',5:'暗属性'}.get(element, f'属性 #{element}'))+' · '+text
    duration = status.get('duration','')
    if duration:
        text += ' · '+duration.replace('（消耗规则待核实）','')
    if status.get('effective') is False:
        text += (' · 暂被覆盖（规则推断）' if status.get('effective_basis') in ('attack_only_rule','debuff_top_two_rule')
                 else ' · 不重复计入（规则筛选）')
    return text


class StatusGroups(tk.Frame):
    def __init__(self, parent, details, enemy=False):
        super().__init__(parent, bg=parent.cget('bg'))
        self.details = details
        self.enemy = enemy
        self.previous = None
        self.expanded = False

    def update_state(self, state):
        value = (state.get('statuses_available'),state.get('statuses',[]),state.get('base_resistances'))
        self.state = state
        if self.previous == value:
            return
        self.previous = deepcopy(value)
        self.draw()

    def draw(self):
        for child in self.winfo_children():
            child.destroy()
        groups, other = group_statuses(self.state)
        if not self.state.get('statuses_available'):
            self.row('状态暂不可读', theme.MUTED)
            if self.enemy:
                self.base_resistances()
            return
        shown = False
        for key, title, color in group_list():
            items = groups[key]
            if not items:
                continue
            shown = True
            self.group_block(title, color, items)
        if not shown:
            self.row('主要乘区暂无已确认状态', theme.MUTED)
        if self.enemy:
            self.base_resistances()
        if other:
            arrow = '▾' if self.expanded else '▸'
            toggle = tk.Label(self, text=f'{arrow}  暂被覆盖 / 其他效果 · {len(other)} 项',
                              bg=theme.mix(theme.SURFACE, theme.LINE, .45), fg=theme.DIM,
                              font=theme.ui(11, 'bold'), anchor='w', padx=10, pady=6,
                              cursor='hand2')
            toggle.pack(fill='x', pady=(6, 3))
            toggle.bind('<Button-1>', lambda e: self.toggle())
            if self.expanded:
                for status in other:
                    self.status_row(status, self, muted=True, background=self.cget('bg'))

    def group_block(self, title, color, items, note=None):
        tint = theme.mix(theme.CARD, color, .11)
        card = RoundedCard(self, background=tint, outline='', radius=14,
                           pad=(12, 9), shadow=False)
        card.pack(fill='x', pady=(0, 6))
        block = card.content
        head = tk.Frame(block, bg=tint)
        head.pack(fill='x', pady=(0, 6))
        dot = tk.Canvas(head, width=9, height=9, bg=tint, highlightthickness=0, bd=0)
        dot.pack(side='left', padx=(0, 7))
        dot.create_oval(1, 1, 8, 8, fill=color, outline='')
        tk.Label(head, text=title, bg=tint, fg=color,
                 font=theme.ui(11, 'bold')).pack(side='left')
        tk.Label(head, text=str(len(items)), bg=tint,
                 fg=theme.mix(color, theme.CARD, .45),
                 font=theme.ui(10)).pack(side='left', padx=(6, 0))
        sources = [item.get('source_name') or item.get('source') or '未确认' for item in items]
        shared = sources[0] if sources and len(set(sources)) == 1 else None
        if shared:
            tk.Label(head, text='来源：' + shared, bg=tint, fg=theme.MUTED,
                     font=theme.ui(9)).pack(side='right', padx=(0, 10))
        for index, status in enumerate(items):
            if index:
                tk.Frame(block, bg=theme.mix(tint, theme.LINE, .45),
                         height=1).pack(fill='x', pady=5)
            self.status_row(status, block, background=tint, color=color,
                            show_source=shared is None)

    def status_row(self, status, parent, muted=False, background=None, color=None,
                   show_source=True):
        bg = background or parent.cget('bg')
        accent = color or theme.LAVENDER
        tile = tk.Frame(parent, bg=bg, cursor='hand2')
        tile.pack(fill='x')
        tile.columnconfigure(1, weight=1)
        tile.columnconfigure(3, minsize=theme.px(52))
        badge = element_badge(status)
        name = status.get('name') or '未知状态'
        if status.get('label') == 'SpecialStatus.ResistDown' and status.get('values', {}).get('rateValueInt', 0) < 0:
            name = '弱点加深 / ' + name
        if badge:
            marker = tk.Label(tile, text=badge[0], bg=badge[2], fg=badge[1],
                              font=theme.ui(9, 'bold'), padx=3, pady=0, cursor='hand2')
            marker.grid(row=0, column=0, sticky='w', padx=(0, 8))
        else:
            marker = tk.Canvas(tile, width=7, height=14, bg=bg, highlightthickness=0,
                               bd=0, cursor='hand2')
            marker.grid(row=0, column=0, sticky='w', padx=(0, 8))
            marker.create_oval(1, 4, 7, 10, fill=accent, outline='')
        name_fg = theme.MUTED if muted else theme.FG
        label = tk.Label(tile, text=name, fg=name_fg, bg=bg, anchor='w', justify='left',
                         wraplength=180, font=theme.ui(11, 'bold'), cursor='hand2')
        label.grid(row=0, column=1, sticky='ew')
        label.bind('<Configure>', lambda e: label.configure(wraplength=max(60, e.width - 4)))
        value = tk.Label(tile, text=status.get('value') or '数值未确认', bg=bg,
                         fg=theme.MUTED if muted else theme.mix(color or theme.CYAN, theme.FG, .15),
                         font=theme.ui(11, 'bold'), anchor='e', cursor='hand2')
        value.grid(row=0, column=2, sticky='e', padx=(10, 8))
        duration = (status.get('duration') or '').replace('（消耗规则待核实）', '')
        if duration:
            chip = tk.Label(tile, text=duration.replace('回合', ' 回合'), bg=theme.mix(theme.CARD, accent, .18),
                            fg=theme.mix(accent, theme.FG, .45), font=theme.ui(9),
                            padx=6, pady=1, cursor='hand2')
            chip.grid(row=0, column=3, sticky='e')
        tags = []
        if status.get('buff_limit_type') == 4 or status.get('source_effect', {}).get('effect', {}).get('limitType') == 'Only':
            tags.append('单独发动')
        if status.get('pending_add'):
            tags.append('预添加')
        if status.get('pending_remove'):
            tags.append('预移除')
        if status.get('effective') is False:
            tags.append('暂未计入')
        meta = list(tags)
        if show_source and not muted:
            meta.append('来源：' + (status.get('source_name') or status.get('source') or '未确认'))
        if meta:
            foot = tk.Label(tile, text=' · '.join(meta), bg=bg,
                            fg=theme.mix(theme.MUTED, accent, .35), anchor='w',
                            justify='left', font=theme.ui(9), cursor='hand2')
            foot.grid(row=1, column=1, columnspan=3, sticky='ew', pady=(2, 0))
        for widget in (tile, marker, label, value, foot if meta else None):
            if widget is not None:
                widget.bind('<Button-1>', lambda e, s=status: self.details(s))

    def toggle(self):
        self.expanded = not self.expanded
        self.draw()

    def base_resistances(self):
        from .resistances import resistance_lines
        color = theme.LAVENDER
        tint = theme.mix(theme.CARD, color, .11)
        card = RoundedCard(self, background=tint, outline='', radius=14,
                           pad=(12, 9), shadow=False)
        card.pack(fill='x', pady=(0, 6))
        body = card.content
        head = tk.Frame(body, bg=tint)
        head.pack(fill='x', pady=(0, 6))
        dot = tk.Canvas(head, width=9, height=9, bg=tint, highlightthickness=0, bd=0)
        dot.pack(side='left', padx=(0, 7))
        dot.create_oval(1, 1, 8, 8, fill=color, outline='')
        tk.Label(head, text='抗性 · 弱点参考', bg=tint, fg=color,
                 font=theme.ui(11, 'bold')).pack(side='left')
        for text in resistance_lines(self.state):
            self.row(text, theme.FG, parent=body)

    def row(self,text,color,bold=False,callback=None,parent=None):
        parent = self if parent is None else parent
        label=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,anchor='w',justify='left',wraplength=250,
            font=theme.ui(11,'bold' if bold else 'normal'),cursor='hand2' if callback else '')
        label.pack(fill='x',padx=2,pady=(4 if bold else 1,1))
        label.bind('<Configure>',lambda e:label.configure(wraplength=max(80,e.width-8)))
        if callback:label.bind('<Button-1>',lambda e:callback())
