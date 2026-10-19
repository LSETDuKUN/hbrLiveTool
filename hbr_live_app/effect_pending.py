"""Reversible, snapshot-only status proposals. Never mutate live battle data."""
from copy import deepcopy
import math

SUPPORTED={'AttackUp','AttackUpIncludeNormal','MindEye','CriticalDamageUp','DefenseDown','Fragile'}


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
        target.setdefault('statuses',[]).append(deepcopy(row['state']))
    return player,enemy
