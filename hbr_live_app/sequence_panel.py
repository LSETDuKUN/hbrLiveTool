"""Three explicit skill steps with visible resource carry-over."""
import tkinter as tk
from . import theme
from .components import RoundedButton


class SequencePanel(tk.Frame):
    def __init__(self,parent,command):
        super().__init__(parent,bg=theme.CARD,padx=10,pady=8)
        tk.Label(self,text='连续伤害预演 · 最多三人 / 同一敌人',bg=theme.CARD,fg=theme.CYAN,
                 font=theme.ui(11,'bold')).pack(anchor='w')
        tk.Label(self,text='按无浮动基准继承 DP、HP、破坏率和锁盾；暂不自动消费 Buff 或施加技能附带效果。',
                 bg=theme.CARD,fg=theme.DIM,font=theme.ui(10),wraplength=800,justify='left').pack(anchor='w')
        bar=tk.Frame(self,bg=theme.CARD);bar.pack(fill='x',pady=5)
        for action,title in [('add','预添加当前技能结果'),('undo','撤销最后一步'),('clear','清空本轮预演及效果')]:
            RoundedButton(bar,title,lambda a=action:command(a),theme.CARD_HI,theme.FG,height=30).pack(side='left',padx=3)
        self.text=tk.Label(self,text='',bg=theme.CARD,fg=theme.FG,font=theme.ui(10),justify='left',anchor='w')
        self.text.pack(fill='x');self.text.bind('<Configure>',lambda e:self.text.configure(wraplength=max(200,e.width-8)))
        self.message=tk.Label(self,text='',bg=theme.CARD,fg=theme.GOLD,font=theme.ui(10),justify='left',anchor='w')
        self.message.pack(fill='x');self.message.bind('<Configure>',lambda e:self.message.configure(wraplength=max(200,e.width-8)))

    def update_sequence(self,sequence):
        lines=[]
        for i,step in enumerate(sequence.steps,1):
            before,after=step['before'],step['after']
            lines.append(f'{i}. {step["actor"]} · {step["skill"]}：打出 {step["raw_damage"]:,.0f} / 扣除 {step["damage"]:,.0f}\n'
                f'    DP {before["dp"]:,.0f} → {after["dp"]:,.0f} · HP {before["hp"]:,.0f} → {after["hp"]:,.0f} · 破坏率 {before["rate"]:g}% → {after["rate"]:g}%')
        if lines:
            lines.append(f'累计打出 {sum(s["raw_damage"] for s in sequence.steps):,.0f} / 实际扣除 {sum(s["damage"] for s in sequence.steps):,.0f}')
        self.text.configure(text='\n'.join(lines) or '尚未添加。先自动填充第一位角色、核对试算，再预添加结果。')
