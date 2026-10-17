"""Read metadata-validated combat inputs without evaluating game methods."""
STATS = dict(power='力量', dexterity='灵巧', toughness='体力', spirit='精神', wisdom='智慧', luck='幸运')
PART_FIELDS = ('Label', 'Power', 'MaxPower', 'RefParamDiffForMax', 'VsDpRate', 'VsHpRate',
               'DamageRateRate', 'Value1', 'Value2', 'StrValue1', 'StrValue2',
               'Condition', 'TargetCondition', 'HitCondition', 'MaxPower2', 'RefParamDiffForMax2',
               'RefParamPower', 'RefParamDexterity', 'RefParamToughness', 'RefParamSpirit',
               'RefParamWisdom', 'RefParamLuck')


def read_inputs(reader, actor):
    from .source import members
    result = dict(stats={k: reader.prop(actor, k) for k in STATS})
    result['stats'] = {k:v for k,v in result['stats'].items() if v is not None}
    for name in ('_borderRefParam', '_defenseRefParam'):
        value = reader.get(actor, name)
        if value is not None: result[name] = value
    field = reader.fields(actor).get('tokenInternal')
    if field and field[1] == 17:
        result['token'] = reader.r.i(actor+field[0])
    if reader.r.cls(actor) != 'BattlePlayerData':
        return result
    result['reinforced_mode_turn'] = reader.get(actor, '_reinforcedModeTurn')
    passive_list = reader.prop(actor, 'passiveSkillList')
    if passive_list and reader.r.cls(passive_list) == 'List`1':
        labels=[]
        for passive in members(reader.r, passive_list):
            if reader.r.cls(passive) != 'BattlePassiveSkill': continue
            domain_passive=reader.get(passive,'domain')
            if domain_passive:
                label=reader.prop(domain_passive,'reasonMasterLabel')
                if label:labels.append(label)
        result['passive_labels']=labels
    pointer = reader.prop(actor, 'frontSkillList')
    index = reader.prop(actor, 'selectedCommandIndex')
    if not pointer or reader.r.cls(pointer) != 'List`1':
        return result
    skills = members(reader.r, pointer)
    if not isinstance(index, int) or not 0 <= index < len(skills):
        return result
    skill = skills[index]
    if reader.r.cls(skill) != 'BattleSkill':
        return result
    domain = reader.prop(skill, 'domainSkillOverwrite') or reader.prop(skill, 'domainSkill')
    if not domain: return result
    master = reader.get(domain, 'master')
    selected = dict(label=reader.get(master, 'Label'), name=reader.get(master, 'Name'),
                    level=reader.prop(skill, 'skillLevel'), parts=[])
    # Do not attach _allyAim: it may be a previous command's cached target.
    for name in ('_allSkillPartList', '_skillPartList'):
        pointer = reader.get(domain, name)
        if not pointer or reader.r.cls(pointer) != 'List`1': continue
        for part in members(reader.r, pointer):
            if reader.r.cls(part) != 'DomainSkillPart': continue
            pm = reader.get(part, 'master')
            if not pm: continue
            values = {key:reader.get(pm, key) for key in PART_FIELDS}
            if any(p.get('Label') == values['Label'] for p in selected['parts']): continue
            field = reader.fields(pm).get('SkillType')
            values['skill_type_raw'] = reader.r.i(pm+field[0]) if field and field[1] == 17 else None
            selected['parts'].append(values)
    # Reject a selection that changed during sampling rather than mixing inputs.
    if reader.prop(actor, 'selectedCommandIndex') == index:
        result['selected_skill'] = selected
    return result
