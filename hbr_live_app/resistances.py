"""Catalog base bonuses plus observed changes; never claim an engine final rate."""
import math

NAMES = dict(fire='火',ice='冰',thunder='雷',light='光',dark='暗',slash='斩',stab='突',strike='打',nonelement='无属性')


def resistance_lines(state):
    base = state.get('base_resistances')
    if not isinstance(base,dict):
        return ['基础抗性 / 弱点：资料未收录']
    lines=[]
    for element,name in NAMES.items():
        value=base.get(element)
        if not isinstance(value,(int,float)) or not math.isfinite(value):continue
        if value == 0:continue
        text=f'{name} · '+('基础弱点加成' if value<0 else '基础抗性')+f' {abs(value):g}%（资料）'
        changes=[s for s in state.get('statuses',[]) if (s.get('element_key') or '').lower()==element
                 and s.get('label') in ('SpecialStatus.ResistDown','SpecialStatus.ResistUp','SpecialStatus.ResistDownOverwrite')
                 and s.get('effective') is not False and not s.get('pending_add') and not s.get('pending_remove')]
        if value<0 and len(changes)==1 and state.get('statuses_available'):
            status=changes[0];rate=status.get('values',{}).get('rateValueInt')
            if status['label']=='SpecialStatus.ResistDown' and isinstance(rate,int) and rate<0:
                text+=f' + 加深 {-rate/100:g}% → {-value-rate/100:g}%（加成推算）'
        elif value<0 and len(changes)>1:
            text+=' · 多项变化，暂不合算'
        lines.append(text)
    return lines or ['资料中未列出非零基础抗性 / 弱点加成']
