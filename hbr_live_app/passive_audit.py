"""Audit only runtime-owned passives. Never infer unlocks from a style catalog.

Conditions are untrusted game data, not Python expressions. Only explicitly
verified low-SP and equipment rules are predicted; other conditions stay pending.
"""
import json
import sqlite3
from functools import lru_cache

LOW_SP = {'Passive.ConsumeSpAttackUp01','Passive.ConsumeSpAttackUp03'}
EQUIPMENT = {'Passive.Start_DarkEnhanceRing02','Passive.Start_HPAttackUpRangeByHitEarring03'}


@lru_cache(maxsize=512)
def passive_record(label):
    if not label:return {}
    try:
        from hbr_data.store import Catalog
        _,rows,_=Catalog().query("SELECT raw_json FROM records WHERE region='cn' AND label=?",(label,),limit=20)
        unique={raw for (raw,) in rows}
        if len(unique)==1:return json.loads(next(iter(unique)))
        if unique:return {}
        # Equipment passives are nested inside accessory records, not top-level records.
        _,rows,truncated=Catalog().query("SELECT raw_json FROM records WHERE region='cn' AND dataset='accessories' AND raw_json LIKE ?",('%'+label+'%',),limit=100)
        if truncated:return {}
        found={}
        def walk(value):
            if isinstance(value,dict):
                if value.get('label')==label and value.get('category')=='Passive':
                    found[json.dumps(value,sort_keys=True)]=value
                for child in value.values():walk(child)
            elif isinstance(value,list):
                for child in value:walk(child)
        for (raw,) in rows:walk(json.loads(raw))
        return next(iter(found.values())) if len(found)==1 else {}
    except (OSError,ValueError,RuntimeError,sqlite3.Error):return {}


def audit_entry(label, runtime=None):
    runtime=runtime or {}
    record=passive_record(label) or passive_record(runtime.get('master_label',''))
    return dict(label=label,name=runtime.get('name') or record.get('name') or label,
                condition=runtime.get('condition',record.get('condition','')),
                timing=record.get('timing','未确认'),description=runtime.get('description') or record.get('desc',''),
                parts=record.get('parts',[]),catalog_found=bool(record),
                classification='已支持装备条件' if label in EQUIPMENT else '已支持低 SP 条件' if label in LOW_SP else
                '条件待核对' if runtime.get('condition') or record.get('condition') else '效果/时机待核对',
                runtime=runtime)


def owned_audit(player):
    inputs=player.get('combat_inputs',player.get('inputs',{}))
    if 'passive_audit' in inputs:return inputs['passive_audit']
    return [audit_entry(label) for label in dict.fromkeys(inputs.get('passive_labels',[]))]


def low_sp_predictions(player, party, selected, skill, skill_attack):
    """Only confirmed 0-SP skill or explicitly supplied actual cost; no cost guessing."""
    if not skill_attack:return [],[]
    cost=selected.get('actual_sp_cost')
    base_cost=selected.get('base_sp_cost')
    if base_cost is None:base_cost=skill.get('sp_cost')
    if cost is None and base_cost==0:cost=0
    additions=[];notes=[];seen=set()
    for owner in party or [player]:
        # A dead/unknown owner is not assumed able to trigger the passive.
        if owner.get('hp') is not None and owner['hp']<=0:continue
        for item in owned_audit(owner):
            label=item['label'];identity=(owner.get('actor_id'),label)
            if label not in LOW_SP or identity in seen:continue
            seen.add(identity)
            if cost is None:
                notes.append(item['name']+'：实际 SP 消耗未确认，暂未预加');continue
            if cost>8:continue
            runtime=item.get('runtime',{})
            if runtime.get('limit_count',0)>0 and runtime.get('used_count',0)>=runtime['limit_count']:
                notes.append(item['name']+'：触发次数已用尽');continue
            # Fail closed if the catalog changes target, timing, amount or condition.
            parts=item.get('parts',[])
            normalized=lambda s:''.join(s.split())
            expected='CountBC(IsPlayer()==1&&IsAttackNormal()==0&&ConsumeSp()<=8)>0'
            if item.get('timing')!='OnPlayerTurnStart' or normalized(item.get('condition',''))!=expected:
                notes.append(item['name']+'：触发条件与已验证规则不一致');continue
            for part in parts:
                if (part.get('skill_type')!='AttackUp' or part.get('target_type')!='AllyAll'
                    or normalized(part.get('target_condition',''))!='IsAttackNormal()==0&&ConsumeSp()<=8'
                    or part.get('cond') or part.get('hit_condition') or part.get('elements')
                    or part.get('power')!=[1.0,0.0]):continue
                additions.append(dict(label='SpecialStatus.AttackUp',name=item['name'],source=label,
                    source_name=(owner.get('name') or owner.get('actor') or '队友')+' · '+item['name'],
                    element_type=0,duration_kind='turn',remaining=1,buff_limit_type=0,
                    values=dict(amountOnDpDamageInt=10000,amountOnHpDamageInt=10000),predicted=True))
                notes.append(item['name']+'：预选技能 SP≤8，预加普通加攻100%并参与两层/单独发动覆盖')
    return additions,notes


