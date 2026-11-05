"""Search and presentation helpers for team-owned snapshots."""
from .passive_audit import EQUIPMENT, DR_EQUIPMENT, OD_EQUIPMENT


def member_matches(member, query):
    text = ' '.join(str(member.get(k) or '') for k in ('actor', 'style_name', 'style_label'))
    return ''.join(query.casefold().split()) in ''.join(text.casefold().split())


def effect_group(effect):
    label = effect.get('label', '')
    if label in EQUIPMENT | DR_EQUIPMENT | OD_EQUIPMENT:
        return '饰品效果'
    if any(word in label for word in ('Earring', 'Necklace', 'Ring', 'Accessory', 'Bracelet', 'Bangle')):
        return '饰品效果'
    if label.startswith('Passive.SupportSkill_'):
        return '共鸣被动'
    return '天赋与其他被动'


def equipment_slot(effect):
    label = effect.get('label', '')
    for word, name in (('Bracelet', '手环'), ('Bangle', '手环'), ('Earring', '耳坠'), ('Ring', '戒指'), ('Necklace', '项链')):
        if word in label: return name
    return '部位未确认'
