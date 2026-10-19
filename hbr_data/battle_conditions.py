"""Small explicit condition vocabulary. Unknown expressions are never evaluated."""
import re


def context_for(player=None, enemy=None, modes=None):
    context=dict(modes or {});player=player or {};enemy=enemy or {}
    context['target_down']=enemy.get('enemy_progress',{}).get('down')
    context['position']=player.get('actor_position')
    context['dp']=player.get('dp');context['dp_max']=player.get('dp_max')
    enemies=context.get('enemies')
    if enemies is not None:
        alive=[e for e in enemies if e.get('hp',1)>0]
        downs=[e.get('enemy_progress',{}).get('down') for e in alive]
        context['any_down']=True if any(isinstance(d,(int,float)) and d>0 for d in downs) else False if all(d is not None for d in downs) else None
    elif isinstance(context['target_down'],(int,float)) and context['target_down']>0 and enemy.get('hp',1)>0:
        context['any_down']=True
    return context


def evaluate(text,context):
    text=''.join((text or '').split())
    if not text:return True
    if text=='IsOverDrive()':return context.get('od_active')
    if text=='IsCharging()':return context.get('charging')
    if text=='TargetBreakDownTurn()>0':
        down=context.get('target_down');return down>0 if isinstance(down,(int,float)) else None
    if text=='IsFront()':
        pos=context.get('position');return pos in (0,1,2) if pos is not None else None
    any_down='CountBC(IsDead()==0&&IsPlayer()==0&&BreakDownTurn()>0)>0'
    if text==any_down:return context.get('any_down')
    if text==any_down+'&&IsFront()':
        a,b=context.get('any_down'),evaluate('IsFront()',context)
        return False if a is False or b is False else True if a is True and b is True else None
    match=re.fullmatch(r'DpRate\(\)>=([0-9.]+)',text)
    if match:
        dp,maximum=context.get('dp'),context.get('dp_max')
        if isinstance(dp,(int,float)) and isinstance(maximum,(int,float)) and maximum>0:return dp/maximum>=float(match[1])
    return None


def conditional_attack(part):
    """DamageRateChangeAttackSkill: value[0] replaces DR, value[1] scales power."""
    if part.get('skill_type')!='DamageRateChangeAttackSkill':return None
    values=part.get('value') or []
    if len(values)<2 or not all(isinstance(v,(int,float)) and v>0 for v in values[:2]):return None
    return dict(power_factor=values[1],destruction=values[0],condition=part.get('cond'))
