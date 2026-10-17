"""Presentation groups only: never add incompatible effect values together."""
import tkinter as tk
from .statuses import status_line

GROUPS = (
    ('boost', '加攻 · 心眼', '#f5aacb'),
    ('funnel', '连击珠', '#83e5ed'),
    ('charge', '充能 / 蓄力', '#a5e9b4'),
    ('critical', '暴击 · 爆伤', '#ffd398'),
    ('debuff', '减防 · 脆弱', '#e9a5b8'),
    ('resist', '抗性 · 弱点', '#b8b0f3'),
    ('negative', '其他已识别减益', '#eda49e'))
BACKGROUNDS = dict(boost='#493448', funnel='#253f46', charge='#2d4438', critical='#493f2d',
                   debuff='#493039', resist='#38324f', negative='#47342f')
KINDS = {
    'boost': {'AttackUp','AttackUpIncludeNormal','AttackUpOnlyNormal','MindEye'},
    'funnel': {'Funnel'},
    'charge': {'BuffCharge'},
    'critical': {'CriticalRateUp','CriticalDamageUp','CriticalRateDown','CriticalDamageDown'},
    'debuff': {'DefenseDown','Fragile'},
    'resist': {'ResistUp','ResistDown','ResistDownOverwrite'},
    'negative': {'AttackDown','ConfusionRandom','StunRandom','SuperStun','Misfortune',
                 'ImprisonRandom','BindRandom','VirusRandom','IllusionRandom','Fatigue','Restraint','RestraintRandom'}}


def group_statuses(state):
    groups = {key: [] for key,_,_ in GROUPS}
    other = []
    for status in state.get('statuses', []):
        kind = status.get('label','').removeprefix('SpecialStatus.')
        key = next((key for key, kinds in KINDS.items() if kind in kinds), None)
        if key and status.get('effective') is not False and not status.get('hidden') and not status.get('pending_add') and not status.get('pending_remove'):
            groups[key].append(status)
        else:
            other.append(status)
    return groups, other


def effect_line(status):
    text = status_line(status)
    if status.get('label')=='SpecialStatus.ResistDown' and status.get('values',{}).get('rateValueInt',0)<0:
        text=text.replace('抗性降低','弱点加深 / 抗性降低')
    if not status.get('value'):
        text += ' · 数值未确认'
    element = status.get('element_type')
    if status.get('element_name'):
        text = status['element_name']+'属性 · '+text
    elif element is not None:
        text = ({0:'普通',3:'雷属性'}.get(element, f'属性 #{element}'))+' · '+text
    duration = status.get('duration','')
    if duration:
        text += ' · '+duration.replace('（消耗规则待核实）','')
    if status.get('effective') is False:
        text += (' · 暂被覆盖（规则推断）' if status.get('effective_basis') == 'attack_only_rule'
                 else ' · 不重复计入（规则筛选）')
    return text


class StatusGroups(tk.Frame):
    def __init__(self, parent, details, enemy=False):
        super().__init__(parent,bg='#302b46')
        self.details = details
        self.enemy = enemy
        self.previous = None
        self.expanded = False

    def update_state(self, state):
        value = (state.get('statuses_available'),state.get('statuses',[]),state.get('base_resistances'))
        self.state = state
        if self.previous == value:
            return
        self.previous = value
        self.draw()

    def draw(self):
        for child in self.winfo_children():child.destroy()
        groups, other = group_statuses(self.state)
        if not self.state.get('statuses_available'):
            self.row('状态暂不可读', '#bdb1d4')
            if self.enemy:self.base_resistances()
            return
        shown = False
        for key,title,color in GROUPS:
            items = groups[key]
            if not items:continue
            shown = True
            block = tk.Frame(self,bg=BACKGROUNDS[key],padx=6,pady=5)
            block.pack(fill='x',pady=3)
            self.row(title, color, bold=True, parent=block)
            # Each applied effect remains separate, including different durations.
            for status in items:
                self.row(effect_line(status), '#f7f0ff', callback=lambda s=status:self.details(s), parent=block)
        if not shown:
            self.row('主要乘区暂无已确认状态', '#bdb1d4')
        if self.enemy:
            self.base_resistances()
        if other:
            tk.Button(self,text=('▾' if self.expanded else '▸')+f' 暂被覆盖 / 其他效果 · {len(other)} 项',
                command=self.toggle,bg='#302b46',fg='#bdb1d4',relief='flat',anchor='w').pack(fill='x',pady=3)
            if self.expanded:
                for status in other:
                    self.row(effect_line(status), '#bdb1d4', callback=lambda s=status:self.details(s))

    def toggle(self):
        self.expanded = not self.expanded
        self.draw()

    def base_resistances(self):
        from .resistances import resistance_lines
        block=tk.Frame(self,bg=BACKGROUNDS['resist'],padx=6,pady=5)
        block.pack(fill='x',pady=3)
        self.row('抗性 · 弱点参考', '#b8b0f3',bold=True,parent=block)
        for text in resistance_lines(self.state):self.row(text,'#f7f0ff',parent=block)

    def row(self,text,color,bold=False,callback=None,parent=None):
        parent = self if parent is None else parent
        label=tk.Label(parent,text=text,bg=parent.cget('bg'),fg=color,anchor='w',justify='left',wraplength=250,
            font=('Microsoft YaHei UI',-12,'bold' if bold else 'normal'),cursor='hand2' if callback else '')
        label.pack(fill='x',padx=4,pady=(4 if bold else 1,1))
        label.bind('<Configure>',lambda e:label.configure(wraplength=max(80,e.width-8)))
        if callback:label.bind('<Button-1>',lambda e:callback())
