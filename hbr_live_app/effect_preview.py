"""Single-effect proposals, with conditions preserved rather than executed."""
from dataclasses import asdict
from .damage_autofill import catalog_skill, WEIGHTS
from .effect_math import EffectInputs
from .passive_audit import owned_audit
from hbr_data.skill_tree import effects

KINDS = {'AttackUp':'加攻', 'AttackUpIncludeNormal':'含普攻加攻', 'MindEye':'心眼',
         'CriticalRateUp':'暴击率', 'CriticalDamageUp':'暴伤', 'DefenseDown':'减防',
         'Fragile':'脆弱', 'Zone':'场地'}
SCOPES = {'GiveAttackBuffUp': {'AttackUp','AttackUpIncludeNormal'},
          'GiveCriticalDamageBuffUp': {'CriticalDamageUp'},
          'GiveDefenseDebuffUp': {'DefenseDown'},
          'GiveDebuffUp': {'DefenseDown','Fragile'}}


def active(s):
    return (s.get('effective') is not False and not s.get('pending_add') and not s.get('pending_remove')
            and not (s.get('duration_kind') in ('turn','count') and s.get('remaining') is not None
                     and s['remaining']<=0))


def proposals(player, enemy, modes=None, lookup=None):
    lookup=lookup or catalog_skill; modes=modes or {}
    inp=player.get('combat_inputs',player.get('inputs',{})); selected=inp.get('selected_skill',{})
    skill=lookup(selected.get('label')) if selected.get('label') else {}
    sources=[(skill,selected,False)] if skill else []
    sources += [(p,{},True) for p in owned_audit(player)]
    states=[s for s in player.get('statuses',[]) if active(s)]
    morale=max([s.get('values',{}).get('numValue',0) for s in states
                if s.get('label')=='SpecialStatus.Morale'] or [0])
    reduction=max([{'SpecialStatus.Misfortune':20,'SpecialStatus.FearOfDevil':100}.get(s.get('label'),0)
                   for s in enemy.get('statuses',[]) if active(s)] or [0])
    result=[]
    for source,live_skill,passive in sources:
        for part in effects(source,modes):
            typ=part.get('skill_type')
            if typ not in KINDS:continue
            notes=[];missing=[]
            live=next((p for p in live_skill.get('parts',[]) if p.get('Label')==part.get('label')), {})
            def pick(key,fallback):
                value=live.get(key)
                if value is not None:
                    notes.append(f'{key}：内存 {value}');return value
                return fallback
            power=part.get('power') or [None,None]
            low=pick('Power',power[0]);high=pick('MaxPower',power[1])
            threshold=pick('RefParamDiffForMax',part.get('diff_for_max'))
            weights={k:pick('RefParam'+k.capitalize(),part.get('parameters',{}).get(db)) for k,db in WEIGHTS.items()}
            fixed=threshold==0 and all(w==0 for w in weights.values())
            growth=part.get('growth')
            if not growth or len(growth)!=2:
                growth=[0,0];notes.append('成长缺失：暂填 0，请核对')
            stats=inp.get('stats',{})
            required=[k for k,w in weights.items() if w]
            attribute=None
            if fixed:attribute=0
            elif all(w is not None for w in weights.values()) and required and all(stats.get(k) is not None for k in required):
                attribute=sum((stats[k]+morale*5)*weights[k] for k in required)/sum(weights.values())
            notes.append('权重 '+str(weights)+'；原始属性 '+str(stats)+f'；士气 {morale} 层，每项 +{morale*5}')
            kind='fixed' if fixed else 'debuff' if typ in ('DefenseDown','Fragile') else 'buff'
            enemy_value=enemy.get('combat_inputs',enemy.get('inputs',{})).get('_defenseRefParam') if kind=='debuff' else 0
            values=asdict(EffectInputs(kind=kind,minimum=None if low is None else low*100,
                maximum=0 if fixed else None if high is None else high*100,threshold=threshold,
                attribute=attribute,enemy=enemy_value,level=1 if passive else live_skill.get('level'),
                growth_min=growth[0],growth_max=growth[1],reduction=reduction if kind=='debuff' else 0,
                over_rate=.001 if kind=='debuff' else .0002))
            for key,value in values.items():
                if value is None:missing.append(key)
            notes.append('宝珠默认 0：仅在确认该效果可强化后调整至 5。数据：内存同标签优先，其余来自本地资料库。')
            if kind!='fixed':
                notes.append('试算模型：按资料库上下限线性插值，超过阈值继续小斜率增长；尚未用实战验证低属性区间与宝珠增量。')
            conditions=part.get('_branch_path',[])+[source.get('condition') or source.get('cond'),part.get('cond'),part.get('target_condition'),part.get('hit_condition')]
            conditions=[c for c in conditions if c]
            notes.append('目标：'+str(part.get('target_type'))+'；元素：'+str(part.get('elements'))+'；期限/叠加：'+str(part.get('effect')))
            if passive:notes.append('已持有天赋/被动：时机 '+str(source.get('timing','未确认'))+'；只计算条件成立时的效果，不代表当前已发动；固定被动不自动吃效果量提升。')
            if conditions:notes.append('条件待人工核对：'+'；'.join(conditions))
            boosts=[];applicable_boosts=[];uncertain=False
            for s in states:
                boost=s.get('label','').removeprefix('SpecialStatus.')
                if not boost.startswith('Give'):continue
                rate=s.get('values',{}).get('rateValueInt')
                scope=typ in SCOPES.get(boost,set()) and not passive
                from .effect_passives import condition_check
                conditional=any(condition_check(s.get('source_effect',{}).get(k),player) is not True
                                for k in ('condition','target_condition','hit_condition')) or bool(s.get('element_type'))
                if scope:
                    if not conditional and isinstance(rate,(int,float)) and rate>=0:applicable_boosts.append(rate/100)
                    else:uncertain=True
                # Do not auto-stack enhancement statuses whose limit rules are unverified.
                boosts.append(f'{s.get("source_name") or boost} / {boost}：'+
                    (f'{rate/100:g}%' if isinstance(rate,(int,float)) else '数值未读到')+
                    ('；类型适用' if scope else '；不适用或范围待核对')+('；条件需核对' if conditional else ''))
            if not passive and typ in ('AttackUp','AttackUpIncludeNormal','DefenseDown','Fragile'):
                if modes.get('transcend') and modes.get('lightning_style'):
                    boosts.append('雷超越：20%（当前雷风格；与其他提升的叠加请核对）')
                    applicable_boosts.append(20)
                if modes.get('high_boost',any(s.get('label')=='SpecialStatus.HighBoost' for s in states)):
                    boosts.append('高阶增幅：20%（与其他提升的叠加请核对）')
                    applicable_boosts.append(20)
            if len(applicable_boosts)==1 and not uncertain:
                values['enhancement']=applicable_boosts[0]
                notes.append(f'效果类型适用且仅一项无条件提升，预填 {applicable_boosts[0]:g}%。')
            elif applicable_boosts or uncertain:
                notes.append('存在多项提升或未确认条件，合计暂填 0；请核对叠加后填写，当前结果不含这些提升。')
            if not passive:
                from .effect_passives import enhancements
                passive_amount,passive_notes=enhancements(player,typ,SCOPES,states)
                values['enhancement']+=passive_amount
                notes.extend(passive_notes)
            notes.append('效果量提升候选：\n'+'\n'.join(boosts or ['未读到适用候选']))
            if missing:notes.append('缺失参数，补齐后计算：'+', '.join(missing))
            names={'Thunder':'雷','Fire':'火','Ice':'冰','Light':'光','Dark':'暗'}
            element='/'.join(names.get(x,x) for x in part.get('elements') or []) or '普通'
            branch=' / '.join(part.get('_branch_path',[]))
            result.append(dict(title=f'{source.get("name") or source.get("label")} · {element}{KINDS[typ]} · {branch} · {part.get("label")}',
                               values=values,notes='\n'.join(notes),part=part))
    return result