def equipment_bonuses(player, skill, element, skill_attack):
    """Verified equipment only; real final values supersede pre-action estimates."""
    result=[];notes=[];handled=set()
    inputs=player.get('combat_inputs',player.get('inputs',{}))
    labels=set(inputs.get('passive_labels',[])) | {p['label'] for p in inputs.get('passive_audit',[])}
    states=player.get('statuses',[])
    labels.update(s.get('source') for s in states)
    for label in sorted(labels & EQUIPMENT):
        handled.add(label)
        if not skill_attack:continue
        ring=label=='Passive.Start_DarkEnhanceRing02'
        if ring and element!='Dark':continue
        key='element_attack' if ring else 'hp_bonus'
        actual=[]
        for s in states:
            if s.get('source')!=label or s.get('effective') is False or s.get('pending_add') or s.get('pending_remove'):continue
            if s.get('duration_kind') in ('turn','count') and s.get('remaining',1)<=0:continue
            value=s.get('values',{}).get('amountOnHpDamageInt')
            if isinstance(value,(int,float)) and value>=0:actual.append(value/100)
        if actual:
            result.append((key,max(actual)))
            notes.append(f'{label}：采用实际装备状态 {max(actual):g}%，不重复预加');continue
        position=player.get('actor_position',player.get('position'))
        if position not in (0,1,2):
            notes.append(label+'：前排条件未满足或未确认，暂未预加');continue
        record=passive_record(label)
        if record.get('timing')!='OnPlayerTurnStart' or record.get('condition')!='IsFront()':
            notes.append(label+'：装备触发规则未匹配');continue
        for part in record.get('parts',[]):
            if part.get('target_type')!='Self' or any(part.get(k) for k in ('cond','target_condition','hit_condition')):continue
            if ring and part.get('skill_type')=='AttackUp' and part.get('elements')==['Dark']:
                value=part['power'][0]*100
            elif not ring and part.get('skill_type')=='AttackUpRangeByHit' and part.get('multipliers',{}).get('dp')==0 and part.get('multipliers',{}).get('hp')==1:
                hits=skill.get('hit_count')
                if not isinstance(hits,int) or hits<=0:
                    notes.append(label+'：技能主 Hit 数未确认，未猜测 HP 特攻');continue
                low,high=part['power'];at_low,at_high=part['value']
                if at_low<=at_high:continue
                fraction=max(0,min(1,(hits-at_high)/(at_low-at_high)))
                value=(high+(low-high)*fraction)*100
                notes.append(f'攻击饰品按 {hits} 个主 Hit 计算（不计追加连击）：{value:g}%')
            else:continue
            result.append((key,value));notes.append(f'{record.get("name",label)}：攻击前预填 {value:g}% ← {label}')
    return result,handled,notes


def audit_text(players):
    lines=['仅列运行时已加载天赋/被动（含读到的共鸣来源）；未解锁项目不按风格资料猜测。',
           '已施加效果继续读取真实状态；未确认条件不额外预加。没有读到通用条件判定结果。']
    for player in players:
        lines.append('\n【'+str(player.get('name') or player.get('actor') or '角色')+'】')
        entries=owned_audit(player)
        if not entries:lines.append('被动清单未读取')
        for item in entries:
            lines.append(f"{item['name']} · {item['classification']} · {item['timing']}")
            lines.append('  标识：'+item['label'])
            if item.get('description'):lines.append('  '+item['description'].replace('\n',' / '))
            if item.get('condition'):lines.append('  触发条件：'+item['condition'])
            if not item.get('catalog_found'):lines.append('  本地效果资料未匹配，保留运行时信息待核对')
            for p in item.get('parts',[]):
                lines.append(f"  → {p.get('target_type')} · {p.get('skill_type')} · power={p.get('power')} · value={p.get('value')}")
                lines.append('    对象条件：'+(p.get('target_condition') or '无')+'；效果条件：'+(p.get('cond') or p.get('hit_condition') or '无'))
    return '\n'.join(lines)
