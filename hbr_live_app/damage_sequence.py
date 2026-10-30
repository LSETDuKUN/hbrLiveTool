"""Explicit deterministic, single-target skill steps; never mutate live snapshots."""
from copy import deepcopy
import math
from .destruction import simulate_pools


class DamageSequence:
    def __init__(self):
        self.steps=[]
        self.enemy_id=None

    def clear(self):
        self.steps.clear();self.enemy_id=None

    def undo(self):
        if self.steps:self.steps.pop()
        if not self.steps:self.enemy_id=None

    @property
    def current(self):
        return self.steps[-1]['after'] if self.steps else None

    def overlay(self,enemy):
        result=deepcopy(enemy)
        if not self.steps:return result
        if enemy.get('address')!=self.enemy_id:
            raise ValueError('连续预演已绑定另一敌人，请先清空预演')
        state=self.current
        result.update(dp=state['dp'],hp=state['hp'])
        progress=result.setdefault('enemy_progress',{})
        progress['damage_rate']=state['rate']
        if state['shield'] is not None:progress['shield']=deepcopy(state['shield'])
        return result

    def append(self,actor_id,actor,skill,enemy_id,config):
        if actor_id is None or enemy_id is None:raise ValueError('请先自动填充角色和敌人')
        if len(self.steps)>=3:raise ValueError('同一轮预演最多三人；可撤销最后一步或清空重来')
        if any(s['actor_id']==actor_id for s in self.steps):raise ValueError('该角色已加入本轮预演，请撤销后再调整')
        if config.get('enemy_hp') is None:raise ValueError('连续预演需要已确认的剩余 HP')
        before=dict(dp=config['enemy_dp'],hp=config['enemy_hp'],rate=config['inputs'].destruction,
                    shield=deepcopy(config.get('shield')))
        if self.current:
            if enemy_id!=self.enemy_id:raise ValueError('同一轮预演只能衔接同一敌人')
            labels={'dp':'剩余 DP','hp':'剩余 HP','rate':'破坏率'}
            changed=[f'{label}（当前 {before[k]:.12g}，上一步 {self.current[k]:.12g}）'
                     for k,label in labels.items() if not math.isclose(before[k],self.current[k],rel_tol=1e-8,abs_tol=1e-5)]
            if before['shield']!=self.current['shield']:changed.append('盾层 / 锁盾状态')
            if changed:
                raise ValueError('衔接的敌人状态不一致：'+'、'.join(changed)+'。请重新自动填充以继承上一步；Buff / Debuff 可自由调整，不要求一致。')
        if before['hp']<=0:raise ValueError('前一步已预测击杀，不能继续添加伤害')
        detail=simulate_pools(**config)
        shield=deepcopy(before['shield'])
        if shield and shield.get('remaining',0)>0 and not shield.get('locked') and detail['dp_damage']>=before['dp']:
            shield['remaining']-=1
            shield['broken']=shield.get('broken',0)+1
            shield['index']=shield.get('index',0)+1
            shield['breaks_this_turn']=(shield.get('breaks_this_turn') or 0)+1
            shield['locked']=shield['remaining']>0
            shield['next_dp']=None
        after=dict(dp=detail['remaining_dp'],hp=detail['remaining_hp'],rate=detail['final'],shield=shield)
        step=dict(actor_id=actor_id,actor=actor,skill=skill,before=before,after=after,
                  raw_damage=detail['raw_damage'],damage=detail['damage'],detail=detail,config=deepcopy(config))
        self.steps.append(step);self.enemy_id=enemy_id
        return step
