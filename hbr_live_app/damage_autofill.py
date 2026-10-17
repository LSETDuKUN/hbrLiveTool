"""Snapshot-based suggestions. Never apply an unexecuted skill's debuffs."""
import json
import sqlite3
from functools import lru_cache
from .damage_math import DamageInputs

WEIGHTS = dict(power='str',dexterity='dex',toughness='con',spirit='spr',wisdom='wis',luck='luk')


@lru_cache(maxsize=256)
def catalog_skill(label):
    try:
        from hbr_data.store import Catalog
        _,rows,_=Catalog().query("SELECT raw_json FROM skills WHERE region='cn' AND label=?",(label,),limit=50)
        candidates={}
        for row in rows:
            s=json.loads(row[0]); candidates[json.dumps(s.get('parts',[]),sort_keys=True)]=s
        return next(iter(candidates.values())) if len(candidates)==1 else {}
    except (OSError,ValueError,RuntimeError,sqlite3.Error):return {}


@lru_cache(maxsize=128)
def style_elements(label):
    try:
        from hbr_data.store import Catalog
        _,rows,_=Catalog().query("SELECT raw_json FROM styles WHERE region='cn' AND label=?",(label,),limit=2)
        return json.loads(rows[0][0]).get('elements',[]) if len(rows)==1 else []
    except (OSError,ValueError,RuntimeError,sqlite3.Error):return []


