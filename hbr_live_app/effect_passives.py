"""Predict owned, verified before-action enhancement passives once per source."""
import re
from .passive_audit import owned_audit, audit_entry


def condition_check(condition, player):
    condition=''.join((condition or '').split())
    if not condition:return True
    if condition=='IsFront()':
        pos=player.get('actor_position')
        return pos in (0,1,2) if pos is not None else None
    match=re.fullmatch(r'DpRate\(\)>=([0-9.]+)',condition)
    if match:
        dp,maximum=player.get('dp'),player.get('dp_max')
        if isinstance(dp,(int,float)) and isinstance(maximum,(int,float)) and maximum>0:
            return dp/maximum>=float(match[1])
    return None


def enhancements(player,typ,scopes,states):
    applied={s.get('source') for s in states};seen=set();total=0;notes=[]
    for owned in owned_audit(player):
        item=audit_entry(owned['label'],owned.get('runtime',{})) if not owned.get('parts') and owned.get('label') else owned
        identity=item.get('runtime',{}).get('master_label') or item.get('label')
        if identity in seen:continue
        seen.add(identity)
        if identity in applied or item.get('label') in applied:continue
        runtime=item.get('runtime',{})
        if runtime.get('limit_count',0)>0 and runtime.get('used_count',0)>=runtime['limit_count']:continue
        for part in item.get('parts',[]):
            if typ not in scopes.get(part.get('skill_type'),set()):continue
            label=item.get('name') or identity
            checks=[condition_check(item.get('condition'),player),condition_check(part.get('cond'),player),
                    condition_check(part.get('target_condition'),player),condition_check(part.get('hit_condition'),player)]
            if False in checks:notes.append(f'{label}：当前不满足发动条件');continue
            power=part.get('power') or []
            if (item.get('timing')!='OnPlayerTurnStart' or part.get('target_type')!='Self'
                or part.get('elements') or None in checks or not power):
                notes.append(f'{label}：效果量提升条件/时机待核对，未预加');continue
            amount=power[0]*100;total+=amount
            notes.append(f'{label} [{identity}]：行动开始时预加效果量提升 {amount:g}%；与已存在同来源状态去重')
    return total,notes
