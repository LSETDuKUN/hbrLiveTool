"""Presentation groups only: never add incompatible effect values together."""
import tkinter as tk
from copy import deepcopy

from . import theme
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
        for child in self.winfo_children():child.destroy()
        groups, other = group_statuses(self.state)
        if not self.state.get('statuses_available'):
            self.row('状态暂不可读', theme.MUTED)
            if self.enemy:self.base_resistances()
            return
        shown = False
        for key,title,color in group_list():
            items = groups[key]
            if not items:continue
            shown = True
            block = tk.Frame(self,bg=group_backgrounds()[key])
            block.pack(fill='x',pady=3)
            accent = tk.Frame(block,bg=color,width=3)
            accent.pack(side='left',fill='y')
            body = tk.Frame(block,bg=group_backgrounds()[key])
            body.pack(side='left',fill='x',expand=True,padx=(10,8),pady=7)
            self.row(title, color, bold=True, parent=body)
            # Each applied effect remains separate, including different durations.
            for status in items:
                self.status_row(status, body)
        if not shown:
            self.row('主要乘区暂无已确认状态', theme.MUTED)
        if self.enemy:
            self.base_resistances()
        if other:
            tk.Button(self,text=('▾' if self.expanded else '▸')+f' 暂被覆盖 / 其他效果 · {len(other)} 项',
                command=self.toggle,bg=self.cget('bg'),fg=theme.DIM,relief='flat',anchor='w',
                activebackground=self.cget('bg'),activeforeground=theme.FG,font=theme.ui(11)).pack(fill='x',pady=3)
            if self.expanded:
                for status in other:
                    self.status_row(status, self, muted=True)

    def status_row(self, status, parent, muted=False):
        line=tk.Frame(parent,bg=parent.cget('bg'))
        line.pack(fill='x',pady=1)
        badge=element_badge(status)
        if badge:
            name,fg,bg=badge
            tag=tk.Label(line,text=name,bg=bg,fg=fg,font=theme.ui(10,'bold'),
                         padx=5,pady=1,highlightthickness=1,highlightbackground=fg,cursor='hand2')
            tag.pack(side='left',anchor='n',padx=(0,5),pady=2)
            tag.bind('<Button-1>',lambda e:self.details(status))
        body=tk.Frame(line,bg=line.cget('bg'))
        body.pack(side='left',fill='x',expand=True)
        self.row(effect_line(status),theme.MUTED if muted else theme.FG,
                 callback=lambda:self.details(status),parent=body)

    def toggle(self):
        self.expanded = not self.expanded
        self.draw()

    def base_resistances(self):
        from .resistances import resistance_lines
        block=tk.Frame(self,bg=group_backgrounds()['resist'])
        block.pack(fill='x',pady=3)
        accent=tk.Frame(block,bg=theme.LAVENDER,width=3)
        accent.pack(side='left',fill='y')
        body=tk.Frame(block,bg=group_backgrounds()['resist'])
        body.pack(side='left',fill='x',expand=True,padx=(10,8),pady=7)
        self.row('抗性 · 弱点参考', theme.LAVENDER, bold=True, parent=body)
        for text in resistance_lines(self.state):self.row(text, theme.FG, parent=body)

    def row(self,text,color,bold=False,callback=None,parent=None):
        parent = self if parent is None else parent
        label=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,anchor='w',justify='left',wraplength=250,
            font=theme.ui(11,'bold' if bold else 'normal'),cursor='hand2' if callback else '')
        label.pack(fill='x',padx=2,pady=(4 if bold else 1,1))
        label.bind('<Configure>',lambda e:label.configure(wraplength=max(80,e.width-8)))
        if callback:label.bind('<Button-1>',lambda e:callback())
