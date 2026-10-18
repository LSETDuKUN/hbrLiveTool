"""Editable accessory contributions, reconciled as deltas exactly once."""
import math
import tkinter as tk
from tkinter import ttk

SLOTS=[(f'{e}EnhanceRing',f'{name}属性戒指','element_attack')
       for e,name in [('Fire','火'),('Ice','冰'),('Thunder','雷'),('Light','光'),('Dark','暗')]]+[
    ('DPAttackUpRangeByHitEarring','DP 特攻耳坠','dp_bonus'),
    ('HPAttackUpRangeByHitEarring','HP 特攻耳坠','hp_bonus'),
    ('DamageRateUpByHitEarring','破坏耳坠','destruction_bonus'),
    ('OverDrivePointUpByHitEarring','OD 耳坠','od_gain_bonus'),
    ('SkillEnhance','特殊项链 · 技能加攻','attack'),
    ('DamageRateUp_10','特殊项链 · 破坏增长','destruction_bonus')]
DESTINATIONS=dict(element_attack='元素加攻',dp_bonus='DP 特攻',hp_bonus='HP 特攻',
                  destruction_bonus='破坏率增长',od_gain_bonus='OD 获取',attack='普通加攻')


def matches(label,slot):
    prefix='Passive.Start_'+slot
    return label==prefix or (label.startswith(prefix) and label[len(prefix):].isdigit())


def totals(rows):
    result={}
    for enabled,value,key in rows:
        if not enabled:continue
        amount=float(value or 0)
        if not math.isfinite(amount) or amount<0:raise ValueError('饰品增益必须为有限非负数')
        result[key]=result.get(key,0)+amount
    return result


class EquipmentEditor(ttk.Frame):
    def __init__(self,parent):
        super().__init__(parent)
        self.rows=[];self.applied={}
        ttk.Label(self,text='已计入对应乘区；修改后点击“计算”，只替换该饰品贡献，不会重复叠加。\n未检测到的项目默认不计入；如手动勾选，请同时填写已核实的增益。\n检测依据是装备效果标识；特殊项链按效果列出，不据此猜测具体项链名称。',wraplength=850).pack(anchor='w',pady=8)
        for slot,name,key in SLOTS:
            frame=ttk.LabelFrame(self,text=name,padding=8);frame.pack(fill='x',pady=4)
            enabled=tk.BooleanVar(self,value=False);value=tk.StringVar(self,value='0')
            ttk.Checkbutton(frame,text='计入',variable=enabled).pack(side='left')
            ttk.Entry(frame,textvariable=value,width=10).pack(side='left',padx=8)
            ttk.Label(frame,text='% → '+DESTINATIONS[key]).pack(side='left')
            note=ttk.Label(frame,text='未检测',wraplength=440);note.pack(side='left',padx=12)
            self.rows.append(dict(slot=slot,key=key,enabled=enabled,value=value,note=note))

    def load(self,details,owned):
        for row in self.rows:
            entries=[d for d in details if matches(d['label'],row['slot'])]
            found=[label for label in owned if matches(label,row['slot'])]
            row['enabled'].set(bool(found or entries))
            row['value'].set(f'{sum(d["value"] for d in entries):.10g}')
            text='；'.join(d['name']+' · '+d['origin'] for d in entries)
            row['note'].configure(text=text or ('已检测到；条件不符或数据未确认，自动计入 0' if found else '未检测到，可手动填写'))
        self.applied=self.current()

    def current(self):
        return totals((r['enabled'].get(),r['value'].get(),r['key']) for r in self.rows)

    def apply(self,variables):
        current=self.current();updates={}
        for key in set(current)|set(self.applied):
            delta=current.get(key,0)-self.applied.get(key,0)
            if abs(delta)<1e-10:continue
            value=float(variables[key].get() or 0)+delta
            if not math.isfinite(value) or value < -1e-8:
                raise ValueError('饰品调整会使乘区变为负数，请先恢复自动填充或核对该乘区')
            updates[key]=max(0,value)
        # Validate all changes before mutating any field or the applied ledger.
        for key,value in updates.items():variables[key].set(f'{value:.10g}')
        self.applied=current
