"""Reversible, snapshot-only status proposals. Never mutate live battle data."""
from copy import deepcopy
import math

SUPPORTED={'AttackUp','AttackUpIncludeNormal','MindEye','CriticalDamageUp','DefenseDown','Fragile','Funnel'}
PREVIEW_KEYS=('attack','element_attack','mind_eye','critical_bonus','element_critical_bonus','defense_down','element_defense_down','fragile','chain')


def pending_state(item,amount,target):
    part=item['part'];kind=part.get('skill_type')
    if kind not in SUPPORTED:raise ValueError('此效果暂不支持预添加到伤害乘区')
    if not math.isfinite(amount) or amount<0:raise ValueError('效果量无效')
    enemy=kind in ('DefenseDown','Fragile')
    if not enemy and part.get('target_type')=='Self' and item.get('caster')!=target.get('actor_id'):
        raise ValueError('自身效果不能施加给另一个角色')
    elements=part.get('elements') or []
    if len(elements)>1:raise ValueError('多属性效果暂需分别核对，未预添加')
    effect=part.get('effect') or {};exit_cond=effect.get('exitCond')
    duration='permanent' if exit_cond=='Eternal' else 'count' if exit_cond=='Count' else 'turn'
    state=dict(label='SpecialStatus.'+kind,source=item.get('source') or part.get('label'),
               source_name='手动预添加 · '+item['title'],element_type=0,
               element_key=elements[0] if elements else None,duration_kind=duration,remaining=1,
               source_effect={'effect':effect},
               buff_limit_type=4 if effect.get('limitType')=='Only' else 0,
               values=dict(rateValueInt=amount*100,amountOnDpDamageInt=amount*100,amountOnHpDamageInt=amount*100))
    if kind=='Funnel':
        count=item.get('funnel_count')
        if not isinstance(count,(int,float)) or not math.isfinite(count) or int(count)!=count or not 1<=count<=100:
            raise ValueError('请核对连击珠颗数（1～100 的整数）')
        state['values']['numValue']=int(count)
    if item.get('passive'):
        if any(s.get('source') in (item.get('source'),part.get('label')) for s in target.get('statuses',[])):
            raise ValueError('当前已有同来源被动状态，请核对自动填充；不重复预加')
        if kind!='CriticalDamageUp':
            raise ValueError('该被动/饰品已有独立自动填充；当前仅开放被动爆伤的手动预添加')
    return enemy,state


def with_pending(player,enemy,rows):
    player,enemy=deepcopy(player),deepcopy(enemy)
    for row in rows:
        target=enemy if row['enemy'] else player
        identity=target.get('address') if row['enemy'] else target.get('actor_id')
        if 'target_ids' in row and identity not in row['target_ids']:continue
        target.setdefault('statuses',[]).append(deepcopy(row['state']))
    return player,enemy


def targeted_row(item,amount,party,enemies,selected_player,selected_enemy):
    """Resolve recipients once, without changing live statuses or re-targeting on switches."""
    kind=item['part'].get('skill_type');scope=item['part'].get('target_type')
    enemy=kind in ('DefenseDown','Fragile')
    if enemy:
        targets=enemies if scope=='All' else [selected_enemy] if scope=='Single' else []
    elif scope=='Self':targets=[p for p in party if p.get('actor_id')==item.get('caster')]
    elif scope=='AllyAll':targets=party
    elif scope in ('AllyFront','AllyBack'):
        positions=(0,1,2) if scope=='AllyFront' else (3,4,5)
        targets=[p for p in party if p.get('actor_position') in positions]
    elif scope=='AllySingle':targets=[selected_player]
    else:targets=[]
    if not targets:raise ValueError('施加对象未确认，未预添加：'+str(scope))
    if any(p.get('address' if enemy else 'actor_id') is None for p in targets):
        raise ValueError('施加对象身份未读到，无法可靠保存预添加')
    condition=item['part'].get('target_condition')
    if condition:
        from hbr_data.battle_conditions import evaluate,context_for
        selected=[]
        for target in targets:
            verdict=evaluate(condition,context_for(target if not enemy else selected_player,target if enemy else selected_enemy,{}))
            if verdict is None:raise ValueError('目标条件暂不能自动判定：'+condition)
            if verdict:selected.append(target)
        targets=selected
        if not targets:raise ValueError('没有符合目标条件的角色或敌人')
    side,state=pending_state(item,amount,targets[0])
    return dict(item=deepcopy(item),enemy=side,state=state,amount=amount,
                target_ids=[p.get('address') if enemy else p.get('actor_id') for p in targets],
                target_names=[str(p.get('actor') or p.get('name') or p.get('actor_id') or p.get('address')) for p in targets])
