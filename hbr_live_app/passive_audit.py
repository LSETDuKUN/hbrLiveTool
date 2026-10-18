"""Audit only runtime-owned passives. Never infer unlocks from a style catalog.

Conditions are untrusted game data, not Python expressions. Only explicitly
verified low-SP and equipment rules are predicted; other conditions stay pending.
"""
import json
import sqlite3
from functools import lru_cache

LOW_SP = {'Passive.ConsumeSpAttackUp01','Passive.ConsumeSpAttackUp03'}
EQUIPMENT = ({f'Passive.Start_{e}EnhanceRing{i:02}' for e in ('Fire','Ice','Thunder','Light','Dark') for i in range(5)}
             | {f'Passive.Start_{pool}AttackUpRangeByHitEarring{i:02}' for pool in ('DP','HP') for i in (1,2,3)}
             | {'Passive.Start_SkillEnhance'})
DR_EQUIPMENT = {f'Passive.Start_DamageRateUpByHitEarring{i:02}' for i in (1,2,3)} | {'Passive.Start_DamageRateUp_10'}
OD_EQUIPMENT = {f'Passive.Start_OverDrivePointUpByHitEarring{i:02}' for i in (1,2,3)}


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
                classification='已支持装备条件' if label in EQUIPMENT | OD_EQUIPMENT | DR_EQUIPMENT else '已支持低 SP 条件' if label in LOW_SP else
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


def accessory_effects(player, skill, element, skill_attack=True, details=None):
    """Owned effects only. Inspect source parts, never infer an equipped tier."""
    import math
    result=[];handled=set();notes=[]
    inputs=player.get('combat_inputs',player.get('inputs',{}))
    states=player.get('statuses',[])
    labels=set(inputs.get('passive_labels',[])) | {p['label'] for p in inputs.get('passive_audit',[])}
    labels.update(s.get('source') for s in states if s.get('source'))
    supported=EQUIPMENT | DR_EQUIPMENT | OD_EQUIPMENT
    for label in sorted(labels):
        if label not in supported:
            if any(x in label for x in ('Ring','Earring','Necklace','Accessory')):
                notes.append(label+'：饰品效果尚未确认，未自动预加')
            continue
        record=passive_record(label)
        if not record:
            notes.append(label+'：装备资料未确认，仅保留实际状态解析')
            continue
        handled.add(label)
        if not skill_attack and label in EQUIPMENT:continue
        if record.get('timing')!='OnPlayerTurnStart' or record.get('condition') not in ('','IsFront()'):
            notes.append(label+'：装备触发规则未匹配');continue
        for part in record.get('parts',[]):
            if part.get('target_type')!='Self' or any(part.get(k) for k in ('cond','target_condition','hit_condition')):continue
            kind=part.get('skill_type');elements=part.get('elements') or []
            if elements and elements!=[element]:
                notes.append(record.get('name',label)+'：技能属性不匹配，未计入');continue
            mult=part.get('multipliers') or {}
            if kind=='AttackUp' and elements and mult.get('dp')==mult.get('hp')==1:key='element_attack'
            elif kind=='AttackUp' and label=='Passive.Start_SkillEnhance' and not elements and mult.get('dp')==mult.get('hp')==1:key='attack'
            elif kind=='AttackUpRangeByHit' and (mult.get('dp'),mult.get('hp')) in ((1,0),(0,1)):
                key='dp_bonus' if mult['dp'] else 'hp_bonus'
            elif kind in ('DamageRateUp','DamageRateUpByHit'):key='destruction_bonus'
            elif kind=='OverDrivePointUpByHit':key='od_gain_bonus'
            else:continue
            field='amountOnDpDamageInt' if key=='dp_bonus' else 'amountOnHpDamageInt' if key in ('hp_bonus','element_attack','attack') else 'rateValueInt'
            matching=[s for s in states if s.get('source')==label]
            actual=[s.get('values',{}).get(field) for s in matching
                    if s.get('effective') is not False and not s.get('pending_add') and not s.get('pending_remove')
                    and (s.get('duration_kind') not in ('turn','count') or s.get('remaining',1)>0)]
            actual=[v/100 for v in actual if isinstance(v,(int,float)) and math.isfinite(v) and v>=0]
            if actual:
                value=max(actual);origin='实际状态（不重复预加）'
            elif matching:
                notes.append(label+'：实际状态未生效或数值未确认，未替换为预测值');continue
            else:
                if record.get('condition')=='IsFront()' and player.get('actor_position',player.get('position')) not in (0,1,2):
                    notes.append(label+'：前排条件未满足或未确认，暂未预加');continue
                power=part.get('power',[])
                if len(power)!=2 or not all(isinstance(v,(int,float)) and math.isfinite(v) for v in power):continue
                value=power[0]*100
                if kind in ('AttackUpRangeByHit','DamageRateUpByHit','OverDrivePointUpByHit'):
                    hits=skill.get('hit_count');endpoints=part.get('value',[])
                    if not isinstance(hits,int) or hits<1:
                        notes.append(label+'：主 Hit 数未确认，未猜测饰品增幅');continue
                    if len(endpoints)!=2 or endpoints[0]==endpoints[1]:continue
                    fraction=max(0,min(1,(hits-endpoints[0])/(endpoints[1]-endpoints[0])))
                    value=100*(power[0]+(power[1]-power[0])*fraction)
                origin='攻击前预填'
            if not math.isfinite(value) or value<0:continue
            result.append((key,value))
            if details is not None:
                details.append(dict(label=label,key=key,value=value,name=record.get('name',label),origin=origin))
            notes.append(f'{record.get("name",label)} → {key} +{value:g}% · {origin} ← {label}')
    return result,handled,notes


def equipment_bonuses(player, skill, element, skill_attack):
    effects,handled,notes=accessory_effects(player,skill,element,skill_attack)
    return [(k,v) for k,v in effects if k not in ('destruction_bonus','od_gain_bonus')],handled,notes


def od_gain_bonus(player,skill):
    effects,_,notes=accessory_effects(player,skill,None,False)
    return sum(v for k,v in effects if k=='od_gain_bonus'),notes


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
