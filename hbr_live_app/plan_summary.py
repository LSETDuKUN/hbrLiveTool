"""Compact roster summary above the planned action table."""
import tkinter as tk
from . import theme
from .history import skill_summary,summary_text,actor_title
from .portraits import Portraits


class PlanSummary(tk.Frame):
    def __init__(self,parent):
        super().__init__(parent,bg=theme.BG)
        self.portraits=Portraits(self)
        self.previous=None

    def update_events(self,events):
        summary=skill_summary(events)
        if self.previous==summary:return
        self.previous=summary
        for child in self.winfo_children():child.destroy()
        tk.Label(self,text='计划技能汇总 · 本场计划使用的技能',
                 bg=theme.BG,fg=theme.DIM,font=theme.ui(10)).pack(anchor='w')
        canvas=tk.Canvas(self,height=100,bg=theme.BG,highlightthickness=0)
        canvas.pack(fill='x')
        bar=tk.Scrollbar(self,orient='horizontal',command=canvas.xview)
        bar.pack(fill='x');canvas.configure(xscrollcommand=bar.set)
        body=tk.Frame(canvas,bg=theme.BG);canvas.create_window(0,0,window=body,anchor='nw')
        for actor in summary:
            card=tk.Frame(body,bg=theme.CARD,padx=8,pady=7);card.pack(side='left',padx=3,anchor='n')
            photo=self.portraits.get(actor.get('style_label'))
            tk.Label(card,image=photo,text='' if photo else actor_title(actor),bg=theme.CARD,
                     fg=theme.FG,font=theme.ui(10),wraplength=80).pack(side='left',padx=(0,7))
            skills=tk.Frame(card,bg=theme.CARD);skills.pack(side='left')
            labels=[s['name']+(' · 小按钮' if s['instant'] else '') for s in actor['skills']]
            if actor['unknown']:labels.append('预选未读到')
            for i,label in enumerate(labels):
                tk.Label(skills,text=label,bg=theme.GOLD_DEEP,fg=theme.GOLD,font=theme.ui(10),
                         padx=8,pady=5,highlightthickness=1,highlightbackground=theme.LINE,
                         wraplength=180).grid(row=i//2,column=i%2,padx=3,pady=3,sticky='w')
        body.bind('<Configure>',lambda e:canvas.configure(scrollregion=canvas.bbox('all'),height=max(80,e.height)))
