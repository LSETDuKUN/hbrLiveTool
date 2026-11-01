"""Editable effect preview using the shared dashboard theme."""
import tkinter as tk
from tkinter import ttk
from dataclasses import asdict
from . import theme
from .components import RoundedCard, RoundedButton, RoundedEntry, RoundedSelect, ToggleChip
from .effect_math import EffectInputs, calculate_effect
from .effect_preview import proposals, KINDS

FIELDS=(('效果基础', (('minimum','一级下限 / 固定量 %'),('maximum','一级上限 %'),('threshold','满额差值'),
                   ('level','技能等级'),('growth_min','下限每级成长（0.05=5%）'),('growth_max','上限每级成长'))),
        ('属性与增强', (('attribute','施加者加权属性（含士气）'),('enemy','敌方属性（原值）'),('reduction','灾厄属性降低（不含暴击）'),
                     ('orb','宝珠等级（确认适用后填写）'),('enhancement','适用效果量提升合计 %'),('over_rate','超差每点系数'))))


class EffectEditor(tk.Frame):
    def __init__(self,parent,on_pending=None):
        super().__init__(parent,bg=theme.BG)
        self.items=[];self.values={};self.kind=tk.StringVar(self,value='buff')
        self.on_pending=on_pending
        self.orb_enabled=tk.BooleanVar(self,value=False)
        self.orb_level=tk.StringVar(self,value='5')
        tk.Label(self,text='效果试算 · 按技能对象预添加；切换角色保留，删除可撤销（仅试算，不修改实时状态）',bg=theme.BG,fg=theme.DIM,
                 font=theme.ui(12)).pack(anchor='w',pady=8)
        self.caster_box=RoundedSelect(self,values=(),width=theme.px(260))
        self.caster_box.pack(anchor='w',pady=4)
        self.caster_box.bind('<<ComboboxSelected>>',self.change_caster)
        self.target_note=tk.Label(self,text='',bg=theme.BG,fg=theme.CYAN,anchor='w',font=theme.ui(10))
        self.target_note.pack(fill='x')
        self.recipient_box=RoundedSelect(self,values=(),width=theme.px(300))
        self.recipient_box.pack(anchor='w',pady=4)
        self.funnel_count=tk.StringVar(self,value='3')
        self.funnel_row=tk.Frame(self,bg=theme.BG)
        tk.Label(self.funnel_row,text='连击珠颗数（效果量为每颗 %）',bg=theme.BG,fg=theme.DIM).pack(side='left')
        RoundedEntry(self.funnel_row,textvariable=self.funnel_count,width=80).pack(side='left')
        self.selector=RoundedSelect(self,values=(),width=theme.px(520))
        self.selector.pack(anchor='w',pady=8);self.selector.bind('<<ComboboxSelected>>',self.choose)
        self.overview=tk.Label(self,text='',bg=theme.BG,fg=theme.DIM,justify='left',anchor='w',font=theme.ui(10))
        self.overview.pack(fill='x',pady=4)
        self.overview.bind('<Configure>',lambda e:self.overview.configure(wraplength=max(200,e.width-8)))
        row=tk.Frame(self,bg=theme.BG);row.pack(fill='x',pady=8)
        tk.Label(row,text='公式类型',bg=theme.BG,fg=theme.DIM,font=theme.ui(11)).pack(side='left')
        RoundedSelect(row,textvariable=self.kind,values=['buff','debuff','fixed'],
                      width=theme.px(120),height=theme.px(32)).pack(side='left',padx=8)
        tk.Label(row,text='buff 增益 / debuff 减益 / fixed 固定值',bg=theme.BG,fg=theme.DIM).pack(side='left')
        RoundedButton(row,'计算效果量',self.compute,theme.PINK_FILL,theme.on_fill,height=32).pack(side='right')
        grid=tk.Frame(self,bg=theme.BG);grid.pack(fill='x')
        defaults=asdict(EffectInputs())
        for col,(title,fields) in enumerate(FIELDS):
            grid.columnconfigure(col,weight=1,uniform='effect')
            card=RoundedCard(grid,background=theme.CARD,outline=theme.LINE,accent=theme.CYAN if col else theme.PINK,
                             pad=(14,12),stretch=True)
            card.grid(row=0,column=col,sticky='nsew',padx=5,pady=5);body=card.content
            body.columnconfigure(1,weight=1)
            tk.Label(body,text=title,bg=theme.CARD,fg=theme.FG,font=theme.ui(12,'bold')).grid(row=0,column=0,sticky='w')
            for n,(key,title) in enumerate(fields,1):
                tk.Label(body,text=title,bg=theme.CARD,fg=theme.DIM,font=theme.ui(10)).grid(row=n,column=0,sticky='w',pady=5)
                var=tk.StringVar(self,value=str(defaults[key]));self.values[key]=var
                if key=='orb':
                    controls=tk.Frame(body,bg=theme.CARD);controls.grid(row=n,column=1,sticky='e')
                    ToggleChip(controls,text='启用',variable=self.orb_enabled,accent=theme.MINT,
                               height=theme.px(28),command=self.compute).pack(side='left',padx=(0,6))
                    RoundedSelect(controls,textvariable=self.orb_level,values=['1','2','3','4','5'],
                                  width=theme.px(64),height=theme.px(28)).pack(side='left')
                    self.orb_level.trace_add('write',lambda *_:self.compute() if hasattr(self,'result') else None)
                else:
                    RoundedEntry(body,textvariable=var,width=theme.px(124)).grid(row=n,column=1,sticky='e',padx=5)
        self.result=tk.Label(self,text='选择效果，或手动输入参数。',bg=theme.BG,fg=theme.CYAN,
                             font=theme.ui(12,'bold'),anchor='w',justify='left')
        self.result.pack(fill='x',pady=12)
        actions=tk.Frame(self,bg=theme.BG);actions.pack(fill='x');self.actions=actions
        RoundedButton(actions,'预添加当前效果',self.add_pending,theme.PINK_FILL,theme.on_fill,height=32).pack(side='left')
        RoundedButton(actions,'删除所选预添加',self.remove_pending,theme.CARD,theme.FG,height=32).pack(side='left',padx=8)
        self.pending_list=tk.Listbox(self,height=4,bg=theme.CARD,fg=theme.FG,exportselection=False,
                                     relief='flat',borderwidth=0,highlightthickness=1,
                                     highlightbackground=theme.LINE,highlightcolor=theme.PINK,
                                     selectbackground=theme.mix(theme.CARD,theme.PINK,.35),
                                     selectforeground=theme.FG,font=theme.ui(11),activestyle='none')
        self.pending_list.pack(fill='x',pady=6)
        self.notes=tk.Text(self,height=15,wrap='word',bg=theme.CARD,fg=theme.DIM,relief='flat',font=theme.ui(10),padx=12,pady=12)
        self.notes.pack(fill='both',expand=True,pady=8)
        self.set_notes('点击顶部“自动填充”读取预选技能与已持有被动。效果量提升范围未确认时，请人工核对；场地和固定被动不默认增强。')

    def set_notes(self,text):
        self.notes.configure(state='normal');self.notes.delete('1.0','end');self.notes.insert('end',text);self.notes.configure(state='disabled')

    def load_party(self,party,player,enemy,modes):
        self.party=party or [player];self.enemy=enemy;self.modes=modes
        self.target_note.configure(text='群体效果按预添加时的站位分配；自身效果给施加者。单体增益请选择下方受益者。')
        self.recipient_box.configure(values=['单体受益者：'+str(p.get('actor') or p.get('name') or p.get('actor_id')) for p in self.party])
        self.recipient_box.current(next((i for i,p in enumerate(self.party) if p.get('actor_id')==player.get('actor_id')),0))
        self.caster_box.configure(values=['施加者：'+str(p.get('actor') or p.get('name') or p.get('actor_id')) for p in self.party])
        self.caster_box.current(next((i for i,p in enumerate(self.party) if p.get('actor_id')==player.get('actor_id')),0))
        self.load(player,enemy,modes)

    def change_caster(self,event=None):
        i=self.caster_box.current()
        if i>=0:self.load(self.party[i],self.enemy,self.modes)

    def add_pending(self):
        try:
            index=self.selector.current()
            if not 0<=index<len(self.items):raise ValueError('请先选择技能效果')
            item=dict(self.items[index])
            if item['part'].get('skill_type')=='Funnel':item['funnel_count']=float(self.funnel_count.get())
            i=self.recipient_box.current()
            if i>=0:item['recipient_id']=self.party[i].get('actor_id')
            if self.on_pending:self.on_pending('add',(item,self.calculate()['final']))
        except (ValueError,TypeError) as exc:self.result.configure(text=str(exc))

    def remove_pending(self):
        selected=self.pending_list.curselection()
        try:
            if selected and self.on_pending:self.on_pending('remove',selected[0])
        except (ValueError,TypeError) as exc:self.result.configure(text=str(exc))

    def calculate(self):
        self.values['orb'].set(self.orb_level.get() if self.orb_enabled.get() else '0')
        return calculate_effect(EffectInputs(kind=self.kind.get(),**{k:float(v.get()) for k,v in self.values.items()}))

    def load(self,player,enemy,modes):
        self.orb_enabled.set(False);self.orb_level.set('5')
        from .damage_autofill import style_elements
        modes=dict(modes,lightning_style='Thunder' in style_elements(player.get('style_label','')))
        self.items=proposals(player,enemy,modes)
        self.selector.configure(values=[item['title'] for item in self.items])
        summaries=[]
        for item in self.items:
            try:amount=f'{calculate_effect(EffectInputs(**item["values"]))["final"]:.3f}%'
            except (ValueError,TypeError,OverflowError):amount='参数待补齐'
            summaries.append(item['title']+' → '+amount)
        from .damage_autofill import catalog_skill
        from hbr_data.skill_tree import effects
        selected=player.get('combat_inputs',player.get('inputs',{})).get('selected_skill',{})
        skill=catalog_skill(selected['label']) if selected.get('label') else {}
        for part in effects(skill,modes):
            if part.get('skill_type') not in KINDS:
                summaries.append('其他效果：'+str(part.get('skill_type'))+' / '+str(part.get('label'))+
                    ' / '+' / '.join(part.get('_branch_path',[]))+'（不按 Buff 百分比计算）')
        self.overview.configure(text='所有可计算效果（条件分支分别展示，不相加）：\n'+'\n'.join(summaries) if summaries else '')
        if self.items:self.selector.current(0);self.choose()
        else:
            self.funnel_row.pack_forget()
            self.selector.set('未找到支持的效果；可手填')
            self.kind.set('buff')
            for k,v in asdict(EffectInputs()).items():
                if k in self.values:self.values[k].set(str(v))
            self.result.configure(text='没有可自动填充的效果；已清除上一角色参数。')
            self.set_notes('未读到预选辅助效果或支持的持有被动。可手填；不能据此认定该角色没有增益能力。')

    def choose(self,event=None):
        index=self.selector.current()
        if not 0<=index<len(self.items):return
        item=self.items[index];self.kind.set(item['values']['kind'])
        if item['part'].get('skill_type')=='Funnel':
            count=item.get('funnel_count');self.funnel_count.set('' if count is None else f'{count:g}')
            self.funnel_row.pack(fill='x',before=self.result)
        else:self.funnel_row.pack_forget()
        self.orb_enabled.set(item['values'].get('orb',0)>0);self.orb_level.set('5')
        for key,var in self.values.items():
            value=item['values'][key];var.set('' if value is None else f'{value:g}')
        self.set_notes(item['notes']);self.compute()

    def compute(self):
        try:
            result=self.calculate()
            index=self.selector.current()
            if 0<=index<len(self.items) and self.items[index]['part'].get('skill_type')=='Funnel':
                self.result.configure(text=f'连击珠：{self.funnel_count.get() or "待核对"} 颗 × {result["final"]:g}% / 颗')
                return
            diff='固定值' if result['difference'] is None else f'有效差值 {result["difference"]:.2f}'
            self.result.configure(text=f'预计效果量 {result["final"]:.3f}%  ·  {diff}\n'
                f'基础 {result["base"]:.3f} + 宝珠 {result["orb"]:.3f} + 超差 {result["over"]:.3f}，再乘 (1 + {result["enhancement"]:g}%)')
        except (ValueError,TypeError,OverflowError) as exc:
            self.result.configure(text='请补齐或修正参数：'+str(exc))