def autofill(player, enemy, fields=None, lookup=catalog_skill, modes=None, party=None):
    from .passive_audit import low_sp_predictions, equipment_bonuses, LOW_SP
    values=vars(DamageInputs()).copy(); notes=[]; skipped=[]
    values['critical_rate_bonus']=0
    values['element_critical_rate_bonus']=0
    inputs=player.get('combat_inputs',player.get('inputs',{}))
    selected=inputs.get('selected_skill',{}); db=lookup(selected.get('label','')) if selected.get('label') else {}
    attacks=[p for p in db.get('parts',[]) if p.get('skill_type') in
             ('AttackSkill','AttackNormal','TokenAttack','PenetrationCriticalAttack','AttackByOwnDpRate','DamageRateChangeAttackSkill')]
    raw=[p for p in selected.get('parts',[]) if p.get('skill_type_raw')==10]
    part=attacks[0] if len(attacks)==1 else {}
    live=next((p for p in selected.get('parts',[]) if p.get('Label')==part.get('label')),None)
    if live is None and len(raw)==1:live=raw[0]
    live=live or {}
    def pick(key, fallback):
        return live[key] if live.get(key) is not None else fallback
    power=part.get('power',[None,None]); mult=part.get('multipliers',{})
    params=dict(min_power=pick('Power',power[0]),max_power=pick('MaxPower',power[1]),
                difference=pick('RefParamDiffForMax',part.get('diff_for_max')),
                level=selected.get('level'),orb=5,
                enemy=enemy.get('combat_inputs',enemy.get('inputs',{})).get('_defenseRefParam'),
                growth_min=(part.get('growth') or [.05,.02])[0],
                growth_max=(part.get('growth') or [.05,.02])[1])
    for stat,dbkey in WEIGHTS.items():
        params[stat]=inputs.get('stats',{}).get(stat)
        params['weight_'+stat]=pick('RefParam'+stat.capitalize(),part.get('parameters',{}).get(dbkey))
    for pool in ('dp','hp'):
        rate=pick('Vs'+pool.capitalize()+'Rate',mult.get(pool))
        if isinstance(rate,(int,float)) and rate>=1: values[pool+'_bonus']=(rate-1)*100
    values['target_pool']='dp' if enemy.get('dp',0)>0 else 'hp'
    pool=values['target_pool']; elements=part.get('elements',[]); element=elements[0] if len(elements)==1 else None
    physical=part.get('type')
    modes=modes or {}
    ghost=modes.get('ghost',False) and player.get('style_label')=='STezuka03'
    skill_attack=bool(part) and part.get('skill_type')!='AttackNormal'
    burst=bool(modes.get('transcend') and modes.get('lightning_style') and element=='Thunder')
    notes.append('技能：'+str(selected.get('name') or '未读取')+'；威力/权重优先内存，属性/成长查本地资料。宝珠默认 5 级。')
    if not part:skipped.append('技能属性/类型未唯一确认：属性相关状态未自动计入')
    if part.get('skill_type') not in ('AttackSkill','AttackNormal',None):skipped.append('特殊攻击 '+part['skill_type']+' 的条件倍率待核对')
    def applicable(s):
        if s.get('effective') is False or s.get('pending_add') or s.get('pending_remove'):return False
        if s.get('duration_kind') in ('turn','count') and s.get('remaining',1)<=0:return False
        info=s.get('source_effect',{})
        cond=' && '.join(info.get(k,'') for k in ('target_condition','condition','hit_condition') if info.get(k))
        if cond and cond!='IsWeakElement()' and s.get('source') not in LOW_SP:
            skipped.append((s.get('name') or s.get('label',''))+'：条件未解析 '+cond);return False
        el=s.get('element_key')
        raw_el=s.get('element_type')
        if el:return el==element or el==physical
        if raw_el not in (None,0):
            if raw_el==3 and element=='Thunder':return True
            skipped.append((s.get('name') or s.get('label',''))+'：属性未确认或不匹配');return False
        return True
    # Finite duplicate categories compete; permanent entries remain additive.
    def aggregate(entries):
        permanent=[]; groups={}
        for s,key,value in entries:
            if (s.get('duration_kind')=='permanent' and s.get('buff_limit_type')!=4) or s.get('source')=='Passive.Condition_AttackUp11':
                permanent.append((s,key,value));continue
            group=(key,s.get('label'),s.get('element_key'),s.get('element_type') or 0)
            groups.setdefault(group,[]).append((s,key,value))
        chosen=list(permanent)
        for group in groups.values():
            only=[e for e in group if e[0].get('buff_limit_type')==4]
            regular=sorted([e for e in group if e[0].get('buff_limit_type')!=4],key=lambda e:e[2],reverse=True)[:2]
            best=max(only,key=lambda e:e[2],default=None)
            chosen.extend([best] if best and best[2]>=sum(e[2] for e in regular) else regular)
            if len(group)>1:notes.append('同类有限期状态按两层/单独发动取高（规则推断）')
        for s,key,value in chosen:
            values[key]+=value
            if key=='chain':
                count=s.get('values',{}).get('numValue',3 if s.get('source_name','').startswith('鬼神') else 0)
                if isinstance(count,int) and 0<count<=100:chain_weights.extend([value/100/count]*count)
            notes.append(f'{key} +{value:g}% ← '+(s.get('source_name') or s.get('source') or s.get('name','状态')))
    entries=[];chain_weights=[]
    active_player=[s for s in player.get('statuses',[]) if applicable(s)]
    morale=max((s.get('values',{}).get('numValue',0) for s in active_player
                if s.get('label')=='SpecialStatus.Morale'),default=0)
    params['morale_level']=morale
    notes.append(f'士气 {morale} 层：基础六维另加 {morale*5}，不修改原始属性；可在属性页核对调整')
    marks=[s for s in active_player if s.get('label')=='SpecialStatus.ThunderMark']
    mark=max(marks,key=lambda s:s.get('values',{}).get('numValue',0),default=None)
    if mark:
        rank=mark.get('values',{}).get('numValue',0)
        if rank>=1 and skill_attack:values['attack']+=30
        if rank>=4:values['critical_rate_bonus']+=30
        if rank>=5:values['critical_bonus']+=30
        notes.append(f'雷之印等级 {rank}：最多一份；技能加攻30%、等级4暴击率30%、等级5爆伤30%按门槛计入')
        if rank>=3:notes.append('雷之印破坏率增长 +10%：未模拟逐 Hit 增长，不直接加到当前破坏率')
    high=[s for s in active_player if s.get('label')=='SpecialStatus.HighBoost']
    high_enabled=modes.get('high_boost',bool(high))
    if high_enabled and skill_attack:
        values['attack']+=180
        notes.append('高阶增幅 +180%（本地 HighBoost 资料，只计一份）；不再次强化已施加 Buff/Debuff')
    servants=[s for s in active_player if s.get('label')=='SpecialStatus.BIYamawakiServant']
    if servants and skill_attack:
        amounts=[s.get('values',{}).get('rateValueInt') for s in servants]
        amount=max((v/100 for v in amounts if isinstance(v,(float,int)) and v>0),default=40)
        values['attack']+=amount
        notes.append(f'魔界骑兵 / BIYamawakiServant +{amount:g}%：最多一份，优先读取 rateValueInt，缺失时使用本地资料 40%')
    active_enemy=[s for s in enemy.get('statuses',[]) if applicable(s)]
    params['calamity']=20 if any(s.get('label')=='SpecialStatus.Misfortune' for s in active_enemy) else 0
    params['fear_of_devil']=100 if any(s.get('label')=='SpecialStatus.FearOfDevil' for s in active_enemy) else 0
    notes.append('敌方属性修正：灾厄20 / 大灾厄100 / 暴击50只取最高；暴击50仅用于伤害，不用于减益预计算')
    equipment,handled_equipment,equipment_notes=equipment_bonuses(player,db,element,skill_attack)
    for key,value in equipment:values[key]+=value
    notes.extend(equipment_notes)
    for state,enemy_side in [(player,False),(enemy,True)]:
        if not state.get('statuses_available',False):skipped.append(('敌方' if enemy_side else '角色')+'状态未完整读取')
        for s in state.get('statuses',[]):
            if not enemy_side and s.get('source') in handled_equipment:continue
            if not applicable(s):continue
            kind=s.get('label','').removeprefix('SpecialStatus.');v=s.get('values',{})
            key=None;value=None
            amount=v.get('amountOn'+pool.capitalize()+'DamageInt')
            rate=v.get('rateValueInt')
            if not enemy_side:
                if kind in ('AttackUp','AttackUpIncludeNormal','Morale'):
                    key='attack';value=amount/100 if amount is not None else None
                elif kind=='BuffCharge':
                    key='charge';value=amount/100 if amount is not None else None
                    skipped.append('充能附带暴击率的运行时尺度尚未核实；当前按勾选的暴击情景计算')
                elif kind in ('MindEye','CriticalDamageUp','CriticalRateUp'):
                    key={'MindEye':'mind_eye','CriticalDamageUp':'critical_bonus','CriticalRateUp':'critical_rate_bonus'}[kind];value=rate/100 if rate is not None else None
                elif kind=='Funnel' and rate is not None and isinstance(v.get('numValue'),int):key='chain';value=rate*v['numValue']/100
            else:
                if kind=='DefenseDown':key='defense_down';value=abs(amount)/100 if amount is not None else None
                elif kind=='Fragile':key='fragile';value=rate/100 if rate is not None else None
                elif kind=='ResistDown' and rate is not None and rate<0 and s.get('element_key')==element:
                    key='weakness_deepen';value=-rate/100
            if (not enemy_side and kind in ('AttackUp','AttackUpIncludeNormal')
                    and 'Accessory' in s.get('source','')):
                dp,hp=v.get('amountOnDpDamageInt'),v.get('amountOnHpDamageInt')
                if dp==0 and isinstance(hp,(int,float)) and hp>0:key='hp_bonus';value=hp/100
                elif hp==0 and isinstance(dp,(int,float)) and dp>0:key='dp_bonus';value=dp/100
                if key in ('hp_bonus','dp_bonus'):notes.append('饰品单承伤池增益按特攻加算（依据用户规则，需核对来源）')
            if s.get('element_key') or s.get('element_type') not in (None,0):
                key={'attack':'element_attack','defense_down':'element_defense_down',
                     'critical_bonus':'element_critical_bonus','critical_rate_bonus':'element_critical_rate_bonus'}.get(key,key)
            if key and value is not None and value>=0:entries.append((s,key,value))
            elif kind not in ('CriticalRateUp','ThunderMark','HighBoost','BIYamawakiServant','FearOfDevil','Misfortune'):skipped.append((s.get('name') or kind)+'：未映射到已确认乘区')
    predicted,prediction_notes=low_sp_predictions(player,party,selected,db,skill_attack)
    notes.extend(prediction_notes)
    # Match each real instance once: same passive on two owners may stack twice.
    materialized={}
    for s,k,v in entries:
        materialized[s.get('source')]=materialized.get(s.get('source'),0)+1
    for s in predicted:
        if materialized.get(s['source'],0):
            materialized[s['source']]-=1
            notes.append(s['source_name']+'：已有实际状态，不重复预加')
        else:entries.append((s,'attack',100))
    # A confirmed flat self funnel with a Before hit applies to this very attack.
    for buff in db.get('parts',[]) if skill_attack else []:
        if (buff.get('skill_type')!='Funnel' or buff.get('target_type')!='Self'
            or any(buff.get(k) for k in ('cond','target_condition','hit_condition'))
            or not buff.get('hits') or not all(h.get('type')=='Before' for h in buff['hits'])
            or any(buff.get('growth',[]))):continue
        count=(buff.get('power') or [0])[0];rate=(buff.get('value') or [0])[0]
        if not isinstance(count,(int,float)) or count!=int(count) or not 0<count<=100 or not isinstance(rate,(int,float)) or rate<=0:continue
        source=selected.get('label')
        if any(k=='chain' and s.get('source') in (source,buff.get('label')) for s,k,v in entries):
            notes.append('技能攻击前连击已有实际状态，不重复预加');continue
        effect=buff.get('effect',{})
        if effect.get('exitCond')!='Count' or effect.get('limitType') not in ('Default','None','Only'):continue
        s=dict(label='SpecialStatus.Funnel',source=source,source_name='预选技能攻击前连击',
               element_type=0,duration_kind='count',remaining=1,buff_limit_type=4 if effect.get('limitType')=='Only' else 0,
               values=dict(numValue=int(count)))
        entries.append((s,'chain',count*rate*100))
        notes.append(f'预选技能攻击前连击：{int(count)}×{rate:.0%}，参与同类覆盖筛选')
    def virtual(kind,key,value,source):
        entries.append((dict(label='SpecialStatus.'+kind,element_type=0,duration_kind='count',
                             buff_limit_type=4,source_name=source),key,value))
    if ghost and skill_attack:
        virtual('MindEye','mind_eye',120,'鬼神状态（截图规则）')
        virtual('Funnel','chain',75,'鬼神状态：3×25%（截图规则）')
        if modes.get('gidou') and not any(s.get('source')=='Passive.Condition_AttackUp11' for s,k,v in entries if k=='attack'):
            values['attack']+=300
            notes.append('attack +300% ← 鬼道天赋（攻击前预测；同源实际 Buff 出现后不重复加）')
    if modes.get('transcend') and modes.get('lightning_style'):
        values['attack']+=300
        notes.append('attack +300% ← 雷风格超越；既存 Buff/Debuff 不再次乘 1.2')
    if burst:
        virtual('CriticalDamageUp','critical_bonus',100,'雷属性爆发：单独发动爆伤')
        values['critical']=True
        notes.append('雷属性爆发：必定暴击；基础公式 +50 属性差、基础暴伤 +50% 各只计一次')
        notes.append('破坏率上限额外 300% 不等于当前破坏率 +300%；本次仍用读取的当前值')
    aggregate(entries)
    if burst:values['critical_rate_bonus']=max(100,values['critical_rate_bonus'])
    for s in (fields or {}).get('statuses',[]):
        if s.get('label')=='SpecialStatus.Zone' and applicable(s) and s.get('element_key')==element and element:
            rate=s.get('values',{}).get('rateValueInt')
            if isinstance(rate,int):
                bonus=rate/100-100;values['field']+=bonus;notes.append(f'场地 +{bonus:g}%（内存最终系数，不再叠场地强化）')
    base=enemy.get('base_resistances') or {}; resistance_factors=[]
    for element_key,out in [(physical,'weapon_bonus'),(element,'element_bonus')]:
        r=base.get((element_key or '').lower())
        if isinstance(r,(int,float)):
            if r<0:values[out]=-r
            elif 0<=r<=100:resistance_factors.append(1-r/100)
            else:skipped.append('抗性超过 100%，需核对吸收');values['absorbed']=True
        elif element_key:skipped.append(element_key+' 基础相性未收录')
    import math
    values['resistance']=(1-math.prod(resistance_factors))*100
    dr=enemy.get('enemy_progress',{}).get('damage_rate')
    if isinstance(dr,(int,float)) and dr>=100:values['destruction']=dr;notes.append(f'当前破坏率 {dr:g}%（不预测后续 Hit 增长）')
    else:skipped.append('破坏率未读到，暂用 100%')
    notes.append('暴击为用户可修改的情景，暴击率不直接乘伤害；未加入预选技能附带的减防。')
    skipped.append('未作为状态读取的饰品/被动不自动猜测；Token/血量特殊倍率与逐 Hit 破坏率增长未预测')
    params['critical_rate_bonus']=values.pop('critical_rate_bonus')
    params['element_critical_rate_bonus']=values.pop('element_critical_rate_bonus')
    notes.append('暴击率栏仅列已识别加成，不含未确认的基础率/充能；用于核对，不是期望伤害概率。')
    hits=part.get('hits') or db.get('hits',[])
    hit_weights=[h['power_ratio'] for h in hits if h.get('type')=='Main' and isinstance(h.get('power_ratio'),(int,float)) and h['power_ratio']>0]
    hit_note='本地技能逐 Hit 权重'
    if not hit_weights:
        count=db.get('hit_count',0)
        hit_weights=[1/count]*count if isinstance(count,int) and 0<count<=100 else []
        hit_note='仅有 Hit 数：暂按等权（可修改）' if count!=1 else '单 Hit'
    if hit_weights:
        total=sum(hit_weights);hit_weights=[w/total for w in hit_weights]+chain_weights
    if values['chain'] and not chain_weights:
        hit_weights=[];hit_note='连击逐 Hit 权重未确认，请手动填写完整权重'
    return dict(values=values,params=params,notes=notes,skipped=list(dict.fromkeys(skipped)),
                hit_weights=hit_weights,hit_note=hit_note,skill=selected.get('name','未选技能'))
