"""Short catalog descriptions; power parameters are never actual damage estimates."""
EFFECT_NAMES = {'AttackDown': '攻击降低', 'DefenseDown': '防御降低', 'DefenseUp': '防御提升',
    'AttackUp': '攻击提升', 'Charge': '蓄力', 'ConfusionRandom': '混乱', 'StunRandom': '概率眩晕',
    'SuperStun': '强眩晕', 'Misfortune': '厄运', 'ImprisonRandom': '概率封印',
    'BindRandom': '概率束缚', 'VirusRandom': '病毒', 'IllusionRandom': '幻惑',
    'SpiritDownRate': '精神降低', 'SpiritDownValue': '精神降低',
    'ToughnessDownRate': '体力降低', 'ToughnessDownValue': '体力降低',
    'PowerDownRate': '力量降低', 'WisdomDownRate': '智力降低',
    'DamageSp': 'SP 减少', 'DamageSpRandom': '概率 SP 减少', 'SpecifySpDamage': 'SP 减少',
    'ContinuousSpDamage': '持续 SP 减少', 'ContinuousDamageRate': '持续伤害',
    'ContinuousDpDamageRate': '持续 DP 伤害', 'OverDrivePointDown': 'OD 减少',
    'HealDp': '回复 DP', 'HealDpRate': '按比例回复 DP', 'HealHpRate': '按比例回复 HP',
    'Summon': '召唤', 'RemoveSpecialStatus': '移除状态', 'RemoveDebuff': '解除减益',
    'HealDown': '回复量降低', 'Fatigue': '疲劳', 'Restraint': '拘束',
    'RestraintRandom': '概率拘束', 'CorrosionDp': 'DP 腐蚀', 'CorrosionDpRandom': '概率 DP 腐蚀'}


def preview_effects(skill):
    notes = []
    if skill.get('hit_count', 0) > 0:
        notes.append(f'{skill["hit_count"]} Hit')
    target = {'Single': '单体', 'All': '全体', 'Self': '自身'}.get(skill.get('target_type'))
    if target:
        notes.append(target)
    for part in skill.get('parts') or []:
        kind = part.get('skill_type')
        if kind == 'AttackSkill':
            power = part.get('power')
            if isinstance(power, list) and len(power) == 2 and all(isinstance(v, (int, float)) for v in power):
                notes.append(f'资料威力 {power[0]:g}–{power[1]:g}（非实伤）')
            for element in part.get('elements') or []:
                notes.append({'Fire':'火', 'Ice':'冰', 'Thunder':'雷', 'Light':'光', 'Dark':'暗'}.get(element, element))
        elif kind and kind != 'Nothing':
            note = EFFECT_NAMES.get(kind, f'效果：{kind}')
            if part.get('cond'):
                note += '（有条件）'
            notes.append(note)
    return ' · '.join(dict.fromkeys(notes)) or skill.get('desc') or '效果未收录'
