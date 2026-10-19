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
        catalog=Catalog()
        _,rows,_=catalog.query("SELECT raw_json FROM skill_catalog WHERE region='cn' AND label=?",(label,),limit=50)
        if not rows:
            _,rows,_=catalog.query("SELECT raw_json FROM skills WHERE region='cn' AND label=?",(label,),limit=50)
        # Prefer the parent record over nested projections with the same label.
        top=[row for row in rows if not json.loads(row[0]).get('is_strval')]
        rows=top or rows
        candidates={}
        for row in rows:
            s=json.loads(row[0]); candidates[json.dumps({k:s.get(k) for k in ('parts','hits','hit_count','sp_cost','max_level')},sort_keys=True)]=s
        return next(iter(candidates.values())) if len(candidates)==1 else {}
    except (OSError,ValueError,RuntimeError,sqlite3.Error):return {}


@lru_cache(maxsize=128)
def style_elements(label):
    try:
        from hbr_data.store import Catalog
        _,rows,_=Catalog().query("SELECT raw_json FROM styles WHERE region='cn' AND label=?",(label,),limit=2)
        return json.loads(rows[0][0]).get('elements',[]) if len(rows)==1 else []
    except (OSError,ValueError,RuntimeError,sqlite3.Error):return []


def autofill(player, enemy, fields=None, lookup=catalog_skill, modes=None, party=None, _compare_pools=True):
    from .passive_audit import low_sp_predictions, accessory_effects, LOW_SP
    values=vars(DamageInputs()).copy(); notes=[]; skipped=[]
    values['destruction_bonus']=0
    values['critical_rate_bonus']=0
    values['element_critical_rate_bonus']=0
    inputs=player.get('combat_inputs',player.get('inputs',{}))
    from hbr_data.battle_conditions import context_for,evaluate,conditional_attack
    from .conditional_passives import predictions
    from .status_rules import independent,active
    modes=context_for(player,enemy,modes)
    added,passive_notes=predictions(player,modes)
    player=dict(player,statuses=list(player.get('statuses',[]))+added)
    notes.extend(passive_notes)
    selected=inputs.get('selected_skill',{}); db=lookup(selected.get('label','')) if selected.get('label') else {}
    from hbr_data.skill_tree import resolve
    branching=any(any(isinstance(child,dict) and 'parts' in child for child in p.get('strval',[])) for p in db.get('parts',[]))
    db=resolve(db,modes)
    live_hits=selected.get('hit_count') if not branching else None
    if branching:
        paths=list(dict.fromkeys(' / '.join(p.get('_branch_path',[])) for p in db.get('parts',[]) if p.get('_branch_path')))
        if paths:notes.append('条件技能已选分支：'+'；'.join(paths)+'；段数采用该分支资料')
        else:skipped.append('技能条件/切换分支尚未确定：未猜测攻击分支，请核对')
    if isinstance(live_hits,int) and 0<live_hits<=256:
        if db.get('hit_count') not in (None,live_hits):
            skipped.append(f'游戏段数 {live_hits} 与资料库 {db["hit_count"]} 不同：采用游戏段数，分布需核对')
        db['hit_count']=live_hits
        notes.append(f'本体段数 {live_hits}：游戏读取')
    else:notes.append('本体段数：本地资料库（游戏字段未读到）；逐段伤害分布：本地资料库，可手动修改')
    attacks=[p for p in db.get('parts',[]) if p.get('skill_type') in
             ('AttackSkill','AttackNormal','TokenAttack','PenetrationCriticalAttack','AttackByOwnDpRate','DamageRateChangeAttackSkill')]
    raw=[p for p in selected.get('parts',[]) if p.get('skill_type_raw')==10]
    part=attacks[0] if len(attacks)==1 else {}
    live=next((p for p in selected.get('parts',[]) if p.get('Label')==part.get('label')),None)
    if live is None and len(raw)==1 and not branching:live=raw[0]
    live=live or {}
    def pick(key, fallback):
        if live.get(key) is not None:
            notes.append(f'{key}：游戏 {live[key]}' + (f'（资料库 {fallback}，存在差异）' if fallback is not None and live[key]!=fallback else ''))
        else:notes.append(f'{key}：资料库补充 {fallback}' if fallback is not None else f'{key}：未读到')
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
    changed=conditional_attack(part)
    changed_active=changed and evaluate(changed['condition'],modes) is True
    if changed_active:
        factor=pick('Value2',changed['power_factor'])
        for key in ('min_power','max_power'):
            if params[key] is not None:params[key]*=factor
        notes.append(f'技能条件 {changed["condition"]} 成立：基础威力 ×{factor:g}，不是额外倒地乘区')
    elif changed:
        skipped.append('条件威力/破坏倍率未启用：'+str(changed['condition'])+'（不满足或状态未知）')
    for pool in ('dp','hp'):
        rate=pick('Vs'+pool.capitalize()+'Rate',mult.get(pool))
        if isinstance(rate,(int,float)) and rate>=1: values[pool+'_bonus']=(rate-1)*100
    dp_scaling=part.get('skill_type')=='AttackByOwnDpRate'
    if dp_scaling:
        endpoints=part.get('value') or [None,None]
        params.update(own_dp=player.get('dp'),own_dp_max=player.get('dp_max'),
                      dp_zero_factor=pick('Value1',endpoints[0]),dp_full_factor=pick('Value2',endpoints[1]))
        if all(params[k] is not None for k in ('own_dp','own_dp_max','dp_zero_factor','dp_full_factor')):
            from .destruction import dp_factor
            try:
                values['health_factor']=dp_factor(*(params[k] for k in ('own_dp','own_dp_max','dp_zero_factor','dp_full_factor')))
                notes.append(f'自身 DP 线性技能倍率 ×{values["health_factor"]:g}：0 DP / 满 DP 端点，超过满 DP 按满值')
            except ValueError as exc:skipped.append(str(exc))
        else:skipped.append('自身 DP 线性技能参数缺失，请补充后计算；不猜测当前 DP 比例')
    params['enemy_dp']=enemy.get('dp')
    params['enemy_hp']=enemy.get('hp')
    values['target_pool']='dp' if enemy.get('dp',0)>0 else 'hp'
    pool=values['target_pool']; elements=part.get('elements',[]); element=elements[0] if len(elements)==1 else None
    physical=part.get('type')
    modes=modes or {}
    if modes.get('od_active') is True and modes.get('od_level') in (1,2,3):
        values['od']=1+modes['od_level']*.1
        notes.append(f'当前 OD Lv.{modes["od_level"]}：伤害倍率 {values["od"]:g}')
    elif modes.get('od_active') is not False:skipped.append('OD 状态或发动等级未确认：暂用倍率 1，可手动修改')
    ghost=modes.get('ghost',False) and player.get('style_label')=='STezuka03'
    skill_attack=bool(part) and part.get('skill_type')!='AttackNormal'
    burst=bool(modes.get('transcend') and modes.get('lightning_style') and element=='Thunder')
    notes.append('技能：'+str(selected.get('name') or '未读取')+'；威力/权重优先内存，属性/成长查本地资料。宝珠默认 5 级。')
    if not part:skipped.append('技能属性/类型未唯一确认：属性相关状态未自动计入')
    if part.get('skill_type') not in ('AttackSkill','AttackNormal',None) and not changed_active:skipped.append('特殊攻击 '+part['skill_type']+' 的条件倍率待核对')
    def applicable(s):
        if not active(s):return False
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
            if independent(s) or (s.get('duration_kind')=='permanent' and s.get('buff_limit_type')!=4):
                permanent.append((s,key,value));continue
            # Numeric and named element encodings describe the same stacking pool.
            element_id=s.get('element_key') or {1:'Fire',2:'Ice',3:'Thunder',4:'Light',5:'Dark'}.get(s.get('element_type'))
            group=(key,s.get('label'),element_id)
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
        if rank>=3:
            values['destruction_bonus']+=10
            notes.append('雷之印破坏率增长 +10%（不加到当前破坏率）')
    high=[s for s in active_player if s.get('label')=='SpecialStatus.HighBoost']
    high_enabled=modes.get('high_boost',bool(high))
    if high_enabled and skill_attack:
        values['attack']+=180
        notes.append('高阶增幅 +180%（本地 HighBoost 资料，只计一份）；不再次强化已施加 Buff/Debuff')
    servants=[s for s in active_player if s.get('label')=='SpecialStatus.BIYamawakiServant']
    if servants and skill_attack:
        amounts=[s.get('values',{}).get('rateValueInt') for s in servants]
        amount=max((v/100 for v in amounts if isinstance(v,(float,int)) and v>0),default=40)
        values['servant_mind_eye']+=amount
        notes.append(f'仆人心眼 / BIYamawakiServant +{amount:g}%：仅弱点生效，可与普通心眼相加；最多一份，缺失时使用本地资料 40%')
    active_enemy=[s for s in enemy.get('statuses',[]) if applicable(s)]
    params['calamity']=20 if any(s.get('label')=='SpecialStatus.Misfortune' for s in active_enemy) else 0
    params['fear_of_devil']=100 if any(s.get('label')=='SpecialStatus.FearOfDevil' for s in active_enemy) else 0
    notes.append('敌方属性修正：灾厄20 / 大灾厄100 / 暴击50只取最高；暴击50仅用于伤害，不用于减益预计算')
    equipment_details=[]
    equipment,handled_equipment,equipment_notes=accessory_effects(player,db,element,skill_attack,details=equipment_details)
    params['od_gain_bonus']=0
    for key,value in equipment:
        if key=='od_gain_bonus':params[key]+=value
        else:values[key]+=value
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
                elif kind=='DamageRateUp':
                    key='destruction_bonus';value=rate/100 if rate is not None else None
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
        if (buff.get('skill_type')!='DamageRateUp' or buff.get('target_type') not in ('Self','AllyFront')
                or any(buff.get(k) for k in ('cond','target_condition','hit_condition'))
                or not buff.get('hits') or not all(h.get('type')=='Before' for h in buff['hits'])
                or any(buff.get('growth',[]))):continue
        if buff.get('target_type')=='AllyFront' and player.get('actor_position',player.get('position')) not in (0,1,2):continue
        effect=buff.get('effect',{})
        if effect.get('exitCond')!='Count' or effect.get('limitType') not in ('Default','None','Only'):continue
        rate=(buff.get('power') or [None])[0]
        if not isinstance(rate,(int,float)) or rate<0:continue
        if any(k=='destruction_bonus' and s.get('source') in (selected.get('label'),buff.get('label')) for s,k,v in entries):continue
        entries.append((dict(label='SpecialStatus.DamageRateUp',source=selected.get('label'),
                             source_name='预选技能命中前破坏率提升',element_type=0,duration_kind='count',
                             buff_limit_type=4 if effect.get('limitType')=='Only' else 0),
                        'destruction_bonus',rate*100))
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
        values['destruction_bonus']+=10
        notes.append('雷风格超越：破坏率增长 +10%')
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
    if isinstance(dr,(int,float)) and dr>=100:values['destruction']=dr;notes.append(f'当前破坏率 {dr:g}%：作为递推起点')
    else:skipped.append('破坏率未读到，暂用 100%')
    notes.append('暴击为用户可修改的情景，暴击率不直接乘伤害；未加入预选技能附带的减防。')
    skipped.append('未作为状态读取的饰品/被动不自动猜测；Token/血量特殊倍率未预测')
    params['destruction_bonus']=values.pop('destruction_bonus')
    params['skill_dr']=pick('DamageRateRate',mult.get('dr'))
    if changed_active:
        params['skill_dr']=pick('Value1',changed['destruction'])
        notes.append(f'条件成立时破坏倍率替换为 {params["skill_dr"]:g}')
    progress=enemy.get('enemy_progress',{})
    params['enemy_dr']=progress.get('destruction_coefficient')
    params['max_dr']=progress.get('destruction_max')
    super_element=modes.get('super_break_element') or ('Thunder' if modes.get('transcend') else None)
    if element and element==super_element and isinstance(params['max_dr'],(int,float)):
        params['max_dr']+=300
        notes.append('爆发情景：破坏率上限预加 300 个百分点；其他上限效果请核对')
    notes.append('max_dr 为本技能可增长到的上限；已有破坏率高于它时保持原值、不再增长')
    if any(s.get('label') in ('SpecialStatus.DamageRateResistUp','SpecialStatus.DamageRateResistDown') for s in active_enemy):
        params['enemy_dr']=None
        skipped.append('敌方存在破坏抗性状态：换算未验证，请手填最终有效破坏系数后启用递推')
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
    params['main_hits']=len(hit_weights) or None
    exact_hits=(bool(hit_weights) and hit_note=='本地技能逐 Hit 权重'
                and db.get('hit_count',len(hit_weights))==len(hit_weights))
    if hit_weights and not exact_hits:
        skipped.append('本体逐 Hit 分配缺失或与段数不符：不自动启用破坏率递推')
    if hit_weights:
        total=sum(hit_weights);hit_weights=[w/total for w in hit_weights]+chain_weights
    if values['chain'] and not chain_weights:
        hit_weights=[];hit_note='连击逐 Hit 权重未确认，请手动填写完整权重'
    result=dict(dp_scaling=dp_scaling,pool_simulation=bool(enemy.get('dp',0)>0 and not progress.get('dp_extra')),
                destruction_ready=exact_hits and bool(hit_weights) and all(params.get(k) is not None for k in ('skill_dr','enemy_dr','max_dr')),
                equipment_notes=equipment_notes,equipment_details=equipment_details,
                equipment_owned=list(set(inputs.get('passive_labels',[])) | {p['label'] for p in inputs.get('passive_audit',[])}
                                     | {s.get('source') for s in player.get('statuses',[]) if s.get('source')}),
                values=values,params=params,notes=notes,skipped=list(dict.fromkeys(skipped)),
                hit_weights=hit_weights,hit_note=hit_note,skill=selected.get('name','未选技能'))
    result['hp_adjustments']={}
    if _compare_pools and enemy.get('dp',0)>0:
        hp=autofill(player,dict(enemy,dp=0),fields,lookup,modes,party,_compare_pools=False)['values']
        for key in ('attack','element_attack','charge','defense_down','element_defense_down'):
            delta=hp[key]-values[key]
            if delta:
                result['hp_adjustments'][key]=delta
                notes.append(f'跨池 HP 阶段：{key} 相对 DP 阶段调整 {delta:+g} 个百分点（当前状态）')
    return result
