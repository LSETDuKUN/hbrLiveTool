"""Manual, inspectable first step toward battle damage prediction."""
import json
import tkinter as tk
from tkinter import ttk
from .damage_math import DamageInputs, calculate, skill_base
from .damage_autofill import autofill, WEIGHTS, style_elements

FIELDS = (
    ('base', '基础伤害（可空）'), ('attack', '有效加攻合计 %'), ('charge', '充能加攻 %'),
    ('mind_eye', '心眼 %'), ('defense_down', '有效减防 %'), ('fragile', '脆弱 %'),
    ('weapon_bonus', '武器弱点加成 %'), ('element_bonus', '元素弱点加成 %'),
    ('weakness_deepen', '弱点加深 %'), ('resistance', '抗性 %'),
    ('critical_bonus', '暴击额外伤害 %'), ('chain', '连击权重合计 %'),
    ('destruction', '破坏率 %'), ('od', 'OD 倍率'), ('token_bonus', 'Token 增伤 %'),
    ('dp_bonus', '对 DP 特攻 %'), ('hp_bonus', '对 HP 特攻 %'),
    ('health_factor', '血量条件倍率'), ('down_factor', '倒地条件倍率'), ('other_factor', '其他独立倍率'))
NAMES = dict(attack='加攻（含充能／适用心眼）', defense='减防（含适用脆弱）', affinity='相性',
             critical='暴伤', chain='连击', destruction='破坏率', od='OD', token='Token',
             specialization='DP/HP 特攻', health='血量条件', down='倒地条件', other='其他')


