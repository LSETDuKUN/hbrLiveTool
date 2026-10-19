"""Display-only skill scenarios; preserve source trees and shared effects."""
from copy import deepcopy

WRAPPERS={'SkillCondition','SkillSwitch','SkillRandom'}


def choice_name(part,index,child):
    cond=''.join((part.get('cond') or '').split())
    if cond=='IsOverDrive()':return 'OD 中' if index==0 else '非 OD'
    if cond=='TargetBreakDownTurn()>0':return '目标倒地' if index==0 else '目标未倒地'
    if 'BreakDownTurn()' in cond:return '存在倒地敌人' if index==0 else '无倒地敌人'
    if part.get('skill_type')=='SkillCondition':return f'条件{"成立" if index==0 else "不成立"}：{cond}'
    return child.get('desc') or child.get('name') or f'形态 {index+1}'


def variants(skill,path=()):
    for position,part in enumerate(skill.get('parts',[])):
        if part.get('skill_type') not in WRAPPERS:continue
        children=[(i,c) for i,c in enumerate(part.get('strval') or []) if isinstance(c,dict) and isinstance(c.get('parts'),list)]
        if not children:continue
        result=[]
        for index,child in children:
            view=deepcopy(skill)
            view['parts']=deepcopy(skill['parts'][:position]+child['parts']+skill['parts'][position+1:])
            for key in ('hits','hit_count','sp_cost'):
                if key in child:view[key]=deepcopy(child[key])
            result.extend(variants(view,path+(choice_name(part,index,child),)))
        return result
    return [(' / '.join(path) or '默认',skill)]
