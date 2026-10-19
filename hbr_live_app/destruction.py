"""Per-hit destruction and explicit shield overflow accounting."""
import math


def per_hit(weights, main_hits, skill_dr, enemy_coefficient, bonus, initial, maximum,
            target_pool='hp'):
    weights=tuple(float(w) for w in weights)
    numbers=(skill_dr,enemy_coefficient,bonus,initial,maximum,*weights)
    if any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 for v in numbers):
        raise ValueError('破坏率参数必须是有限非负数')
    if not isinstance(main_hits,int) or not 1<=main_hits<=len(weights)<=256:
        raise ValueError('请确认本体段数与完整 Hit 权重')
    if any(w<=0 for w in weights) or not math.isclose(sum(weights[:main_hits]),1,abs_tol=1e-6):
        raise ValueError('本体 Hit 权重之和必须为 1，连击权重另接在后')
    if target_pool not in ('hp','dp') or initial<100 or maximum<100:
        raise ValueError('请核对承伤池、初始破坏率和上限（均不得低于 100%）')
    current=initial;rows=[];final_weights=[]
    for index,weight in enumerate(weights):
        main=index<main_hits
        increment=skill_dr*(1/main_hits if main else weight)*enemy_coefficient*(1+bonus/100)
        if target_pool=='dp':increment=0
        before=current
        current+=min(increment,max(0,maximum-current))
        final_weight=weight*(before/100 if target_pool=='hp' else 1)
        final_weights.append(final_weight)
        rows.append(dict(hit=index+1,kind='本体' if main else '连击',weight=weight,
                         before=before,after=current,increment=current-before,
                         theoretical_increment=increment,clipped=increment-(current-before),damage_weight=final_weight))
    if not math.isfinite(sum(final_weights)):
        raise ValueError('逐段伤害溢出')
    theoretical=sum(row['theoretical_increment'] for row in rows)
    return dict(rows=rows,weights=final_weights,final=current,theoretical_increment=theoretical,
                theoretical_final=initial+theoretical,actual_increment=current-initial,
                clipped=theoretical-(current-initial),
                average=sum(final_weights)/sum(weights),weighted=sum(final_weights))


def apply_to_result(result, inputs, weights, main_hits, skill_dr, enemy_coefficient, bonus, maximum):
    """Replace fixed DR once; preserve the independent chain multiplier."""
    if not math.isclose(sum(weights[main_hits:]),inputs.chain/100,abs_tol=1e-6):
        raise ValueError('连击合计与逐 Hit 权重不一致，请同步修改')
    detail=per_hit(weights,main_hits,skill_dr,enemy_coefficient,bonus,
                   inputs.destruction,maximum,inputs.target_pool)
    old=result['factors']['destruction']
    if old<=0:raise ValueError('初始破坏率必须大于零')
    ratio=detail['average']/old
    result={**result,'factors':{**result['factors'],'destruction':detail['average']}}
    for key in ('multiplier','damage','minimum','maximum'):
        if result[key] is not None:
            result[key]*=ratio
            if not math.isfinite(result[key]):raise ValueError('递推伤害数值过大')
    result['note']='已按各段命中前破坏率递推；不模拟跨 DP 破盾、后续施加效果与伤害衰减'
    return result,detail


def dp_factor(current, maximum, at_zero, at_full):
    """Skill value[0/1] are DP=0/full endpoints, not a separate universal buff."""
    if any(not math.isfinite(v) or v<0 for v in (current,maximum,at_zero,at_full)) or maximum<=0:
        raise ValueError('自身 DP、DP 上限及技能端点必须有效，DP 上限须大于零')
    return at_zero+(at_full-at_zero)*min(1,current/maximum)


def simulate_pools(inputs, weights, main_hits, skill_dr, enemy_coefficient, bonus, maximum,
                   enemy_dp, enemy_hp=None, hp_adjustments=None):
    """Resolve damage first; a hit that removes the shield then grants DR."""
    from dataclasses import replace
    from .damage_math import calculate
    if not math.isfinite(enemy_dp) or enemy_dp<0 or (enemy_hp is not None and (not math.isfinite(enemy_hp) or enemy_hp<0)):
        raise ValueError('敌人剩余 DP / HP 必须为有限非负数')
    if not math.isclose(sum(weights[main_hits:]),inputs.chain/100,abs_tol=1e-6):
        raise ValueError('连击合计与逐 Hit 权重不一致，请同步修改')
    template=per_hit(weights,main_hits,skill_dr,enemy_coefficient,bonus,inputs.destruction,maximum)
    bases={}
    for pool in ('dp','hp'):
        changes={key:getattr(inputs,key)+delta for key,delta in (hp_adjustments or {}).items()} if pool=='hp' else {}
        bases[pool]=calculate(replace(inputs,target_pool=pool,destruction=100,chain=0,**changes))['damage']
    if any(v is None for v in bases.values()):raise ValueError('跨池计算需要基础伤害，且不适用于吸收情景')
    dp=enemy_dp;hp=enemy_hp;rate=inputs.destruction;rows=[];theoretical=0;total_dp=total_hp=overflow=0
    for item in template['rows']:
        alive=hp is None or hp>0
        pool='dp' if dp>0 else 'hp'
        before=rate
        raw=bases[pool]*item['weight']*(rate/100 if pool=='hp' else 1) if alive else 0
        if not math.isfinite(raw):raise ValueError('逐段伤害溢出')
        if pool=='dp':
            applied=min(dp,raw);dp-=applied;total_dp+=applied;lost=raw-applied;overflow+=lost
        else:
            applied=raw if hp is None else min(hp,raw)
            if hp is not None:hp-=applied
            total_hp+=applied;lost=0
        increment=item['theoretical_increment'] if dp<=0 and alive else 0
        rate+=min(increment,max(0,maximum-rate));theoretical+=increment
        rows.append(dict(item,pool=pool,before=before,after=rate,increment=rate-before,
                         theoretical_increment=increment,clipped=increment-(rate-before),
                         raw_damage=raw,applied_damage=applied,overflow=lost,remaining_dp=dp,remaining_hp=hp))
    return dict(rows=rows,final=rate,initial=inputs.destruction,theoretical_increment=theoretical,
                theoretical_final=inputs.destruction+theoretical,actual_increment=rate-inputs.destruction,
                clipped=theoretical-(rate-inputs.destruction),dp_damage=total_dp,hp_damage=total_hp,
                damage=total_dp+total_hp,overflow=overflow,remaining_dp=dp,remaining_hp=hp,segmented=True)