class DamageWindow(tk.Toplevel):
    def __init__(self, parent, snapshot):
        super().__init__(parent)
        self.title('伤害试算 · 实验版');self.geometry('900x760')
        self.snapshot = snapshot
        self.loaded_snapshot={};self.fill_notes='尚未自动填充'
        selectors=ttk.Frame(self,padding=8);selectors.pack(fill='x')
        self.player_box=ttk.Combobox(selectors,state='readonly',width=22);self.player_box.pack(side='left')
        self.enemy_box=ttk.Combobox(selectors,state='readonly',width=22);self.enemy_box.pack(side='left',padx=6)
        ttk.Button(selectors,text='刷新角色/敌人列表',command=self.reload_choices).pack(side='left')
        ttk.Button(selectors,text='自动填充（覆盖表单）',command=self.fill).pack(side='left',padx=6)
        modes_bar=ttk.Frame(self,padding=(8,0,8,6));modes_bar.pack(fill='x')
        self.mode_choices={}
        for key,label in [('transcend','雷超越'),('high_boost','高阶增幅')]:
            ttk.Label(modes_bar,text=label).pack(side='left',padx=(8,2))
            var=tk.StringVar(self,value='自动');self.mode_choices[key]=var
            ttk.Combobox(modes_bar,textvariable=var,values=['自动','启用','禁用'],state='readonly',width=6).pack(side='left')
        ttk.Label(modes_bar,text='修改后点击自动填充；仅影响试算').pack(side='left',padx=10)
        tabs = ttk.Notebook(self); tabs.pack(fill='both', expand=True)
        form = ttk.Frame(tabs, padding=12); tabs.add(form, text='乘区试算')
        skill_form=ttk.Frame(tabs,padding=12);tabs.add(skill_form,text='技能与属性（可修改）')
        data = ttk.Frame(tabs, padding=12); tabs.add(data, text='当前内存参数')
        ttk.Label(form, text='自动填充只取当前已施加效果；填充后可修改，实时采样不会覆盖你的修改。\n'
                  '未计入项目请查看“当前内存参数”页；尚不预测逐 Hit、破盾或预施加效果。',
                  wraplength=840).pack(anchor='w', pady=(0,8))
        grid = ttk.Frame(form); grid.pack(fill='x')
        self.values = {};defaults = DamageInputs()
        for idx,(key,title) in enumerate(FIELDS):
            row,col=idx//2,(idx%2)*2
            ttk.Label(grid,text=title).grid(row=row,column=col,sticky='w',padx=5,pady=4)
            value=getattr(defaults,key)
            var=tk.StringVar(self,value='' if value is None else str(value));self.values[key]=var
            ttk.Entry(grid,textvariable=var,width=15).grid(row=row,column=col+1,sticky='ew',padx=(4,20))
        self.pool=tk.StringVar(self,value='hp')
        options=ttk.Frame(form);options.pack(fill='x',pady=8)
        for pool in ('dp','hp'):
            ttk.Radiobutton(options,text='打 '+pool.upper(),variable=self.pool,value=pool).pack(side='left')
        self.flags={}
        for key,title in [('critical','暴击'),('penetration_critical','贯通暴击：强制弱点判定'),('absorbed','吸收')]:
            var=tk.BooleanVar(self,value=getattr(defaults,key));self.flags[key]=var
            ttk.Checkbutton(options,text=title,variable=var).pack(side='left',padx=6)
        ttk.Button(form,text='计算',command=self.compute).pack(anchor='w')
        self.result=tk.Text(form,height=10,wrap='word');self.result.pack(fill='both',expand=True,pady=8)
        self.use_skill=tk.BooleanVar(self,value=False)
        ttk.Checkbutton(skill_form,text='计算时使用以下技能参数生成基础伤害（取消则使用手填基础伤害）',variable=self.use_skill).pack(anchor='w')
        self.skill_title=ttk.Label(skill_form,text='尚未自动填充');self.skill_title.pack(anchor='w',pady=8)
        self.params={};pg=ttk.Frame(skill_form);pg.pack(fill='x')
        names=[('min_power','最小威力'),('max_power','最大威力'),('difference','属性差阈值'),('level','技能等级'),
               ('enemy','敌方防御参考值'),('orb','宝珠等级（默认满级 5）'),('growth_min','最小威力等级成长'),('growth_max','最大威力等级成长'),
               ('critical_rate_bonus','已识别暴击率加成 %（供核对）'),('morale_level','士气等级（每层六维 +5）')]
        from .damage_inputs import STATS
        names += [(key,STATS[key]) for key in WEIGHTS]+[('weight_'+key,STATS[key]+'权重') for key in WEIGHTS]
        for idx,(key,label) in enumerate(names):
            row,col=idx//2,(idx%2)*2
            ttk.Label(pg,text=label).grid(row=row,column=col,sticky='w',padx=4,pady=5)
            var=tk.StringVar(self,value='');self.params[key]=var
            ttk.Entry(pg,textvariable=var,width=15).grid(row=row,column=col+1,padx=8)
        ttk.Label(skill_form,text='权重为 0 的属性不参与计算。特殊技能条件、偏向和其他独立修正仍需核对。',wraplength=820).pack(anchor='w',pady=8)
        ttk.Label(data,text='刷新获取当前已连接战斗的快照；原始参数并非预计算伤害。').pack(anchor='w')
        ttk.Button(data,text='刷新参数快照',command=self.refresh).pack(anchor='w',pady=6)
        scrollbar=ttk.Scrollbar(data);scrollbar.pack(side='right',fill='y')
        self.raw=tk.Text(data,wrap='word',yscrollcommand=scrollbar.set)
        self.raw.pack(fill='both',expand=True);scrollbar.configure(command=self.raw.yview)
        self.reload_choices();self.refresh()
        if self.loaded_snapshot.get('connected') and self.player_box.current()>=0 and self.enemy_box.current()>=0:self.fill()
        else:self.compute()

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
        modes['lightning_style']='Thunder' in style_elements(player.get('style_label',''))
        filled=autofill(player,enemy,data.get('field_state'),modes=modes)
        filled['notes'].append('模式判断：'+str(modes)+'；自动依据雷量表、风格资料、强化剩余回合及运行时天赋列表，可手动纠正。')
        if not gauge:filled['skipped'].append('元素量表未读取：超越可手动启用，仍需确认是雷属性风格')
        for k,var in self.values.items():
            v=filled['values'][k];var.set('' if v is None else f'{v:g}')
        for k,var in self.flags.items():var.set(filled['values'][k])
        self.pool.set(filled['values']['target_pool'])
        for k,var in self.params.items():
            v=filled['params'].get(k);var.set('' if v is None else f'{v:g}')
        self.use_skill.set(True);self.skill_title.configure(text=filled['skill'])
        self.fill_notes='自动填充来源与假设：\n'+'\n'.join(filled['notes'])+'\n\n未自动计入 / 待核对：\n'+'\n'.join(filled['skipped'])
        self.refresh();self.compute()

    def compute(self):
        try:
            values={k:float(v.get()) for k,v in self.values.items() if k!='base'}
            base=self.values['base'].get().strip()
            if self.use_skill.get():
                computed,weighted=skill_base({k:v.get() for k,v in self.params.items()},self.flags['critical'].get())
                base=str(computed);self.values['base'].set(f'{computed:.8g}')
            values.update(base=float(base) if base else None,target_pool=self.pool.get(),
                          **{k:v.get() for k,v in self.flags.items()})
            result=calculate(DamageInputs(**values))
            text='弱点条件：'+('满足' if result['weak'] else '不满足（不计心眼／脆弱）')+'\n'
            text+='  ×  '.join(f'{NAMES[k]} {v:.4g}' for k,v in result['factors'].items())+'\n\n'
            if result['multiplier'] is not None:text+=f"总倍率：{result['multiplier']:.6g}\n"
            if result['damage'] is not None:
                text+=f"未衰减试算伤害：{result['damage']:,.2f}\n"
                text+=f"0.9–1.1 浮动边界：{result['minimum']:,.2f} – {result['maximum']:,.2f}\n"
                text+='这是理论边界，不表示总伤害在区间内均匀分布；多 Hit 独立浮动通常更集中。\n'
            text+=result['note']+'\n充能暂按参考计算器并入加攻。Token 与血量条件需填技能适用的实际增幅。'
        except (ValueError, OverflowError) as exc:
            text='无法计算：'+str(exc)
        self.result.configure(state='normal');self.result.delete('1.0','end');self.result.insert('end',text)
        self.result.configure(state='disabled')

    def refresh(self):
        from .damage_inputs import STATS
        data=self.snapshot()
        lines=[self.fill_notes,'\n已连接战斗' if data.get('connected') else '\n未连接：如有数据，属于保留快照']
        for player in data.get('players',[]):
            inputs=player['inputs'];skill=inputs.get('selected_skill',{})
            lines.append('\n'+str(player.get('name') or '角色')+' · '+str(skill.get('name') or '预选未读到'))
            lines.append(' / '.join(f'{STATS[k]} {v}' for k,v in inputs.get('stats',{}).items()))
            lines.append('Token：'+str(inputs.get('token','未读到')))
        for enemy in data.get('enemies',[]):
            inputs=enemy['inputs']
            lines.append('\n'+str(enemy.get('name') or '敌人')+
                         ' · 边界参考 '+str(inputs.get('_borderRefParam','未读到'))+
                         ' / 防御参考 '+str(inputs.get('_defenseRefParam','未读到')))
        lines.append('\n以下为技能威力、偏向权重及条件原始参数（未自动代入）：\n')
        self.raw.configure(state='normal');self.raw.delete('1.0','end')
        self.raw.insert('end','\n'.join(lines)+json.dumps(data,ensure_ascii=False,indent=2));self.raw.configure(state='disabled')
