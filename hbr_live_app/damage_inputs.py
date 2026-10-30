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
    field = reader.fields(actor).get('spInternal')
    if field and field[1] == 17:
        result['current_sp'] = reader.r.i(actor+field[0])
    # Keep these observations separate: they can be stale outside resolution.
    result['expected_sp'] = reader.prop(actor, 'expectedSp')
    result['sp_to_consume'] = reader.prop(actor, 'spToConsume')
    passive_list = reader.prop(actor, 'passiveSkillList')
    if passive_list and reader.r.cls(passive_list) == 'List`1':
        from .passive_audit import audit_entry
        labels=[];audit=[]
        for passive in members(reader.r, passive_list):
            if reader.r.cls(passive) != 'BattlePassiveSkill': continue
            domain_passive=reader.get(passive,'domain')
            if domain_passive:
                label=reader.prop(domain_passive,'reasonMasterLabel')
                if label:
                    labels.append(label)
                    master_passive=reader.get(domain_passive,'master')
                    runtime={}
                    if master_passive and reader.r.cls(master_passive)=='MasterPassiveSkill':
                        for key,field in [('name','Name'),('condition','Condition'),('description','Description'),('master_label','Label')]:
                            value=reader.get(master_passive,field)
                            if value is not None:runtime[key]=value
                    for key,field in [('used_count','usedCount'),('limit_count','limitCount')]:
                        value=reader.prop(passive,field)
                        if value is not None:runtime[key]=value
                    audit.append(audit_entry(label,runtime))
        result['passive_labels']=labels
        result['passive_audit']=audit
    result.update(read_selection(reader,actor))
    return result


def read_selection(reader, actor):
    """Read the live command separately from cached stats and equipment."""
    from .source import members
    result={}
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
    original = reader.prop(skill, 'domainSkill')
    domain = reader.prop(skill, 'domainSkillOverwrite') or original
    if not domain: return result
    master = reader.get(domain, 'master')
    selected = dict(label=reader.get(master, 'Label'), name=reader.get(master, 'Name'),
                    level=reader.prop(skill, 'skillLevel'),base_sp_cost=reader.get(master,'Sp'), parts=[])
    # Overwrite masters may intentionally omit their display name. Keep their
    # effective parts/label, using only the selected base skill's name as fallback.
    if not selected['name'] and original and original!=domain:
        base_master=reader.get(original,'master')
        if base_master:
            selected['base_label']=reader.get(base_master,'Label')
            selected['name']=reader.get(base_master,'Name')
            if selected['name']:selected['name_source']='selected_base_skill'
    hit_count=reader.get(master,'HitCount')
    if isinstance(hit_count,int) and 0<hit_count<=256:selected['hit_count']=hit_count
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
