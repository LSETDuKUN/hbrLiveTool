"""Owned down-turn passives, predicted before action and deduplicated by source."""
from .passive_audit import owned_audit,audit_entry
from hbr_data.battle_conditions import evaluate

SUPPORTED={'CriticalDamageUp','AttackUp','DamageRateUp'}


def predictions(player,context):
    result=[];notes=[];seen=set()
    for owned in owned_audit(player):
        item=audit_entry(owned['label'],owned.get('runtime',{})) if not owned.get('parts') and owned.get('label') else owned
        label=item.get('runtime',{}).get('master_label') or item.get('label')
        if label in seen:continue
        seen.add(label)
        if 'BreakDownTurn()' not in item.get('condition','') or item.get('timing')!='OnPlayerTurnStart':continue
        runtime=item.get('runtime',{})
        if runtime.get('limit_count',0)>0 and runtime.get('used_count',0)>=runtime['limit_count']:continue
        decision=evaluate(item.get('condition'),context)
        if decision is not True:
            notes.append(f'{item.get("name",label)}：倒地被动条件'+('不满足' if decision is False else '未知')+'，未预加');continue
        for part in item.get('parts',[]):
            typ=part.get('skill_type');power=part.get('power') or []
            if (typ not in SUPPORTED or part.get('target_type')!='Self' or not power
                    or part.get('diff_for_max')!=0 or any(part.get('growth',[]))
                    or any(evaluate(part.get(k),context) is not True for k in ('cond','target_condition','hit_condition'))):continue
            if any(s.get('source') in (label,item.get('label')) and s.get('label')=='SpecialStatus.'+typ
                   and not s.get('pending_remove') and not s.get('pending_add')
                   and not (s.get('duration_kind') in ('turn','count') and (s.get('remaining') or 0)<=0)
                   for s in player.get('statuses',[])):continue
            amount=power[0]*10000;effect=part.get('effect') or {}
            elements=part.get('elements') or []
            if len(elements)>1:continue
            result.append(dict(label='SpecialStatus.'+typ,source=label,source_name=item.get('name',label)+'（行动前预测）',
                source_effect={'effect':effect},duration_kind='turn',remaining=1,element_type=0,
                element_key=elements[0] if elements else None,buff_limit_type=0,
                values=dict(rateValueInt=amount,amountOnDpDamageInt=amount,amountOnHpDamageInt=amount)))
            notes.append(f'{item.get("name",label)}：已满足倒地条件，预加 {typ} {power[0]*100:g}%')
    return result,notes
