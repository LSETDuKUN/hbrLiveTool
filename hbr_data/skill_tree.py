"""Preserve skill identity; traverse conditional children without name matching."""
from copy import deepcopy
from .battle_conditions import evaluate as condition_value


def effects(skill, context=None, include_unknown=True, path=()):
    context=context or {}
    for part in skill.get('parts',[]):
        children=part.get('strval') or []
        nested=any(isinstance(child,dict) and isinstance(child.get('parts'),list) for child in children)
        if not nested:
            item=deepcopy(part)
            if path:item['_branch_path']=list(path)
            yield item
            continue
        conditional=part.get('skill_type')=='SkillCondition'
        value=condition_value(part.get('cond'),context) if conditional and part.get('cond') else None
        for index,child in enumerate(children):
            if not isinstance(child,dict) or not isinstance(child.get('parts'),list):continue
            if value is not None and index!=(0 if value else 1):continue
            if value is None and not include_unknown:continue
            condition=part.get('cond') or part.get('skill_type','未知分支')
            choice=('是' if index==0 else '否') if conditional and index<2 else str(index+1)
            title=f'{condition} = {choice} [{child.get("label","")}]'
            yield from effects(child,context,include_unknown,path+(title,))


def resolve(skill, context=None):
    result=deepcopy(skill)
    result['parts']=list(effects(skill,context,include_unknown=False))
    # Damage hit distribution belongs to the chosen child, not its wrapper.
    for part in skill.get('parts',[]):
        if part.get('skill_type')!='SkillCondition' or not part.get('cond'):continue
        value=condition_value(part.get('cond'),context or {})
        if value is None:continue
        children=part.get('strval') or [];index=0 if value else 1
        if index<len(children) and isinstance(children[index],dict):
            child=resolve(children[index],context)
            for key in ('hits','hit_count'):
                if key in child:result[key]=child[key]
    return result


def roots(value, pointer=''):
    """Only top-level skill entities; children remain inside their parent card."""
    if isinstance(value,dict):
        if 'hit_count' in value and isinstance(value.get('parts'),list):
            yield pointer,value;return
        for key,child in value.items():yield from roots(child,pointer+'/'+str(key))
    elif isinstance(value,list):
        for index,child in enumerate(value):yield from roots(child,pointer+'/'+str(index))
